"""Style samples must describe human conversations, not the bot's own output."""

import json
import asyncio
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import inspect as sa_inspect, text
from astrbot.api.message_components import At


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
if str(PACKAGE_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT.parent))

from self_learning_EterU.models.orm.expression import ExpressionPattern
from self_learning_EterU.models.orm.learning import StyleLearningReview
from self_learning_EterU.config import PluginConfig
from self_learning_EterU.core.database.engine import DatabaseEngine
from self_learning_EterU.core.factory import QQFilter
from self_learning_EterU.main import SelfLearningPlugin
from self_learning_EterU.repositories.raw_message_repository import RawMessageRepository
from self_learning_EterU.services.analysis.expression_pattern_learner import ExpressionPatternLearner
from self_learning_EterU.services.core_learning.message_collector import MessageCollectorService
from self_learning_EterU.services.core_learning.progressive_learning import ProgressiveLearningService
from self_learning_EterU.services.database.facades.message_facade import MessageFacade
from self_learning_EterU.services.learning.conversation_samples import (
    extract_human_dialog_pairs,
)
from self_learning_EterU.services.learning.dialog_analyzer import DialogAnalyzer
from self_learning_EterU.services.learning.expression_learning import ExpressionLearningModule
from self_learning_EterU.services.learning.message_pipeline import MessagePipeline
from self_learning_EterU.services.learning.realtime_processor import RealtimeProcessor


pytestmark = pytest.mark.unit


def message(sender, text, timestamp=None, **extra):
    result = {"sender_id": sender, "message": text, "group_id": "group-a", **extra}
    if timestamp is not None:
        result["timestamp"] = timestamp
    return result


@pytest.mark.parametrize("same_second", [False, True])
def test_human_dialog_pairs_preserve_context_and_response_user_scope(same_second):
    context = SimpleNamespace(**message(
        "alice", "The build finally finished!", datetime.fromtimestamp(1_700_000_000),
        message_id="z-platform-id", id=101,
    ))
    response = message(
        "bob", "Ship it before it changes its mind.",
        1_700_000_000 if same_second else 1_700_000_010,
        message_id="a-platform-id", id=102, reply_to="z-platform-id",
    )

    pairs = extract_human_dialog_pairs([response, context], "group-a", user_id="bob")

    assert [(p["situation"], p["expression"]) for p in pairs] == [
        (context.message, response["message"])
    ]
    assert pairs[0]["sender_id"] == "bob"
    assert extract_human_dialog_pairs([context, response], "group-a", user_id="alice") == []


@pytest.mark.parametrize("barrier", [
    message("BoT", "Here is the bot's response."),
    message("robot-account", "Bot content", is_bot=True),
    message("robot-account", "Bot content", metadata={"is_bot": True}),
    message("robot-account", "Bot content", role="assistant"),
    message("robot-account", "Bot content", platform="bot"),
    message("alice", "An explicit question to the bot", is_bot_target=True),
    message("system", "System message"),
    message("alice", "/help"),
    message("alice", "[image]"),
    message("outsider", "Foreign group content", group_id="group-b"),
    {"message": "Missing sender", "group_id": "group-a"},
])
def test_excluded_messages_are_boundaries_not_bridges(barrier):
    timeline = [
        message("alice", "Why is the build taking so long?"),
        barrier,
        message("bob", "It must be compiling the universe."),
    ]

    assert extract_human_dialog_pairs(timeline, "group-a") == []


@pytest.mark.parametrize("response", [
    message("alice", "Another message from the same user.", 105),
    message("bob", "A reply after a long unrelated gap.", 401),
    message("bob", "This answers someone else instead.", 105, reply_to="other"),
])
def test_human_pairs_need_two_speakers_and_bounded_matching_context(response):
    context = message("alice", "The build finally finished!", 100, message_id="q1")
    assert extract_human_dialog_pairs([context, response], "group-a") == []


@pytest.fixture
def expression_module():
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

    db = SimpleNamespace(
        get_session=get_session,
        get_recent_bot_responses=Mock(side_effect=AssertionError("Never fetch bot replies")),
    )
    return ExpressionLearningModule(db), added


