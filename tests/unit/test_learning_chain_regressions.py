import asyncio
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from self_learning_EterU.core.interfaces import MessageData
from self_learning_EterU.config import PluginConfig
from self_learning_EterU.services.core_learning.progressive_learning import (
    ProgressiveLearningService,
)
from self_learning_EterU.services.core_learning.message_collector import (
    MessageCollectorService,
)
from self_learning_EterU.services.database.sqlalchemy_database_manager import (
    SQLAlchemyDatabaseManager,
)
from self_learning_EterU.services.integration.maibot_enhanced_learning_manager import (
    MaiBotEnhancedLearningManager,
)
from self_learning_EterU.services.jargon.jargon_miner import JargonMiner
from self_learning_EterU.webui.services.learning_service import LearningService
from self_learning_EterU.services.learning.message_pipeline import MessagePipeline
from self_learning_EterU.services.learning.realtime_processor import RealtimeProcessor
from self_learning_EterU.services.state.enhanced_interaction import (
    EnhancedInteractionService,
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_progressive_learning_fetches_unprocessed_messages_for_current_group():
    service = ProgressiveLearningService.__new__(ProgressiveLearningService)
    service.batch_size = 42
    service.message_collector = SimpleNamespace(
        get_unprocessed_messages=AsyncMock(return_value=[]),
    )

    await service._execute_learning_batch_background("group-a")

    service.message_collector.get_unprocessed_messages.assert_awaited_once_with(
        limit=42,
        group_id="group-a",
    )


@pytest.mark.unit
def test_realtime_expression_builder_keeps_current_sender_messages():
    raw_messages = [
        {
            "id": 1,
            "sender_id": "user-a",
            "sender_name": "User A",
            "message": "这个表达应该留下来参与学习",
            "group_id": "group-a",
            "timestamp": time.time(),
            "platform": "test",
        }
    ]

    result = RealtimeProcessor._build_message_data_list(
        raw_messages,
        group_id="group-a",
        sender_id="user-a",
    )

    assert len(result) == 1
    assert result[0].sender_id == "user-a"
    assert result[0].message == "这个表达应该留下来参与学习"


@pytest.mark.unit
def test_maibot_expression_trigger_uses_message_field():
    manager = MaiBotEnhancedLearningManager.__new__(MaiBotEnhancedLearningManager)
    manager.group_learning_states = {}
    manager.MIN_MESSAGES_FOR_LEARNING = 2
    manager.LEARNING_COOLDOWN = 0

    messages = [
        MessageData(
            sender_id="user-a",
            sender_name="User A",
            message="这是一条足够长的用户消息",
            group_id="group-a",
            timestamp=time.time(),
            platform="test",
        ),
        MessageData(
            sender_id="user-b",
            sender_name="User B",
            message="这是另一条足够长的用户消息",
            group_id="group-a",
            timestamp=time.time(),
            platform="test",
        ),
    ]

    assert manager._should_trigger_expression_learning("group-a", messages) is True


@pytest.mark.unit
def test_fresh_jargon_miner_first_trigger_is_not_blocked_by_cooldown():
    miner = JargonMiner(
        chat_id="group-a",
        llm_adapter=object(),
        db_manager=object(),
        config=SimpleNamespace(),
    )

    assert miner.should_trigger(10) is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_message_pipeline_runs_expression_learning_without_realtime_mode():
    config = SimpleNamespace(
        enable_jargon_learning=False,
        enable_expression_patterns=True,
        enable_realtime_learning=False,
        enable_style_learning=False,
        enable_goal_driven_chat=False,
    )
    collector = SimpleNamespace(collect_message=AsyncMock())
    enhanced_interaction = SimpleNamespace(
        update_conversation_context=AsyncMock(),
    )
    realtime_processor = SimpleNamespace(
        process_expression_learning_background=AsyncMock(),
        process_realtime_background=AsyncMock(),
    )

    pipeline = MessagePipeline(
        plugin_config=config,
        message_collector=collector,
        enhanced_interaction=enhanced_interaction,
        jargon_miner_manager=None,
        jargon_statistical_filter=None,
        v2_integration=None,
        realtime_processor=realtime_processor,
        group_orchestrator=SimpleNamespace(),
        conversation_goal_manager=None,
        affection_manager=SimpleNamespace(),
        db_manager=SimpleNamespace(),
    )

    spawned = []

    def spawn_now(coro):
        task = asyncio.create_task(coro)
        spawned.append(task)
        return task

    pipeline._spawn = spawn_now
    event = SimpleNamespace(
        get_sender_name=lambda: "User A",
        get_platform_name=lambda: "test",
    )

    await pipeline.process_learning("group-a", "user-a", "这是表达学习消息", event)
    await asyncio.gather(*spawned)

    realtime_processor.process_expression_learning_background.assert_awaited_once_with(
        "group-a",
        "这是表达学习消息",
        "user-a",
    )
    realtime_processor.process_realtime_background.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_message_pipeline_collects_to_database_and_triggers_learning_paths(
    tmp_path,
):
    config = PluginConfig(
        data_dir=str(tmp_path),
        db_type="sqlite",
        enable_web_interface=False,
        enable_jargon_learning=True,
        enable_expression_patterns=True,
        enable_realtime_learning=False,
        enable_style_learning=False,
        enable_goal_driven_chat=False,
    )
    db = SQLAlchemyDatabaseManager(config)
    expression_calls = []
    spawned = []

    async def noop(*args, **kwargs):
        return None

    async def expression_background(group_id, message_text, sender_id):
        expression_calls.append((group_id, message_text, sender_id))

    class Event:
        def get_sender_name(self):
            return "User A"

        def get_platform_name(self):
            return "test"

    try:
        assert await db.start() is True
        collector = MessageCollectorService(
            config,
            context=None,
            database_manager=db,
        )
        pipeline = MessagePipeline(
            plugin_config=config,
            message_collector=collector,
            enhanced_interaction=SimpleNamespace(update_conversation_context=noop),
            jargon_miner_manager=None,
            jargon_statistical_filter=SimpleNamespace(
                update_from_message=lambda *args, **kwargs: None
            ),
            v2_integration=None,
            realtime_processor=SimpleNamespace(
                process_expression_learning_background=expression_background,
                process_realtime_background=noop,
            ),
            group_orchestrator=SimpleNamespace(smart_start_learning_for_group=noop),
            conversation_goal_manager=None,
            affection_manager=SimpleNamespace(),
            db_manager=db,
        )

        def spawn_now(coro):
            task = asyncio.create_task(coro)
            spawned.append(task)
            return task

        pipeline._spawn = spawn_now

        for idx in range(10):
            await pipeline.process_learning(
                "group-a",
                f"user-{idx % 2}",
                f"第{idx + 1}条用于学习链路的黑话表达消息",
                Event(),
            )

        await asyncio.gather(*spawned)

        stats = await collector.get_statistics("group-a")
        recent = await db.get_recent_raw_messages("group-a", limit=20)

        assert stats["raw_messages"] == 10
        assert len(recent) == 10
        assert len(expression_calls) == 10
        assert pipeline._last_jargon_trigger_counts["group-a"] == 10
    finally:
        if spawned:
            await asyncio.gather(*spawned, return_exceptions=True)
        await db.stop()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_message_pipeline_jargon_trigger_uses_threshold_crossing_not_exact_modulo():
    config = SimpleNamespace(
        enable_jargon_learning=True,
        enable_expression_patterns=False,
        enable_realtime_learning=False,
        enable_style_learning=False,
        enable_goal_driven_chat=False,
    )
    collector = SimpleNamespace(
        collect_message=AsyncMock(),
        get_statistics=AsyncMock(
            side_effect=[
                {"raw_messages": 11},
                {"raw_messages": 19},
                {"raw_messages": 21},
            ]
        ),
    )
    enhanced_interaction = SimpleNamespace(
        update_conversation_context=AsyncMock(),
    )

    pipeline = MessagePipeline(
        plugin_config=config,
        message_collector=collector,
        enhanced_interaction=enhanced_interaction,
        jargon_miner_manager=SimpleNamespace(),
        jargon_statistical_filter=None,
        v2_integration=None,
        realtime_processor=SimpleNamespace(),
        group_orchestrator=SimpleNamespace(),
        conversation_goal_manager=None,
        affection_manager=SimpleNamespace(),
        db_manager=SimpleNamespace(),
    )

    pipeline.mine_jargon = AsyncMock()
    spawned = []

    def spawn_now(coro):
        task = asyncio.create_task(coro)
        spawned.append(task)
        return task

    pipeline._spawn = spawn_now
    event = SimpleNamespace(
        get_sender_name=lambda: "User A",
        get_platform_name=lambda: "test",
    )

    await pipeline.process_learning("group-a", "user-a", "第11条消息", event)
    await asyncio.gather(*spawned)
    spawned.clear()

    await pipeline.process_learning("group-a", "user-a", "第19条消息", event)
    await asyncio.gather(*spawned)
    spawned.clear()

    await pipeline.process_learning("group-a", "user-a", "第21条消息", event)
    await asyncio.gather(*spawned)

    assert pipeline.mine_jargon.await_count == 2
    pipeline.mine_jargon.assert_any_await("group-a")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_realtime_expression_learning_is_batch_gated():
    config = SimpleNamespace(
        message_min_length=1,
        message_max_length=500,
        enable_expression_patterns=True,
        expression_learning_trigger_messages=10,
    )
    collector = SimpleNamespace(
        get_statistics=AsyncMock(
            side_effect=[
                {"raw_messages": 9},
                {"raw_messages": 10},
                {"raw_messages": 19},
                {"raw_messages": 20},
            ]
        )
    )
    learner = SimpleNamespace(trigger_learning_for_group=AsyncMock(return_value=False))
    factory_manager = SimpleNamespace(
        get_component_factory=lambda: SimpleNamespace(
            create_expression_pattern_learner=lambda: learner
        )
    )
    db_manager = SimpleNamespace(
        get_recent_raw_messages=AsyncMock(
            return_value=[
                {
                    "id": idx,
                    "sender_id": f"user-{idx}",
                    "sender_name": f"User {idx}",
                    "message": f"这是第{idx}条足够长的表达学习消息",
                    "timestamp": time.time(),
                    "platform": "test",
                }
                for idx in range(1, 6)
            ]
        )
    )
    processor = RealtimeProcessor(
        plugin_config=config,
        message_collector=collector,
        multidimensional_analyzer=SimpleNamespace(),
        persona_manager=SimpleNamespace(),
        temporary_persona_updater=SimpleNamespace(),
        dialog_analyzer=SimpleNamespace(),
        learning_stats=SimpleNamespace(style_updates=0),
        factory_manager=factory_manager,
        db_manager=db_manager,
    )

    for _ in range(4):
        await processor.process_expression_learning(
            "group-a",
            "这是用于表达学习频控的消息",
            "user-a",
        )

    assert learner.trigger_learning_for_group.await_count == 2


@pytest.mark.unit
def test_topic_detection_is_batch_gated():
    service = EnhancedInteractionService.__new__(EnhancedInteractionService)
    service.config = SimpleNamespace(topic_detection_interval_messages=10)
    service._last_topic_detection_counts = {}

    assert service._should_detect_topic("group-a", 2) is False
    assert service._should_detect_topic("group-a", 9) is False
    assert service._should_detect_topic("group-a", 10) is True
    assert service._should_detect_topic("group-a", 19) is False
    assert service._should_detect_topic("group-a", 20) is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_progressive_learning_saves_canonical_style_review_type():
    service = ProgressiveLearningService.__new__(ProgressiveLearningService)
    service._save_expression_patterns = AsyncMock()

    class _FakeSession:
        def __init__(self):
            self.added = None

        def add(self, obj):
            self.added = obj

        async def commit(self):
            return None

        async def refresh(self, obj):
            obj.id = 123

    class _FakeSessionContext:
        def __init__(self, session):
            self._session = session

        async def __aenter__(self):
            return self._session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    fake_session = _FakeSession()
    service.db_manager = SimpleNamespace(
        get_session=lambda: _FakeSessionContext(fake_session)
    )

    style_analysis = {
        "expression_patterns": [
            {
                "situation": "用户问候",
                "expression": "我来了",
                "weight": 1.0,
                "confidence": 0.9,
            }
        ]
    }

    await service._save_style_learning_record(
        "group-a",
        style_analysis,
        messages=[{"message": "你好"}],
        quality_metrics=None,
    )

    assert fake_session.added is not None
    assert fake_session.added.type == "style_learning"
    assert fake_session.added.status == "pending"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_learning_service_style_review_uses_unified_persona_review_path(
    monkeypatch,
):
    calls = []

    class _FakePersonaReviewService:
        def __init__(self, container):
            self.container = container

        async def review_persona_update(self, update_id, action):
            calls.append((update_id, action))
            return True, "ok"

    monkeypatch.setattr(
        "self_learning_EterU.webui.services.learning_service.PersonaReviewService",
        _FakePersonaReviewService,
    )

    service = LearningService(
        SimpleNamespace(
            database_manager=SimpleNamespace(),
            persona_updater=SimpleNamespace(),
        )
    )

    assert await service.approve_style_learning_review(42) == (True, "ok")
    assert calls == [("style_42", "approve")]
