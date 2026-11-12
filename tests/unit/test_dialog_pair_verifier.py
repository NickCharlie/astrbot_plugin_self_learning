import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from self_learning_EterU.services.analysis.expression_pattern_learner import (
    ExpressionPatternLearner,
)
from self_learning_EterU.services.learning.dialog_pair_verifier import (
    MAX_VERIFY_PAIRS,
    DialogPairVerifier,
)
from self_learning_EterU.services.learning.expression_learning import (
    ExpressionLearningModule,
)
from self_learning_EterU.models.orm.expression import ExpressionPattern
from self_learning_EterU.models.orm.learning import StyleLearningReview


class _FakeAdapter:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    async def filter_chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


def _config(enabled=True):
    return SimpleNamespace(enable_expression_pair_llm_verify=enabled)


def _pair(index):
    return {"situation": f"A{index}", "expression": f"B{index}"}


def _message(sender, text, timestamp):
    return {"sender_id": sender, "message": text, "group_id": "group-a", "timestamp": timestamp}


@pytest.mark.asyncio
async def test_verifier_disabled_returns_candidates_without_calling_model():
    adapter = _FakeAdapter('{"valid_ids": [1]}')
    verifier = DialogPairVerifier(_config(enabled=False), adapter)
    pairs = [_pair(1), _pair(2)]

    assert await verifier.verify(pairs) == pairs
    assert adapter.calls == []


@pytest.mark.asyncio
async def test_verifier_without_adapter_keeps_candidates():
    verifier = DialogPairVerifier(_config(enabled=True), None)
    pairs = [_pair(1), _pair(2)]

    assert await verifier.verify(pairs) == pairs


@pytest.mark.asyncio
async def test_verifier_keeps_only_confirmed_pairs_in_one_batch():
    adapter = _FakeAdapter('{"valid_ids": [1, 3]}')
    verifier = DialogPairVerifier(_config(), adapter)
    pairs = [_pair(1), _pair(2), _pair(3)]

    assert await verifier.verify(pairs) == [pairs[0], pairs[2]]
    assert len(adapter.calls) == 1
    prompt = adapter.calls[0]["prompt"]
    assert '"id": 1' in prompt and '"id": 3' in prompt
    assert adapter.calls[0]["temperature"] == 0.1


@pytest.mark.asyncio
async def test_verifier_caps_each_round_to_one_model_batch():
    adapter = _FakeAdapter(json.dumps({"valid_ids": list(range(1, 11))}))
    verifier = DialogPairVerifier(_config(), adapter)
    pairs = [_pair(index) for index in range(1, 13)]

    verified = await verifier.verify(pairs)

    assert len(verified) == MAX_VERIFY_PAIRS
    prompt = adapter.calls[0]["prompt"]
    assert f'"id": {MAX_VERIFY_PAIRS}' in prompt
    assert f'"id": {MAX_VERIFY_PAIRS + 1}' not in prompt


@pytest.mark.asyncio
async def test_verifier_accepts_string_ids():
    adapter = _FakeAdapter('{"valid_ids": ["2"]}')
    verifier = DialogPairVerifier(_config(), adapter)
    pairs = [_pair(1), _pair(2)]

    assert await verifier.verify(pairs) == [pairs[1]]


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [None, "not json", '{"valid_ids": "1"}'])
async def test_verifier_fails_open_on_missing_or_unparseable_response(response):
    adapter = _FakeAdapter(response)
    verifier = DialogPairVerifier(_config(), adapter)
    pairs = [_pair(1), _pair(2)]

    assert await verifier.verify(pairs) == pairs


@pytest.mark.asyncio
async def test_verifier_fails_open_on_model_error():
    adapter = _FakeAdapter(error=RuntimeError("provider down"))
    verifier = DialogPairVerifier(_config(), adapter)
    pairs = [_pair(1), _pair(2)]

    assert await verifier.verify(pairs) == pairs


@pytest.mark.asyncio
async def test_expression_module_persists_only_verified_pairs():
    added = []
    session = SimpleNamespace(
        add=added.append,
        add_all=added.extend,
        commit=AsyncMock(),
        refresh=AsyncMock(side_effect=lambda review: setattr(review, "id", 1)),
    )

    @asynccontextmanager
    async def get_session():
        yield session

    db = SimpleNamespace(get_session=get_session)
    adapter = _FakeAdapter('{"valid_ids": [1]}')
    module = ExpressionLearningModule(
        db, _config(), llm_adapter=adapter
    )
    timeline = [
        _message("alice", "Question one", 100),
        _message("bob", "Answer one", 110),
        _message("alice", "Question two", 120),
        _message("bob", "Answer two", 130),
    ]

    await module.save_style_learning_record("group-a", {}, timeline)

    patterns = [item for item in added if isinstance(item, ExpressionPattern)]
    review = next(item for item in added if isinstance(item, StyleLearningReview))
    assert [(item.situation, item.expression) for item in patterns] == [
        ("Question one", "Answer one")
    ]
    assert len(json.loads(review.learned_patterns)) == 1
    assert "Answer two" not in review.few_shots_content
    assert len(adapter.calls) == 1


@pytest.mark.asyncio
async def test_expression_learner_verifies_before_building_patterns():
    adapter = _FakeAdapter('{"valid_ids": [3]}')
    learner = object.__new__(ExpressionPatternLearner)
    learner.config = SimpleNamespace(target_blacklist=[], target_qq_list=[])
    learner.pair_verifier = DialogPairVerifier(_config(), adapter)
    timeline = [
        _message("alice", "Question one", 100),
        _message("bob", "Answer one", 110),
        _message("alice", "Question two", 120),
        _message("bob", "Answer two", 130),
    ]

    patterns = await learner.learn_expression_patterns(
        timeline, "group-a", persona_id="persona-a"
    )

    assert [(pattern.situation, pattern.expression) for pattern in patterns] == [
        ("Question two", "Answer two")
    ]
    assert patterns[0].persona_id == "persona-a"
    assert len(adapter.calls) == 1
