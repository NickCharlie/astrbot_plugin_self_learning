"""回归测试：学习黑名单在取数与采集层统一生效（issue #284）。

issue #284：``target_blacklist`` 只在入站采集时被 ``QQFilter`` 用一次，批量/风格/
表达/黑话学习直接从 ``raw_messages``、``filtered_messages`` 取数，导致黑名单账号的
历史消息继续被学习（``filtered_messages.filter_reason`` 全为
``style_learning_no_filter``）。修复后黑名单在取数层排除，配置改动立即对旧数据生效。
"""

import asyncio
import sys
import time
from pathlib import Path
from types import SimpleNamespace

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

import pytest  # noqa: E402

from self_learning_EterU.config import PluginConfig, split_learning_blacklist  # noqa: E402
from self_learning_EterU.core.factory import QQFilter  # noqa: E402
from self_learning_EterU.main import SelfLearningPlugin  # noqa: E402
from self_learning_EterU.services.core_learning.progressive_learning import (  # noqa: E402
    ProgressiveLearningService,
)
from self_learning_EterU.services.database.sqlalchemy_database_manager import (  # noqa: E402
    SQLAlchemyDatabaseManager,
)
from self_learning_EterU.services.learning.sample_filter import (  # noqa: E402
    filter_blacklisted_messages,
)


def _config(tmp_path, blacklist):
    return PluginConfig(
        data_dir=str(tmp_path),
        db_type="sqlite",
        enable_web_interface=False,
        target_blacklist=list(blacklist),
    )


def _raw(group_id, sender_id, message, **extra):
    data = {
        "sender_id": sender_id,
        "sender_name": sender_id,
        "message": message,
        "group_id": group_id,
        "timestamp": time.time(),
        "platform": "test",
    }
    data.update(extra)
    return data


@pytest.mark.unit
def test_split_learning_blacklist_separates_senders_and_groups():
    senders, groups = split_learning_blacklist(
        ["2339669671", " group_10001 ", "", None, "2339669671", "group_10002"]
    )

    assert senders == ["2339669671"]
    assert groups == ["10001", "10002"]


@pytest.mark.unit
def test_split_learning_blacklist_matches_qqfilter_semantics():
    """取数层与采集层必须同一套黑名单语义，否则换个入口就漏过滤。"""
    blacklist = ["blocked-user", "group_20002"]
    qq_filter = QQFilter([], blacklist)

    assert qq_filter.is_blacklisted("blocked-user", "111") is True
    assert qq_filter.is_blacklisted("other-user", "20002") is True
    assert qq_filter.is_blacklisted("other-user", "111") is False
    assert split_learning_blacklist(blacklist) == (["blocked-user"], ["20002"])


@pytest.mark.unit
def test_filter_blacklisted_messages_handles_dict_and_objects():
    messages = [
        _raw("group-a", "blocked-user", "黑名单用户消息"),
        _raw("group-b", "user-b", "正常用户消息"),
        SimpleNamespace(sender_id="blocked-user", group_id="group-a"),
    ]

    kept = filter_blacklisted_messages(messages, ["blocked-user"])

    assert len(kept) == 1
    assert kept[0]["sender_id"] == "user-b"


