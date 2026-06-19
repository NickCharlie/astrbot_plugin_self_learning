import asyncio
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from self_learning_EterU.core.interfaces import AnalysisResult, MessageData
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
from self_learning_EterU.models.orm.expression import (
    ExpressionPattern as ExpressionPatternORM,
)
from self_learning_EterU.models.orm.exemplar import Exemplar
from self_learning_EterU.models.orm.learning import StyleLearningReview
from self_learning_EterU.models.orm.memory import Memory
from self_learning_EterU.services.analysis.expression_pattern_learner import (
    ExpressionPattern,
    ExpressionPatternLearner,
)
from self_learning_EterU.services.commands.command_filter import CommandFilter
from self_learning_EterU.services.commands.handlers import PluginCommandHandlers
from self_learning_EterU.services.integration.maibot_enhanced_learning_manager import (
    MaiBotEnhancedLearningManager,
)
from self_learning_EterU.services.jargon.jargon_miner import JargonMiner
from self_learning_EterU.services.learning.remember_service import RememberService
from self_learning_EterU.webui.services.learning_service import LearningService
from self_learning_EterU.services.learning.message_pipeline import MessagePipeline
from self_learning_EterU.services.learning.realtime_processor import RealtimeProcessor
from self_learning_EterU.services.learning.sample_filter import (
    extract_learning_event_metadata,
    filter_learning_messages,
    should_ignore_learning_sample,
)
from self_learning_EterU.services.social.social_context_injector import (
    SocialContextInjector,
)
from self_learning_EterU.services.persona.temporary_persona_updater import (
    TemporaryPersonaUpdater,
)
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
@pytest.mark.asyncio
async def test_background_learning_persists_filter_stats_and_persona_review():
    service = ProgressiveLearningService.__new__(ProgressiveLearningService)
    service.batch_size = 10
    service.config = SimpleNamespace(max_messages_per_batch=200)
    service._group_sessions = {}
    service.update_system_prompt_callback = None
    service.ml_analyzer = SimpleNamespace()
    service.message_collector = SimpleNamespace(
        get_unprocessed_messages=AsyncMock(
            return_value=[
                {
                    "id": 1,
                    "sender_id": "user-a",
                    "sender_name": "User A",
                    "message": "这是一条足够长的学习消息，会进入人格审查",
                    "group_id": "group-a",
                    "timestamp": time.time(),
                }
            ]
        ),
        add_filtered_message=AsyncMock(),
        mark_messages_processed=AsyncMock(),
    )
    service._filter_messages_with_context = AsyncMock(
        return_value=[
            {
                "id": 1,
                "sender_id": "user-a",
                "message": "这是一条足够长的学习消息，会进入人格审查",
                "group_id": "group-a",
                "timestamp": time.time(),
                "relevance_score": 1.0,
                "filter_reason": "style_learning_no_filter",
            }
        ]
    )
    service._get_current_persona = AsyncMock(
        return_value={"prompt": "原人格", "name": "default"}
    )
    service._execute_style_analysis_background = AsyncMock(
        return_value=AnalysisResult(
            success=True,
            confidence=0.8,
            data={"enhanced_prompt": "新增人格特征"},
            timestamp=time.time(),
        )
    )
    service._generate_updated_persona_with_refinement = AsyncMock(
        return_value={"prompt": "原人格\n\n新增人格特征", "name": "default"}
    )
    service.quality_monitor = SimpleNamespace(
        evaluate_learning_batch=AsyncMock(
            return_value=AnalysisResult(
                success=True,
                confidence=0.8,
                data={},
                consistency_score=0.8,
            )
        )
    )
    service.persona_manager = SimpleNamespace(update_persona=AsyncMock(return_value=True))
    service._save_style_learning_record = AsyncMock()
    service.db_manager = SimpleNamespace(
        get_session=lambda: (_ for _ in ()).throw(AssertionError("unused")),
        save_learning_performance_record=AsyncMock(return_value=True),
        add_persona_learning_review=AsyncMock(return_value=42),
    )

    await service._execute_learning_batch_background("group-a")

    service.message_collector.add_filtered_message.assert_awaited_once()
    filter_payload = service.message_collector.add_filtered_message.await_args.args[0]
    assert filter_payload["raw_message_id"] == 1
    assert filter_payload["confidence"] == 1.0
    service.db_manager.add_persona_learning_review.assert_awaited_once()
    review_kwargs = service.db_manager.add_persona_learning_review.await_args.kwargs
    assert review_kwargs["group_id"] == "group-a"
    assert review_kwargs["proposed_content"] == "新增人格特征"
    assert review_kwargs["original_content"] == "原人格"
    assert review_kwargs["new_content"] == "原人格\n\n新增人格特征"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_manual_learning_batch_generates_persona_review():
    service = ProgressiveLearningService.__new__(ProgressiveLearningService)
    service.batch_size = 10
    service.config = SimpleNamespace(max_messages_per_batch=200)
    service._group_sessions = {}
    service.update_system_prompt_callback = None
    service.ml_analyzer = SimpleNamespace()
    service.message_collector = SimpleNamespace(
        get_unprocessed_messages=AsyncMock(
            return_value=[
                {
                    "id": 1,
                    "sender_id": "user-a",
                    "sender_name": "User A",
                    "message": "手动学习也应该产生人格候选",
                    "group_id": "group-a",
                    "timestamp": time.time(),
                }
            ]
        ),
        add_filtered_message=AsyncMock(),
        mark_messages_processed=AsyncMock(),
    )
    service._filter_messages_with_context = AsyncMock(
        return_value=[
            {
                "id": 1,
                "sender_id": "user-a",
                "message": "手动学习也应该产生人格候选",
                "group_id": "group-a",
                "timestamp": time.time(),
                "relevance_score": 1.0,
                "filter_reason": "style_learning_no_filter",
            }
        ]
    )
    service._get_current_persona = AsyncMock(
        return_value={"prompt": "原人格", "name": "default"}
    )
    service._execute_style_analysis_background = AsyncMock(
        return_value=AnalysisResult(
            success=True,
            confidence=0.8,
            data={"enhanced_prompt": "手动学习新增人格特征"},
            timestamp=time.time(),
        )
    )
    service._generate_updated_persona_with_refinement = AsyncMock(
        return_value={"prompt": "原人格\n\n手动学习新增人格特征", "name": "default"}
    )
    service.quality_monitor = SimpleNamespace(
        evaluate_learning_batch=AsyncMock(
            return_value=AnalysisResult(
                success=True,
                confidence=0.8,
                data={},
                consistency_score=0.8,
            )
        )
    )
    service.persona_manager = SimpleNamespace(update_persona=AsyncMock(return_value=True))
    service._save_style_learning_record = AsyncMock()
    service.db_manager = SimpleNamespace(
        save_learning_performance_record=AsyncMock(return_value=True),
        add_persona_learning_review=AsyncMock(return_value=43),
    )

    await service._execute_learning_batch("group-a", from_force_learning=True)

    service.message_collector.add_filtered_message.assert_awaited_once()
    service.db_manager.add_persona_learning_review.assert_awaited_once()
    review_kwargs = service.db_manager.add_persona_learning_review.await_args.kwargs
    assert review_kwargs["proposed_content"] == "手动学习新增人格特征"


