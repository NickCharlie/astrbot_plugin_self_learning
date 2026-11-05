from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from self_learning_EterU.services.core_learning.v2_learning_integration import (
    V2LearningIntegration,
)
from self_learning_EterU.services.learning.jargon_learning import JargonLearningModule


@pytest.mark.unit
@pytest.mark.asyncio
async def test_jargon_exclusion_only_loads_confirmed_terms():
    pending = {"content": "待确认", "is_jargon": None}
    confirmed = {"content": "已确认", "is_jargon": True}
    calls = []

    async def get_recent_jargon_list(**kwargs):
        calls.append(kwargs)
        if kwargs.get("only_confirmed") is True:
            return [confirmed]
        return [pending, confirmed]

    module = JargonLearningModule(
        config=SimpleNamespace(enable_jargon_learning=True),
        message_collector=None,
        jargon_miner_manager=None,
        jargon_statistical_filter=None,
        db_manager=SimpleNamespace(get_recent_jargon_list=get_recent_jargon_list),
    )

    terms = await module._get_existing_jargon_terms("group-a")

    assert terms == {"已确认"}
    assert calls == [
        {
            "chat_id": "group-a",
            "limit": 1000,
            "only_confirmed": True,
        }
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mine_jargon_keeps_pending_statistical_candidates_eligible():
    pending = {"content": "待确认", "is_jargon": None}
    confirmed = {"content": "已确认", "is_jargon": True}
    query_calls = []
    candidate = {
        "term": "待确认",
        "context_examples": ["待确认上下文"],
    }

    async def get_recent_jargon_list(**kwargs):
        query_calls.append(kwargs)
        if kwargs.get("only_confirmed") is True:
            return [confirmed]
        return [pending, confirmed]

    def get_jargon_candidates(group_id, *, top_k, exclude_terms):
        assert group_id == "group-a"
        assert top_k == 20
        return [] if "待确认" in exclude_terms else [candidate]

    statistical_filter = SimpleNamespace(
        get_jargon_candidates=Mock(side_effect=get_jargon_candidates),
    )
    miner = SimpleNamespace(
        should_trigger=Mock(return_value=True),
        run_once=AsyncMock(),
    )
    db = SimpleNamespace(
        get_recent_raw_messages=AsyncMock(
            return_value=[
                {"sender_id": "user-a", "message": "这是一条聊天上下文消息"}
                for _ in range(10)
            ]
        ),
        get_recent_jargon_list=get_recent_jargon_list,
    )
    module = JargonLearningModule(
        config=SimpleNamespace(enable_jargon_learning=True),
        message_collector=SimpleNamespace(
            get_statistics=AsyncMock(return_value={"raw_messages": 10})
        ),
        jargon_miner_manager=SimpleNamespace(
            get_or_create_miner=Mock(return_value=miner)
        ),
        jargon_statistical_filter=statistical_filter,
        db_manager=db,
    )

    await module.mine_jargon("group-a")

    assert query_calls == [
        {
            "chat_id": "group-a",
            "limit": 1000,
            "only_confirmed": True,
        }
    ]
    statistical_filter.get_jargon_candidates.assert_called_once_with(
        "group-a",
        top_k=20,
        exclude_terms={"已确认"},
    )
    miner.run_once.assert_awaited_once()
    assert miner.run_once.await_args.kwargs["statistical_candidates"] == [candidate]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_v2_jargon_batch_only_excludes_confirmed_terms():
    pending = {"content": "待确认", "is_jargon": None}
    confirmed = {"content": "已确认", "is_jargon": True}
    query_calls = []

    async def get_recent_jargon_list(**kwargs):
        query_calls.append(kwargs)
        if kwargs.get("only_confirmed") is True:
            return [confirmed]
        return [pending, confirmed]

    candidate = {"term": "待确认"}

    def get_jargon_candidates(group_id, *, top_k, exclude_terms):
        assert group_id == "group-a"
        assert top_k == 20
        return [] if "待确认" in exclude_terms else [candidate]

    jargon_filter = SimpleNamespace(
        get_jargon_candidates=Mock(side_effect=get_jargon_candidates),
    )
    db = SimpleNamespace(
        get_recent_jargon_list=get_recent_jargon_list,
        save_or_update_jargon=AsyncMock(),
    )
    llm = SimpleNamespace(
        generate_response=AsyncMock(return_value="测试释义"),
    )
    integration = V2LearningIntegration.__new__(V2LearningIntegration)
    integration._jargon_filter = jargon_filter
    integration._llm = llm
    integration._db = db
    integration._knowledge_manager = None
    integration._memory_manager = None
    integration._exemplar_library = None
    integration._social_analyzer = None
    integration._ingestion_buffer = {}

    from self_learning_EterU.services.quality import TieredLearningTrigger

    integration._trigger = TieredLearningTrigger()
    integration._register_trigger_operations()

    assert await integration._trigger.force_tier2("jargon", "group-a") is True

    assert query_calls == [
        {
            "chat_id": "group-a",
            "limit": 1000,
            "only_confirmed": True,
        }
    ]
    jargon_filter.get_jargon_candidates.assert_called_once_with(
        "group-a",
        top_k=20,
        exclude_terms={"已确认"},
    )
    llm.generate_response.assert_awaited_once()
    db.save_or_update_jargon.assert_awaited_once_with(
        "group-a",
        "待确认",
        {
            "meaning": "测试释义",
            "raw_content": "[]",
            "is_jargon": True,
            "count": 1,
            "is_complete": True,
        },
    )