@pytest.mark.asyncio
@pytest.mark.parametrize("analysis", [
    {"style_analysis": {"tone": "informal"}},
    {"expression_patterns": [{"situation": "Model prompt", "expression": "Bot imitation"}]},
    SimpleNamespace(data=None),
])
async def test_basic_style_saves_real_human_patterns_without_model_pairs(expression_module, analysis):
    module, added = expression_module
    timeline = [
        message("alice", "The build finally finished!", 100),
        message("bob", "Ship it before it changes its mind.", 110),
    ]

    await module.save_style_learning_record("group-a", analysis, timeline, persona_id="persona-a")

    patterns = [item for item in added if isinstance(item, ExpressionPattern)]
    review = next(item for item in added if isinstance(item, StyleLearningReview))
    assert [(p.situation, p.expression, p.persona_id, p.group_id) for p in patterns] == [
        (timeline[0]["message"], timeline[1]["message"], "persona-a", "group-a")
    ]
    assert review.status == "pending"
    assert len(json.loads(review.learned_patterns)) == 1
    assert "Bot imitation" not in review.few_shots_content
    assert timeline[1]["message"] in review.few_shots_content


@pytest.mark.asyncio
async def test_basic_style_does_not_learn_or_bridge_bot_responses(expression_module):
    module, added = expression_module
    timeline = [
        message("alice", "Why is the build taking so long?", 100),
        message("bot", "My generated answer must never be learned.", 105),
        message("bob", "It must be compiling the universe.", 110),
    ]

    await module.save_style_learning_record("group-a", {}, timeline)

    assert not any(isinstance(item, ExpressionPattern) for item in added)
    review = next(item for item in added if isinstance(item, StyleLearningReview))
    assert json.loads(review.learned_patterns) == []
    assert timeline[1]["message"] not in review.few_shots_content
    assert await module.merge_bot_messages_for_pairs("group-a", timeline) == timeline


@pytest.mark.asyncio
async def test_pattern_persistence_cannot_override_group_or_persona(expression_module):
    module, added = expression_module
    await module.save_expression_patterns("group-a", [
        {"situation": "A human question", "expression": "A human answer", "persona_id": "other"},
        {"situation": "Foreign context", "expression": "Foreign answer", "group_id": "group-b"},
    ], persona_id="persona-a")

    assert len(added) == 1
    assert (added[0].group_id, added[0].persona_id, added[0].user_id) == (
        "group-a", "persona-a", None
    )


@pytest.mark.asyncio
async def test_explicit_patterns_without_source_messages_remain_supported(expression_module):
    module, added = expression_module
    await module.save_style_learning_record("group-a", {"expression_patterns": [
        {"situation": "A human question", "expression": "A human answer"},
        {"situation": "Wrong group", "expression": "Do not import", "group_id": "group-b"},
    ]}, [], persona_id="persona-a")

    review = next(item for item in added if isinstance(item, StyleLearningReview))
    assert review.status == "pending"
    assert [pattern["expression"] for pattern in json.loads(review.learned_patterns)] == [
        "A human answer"
    ]


@pytest.mark.asyncio
async def test_dialog_analyzer_generates_only_human_few_shots():
    analyzer = DialogAnalyzer(None, None)
    timeline = []
    for index in range(4):
        timeline.extend([
            message("alice", f"When will build number {index} finish?", index * 20),
            message("bob", f"After coffee number {index}, of course.", index * 20 + 1),
            message("bot", "Generated bot response, not a style sample.", index * 20 + 2),
        ])

    result = await analyzer.generate_few_shots_dialog("group-a", timeline)

    assert "After coffee number 0" in result
    assert "Generated bot response" not in result
    assert result.count("\nB:") == 4
    assert not await analyzer.is_valid_dialog_pair(timeline[0], timeline[2], "group-a")