@pytest.mark.unit
def test_progressive_learning_derives_quality_when_monitor_returns_zero():
    service = ProgressiveLearningService.__new__(ProgressiveLearningService)
    service.config = SimpleNamespace(max_messages_per_batch=200)
    metrics = AnalysisResult(
        success=True,
        confidence=0.0,
        data={"overall_quality": 0.0},
        consistency_score=0.0,
    )
    messages = [
        {
            "message": "这是一条足够长的学习消息，用来表达当前群聊的说话习惯",
            "relevance_score": 0.8,
        }
        for _ in range(20)
    ]

    quality_score = service._resolve_learning_quality_score(metrics, messages)
    service._patch_zero_quality_metric(metrics, quality_score)

    assert 0 < quality_score <= 1
    assert metrics.consistency_score == quality_score


@pytest.mark.unit
def test_progressive_learning_fallback_style_analysis_is_reviewable():
    service = ProgressiveLearningService.__new__(ProgressiveLearningService)

    data = service._build_fallback_style_analysis_data(
        [
            {"message": "今天这个功能真的很好用！继续保持这种表达"},
            {"message": "能不能再解释一下为什么会这样？"},
        ]
    )

    assert data["message_count"] == 2
    assert "learning_insights" in data
    assert "代表性表达" in data["learning_insights"]
    assert data["style_analysis"]["expression_features"]


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
def test_learning_sample_filter_blocks_commands_and_system_outputs():
    bot_help = (
        "AstrBot v4.24.5(WebUI: None)\n"
        "/new - Create new conversation\n"
        "/provider - View or switch LLM Provider"
    )
    livingmemory_shutdown_log = (
        "[2026-06-02 11:54:17] [INFO] [LivingMemory] MemoryEngine 已关闭"
    )

    assert should_ignore_learning_sample("/help") is True
    assert should_ignore_learning_sample("/help me") is True
    assert should_ignore_learning_sample("help") is True
    assert should_ignore_learning_sample("help me") is False
    assert should_ignore_learning_sample("/a hello") is True
    assert should_ignore_learning_sample("/帮助 查看菜单") is True
    assert should_ignore_learning_sample("使用 /help 命令查看菜单", sender_id="bot", is_bot=True) is True
    assert should_ignore_learning_sample("发送 /帮助 查看菜单", sender_id="bot", is_bot=True) is True
    assert should_ignore_learning_sample("可用命令：/help /provider", sender_id="bot", is_bot=True) is True
    assert should_ignore_learning_sample("我不会使用命令式的语气聊天") is False
    assert should_ignore_learning_sample(bot_help, sender_id="bot", is_bot=True) is True
    assert should_ignore_learning_sample(livingmemory_shutdown_log) is True
    assert should_ignore_learning_sample("MemoryEngine 已关闭") is True
    assert should_ignore_learning_sample("[PageAPI] 获取图谱概览失败: timeout") is True
    assert should_ignore_learning_sample("[BackupManager] 备份完成: 3 个文件") is True
    assert should_ignore_learning_sample("[AtomLifecycle] 维护任务异常") is True
    assert should_ignore_learning_sample("[StorageMaintenance] 执行存储维护失败") is True
    assert should_ignore_learning_sample("[VectorRetriever] 查询文本过长 (2048 字符)") is True
    assert should_ignore_learning_sample(
        "这是一条普通聊天消息",
        message_type="notice",
    ) is True
    assert should_ignore_learning_sample(
        "这是一条普通群聊消息",
        message_type="group_message",
    ) is False
    assert should_ignore_learning_sample("LivingMemory 今天真好用") is False
    assert should_ignore_learning_sample("这是一条普通聊天消息") is False


