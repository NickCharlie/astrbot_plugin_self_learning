"""Learning switches must gate automatic work without disabling manual work."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from self_learning_EterU.core.interfaces import MessageData
from self_learning_EterU.services.core_learning.v2_learning_integration import (
    V2LearningIntegration,
)
from self_learning_EterU.services.learning.group_orchestrator import (
    GroupLearningOrchestrator,
)
from self_learning_EterU.services.learning.persona_learning import PersonaLearningModule
from self_learning_EterU.services.persona import persona_updater as persona_updater_module
from self_learning_EterU.services.persona.persona_updater import PersonaUpdater
from self_learning_EterU.services.quality import TieredLearningTrigger
from self_learning_EterU.services.jargon.jargon_miner import JargonInferenceEngine
from self_learning_EterU.services.jargon.jargon_statistical_filter import JargonStatisticalFilter


@pytest.mark.unit
@pytest.mark.asyncio
async def test_automatic_group_learning_honors_switches_but_manual_start_still_works():
    config = SimpleNamespace(
        enable_auto_learning=False,
        enable_style_learning=True,
        learning_interval_hours=1,
        min_messages_for_learning=10,
    )
    collector = SimpleNamespace(
        get_statistics=AsyncMock(return_value={"unprocessed_messages": 10}),
    )
    progressive = SimpleNamespace(start_learning=AsyncMock(return_value=True))
    orchestrator = GroupLearningOrchestrator(
        config, collector, progressive, qq_filter=None, db_manager=None,
    )

    await orchestrator.smart_start_learning_for_group("manual-only")
    collector.get_statistics.assert_not_awaited()
    progressive.start_learning.assert_not_awaited()

    await orchestrator._start_group_learning("manual-only")
    progressive.start_learning.assert_awaited_once_with("manual-only")
    progressive.start_learning.reset_mock()

    config.enable_auto_learning = True
    config.enable_style_learning = False
    await orchestrator.smart_start_learning_for_group("style-disabled")
    collector.get_statistics.assert_not_awaited()
    progressive.start_learning.assert_not_awaited()

    config.enable_style_learning = True
    await orchestrator.smart_start_learning_for_group("enabled")
    await asyncio.gather(*list(orchestrator.learning_tasks.values()))
    progressive.start_learning.assert_awaited_once_with("enabled")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_v2_jargon_switch_gates_stats_and_inference_after_runtime_changes():
    config = SimpleNamespace(enable_jargon_learning=False)
    jargon_filter = SimpleNamespace(
        update_from_message=Mock(),
        get_jargon_candidates=Mock(return_value=[
            {"term": "without-context"},
            {"term": "example", "context_examples": ["An example from the group"], "frequency": 3},
        ]),
    )
    db = SimpleNamespace(
        get_recent_jargon_list=AsyncMock(return_value=[]),
        get_jargon=AsyncMock(return_value=None),
        save_or_update_jargon=AsyncMock(),
    )
    llm = SimpleNamespace(generate_response=AsyncMock())
    integration = V2LearningIntegration.__new__(V2LearningIntegration)
    integration._config = config
    integration._jargon_filter = jargon_filter
    integration._db = db
    integration._llm = llm
    integration._knowledge_manager = None
    integration._memory_manager = None
    integration._exemplar_library = None
    integration._social_analyzer = None
    integration._trigger = TieredLearningTrigger()
    integration._register_trigger_operations()
    message = MessageData(
        sender_id="user", sender_name="User", message="A human chat message",
        group_id="group-a", timestamp=1, platform="test",
    )

    for enabled in (False, True, False):
        config.enable_jargon_learning = enabled
        jargon_filter.update_from_message.reset_mock()
        jargon_filter.get_jargon_candidates.reset_mock()
        db.get_recent_jargon_list.reset_mock()
        db.get_jargon.reset_mock()
        db.save_or_update_jargon.reset_mock()
        llm.generate_response.reset_mock()
        llm.generate_response.side_effect = [
            '{"meaning":"A group-specific meaning","no_info":false}',
            '{"meaning":"An ordinary meaning"}',
            '{"is_similar":false}',
        ]

        await integration._trigger.process_message(message, "group-a")
        assert await integration._trigger.force_tier2("jargon", "group-a") is enabled

        assert jargon_filter.update_from_message.call_count == int(enabled)
        assert jargon_filter.get_jargon_candidates.call_count == int(enabled)
        assert db.get_recent_jargon_list.await_count == int(enabled)
        assert db.get_jargon.await_count == 2 * int(enabled)
        assert db.save_or_update_jargon.await_count == int(enabled)
        assert llm.generate_response.await_count == 3 * int(enabled)
        if enabled:
            assert "An example from the group" in llm.generate_response.await_args_list[0].args[0]
            assert db.get_jargon.await_args_list[0].args == ("group-a", "example")
            saved = db.save_or_update_jargon.await_args.args[2]
            assert json.loads(saved["raw_content"]) == ["An example from the group"]
            assert saved["meaning"] == "A group-specific meaning"
            assert saved["count"] == 3
            assert saved["is_jargon"] is None
            assert saved["is_complete"] is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_v2_contextual_jargon_preserves_decisions_and_skips_uncertain_inference():
    integration = V2LearningIntegration.__new__(V2LearningIntegration)
    integration._config = SimpleNamespace(enable_jargon_learning=True)
    integration._llm = SimpleNamespace(generate_response=AsyncMock())
    db = SimpleNamespace(get_jargon=AsyncMock(), save_or_update_jargon=AsyncMock())
    integration._db = db
    candidate = {"term": "example", "context_examples": ["An example from the group"]}

    for protected in (
        {"is_complete": True, "is_jargon": False},
        {"is_jargon": True},
        {"meaning": "An edited definition"},
    ):
        db.get_jargon.return_value = protected
        await integration._infer_jargon_candidate("group-a", candidate)
    integration._llm.generate_response.assert_not_awaited()
    db.save_or_update_jargon.assert_not_awaited()

    db.get_jargon.return_value = None
    integration._llm.generate_response.side_effect = ['{"no_info":true}']
    await integration._infer_jargon_candidate("group-a", candidate)
    db.save_or_update_jargon.assert_not_awaited()

    for malformed_comparison in ('{}', '{"is_similar":"false"}'):
        integration._llm.generate_response.side_effect = [
            '{"meaning":"A group-specific meaning","no_info":false}',
            '{"meaning":"An ordinary meaning"}',
            malformed_comparison,
        ]
        await integration._infer_jargon_candidate("group-a", candidate)
        db.save_or_update_jargon.assert_not_awaited()

    db.get_jargon.side_effect = [None, {"is_complete": True, "meaning": "Reviewed meanwhile"}]
    integration._llm.generate_response.side_effect = [
        '{"meaning":"A group-specific meaning","no_info":false}',
        '{"meaning":"An ordinary meaning"}',
        '{"is_similar":false}',
    ]
    await integration._infer_jargon_candidate("group-a", candidate)
    db.save_or_update_jargon.assert_not_awaited()

    pending = {"raw_content": '["An earlier example in the group"]', "count": 7}
    db.get_jargon.side_effect = [pending, pending]
    integration._llm.generate_response.side_effect = [
        '{"meaning":"An ordinary meaning in context","no_info":false}',
        '{"meaning":"An ordinary meaning"}',
        '{"is_similar":true}',
    ]
    await integration._infer_jargon_candidate("group-a", candidate)
    db.save_or_update_jargon.assert_awaited_once()
    saved = db.save_or_update_jargon.await_args.args[2]
    assert saved["is_jargon"] is False
    assert saved["is_complete"] is False
    assert saved["count"] == 7
    assert json.loads(saved["raw_content"]) == [
        "An earlier example in the group", "An example from the group",
    ]


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("classification", [True, False])
async def test_v2_pending_jargon_merges_concurrent_context_and_refreshes_until_review(
    classification, monkeypatch,
):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from self_learning_EterU.models.orm import Base
    from self_learning_EterU.services.database.facades.jargon_facade import JargonFacade

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    database = JargonFacade(SimpleNamespace(engine=engine, get_session=sessions), SimpleNamespace())
    integration = V2LearningIntegration.__new__(V2LearningIntegration)
    integration._config = SimpleNamespace(enable_jargon_learning=True)
    integration._db = database
    integration._llm = object()
    inference_calls = []

    async def infer(_engine, term, contexts):
        inference_calls.append((term, contexts))
        await asyncio.sleep(0)
        if "unclear" in contexts[-1]:
            return {"no_info": True}
        return {"is_jargon": classification, "meaning": contexts[-1], "no_info": False}

    monkeypatch.setattr(JargonInferenceEngine, "infer_meaning", infer)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        candidates = [
            {"term": "term", "context_examples": [context], "frequency": frequency}
            for context, frequency in (("term first context", 5), ("term later context", 8))
        ]
        await asyncio.gather(*(
            integration._infer_jargon_candidate("group-a", candidate)
            for candidate in candidates
        ))
        row = await database.get_jargon("group-a", "term")
        assert json.loads(row["raw_content"]) == ["term first context", "term later context"]
        assert row["meaning"] == "term later context"
        assert row["count"] == row["last_inference_count"] == 8
        assert row["is_jargon"] is (None if classification else False)
        assert row["is_complete"] is False
        assert len(await database.get_recent_jargon_list(chat_id="group-a", pending_only=True)) == 1
        assert await database.get_jargon_count(chat_id="group-a", pending_only=True) == 1
        assert await database.get_recent_jargon_list(chat_id="group-a", only_confirmed=True) == []

        if classification:
            # An earlier V2 writer used True before the pending-review fix.
            await database.update_jargon({"id": row["id"], "is_jargon": True})
        await integration._infer_jargon_candidate("group-a", {
            "term": "term", "context_examples": ["term unclear new context"], "frequency": 9,
        })
        row = await database.get_jargon("group-a", "term")
        assert row["meaning"] == "term later context"
        assert row["count"] == 9
        assert row["is_jargon"] is (None if classification else False)
        assert json.loads(row["raw_content"])[-1] == "term unclear new context"

        await database.update_jargon({"id": row["id"], "is_jargon": True, "is_complete": True})
        calls_before_review = len(inference_calls)
        assert await integration._infer_jargon_candidate("group-a", candidates[0]) is False
        assert len(inference_calls) == calls_before_review
        assert await database.get_jargon_count(chat_id="group-a", pending_only=True) == 0
        assert len(await database.get_recent_jargon_list(chat_id="group-a", only_confirmed=True)) == 1
    finally:
        await engine.dispose()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_statistical_and_inference_windows_follow_recent_context(monkeypatch):
    statistical = JargonStatisticalFilter()
    monkeypatch.setattr(statistical, "_tokenize", lambda _text: ["term"])
    contexts = [f"term occurrence {index}" for index in range(12)]
    for context in contexts:
        statistical.update_from_message(context, "group-a", "user-a")
    assert statistical._term_contexts["group-a"]["term"] == contexts[-10:]
    assert statistical.get_jargon_candidates("group-a")[0]["context_examples"] == contexts[-5:]

    integration = V2LearningIntegration.__new__(V2LearningIntegration)
    integration._config = SimpleNamespace(enable_jargon_learning=True)
    integration._db = SimpleNamespace(
        get_jargon=AsyncMock(return_value=None), save_or_update_jargon=AsyncMock(),
    )
    integration._llm = SimpleNamespace(generate_response=AsyncMock(return_value='{"no_info":true}'))
    await integration._infer_jargon_candidate("group-a", {"term": "term", "context_examples": contexts})
    prompt = integration._llm.generate_response.await_args.args[0]
    assert contexts[-1] in prompt and contexts[0] not in prompt


@pytest.mark.unit
@pytest.mark.asyncio
async def test_persona_auto_apply_flag_never_bypasses_pending_review(monkeypatch):
    current = {"persona_id": "persona-a", "prompt": "Base persona"}
    monkeypatch.setattr(
        persona_updater_module, "resolve_target_persona",
        AsyncMock(return_value=current),
    )
    config = SimpleNamespace(
        auto_apply_approved_persona=True,
        auto_backup_enabled=True,
        persona_merge_strategy="append",
    )
    framework = SimpleNamespace(update_persona=AsyncMock())
    updater = PersonaUpdater.__new__(PersonaUpdater)
    updater.config = config
    updater.context = SimpleNamespace(persona_manager=framework)
    updater._logger = Mock()
    updater.backup_manager = SimpleNamespace(create_backup_before_update=AsyncMock())
    updater.format_persona_update_report = AsyncMock(return_value="Candidate report")
    updater._update_style_based_features_with_maibot = AsyncMock()
    database = SimpleNamespace(add_persona_learning_review=AsyncMock(return_value=1))
    module = PersonaLearningModule(
        config=config,
        context=updater.context,
        db_manager=database,
        persona_manager=SimpleNamespace(update_persona=updater.update_persona_with_style),
        multidimensional_analyzer=None,
        prompts=None,
        resolve_umo=lambda group_id: group_id,
        json_serializer=str,
    )
    messages = [{"sender_id": "user-a", "message": "A user chatting with another user"}]

    result = await module.apply_persona_learning(
        "group-a",
        {"enhanced_prompt": "Learned trait", "style_attributes": {"formality": "casual"}},
        messages,
        current_persona=current,
        updated_persona={**current, "prompt": "Base persona\n\nLearned trait"},
    )

    assert result is True
    assert current["prompt"] == "Base persona"
    framework.update_persona.assert_not_awaited()
    updater.backup_manager.create_backup_before_update.assert_awaited_once()
    updater._update_style_based_features_with_maibot.assert_awaited_once()
    database.add_persona_learning_review.assert_awaited_once()
    assert database.add_persona_learning_review.await_args.kwargs["proposed_content"] == "Learned trait"