@pytest.mark.asyncio
@pytest.mark.parametrize("user_scoped", [False, True])
async def test_realtime_short_chat_review_preserves_response_scope_and_bot_boundaries(user_scoped):
    timeline = [
        message("alice", "Go?", 100),
        message("bob", "Yep!", 101),
        message("bot", "NEVER LEARN THIS", 102),
        message("alice", "Now?", 103),
        message("carol", "Soon", 104),
        message("bob", "Race?", 105),
        message("carol", "Done", 106),
    ]
    # Exercise the real extraction rule without persistence or singleton state.
    source_learner = object.__new__(ExpressionPatternLearner)
    learned = []

    async def learn(group_id, rows, *, persona_id, user_id):
        assert rows == timeline
        learned.extend(source_learner._extract_few_shot_pairs(
            rows, group_id, persona_id=persona_id, user_id=user_id,
        ))
        return bool(learned)

    learner = SimpleNamespace(
        trigger_learning_for_group=AsyncMock(side_effect=learn),
        get_expression_patterns=AsyncMock(side_effect=lambda *args, **kwargs: learned),
    )
    dialog = SimpleNamespace(
        create_style_learning_review_request=AsyncMock(),
        generate_few_shots_dialog=AsyncMock(side_effect=AssertionError("Use learned samples")),
    )
    processor = RealtimeProcessor(
        plugin_config=SimpleNamespace(
            message_min_length=1, message_max_length=500,
            enable_expression_patterns=True, enable_expression_user_scope=user_scoped,
            expression_learning_trigger_messages=1,
            expression_learning_min_interval_seconds=0,
        ),
        message_collector=SimpleNamespace(get_statistics=AsyncMock(return_value={"raw_messages": 7})),
        multidimensional_analyzer=None, persona_manager=None, temporary_persona_updater=None,
        dialog_analyzer=dialog, learning_stats=SimpleNamespace(style_updates=0),
        factory_manager=None,
        db_manager=SimpleNamespace(get_recent_raw_messages=AsyncMock(return_value=timeline)),
    )
    processor._expression_learner = learner

    await processor.process_expression_learning("group-a", "Yep!", "bob", persona_id="persona-a")

    dialog.create_style_learning_review_request.assert_awaited_once()
    group_id, reviewed, content = dialog.create_style_learning_review_request.await_args.args
    assert group_id == "group-a" and reviewed == learned
    assert "NEVER LEARN THIS" not in content
    assert all(pattern.persona_id == "persona-a" for pattern in learned)
    assert "B: Yep!" in content
    if user_scoped:
        assert all(pattern.user_id == "bob" for pattern in learned)
        assert "B: Soon" not in content and "B: Done" not in content
    else:
        assert all(pattern.user_id is None for pattern in learned)
        assert "B: Soon" in content and "B: Done" in content


@pytest.mark.asyncio
async def test_progressive_source_timeline_respects_blacklist_and_current_persona(expression_module):
    module, added = expression_module
    service = ProgressiveLearningService.__new__(ProgressiveLearningService)
    service.expression_learning = module
    service.persona_learning = SimpleNamespace(apply_persona_learning=AsyncMock())
    service.config = SimpleNamespace(target_blacklist=["blocked"])
    service._group_sessions = {}
    timeline = [
        message("alice", "A question before the interruption", 100),
        message("blocked", "Do not learn me or bridge over me", 101),
        message("bob", "An answer with missing context", 102),
        message("alice", "A separate later question", 1000),
        message("bob", "A separate later answer", 1001),
    ]
    filtered_messages = [timeline[0], timeline[2], timeline[3], timeline[4]]

    await service._apply_learning_updates(
        "group-a", {}, filtered_messages, current_persona={"persona_id": "persona-a"},
        source_messages=timeline,
    )

    patterns = [item for item in added if isinstance(item, ExpressionPattern)]
    assert [(pattern.situation, pattern.expression, pattern.persona_id) for pattern in patterns] == [
        (timeline[3]["message"], timeline[4]["message"], "persona-a")
    ]
    assert timeline[1]["message"] == "Do not learn me or bridge over me"
    assert service.persona_learning.apply_persona_learning.await_args.args[2] is filtered_messages