@pytest.mark.unit
def test_command_filter_recognizes_remember_command():
    command_filter = CommandFilter()

    assert command_filter.is_plugin_command("/remember 这段要记住") is True
    assert command_filter.is_plugin_command("remember 这段要记住") is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_remember_service_links_memory_expression_exemplar_and_review(tmp_path):
    config = PluginConfig(
        data_dir=str(tmp_path),
        db_type="sqlite",
        enable_web_interface=False,
    )
    db = SQLAlchemyDatabaseManager(config)

    try:
        assert await db.start() is True
        service = RememberService(db)

        result = await service.remember(
            group_id="group-a",
            sender_id="user-a",
            content="今天状态怎么样 => 我今天状态不错，想继续聊",
        )

        assert result.memory_id > 0
        assert result.expression_saved is True
        assert result.exemplar_id
        assert result.style_review_id > 0

        async with db.get_session() as session:
            memories = (
                await session.execute(select(Memory))
            ).scalars().all()
            expressions = (
                await session.execute(select(ExpressionPatternORM))
            ).scalars().all()
            exemplars = (
                await session.execute(select(Exemplar))
            ).scalars().all()
            reviews = (
                await session.execute(select(StyleLearningReview))
            ).scalars().all()

        assert memories[0].memory_type == "manual_remember"
        assert memories[0].importance == 9
        assert expressions[0].situation == "今天状态怎么样"
        assert expressions[0].expression == "我今天状态不错，想继续聊"
        assert "A: 今天状态怎么样" in exemplars[0].content
        assert reviews[0].status == "pending"
        assert reviews[0].metadata_
    finally:
        await db.stop()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_remember_command_delegates_to_service():
    remember_service = SimpleNamespace(
        remember=AsyncMock(
            return_value=SimpleNamespace(
                memory_id=1,
                exemplar_id=2,
                style_review_id=3,
            )
        )
    )
    handler = PluginCommandHandlers(
        plugin_config=SimpleNamespace(),
        service_factory=SimpleNamespace(),
        message_collector=SimpleNamespace(),
        persona_manager=SimpleNamespace(),
        progressive_learning=SimpleNamespace(),
        affection_manager=SimpleNamespace(),
        temporary_persona_updater=SimpleNamespace(),
        db_manager=SimpleNamespace(),
        llm_adapter=SimpleNamespace(),
        remember_service=remember_service,
    )
    event = SimpleNamespace(
        get_message_str=lambda: "/remember 打招呼 => 我来了",
        get_group_id=lambda: "group-a",
        get_sender_id=lambda: "user-a",
        get_self_id=lambda: "bot-a",
        plain_result=lambda text: text,
    )

    results = [item async for item in handler.remember(event)]

    remember_service.remember.assert_awaited_once_with(
        group_id="group-a",
        sender_id="user-a",
        content="打招呼 => 我来了",
        persona_id="bot-a",
    )
    assert "已记住这段对话上下文" in results[0]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_remember_command_uses_quoted_context_when_present():
    remember_service = SimpleNamespace(
        remember=AsyncMock(
            return_value=SimpleNamespace(
                memory_id=1,
                exemplar_id=2,
                style_review_id=3,
            )
        )
    )
    handler = PluginCommandHandlers(
        plugin_config=SimpleNamespace(),
        service_factory=SimpleNamespace(),
        message_collector=SimpleNamespace(),
        persona_manager=SimpleNamespace(),
        progressive_learning=SimpleNamespace(),
        affection_manager=SimpleNamespace(),
        temporary_persona_updater=SimpleNamespace(),
        db_manager=SimpleNamespace(),
        llm_adapter=SimpleNamespace(),
        remember_service=remember_service,
    )
    event = SimpleNamespace(
        get_message_str=lambda: "/remember 我来了",
        get_group_id=lambda: "group-a",
        get_sender_id=lambda: "user-a",
        get_self_id=lambda: "bot-a",
        get_message=lambda: [
            SimpleNamespace(type="Reply", text="用户说你好"),
            SimpleNamespace(type="Plain", text="/remember 我来了"),
        ],
        plain_result=lambda text: text,
    )

    results = [item async for item in handler.remember(event)]

    remember_service.remember.assert_awaited_once_with(
        group_id="group-a",
        sender_id="user-a",
        content="用户说你好 => 我来了",
        persona_id="bot-a",
    )
    assert "已记住这段对话上下文" in results[0]


