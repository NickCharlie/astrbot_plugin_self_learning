"""Regression tests for user-configurable learning ignore regexes (issue #315).

媒体解析类插件（如 B 站 BV 解析）会把卡片文本作为 bot 出站消息入库，用户发送的
裸引用（BV 号 / b23.tv 链接）也会进入采集。自定义忽略正则让用户按需把这两类
内容挡在学习样本之外。
"""

from pathlib import Path
import sys

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from self_learning_EterU.config import PluginConfig  # noqa: E402
from self_learning_EterU.services.core_learning.message_collector import (  # noqa: E402
    MessageCollectorService,
)
from self_learning_EterU.services.learning.sample_filter import (  # noqa: E402
    configure_learning_ignore_patterns,
    matches_learning_ignore_pattern,
    should_ignore_learning_sample,
)

CARD_TEXT = "🎬 标题：测试视频 / 👤 UP主：某人 / 👍 点赞：100"


@pytest.fixture(autouse=True)
def _reset_ignore_patterns():
    configure_learning_ignore_patterns(None)
    yield
    configure_learning_ignore_patterns(None)


@pytest.mark.unit
def test_no_patterns_keeps_media_parser_output_learnable():
    assert should_ignore_learning_sample(CARD_TEXT, sender_id="bot", is_bot=True) is False
    assert should_ignore_learning_sample("BV1RA4i6cEBE", sender_id="u1") is False


@pytest.mark.unit
def test_custom_pattern_ignores_bot_card_and_inbound_bv():
    accepted = configure_learning_ignore_patterns(
        [r"^🎬 标题：", r"\bBV[0-9A-Za-z]{10}\b"]
    )

    assert accepted == 2
    assert should_ignore_learning_sample(CARD_TEXT, sender_id="bot", is_bot=True) is True
    assert should_ignore_learning_sample("看这个 BV1RA4i6cEBE", sender_id="u1") is True
    assert should_ignore_learning_sample("今天好开心", sender_id="u1") is False
    assert should_ignore_learning_sample("普通回复", sender_id="bot", is_bot=True) is False


@pytest.mark.unit
def test_invalid_pattern_is_skipped_without_disabling_valid_ones():
    accepted = configure_learning_ignore_patterns(["[unclosed", r"b23\.tv"])

    assert accepted == 1
    assert matches_learning_ignore_pattern("https://b23.tv/abc") is True
    # 无效正则被跳过，不应把普通文本误判为忽略样本
    assert should_ignore_learning_sample("[unclosed", sender_id="u1") is False


@pytest.mark.unit
def test_string_patterns_are_split_by_line():
    assert configure_learning_ignore_patterns("^卡片：\nBV\\d+") == 2
    assert matches_learning_ignore_pattern("卡片：今天") is True
    assert matches_learning_ignore_pattern("BV123") is True


@pytest.mark.unit
def test_overflow_pattern_is_skipped_without_aborting_startup():
    accepted = configure_learning_ignore_patterns(
        ["a{999999999999999999999}", r"b23\.tv"]
    )

    assert accepted == 1
    assert matches_learning_ignore_pattern("https://b23.tv/abc") is True


@pytest.mark.unit
def test_pattern_matching_is_bounded_to_message_prefix():
    configure_learning_ignore_patterns([r"X{10}"])

    assert matches_learning_ignore_pattern("a" * 2000 + "X" * 10) is False
    assert matches_learning_ignore_pattern("a" * 10 + "X" * 10) is True


@pytest.mark.unit
def test_plugin_config_normalizes_patterns_without_splitting_commas():
    config = PluginConfig.create_from_config(
        {
            "Target_Settings": {
                "learning_ignore_patterns": [" a{1,3}b ", "", "a{1,3}b", None],
            }
        }
    )

    assert config.learning_ignore_patterns == ["a{1,3}b"]


class _DatabaseStub:
    def __init__(self):
        self.saved = []

    async def save_raw_message(self, message):
        self.saved.append(message)
        return len(self.saved)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_message_collector_drops_matching_inbound_message():
    configure_learning_ignore_patterns([r"\bBV[0-9A-Za-z]{10}\b"])
    config = PluginConfig()
    database = _DatabaseStub()
    collector = MessageCollectorService(config, context=None, database_manager=database)

    dropped = await collector.collect_message(
        {"sender_id": "u1", "message": "看 BV1RA4i6cEBE", "timestamp": 1.0}
    )
    kept = await collector.collect_message(
        {"sender_id": "u1", "message": "今天好开心", "timestamp": 2.0}
    )

    assert dropped is False
    assert kept is True
    assert [message.message for message in database.saved] == ["今天好开心"]