@pytest.mark.parametrize("wake_flag, mentions, expected", [
    (True, [], True),
    (False, [At(qq="bot-account")], True),
    (False, [At(qq="human-account"), At(qq="all")], False),
    (Mock(), [], False),
])
def test_bot_target_detection_uses_explicit_wake_or_bot_mention(wake_flag, mentions, expected):
    event = SimpleNamespace(
        is_at_or_wake_command=wake_flag, is_wake=True,
        get_self_id=lambda: "bot-account",
    )
    assert MessagePipeline._is_bot_target(event, mentions) is expected


@pytest.mark.asyncio
async def test_bot_target_migrates_legacy_rows_and_survives_collection(tmp_path):
    engine = DatabaseEngine(f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}")
    config = PluginConfig(data_dir=str(tmp_path), db_type="sqlite", enable_web_interface=False)
    db = MessageFacade(engine, config)
    collector = MessageCollectorService(config, None, db)
    try:
        async with engine.engine.begin() as connection:
            await connection.execute(text("""
                CREATE TABLE raw_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender_id VARCHAR(255) NOT NULL, sender_name VARCHAR(255),
                    sender_qq VARCHAR(32), message TEXT NOT NULL,
                    group_id VARCHAR(255), timestamp BIGINT NOT NULL,
                    platform VARCHAR(100), message_id VARCHAR(255), reply_to VARCHAR(255),
                    created_at BIGINT NOT NULL, processed BOOLEAN
                )
            """))
            await connection.execute(text("""
                INSERT INTO raw_messages
                    (sender_id, message, group_id, timestamp, created_at, processed)
                VALUES ('alice', 'An older human message', 'group-a', 100, 100, 0)
            """))

        await engine.create_tables(enable_auto_migration=True)
        assert await collector.collect_message(message(
            "bob", "An explicit question to the bot", 101,
            is_bot_target=True, message_id="target-message", reply_to="original",
        ))
        collector._message_cache.append(message(
            "carol", "A cached explicit question to the bot", 102, is_bot_target=True,
        ))
        await collector._flush_message_cache()
        async with db.get_session() as session:
            saved = await RawMessageRepository(session).save(message(
                "dave", "A repository-saved bot question", 103, is_bot_target=True,
            ))
            assert saved.is_bot_target is True
        async with engine.engine.begin() as connection:
            columns = await connection.run_sync(
                lambda conn: {column["name"] for column in sa_inspect(conn).get_columns("raw_messages")}
            )
        assert {"is_bot_target", "is_style_context"} <= columns

        pending = await db.get_unprocessed_messages(group_id="group-a")
        recent = list(reversed(await db.get_recent_raw_messages("group-a")))
        assert [row["is_bot_target"] for row in pending] == [False, True, True, True]
        assert [row["is_bot_target"] for row in recent] == [False, True, True, True]
        assert not any(row["is_style_context"] for row in recent)
        assert recent[1]["message"] == "An explicit question to the bot"
        assert (recent[1]["message_id"], recent[1]["reply_to"]) == ("target-message", "original")
        assert extract_human_dialog_pairs(recent, "group-a") == []
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_style_context_getter_keeps_target_response_and_blacklist_boundaries(tmp_path):
    engine = DatabaseEngine(f"sqlite:///{(tmp_path / 'context.db').as_posix()}")
    config = PluginConfig(
        data_dir=str(tmp_path), db_type="sqlite", enable_web_interface=False,
        target_qq_list=["alice"], target_blacklist=["blocked"],
    )
    db = MessageFacade(engine, config)
    collector = MessageCollectorService(config, None, db)
    try:
        await engine.create_tables(enable_auto_migration=True)
        timeline = [
            message("bob", "A surrounding human question", 100, is_style_context=True),
            message("alice", "The target user's answer", 101),
            message("blocked", "A historical blocked interruption", 102),
            message("alice", "An answer without matching context", 103),
            message("bob", "A second question saved before whitelist changed", 104),
            message("alice", "Another target answer", 105),
        ]
        for row in timeline:
            assert await collector.collect_message(row)
        sources = await db.get_style_learning_messages("group-a")
        assert len(sources) == 6 and sources[2]["message"] == ""
        assert [row["is_style_context"] for row in sources] == [True, False, True, False, True, False]
        assert [(pair["situation"], pair["expression"]) for pair in extract_human_dialog_pairs(sources, "group-a")] == [
            (timeline[0]["message"], timeline[1]["message"]),
            (timeline[4]["message"], timeline[5]["message"]),
        ]
        assert len(await db.get_recent_raw_messages("group-a")) == 4
        assert len(await db.get_unprocessed_messages(group_id="group-a")) == 4
        assert (await db.get_group_messages_statistics("group-a"))["raw_messages"] == 5
        latest = await db.get_style_learning_messages("group-a", limit=2, start_time=101, end_time=104)
        assert [row["timestamp"] for row in latest] == [103, 104]
        assert await collector.collect_message(message("bob", "Before command", 106, is_style_context=True))
        assert await collector.collect_message(message("alice", "", 107, is_style_context=True))
        assert await collector.collect_message(message("alice", "After command", 108))
        command_gap = await db.get_style_learning_messages("group-a", start_time=106)
        assert command_gap[1]["message"] == ""
        assert extract_human_dialog_pairs(command_gap, "group-a") == []
        assert not await collector.collect_message(message("alice", "/help", 109))
        config.target_qq_list = ["bob"]
        assert not (await db.get_style_learning_messages("group-a"))[0]["is_style_context"]
        config.target_qq_list = []
        assert not any(row["is_style_context"] for row in await db.get_style_learning_messages("group-a"))
        config.target_qq_list = ["group_group-a"]
        assert not (await db.get_style_learning_messages("group-a"))[-2]["is_style_context"]
        config.target_blacklist = ["group_group-a"]
        assert await db.get_style_learning_messages("group-a") == []
    finally:
        await engine.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("sender_id, group_id, text_value, targets, captures", [
    ("bob", "group-a", "A surrounding human question", ["alice"], 1),
    ("blocked", "group-a", "Excluded text", ["alice"], 0),
    ("bob", "", "A private message", ["alice"], 0),
    ("alice", "group-a", "/help", ["alice"], 1),
    ("bob", "other-group", "Outside a group-only target list", ["group_allowed"], 0),
])
async def test_non_target_capture_only_collects_group_style_context(sender_id, group_id, text_value, targets, captures):
    pipeline = MessagePipeline.__new__(MessagePipeline)
    pipeline._message_collector = SimpleNamespace(collect_message=AsyncMock(return_value=True))
    pipeline.process_affection = AsyncMock()
    pipeline.process_learning = AsyncMock()
    plugin = SelfLearningPlugin.__new__(SelfLearningPlugin)
    plugin._shutting_down = False
    plugin.db_manager = SimpleNamespace(is_ready=True)
    plugin.plugin_config = SimpleNamespace(
        enable_message_capture=True, enable_affection_system=True,
        target_blacklist=["blocked"], target_qq_list=targets,
    )
    plugin.qq_filter = QQFilter(targets, ["blocked"])
    plugin._pipeline = pipeline
    plugin._log_message_capture_diag = Mock()
    pending = []
    plugin._track_task = pending.append
    event = SimpleNamespace(
        get_message_str=lambda: text_value,
        get_group_id=lambda: group_id, get_sender_id=lambda: sender_id,
        get_sender_name=lambda: sender_id, get_self_id=lambda: "bot-id",
        get_platform_name=lambda: "test", get_messages=lambda: [],
        message_obj=SimpleNamespace(message_id="source-id"), is_at_or_wake_command=True,
    )

    await plugin.on_message(event)
    if pending:
        await asyncio.gather(*pending)

    assert pipeline._message_collector.collect_message.await_count == captures
    if captures:
        payload = pipeline._message_collector.collect_message.await_args.args[0]
        assert payload["is_style_context"] is True
        assert payload["message_id"] == "source-id" and payload["is_bot_target"] is True
        assert payload["message"] == ("" if text_value == "/help" else text_value)
    pipeline.process_learning.assert_not_awaited()
    pipeline.process_affection.assert_not_awaited()