@pytest.mark.unit
def test_learning_sample_filter_reads_raw_event_metadata_from_objects():
    message = SimpleNamespace(
        message="这是一条普通聊天消息",
        sender_id="user-a",
        raw_event={"message_type": "notice"},
    )

    assert filter_learning_messages([message]) == []


@pytest.mark.unit
def test_learning_event_metadata_logs_unexpected_accessor_failures(caplog):
    class Event:
        def get_message_type(self):
            raise RuntimeError("metadata accessor failed")

        def get_event_type(self):
            return "message"

    with caplog.at_level("DEBUG"):
        metadata = extract_learning_event_metadata(Event())

    assert metadata["event_type"] == "message"
    assert any(
        "Failed to read learning event metadata via Event.get_message_type"
        in record.message
        for record in caplog.records
    )


@pytest.mark.unit
def test_realtime_expression_builder_filters_command_samples():
    raw_messages = [
        {
            "id": 1,
            "sender_id": "user-a",
            "sender_name": "User A",
            "message": "help",
            "group_id": "group-a",
            "timestamp": time.time(),
            "platform": "test",
        },
        {
            "id": 2,
            "sender_id": "user-a",
            "sender_name": "User A",
            "message": "这个表达应该保留用于学习",
            "group_id": "group-a",
            "timestamp": time.time(),
            "platform": "test",
        },
    ]

    result = RealtimeProcessor._build_message_data_list(
        raw_messages,
        group_id="group-a",
        sender_id="user-a",
    )

    assert [item.message for item in result] == ["这个表达应该保留用于学习"]