@pytest.mark.unit
def test_bot_self_messages_are_excluded_without_manual_blacklist():
    """issue #284 期望 3：bot 自身账号默认排除，不依赖用户手动拉黑。"""
    plugin = SelfLearningPlugin
    event = SimpleNamespace(get_self_id=lambda: "bot-a")

    assert plugin._is_self_message(object(), event, "bot-a") is True
    assert plugin._is_self_message(object(), event, "user-a") is False
    # 平台未提供 self_id 时不得误伤正常用户
    assert plugin._is_self_message(object(), SimpleNamespace(), "user-a") is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_learning_reads_exclude_blacklisted_senders(tmp_path):
    """raw_messages 里已有黑名单账号，取数层必须不再返回（issue #284 核心）。"""
    config = _config(tmp_path, ["blocked-user"])
    db = SQLAlchemyDatabaseManager(config)

    try:
        assert await db.start() is True
        for sender, message in (
            ("blocked-user", "黑名单账号的历史消息"),
            ("user-b", "正常账号的历史消息"),
        ):
            assert await db.save_raw_message(_raw("group-a", sender, message)) > 0

        unprocessed = await db.get_unprocessed_messages(limit=10, group_id="group-a")
        recent = await db.get_recent_raw_messages("group-a", limit=10)
        timerange = await db.get_messages_by_group_and_timerange(
            "group-a", 0, int(time.time()) + 10, limit=10
        )

        assert [row["sender_id"] for row in unprocessed] == ["user-b"]
        assert [row["sender_id"] for row in recent] == ["user-b"]
        assert [row["sender_id"] for row in timerange] == ["user-b"]

        # 配置变更后立即对旧数据生效，无需清洗历史
        config.target_blacklist = ["user-b"]
        unprocessed = await db.get_unprocessed_messages(limit=10, group_id="group-a")
        assert [row["sender_id"] for row in unprocessed] == ["blocked-user"]
    finally:
        await db.stop()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_learning_reads_keep_rows_without_group(tmp_path):
    """group_id 为 NULL 的历史行不得被 NOT IN 语义误伤。"""
    config = _config(tmp_path, ["group_99999"])
    db = SQLAlchemyDatabaseManager(config)

    try:
        assert await db.start() is True
        async with db.get_session() as session:
            from self_learning_EterU.models.orm.message import RawMessage

            session.add(
                RawMessage(
                    sender_id="user-legacy",
                    message="群组归属不明的历史消息",
                    group_id=None,
                    timestamp=int(time.time()),
                    created_at=int(time.time()),
                    processed=False,
                )
            )
            await session.commit()

        unprocessed = await db.get_unprocessed_messages(limit=10)

        assert len(unprocessed) == 1
        assert unprocessed[0]["group_id"] is None
    finally:
        await db.stop()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_filtered_message_learning_reads_exclude_blacklisted_senders(tmp_path):
    config = _config(tmp_path, ["blocked-user"])
    db = SQLAlchemyDatabaseManager(config)

    try:
        assert await db.start() is True
        for sender in ("blocked-user", "user-b"):
            await db.add_filtered_message(
                {
                    "message": f"{sender} 的筛选消息",
                    "sender_id": sender,
                    "group_id": "group-a",
                    "timestamp": time.time(),
                    "confidence": 0.9,
                    "filter_reason": "style_learning_no_filter",
                }
            )

        for_learning = await db.get_filtered_messages_for_learning(limit=10)
        recent = await db.get_recent_filtered_messages("group-a", limit=10)

        assert [row["sender_id"] for row in for_learning] == ["user-b"]
        assert [row["sender_id"] for row in recent] == ["user-b"]
    finally:
        await db.stop()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_blacklisted_group_is_excluded_from_learning_reads(tmp_path):
    config = _config(tmp_path, ["group_20002"])
    db = SQLAlchemyDatabaseManager(config)

    try:
        assert await db.start() is True
        await db.save_raw_message(_raw("group-a", "user-a", "未黑名单群组消息"))
        await db.save_raw_message(_raw("20002", "user-a", "黑名单群组消息"))

        unprocessed = await db.get_unprocessed_messages(limit=10)

        assert [row["group_id"] for row in unprocessed] == ["group-a"]
    finally:
        await db.stop()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_progressive_learning_funnel_drops_blacklisted_messages(tmp_path):
    """issue #284 点名的 _filter_messages_with_context：不再照单全收。"""
    config = _config(tmp_path, ["blocked-user"])
    service = SimpleNamespace(config=config)
    messages = [
        _raw("group-a", "blocked-user", "黑名单账号的历史消息"),
        _raw("group-a", "user-b", "正常账号的历史消息"),
    ]

    kept = await ProgressiveLearningService._filter_messages_with_context(
        service, messages
    )

    assert [row["sender_id"] for row in kept] == ["user-b"]
    assert kept[0]["filter_reason"] == "style_learning_no_filter"