@pytest.mark.unit
def test_progressive_fewshot_extraction_skips_command_system_pairs():
    merged = [
        {"sender_id": "user-a", "message": "help", "timestamp": 1},
        {
            "sender_id": "bot",
            "message": (
                "AstrBot v4.24.5(WebUI: None)\n"
                "/new - Create new conversation\n"
                "/provider - View or switch LLM Provider"
            ),
            "timestamp": 2,
        },
        {"sender_id": "user-a", "message": "今天状态怎么样", "timestamp": 3},
        {"sender_id": "bot", "message": "我今天状态不错", "timestamp": 4},
    ]

    pairs = ProgressiveLearningService._extract_fewshot_pairs_from_merged(
        merged,
        "group-a",
    )

    assert len(pairs) == 1
    assert pairs[0]["situation"] == "今天状态怎么样"
    assert pairs[0]["expression"] == "我今天状态不错"


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
async def test_message_pipeline_skips_expression_learning_without_realtime_mode_by_default():
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
        get_self_id=lambda: "bot-a",
    )

    await pipeline.process_learning("group-a", "user-a", "这是表达学习消息", event)
    await asyncio.gather(*spawned)

    realtime_processor.process_expression_learning_background.assert_not_called()
    realtime_processor.process_realtime_background.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_message_pipeline_can_run_expression_learning_when_explicitly_enabled():
    config = SimpleNamespace(
        enable_jargon_learning=False,
        enable_expression_patterns=True,
        enable_realtime_learning=False,
        enable_realtime_expression_learning=True,
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
        get_self_id=lambda: "bot-a",
    )

    await pipeline.process_learning("group-a", "user-a", "这是表达学习消息", event)
    await asyncio.gather(*spawned)

    realtime_processor.process_expression_learning_background.assert_awaited_once_with(
        "group-a",
        "这是表达学习消息",
        "user-a",
        persona_id="bot-a",
    )
    realtime_processor.process_realtime_background.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_message_pipeline_skips_plugin_log_events_before_collection():
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
    event = SimpleNamespace(
        get_sender_name=lambda: "LivingMemory",
        get_platform_name=lambda: "test",
        get_message_type=lambda: "notice",
    )

    collected = await pipeline.process_learning(
        "group-a",
        "plugin",
        "[INFO] [LivingMemory] MemoryEngine 已关闭",
        event,
    )

    assert collected is False
    collector.collect_message.assert_not_called()
    enhanced_interaction.update_conversation_context.assert_not_called()
    realtime_processor.process_expression_learning_background.assert_not_called()
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
        enable_realtime_expression_learning=True,
        enable_style_learning=False,
        enable_goal_driven_chat=False,
    )
    db = SQLAlchemyDatabaseManager(config)
    expression_calls = []
    spawned = []

    async def noop(*args, **kwargs):
        return None

    async def expression_background(
        group_id,
        message_text,
        sender_id,
        persona_id="default",
    ):
        expression_calls.append((group_id, message_text, sender_id, persona_id))

    class Event:
        def get_sender_name(self):
            return "User A"

        def get_platform_name(self):
            return "test"

        def get_self_id(self):
            return "bot-a"

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

        await pipeline.process_learning(
            "group-a",
            "plugin",
            "[INFO] [LivingMemory] MemoryEngine 已关闭",
            Event(),
        )

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
        assert {call[3] for call in expression_calls} == {"bot-a"}
        assert pipeline._last_jargon_trigger_counts["group-a"] == 10
    finally:
        if spawned:
            await asyncio.gather(*spawned, return_exceptions=True)
        await db.stop()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_expression_pattern_save_handles_duplicate_existing_rows(tmp_path):
    config = PluginConfig(
        data_dir=str(tmp_path),
        db_type="sqlite",
        enable_web_interface=False,
    )
    db = SQLAlchemyDatabaseManager(config)

    try:
        assert await db.start() is True
        async with db.get_session() as session:
            session.add_all(
                [
                    ExpressionPatternORM(
                        situation="今晚安排",
                        expression="偷偷刷视频",
                        weight=1.0,
                        last_active_time=10.0,
                        create_time=1.0,
                        group_id="group-a",
                    ),
                    ExpressionPatternORM(
                        situation="今晚安排",
                        expression="偷偷刷视频",
                        weight=3.0,
                        last_active_time=20.0,
                        create_time=2.0,
                        group_id="group-a",
                    ),
                ]
            )
            await session.commit()
            rows_before = (
                await session.execute(
                    select(ExpressionPatternORM).where(
                        ExpressionPatternORM.group_id == "group-a",
                        ExpressionPatternORM.situation == "今晚安排",
                        ExpressionPatternORM.expression == "偷偷刷视频",
                    )
                )
            ).scalars().all()

        assert len(rows_before) == 2
        original_ids = {row.id for row in rows_before}
        strongest_before_id = max(rows_before, key=lambda row: row.weight).id

        learner = ExpressionPatternLearner.__new__(ExpressionPatternLearner)
        learner.db_manager = db

        await learner._save_expression_patterns(
            [
                ExpressionPattern(
                    situation="今晚安排",
                    expression="偷偷刷视频",
                    weight=1.0,
                    last_active_time=30.0,
                    create_time=30.0,
                    group_id="group-a",
                )
            ],
            "group-a",
        )

        async with db.get_session() as session:
            rows = (
                await session.execute(
                    select(ExpressionPatternORM).where(
                        ExpressionPatternORM.group_id == "group-a",
                        ExpressionPatternORM.situation == "今晚安排",
                        ExpressionPatternORM.expression == "偷偷刷视频",
                    )
                )
            ).scalars().all()

        assert len(rows) == 2
        assert {row.id for row in rows} == original_ids
        strongest_after = max(rows, key=lambda row: row.weight)
        assert strongest_after.id == strongest_before_id
        assert strongest_after.weight == 4.0
    finally:
        await db.stop()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_expression_patterns_are_isolated_by_persona_id(tmp_path):
    config = PluginConfig(
        data_dir=str(tmp_path),
        db_type="sqlite",
        enable_web_interface=False,
    )
    db = SQLAlchemyDatabaseManager(config)

    try:
        assert await db.start() is True
        learner = ExpressionPatternLearner.__new__(ExpressionPatternLearner)
        learner.db_manager = db

        await learner._save_expression_patterns(
            [
                ExpressionPattern(
                    situation="打招呼",
                    expression="我是A的说法",
                    weight=1.0,
                    last_active_time=30.0,
                    create_time=30.0,
                    group_id="group-a",
                    persona_id="bot-a",
                ),
                ExpressionPattern(
                    situation="打招呼",
                    expression="我是B的说法",
                    weight=1.0,
                    last_active_time=30.0,
                    create_time=30.0,
                    group_id="group-a",
                    persona_id="bot-b",
                ),
            ],
            "group-a",
        )

        bot_a_patterns = await learner.get_expression_patterns(
            "group-a",
            persona_id="bot-a",
        )
        bot_b_patterns = await learner.get_expression_patterns(
            "group-a",
            persona_id="bot-b",
        )

        assert [pattern.expression for pattern in bot_a_patterns] == ["我是A的说法"]
        assert [pattern.expression for pattern in bot_b_patterns] == ["我是B的说法"]
    finally:
        await db.stop()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_social_context_expression_fallback_keeps_persona_scope():
    calls = []

    class _DB:
        async def get_recent_week_expression_patterns(
            self,
            group_id=None,
            limit=50,
            hours=168,
            persona_id="default",
        ):
            calls.append(
                {
                    "group_id": group_id,
                    "limit": limit,
                    "hours": hours,
                    "persona_id": persona_id,
                }
            )
            if group_id is None and persona_id == "bot-a":
                return [
                    {
                        "situation": "打招呼",
                        "expression": "我是A的说法",
                    }
                ]
            return []

    injector = SocialContextInjector(
        database_manager=_DB(),
        config=SimpleNamespace(expression_patterns_hours=24),
    )

    text = await injector._format_expression_patterns_context(
        "group-a",
        persona_id="bot-a",
        enable_protection=False,
    )

    assert "我是A的说法" in text
    assert calls == [
        {
            "group_id": "group-a",
            "limit": 10,
            "hours": 24,
            "persona_id": "bot-a",
        },
        {
            "group_id": None,
            "limit": 10,
            "hours": 24,
            "persona_id": "bot-a",
        },
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_expression_facade_keeps_grouped_shape_with_persona_rows(tmp_path):
    config = PluginConfig(
        data_dir=str(tmp_path),
        db_type="sqlite",
        enable_web_interface=False,
    )
    db = SQLAlchemyDatabaseManager(config)

    try:
        assert await db.start() is True
        async with db.get_session() as session:
            session.add_all(
                [
                    ExpressionPatternORM(
                        situation="打招呼",
                        expression="我是A的说法",
                        weight=1.0,
                        last_active_time=30.0,
                        create_time=30.0,
                        group_id="group-a",
                        persona_id="bot-a",
                    ),
                    ExpressionPatternORM(
                        situation="打招呼",
                        expression="我是B的说法",
                        weight=1.0,
                        last_active_time=30.0,
                        create_time=30.0,
                        group_id="group-a",
                        persona_id="bot-b",
                    ),
                ]
            )
            await session.commit()

        grouped = await db.get_all_expression_patterns()

        assert set(grouped) == {"group-a"}
        assert {row["persona_id"] for row in grouped["group-a"]} == {
            "bot-a",
            "bot-b",
        }
    finally:
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
        collect_message=AsyncMock(return_value=True),
        get_statistics=AsyncMock(return_value={"raw_messages": 11}),
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

    for count in range(11, 22):
        await pipeline.process_learning(
            "group-a",
            "user-a",
            f"第{count}条消息",
            event,
        )
        await asyncio.gather(*spawned)
        spawned.clear()

    assert pipeline.mine_jargon.await_count == 2
    pipeline.mine_jargon.assert_any_await("group-a")
    collector.get_statistics.assert_awaited_once_with("group-a")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_realtime_filter_disabled_does_not_enqueue_filtered_messages():
    config = SimpleNamespace(
        message_min_length=1,
        message_max_length=500,
        enable_expression_patterns=False,
        enable_realtime_llm_filter=False,
    )
    collector = SimpleNamespace(add_filtered_message=AsyncMock())
    analyzer = SimpleNamespace(filter_message_with_llm=AsyncMock(return_value=True))
    persona_manager = SimpleNamespace(
        get_current_persona_description=AsyncMock(return_value="persona")
    )
    learning_stats = SimpleNamespace(filtered_messages=0, style_updates=0)
    processor = RealtimeProcessor(
        plugin_config=config,
        message_collector=collector,
        multidimensional_analyzer=analyzer,
        persona_manager=persona_manager,
        temporary_persona_updater=SimpleNamespace(),
        dialog_analyzer=SimpleNamespace(),
        learning_stats=learning_stats,
        factory_manager=SimpleNamespace(),
        db_manager=SimpleNamespace(),
    )

    await processor.process_message_realtime(
        "group-a",
        "这是一条足够长的实时消息",
        "user-a",
    )

    collector.add_filtered_message.assert_not_awaited()
    persona_manager.get_current_persona_description.assert_not_awaited()
    analyzer.filter_message_with_llm.assert_not_awaited()
    assert learning_stats.filtered_messages == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_realtime_expression_learning_is_batch_gated():
    config = SimpleNamespace(
        message_min_length=1,
        message_max_length=500,
        enable_expression_patterns=True,
        expression_learning_trigger_messages=10,
        expression_learning_min_interval_seconds=0,
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
            persona_id="bot-a",
        )

    assert learner.trigger_learning_for_group.await_count == 2
    assert learner.trigger_learning_for_group.await_args.kwargs["persona_id"] == "bot-a"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_realtime_expression_learning_respects_min_interval():
    config = SimpleNamespace(
        message_min_length=1,
        message_max_length=500,
        enable_expression_patterns=True,
        expression_learning_trigger_messages=1,
        expression_learning_min_interval_seconds=3600,
    )
    collector = SimpleNamespace(
        get_statistics=AsyncMock(return_value={"raw_messages": 10})
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

    await processor.process_expression_learning(
        "group-a",
        "这是用于表达学习频控的消息",
        "user-a",
    )
    await processor.process_expression_learning(
        "group-a",
        "这是用于表达学习频控的消息",
        "user-a",
    )

    assert learner.trigger_learning_for_group.await_count == 1
    assert collector.get_statistics.await_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_realtime_expression_learning_cooldown_is_persona_scoped():
    config = SimpleNamespace(
        message_min_length=1,
        message_max_length=500,
        enable_expression_patterns=True,
        expression_learning_trigger_messages=1,
        expression_learning_min_interval_seconds=3600,
    )
    collector = SimpleNamespace(
        get_statistics=AsyncMock(return_value={"raw_messages": 10})
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

    await processor.process_expression_learning(
        "group-a",
        "这是用于表达学习频控的消息",
        "user-a",
        persona_id="bot-a",
    )
    await processor.process_expression_learning(
        "group-a",
        "这是用于表达学习频控的消息",
        "user-a",
        persona_id="bot-b",
    )

    assert learner.trigger_learning_for_group.await_count == 2
    persona_ids = [
        call.kwargs["persona_id"]
        for call in learner.trigger_learning_for_group.await_args_list
    ]
    assert persona_ids == ["bot-a", "bot-b"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_realtime_expression_learning_creates_review_without_persona_write():
    config = SimpleNamespace(
        message_min_length=1,
        message_max_length=500,
        enable_expression_patterns=True,
        expression_learning_trigger_messages=1,
        expression_learning_min_interval_seconds=0,
    )
    collector = SimpleNamespace(
        get_statistics=AsyncMock(return_value={"raw_messages": 10})
    )
    pattern = SimpleNamespace(
        situation="用户问候",
        expression="元气回应",
        to_dict=lambda: {"situation": "用户问候", "expression": "元气回应"},
    )
    learner = SimpleNamespace(
        trigger_learning_for_group=AsyncMock(return_value=True),
        get_expression_patterns=AsyncMock(return_value=[pattern]),
    )
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
                    "timestamp": time.time() + idx,
                    "platform": "test",
                }
                for idx in range(1, 6)
            ]
        )
    )
    dialog_analyzer = SimpleNamespace(
        generate_few_shots_dialog=AsyncMock(return_value="A: 你好\nB: 我来了"),
        create_style_learning_review_request=AsyncMock(),
    )
    temporary_persona_updater = SimpleNamespace(
        apply_style_as_begin_dialogs=AsyncMock(),
    )
    update_callback = AsyncMock()

    processor = RealtimeProcessor(
        plugin_config=config,
        message_collector=collector,
        multidimensional_analyzer=SimpleNamespace(),
        persona_manager=SimpleNamespace(),
        temporary_persona_updater=temporary_persona_updater,
        dialog_analyzer=dialog_analyzer,
        learning_stats=SimpleNamespace(style_updates=0),
        factory_manager=factory_manager,
        db_manager=db_manager,
    )
    processor.update_system_prompt_callback = update_callback

    await processor.process_expression_learning(
        "group-a",
        "这是用于表达学习审查的消息",
        "user-a",
        persona_id="bot-a",
    )

    learner.trigger_learning_for_group.assert_awaited_once()
    assert learner.trigger_learning_for_group.await_args.kwargs["persona_id"] == "bot-a"
    learner.get_expression_patterns.assert_awaited_once()
    assert learner.get_expression_patterns.await_args.kwargs["persona_id"] == "bot-a"
    dialog_analyzer.create_style_learning_review_request.assert_awaited_once()
    temporary_persona_updater.apply_style_as_begin_dialogs.assert_not_awaited()
    update_callback.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_runtime_context_updates_are_queued_for_review_without_persona_write():
    updater = TemporaryPersonaUpdater.__new__(TemporaryPersonaUpdater)
    updater.db_manager = SimpleNamespace(
        get_pending_persona_learning_reviews=AsyncMock(return_value=[]),
        add_persona_learning_review=AsyncMock(return_value=99),
    )
    updater._get_framework_persona = AsyncMock(
        return_value={"name": "default", "prompt": "Base prompt"}
    )
    updater._update_framework_persona = AsyncMock()

    update_data = {
        "learning_insights": {
            "interaction_patterns": "喜欢短句互动",
            "improvement_suggestions": "少把记忆主题写进固定人格",
            "effective_strategies": "先审查再应用",
            "learning_focus": "记忆重放学习",
        },
        "context_awareness": {
            "current_topic": "MaiBot 记忆主题",
            "recent_focus": "人格污染",
            "dialogue_flow": "话题相关度: 0.8",
        },
    }

    success = await updater.apply_comprehensive_update_to_system_prompt(
        "group-a",
        update_data,
    )

    assert success is True
    updater._update_framework_persona.assert_not_awaited()
    updater.db_manager.add_persona_learning_review.assert_awaited_once()
    review_kwargs = updater.db_manager.add_persona_learning_review.await_args.kwargs
    assert review_kwargs["group_id"] == "group-a"
    assert review_kwargs["original_content"] == "Base prompt"
    assert review_kwargs["new_content"].startswith("Base prompt\n\n")
    assert "MaiBot 记忆主题" in review_kwargs["proposed_content"]
    assert review_kwargs["metadata"]["runtime_context_review"] is True
    assert review_kwargs["metadata"]["review_flow"] == "maibot_web_review_before_apply"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_expression_pattern_save_handles_duplicate_existing_rows(tmp_path):
    config = PluginConfig(
        data_dir=str(tmp_path),
        db_type="sqlite",
        enable_web_interface=False,
    )
    db = SQLAlchemyDatabaseManager(config)

    try:
        assert await db.start() is True
        async with db.get_session() as session:
            session.add_all(
                [
                    ExpressionPatternORM(
                        situation="今晚安排",
                        expression="偷偷刷视频",
                        weight=1.0,
                        last_active_time=10.0,
                        create_time=1.0,
                        group_id="group-a",
                    ),
                    ExpressionPatternORM(
                        situation="今晚安排",
                        expression="偷偷刷视频",
                        weight=3.0,
                        last_active_time=20.0,
                        create_time=2.0,
                        group_id="group-a",
                    ),
                ]
            )
            await session.commit()
            rows_before = (
                await session.execute(
                    select(ExpressionPatternORM).where(
                        ExpressionPatternORM.group_id == "group-a",
                        ExpressionPatternORM.situation == "今晚安排",
                        ExpressionPatternORM.expression == "偷偷刷视频",
                    )
                )
            ).scalars().all()

        assert len(rows_before) == 2
        original_ids = {row.id for row in rows_before}
        strongest_before_id = max(rows_before, key=lambda row: row.weight).id

        learner = ExpressionPatternLearner.__new__(ExpressionPatternLearner)
        learner.db_manager = db

        await learner._save_expression_patterns(
            [
                ExpressionPattern(
                    situation="今晚安排",
                    expression="偷偷刷视频",
                    weight=1.0,
                    last_active_time=30.0,
                    create_time=30.0,
                    group_id="group-a",
                )
            ],
            "group-a",
        )

        async with db.get_session() as session:
            rows = (
                await session.execute(
                    select(ExpressionPatternORM).where(
                        ExpressionPatternORM.group_id == "group-a",
                        ExpressionPatternORM.situation == "今晚安排",
                        ExpressionPatternORM.expression == "偷偷刷视频",
                    )
                )
            ).scalars().all()

        assert len(rows) == 2
        assert {row.id for row in rows} == original_ids
        strongest_after = max(rows, key=lambda row: row.weight)
        assert strongest_after.id == strongest_before_id
        assert strongest_after.weight == 4.0
    finally:
        await db.stop()


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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_learning_service_batch_style_reviews_use_unified_persona_review_path(
    monkeypatch,
):
    calls = []

    class _FakePersonaReviewService:
        def __init__(self, container):
            self.container = container

        async def review_persona_update(self, update_id, action, comment=""):
            calls.append((update_id, action, comment))
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

    result = await service.batch_review_style_learning_reviews([1, "2"], "approve", "batch")

    assert result["success"] is True
    assert result["details"]["success_count"] == 2
    assert result["details"]["failed_count"] == 0
    assert calls == [
        ("style_1", "approve", "batch"),
        ("style_2", "approve", "batch"),
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_learning_service_batch_delete_style_reviews_use_unified_persona_review_path(
    monkeypatch,
):
    calls = []

    class _FakePersonaReviewService:
        def __init__(self, container):
            self.container = container

        async def delete_persona_update(self, update_id):
            calls.append(update_id)
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

    result = await service.batch_delete_style_learning_reviews([1, "2"])

    assert result["success"] is True
    assert result["details"]["success_count"] == 2
    assert result["details"]["failed_count"] == 0
    assert calls == ["style_1", "style_2"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_learning_service_style_review_exposes_detail_fields():
    database_manager = SimpleNamespace(
        get_pending_style_reviews=AsyncMock(
            return_value=[
                {
                    "id": 7,
                    "group_id": "group-a",
                    "description": "提取了 1 个表达模式",
                    "timestamp": 1234567890,
                    "created_at": "2026-05-25T00:00:00",
                    "status": "pending",
                    "learned_patterns": json.dumps(
                        [
                            {
                                "situation": "打招呼",
                                "expression": "我来了",
                                "confidence": 0.9,
                            }
                        ],
                        ensure_ascii=False,
                    ),
                    "few_shots_content": "A: 你好\nB: 我来了",
                }
            ]
        )
    )
    service = LearningService(SimpleNamespace(database_manager=database_manager))

    result = await service.get_style_learning_reviews()
    review = result["reviews"][0]

    assert review["pattern_details"] == [
        {
            "situation": "打招呼",
            "expression": "我来了",
            "weight": None,
            "confidence": 0.9,
        }
    ]
    assert review["few_shot_pairs"] == [{"user": "你好", "bot": "我来了"}]
