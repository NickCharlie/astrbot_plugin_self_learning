"""
Unit tests for GuardrailsManager JSON parsing / repair (issue #259)

Covers the failure-classification behavior of validate_and_clean_json:
- empty LLM responses
- plain-text responses without any JSON structure
- thinking-tag wrapped JSON (reasoning models)
- markdown / single-quote / trailing-comma recovery
- truncated JSON recovered via optional json-repair fallback
- Pydantic validation failures surfaced through parse_json_direct
- goal manager short-circuiting on empty LLM responses
"""
import importlib.util
import json
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

import utils.guardrails_manager as guardrails_module
from utils.guardrails_manager import (
    GuardrailsManager,
    GoalAnalysisResult,
    ConversationIntentAnalysis,
)

# 测试经由 junction 包名导入，保证包内相对导入（from ..response 等）可解析
from self_learning_EterU.services.quality.conversation_goal_manager import ConversationGoalManager

JSON_REPAIR_AVAILABLE = importlib.util.find_spec("json_repair") is not None


@pytest.fixture
def mock_logger(monkeypatch):
    """替换模块级 logger，便于断言失败分类日志（AstrBot logger 不传播到 root，caplog 抓不到）。"""
    mock = MagicMock()
    monkeypatch.setattr(guardrails_module, "logger", mock)
    return mock


def warning_messages(mock_logger) -> list:
    return [c.args[0] for c in mock_logger.warning.call_args_list if c.args]


@pytest.fixture
def manager(mock_logger) -> GuardrailsManager:
    return GuardrailsManager(max_reasks=0)


@pytest.mark.unit
@pytest.mark.utils
class TestValidateAndCleanJsonEmpty:
    """空响应必须返回 None 且不抛异常（issue #259：区分空响应）。"""

    def test_none_input(self, manager):
        assert manager.validate_and_clean_json(None) is None

    def test_empty_string(self, manager):
        assert manager.validate_and_clean_json("") is None

    def test_whitespace_only(self, manager, mock_logger):
        assert manager.validate_and_clean_json("   \n  ") is None
        assert any("清理后的响应为空" in m for m in warning_messages(mock_logger))


@pytest.mark.unit
@pytest.mark.utils
class TestValidateAndCleanJsonSuccess:
    """常规成功路径不受重构影响。"""

    def test_plain_json(self, manager):
        assert manager.validate_and_clean_json('{"a": 1}') == {"a": 1}

    def test_markdown_wrapped(self, manager):
        text = '```json\n{"goal_type": "casual_chat"}\n```'
        assert manager.validate_and_clean_json(text) == {"goal_type": "casual_chat"}

    def test_prose_around_json(self, manager):
        text = '好的，分析结果如下：\n{"goal_type": "casual_chat", "topic": "日常"}\n请查收。'
        assert manager.validate_and_clean_json(text, expected_type="object")["topic"] == "日常"

    def test_single_quotes_and_trailing_comma(self, manager):
        text = "{'goal_type': 'casual_chat',}"
        assert manager.validate_and_clean_json(text) == {"goal_type": "casual_chat"}

    def test_thinking_tag_wrapped_json(self, manager):
        """推理型模型的 <think> 内容不应干扰 JSON 提取。"""
        text = '<think>用户在打招呼，应该选择闲聊目标。</think>\n{"goal_type": "casual_chat", "topic": "寒暄"}'
        parsed = manager.validate_and_clean_json(text, expected_type="object")
        assert parsed == {"goal_type": "casual_chat", "topic": "寒暄"}

    def test_thinking_tag_only(self, manager, mock_logger):
        """剥离思考标签后为空应归类为“清理后为空”，而不是 JSON 损坏。"""
        assert manager.validate_and_clean_json("<think>只有思考内容</think>") is None
        assert any("清理后的响应为空" in m for m in warning_messages(mock_logger))


@pytest.mark.unit
@pytest.mark.utils
class TestValidateAndCleanJsonFailureClassification:
    """失败必须按类别记录（issue #259 预期行为）。"""

    def test_plain_text_reports_missing_json_structure(self, manager, mock_logger):
        """纯文本回复：无花括号结构时必须明确提示“未找到 JSON 结构”，并附预览。"""
        assert manager.validate_and_clean_json("抱歉，我无法完成这个分析任务。", expected_type="object") is None

        messages = warning_messages(mock_logger)
        assert any("未找到 JSON 结构" in m for m in messages)
        assert any("响应预览" in m for m in messages)

    def test_corrupted_json_reports_parse_failure_with_preview(self, manager, mock_logger):
        """有 JSON 结构但损坏时保留“JSON 解析失败”分类，且预览升到 warning 可见。"""
        text = '{"goal_type": "casual_chat", "topic": "日常", "reasoning": "x",,}'
        result = manager.validate_and_clean_json(text, expected_type="object")

        messages = warning_messages(mock_logger)
        assert any("JSON 解析失败" in m for m in messages)
        assert any("响应预览" in m and "goal_type" in m for m in messages)
        # 常规正则修不了 ",,"，最终由 json-repair 兜底或返回 None
        if result is not None:
            assert isinstance(result, dict)

    def test_json_repair_fallback_returns_none_when_unavailable(self, monkeypatch):
        """未安装 json-repair 时兜底必须静默跳过（sys.modules 置 None 触发 ImportError）。"""
        monkeypatch.setitem(sys.modules, "json_repair", None)
        assert GuardrailsManager._json_repair_fallback('{"goal_type": "emotion') is None

    @pytest.mark.skipif(not JSON_REPAIR_AVAILABLE, reason="json-repair 未安装")
    def test_truncated_json_recovered_by_json_repair(self, manager):
        """截断的 JSON（如 max_tokens 提前截断）由 json-repair 兜底恢复。"""
        parsed = manager.validate_and_clean_json('{"goal_type": "emotional_sup', expected_type="object")
        assert parsed is not None
        assert parsed.get("goal_type", "").startswith("emotional_sup")

    @pytest.mark.skipif(JSON_REPAIR_AVAILABLE, reason="json-repair 已安装，不适用")
    def test_truncated_json_returns_none_without_json_repair(self, manager):
        assert manager.validate_and_clean_json('{"goal_type": "emotional_sup', expected_type="object") is None


@pytest.mark.unit
@pytest.mark.utils
class TestParseJsonDirect:
    """parse_json_direct 组合解析与 Pydantic 校验。"""

    def test_valid_goal_analysis(self, manager):
        text = '{"goal_type": "emotional_support", "topic": "工作压力", "confidence": 0.9}'
        result = manager.parse_json_direct(text, model_class=GoalAnalysisResult)
        assert isinstance(result, GoalAnalysisResult)
        assert result.goal_type == "emotional_support"

    def test_plain_text_returns_none(self, manager):
        assert manager.parse_json_direct("今天天气不错", model_class=GoalAnalysisResult) is None

    def test_pydantic_validation_failure_returns_none(self, manager):
        """合法 JSON 但字段非法（goal_type 超长）→ None，属于字段校验失败类别。"""
        text = json.dumps({"goal_type": "a" * 51, "topic": "test"})
        assert manager.parse_json_direct(text, model_class=GoalAnalysisResult) is None

    def test_intent_analysis_missing_fields_use_defaults(self, manager):
        result = manager.parse_json_direct('{"reasoning": "ok"}', model_class=ConversationIntentAnalysis)
        assert isinstance(result, ConversationIntentAnalysis)
        assert result.topic_completed is False
        assert result.user_engagement == 0.5


@pytest.mark.unit
@pytest.mark.utils
class TestGoalManagerEmptyResponseShortCircuit:
    """LLM 空响应必须显式降级，不再流入 JSON 解析报错（issue #259）。"""

    @pytest.fixture
    def goal_manager(self):
        mgr = ConversationGoalManager(MagicMock(), MagicMock(), MagicMock())
        # 用 MagicMock 替换真实保护服务，便于断言“未进入消毒阶段”；wrap_prompt 保持透传
        real_wrap = mgr.prompt_protection.wrap_prompt
        mgr.prompt_protection = MagicMock()
        mgr.prompt_protection.wrap_prompt.side_effect = lambda prompt, **kwargs: real_wrap(prompt, **kwargs)
        return mgr

    async def test_initial_goal_none_response(self, goal_manager):
        goal_manager.llm.refine_chat_completion = AsyncMock(return_value=None)
        result = await goal_manager._analyze_initial_goal("你好")
        assert result["goal_type"] == "casual_chat"
        assert result["reasoning"] == "模型未返回有效分析结果"
        goal_manager.prompt_protection.sanitize_response.assert_not_called()

    @pytest.mark.parametrize("response", [None, "", "   \n"])
    async def test_dynamic_stages_empty_response_uses_base_without_json_parsing(
        self, goal_manager, response
    ):
        goal_manager.llm.refine_chat_completion = AsyncMock(return_value=response)
        goal_manager.guardrails = MagicMock()
        goal_manager._parse_array_fallback = MagicMock()
        base_stages = ["了解话题", "自然交流"]

        result = await goal_manager._plan_dynamic_stages(
            "casual_chat", "日常", "你好", base_stages
        )

        assert result == base_stages
        goal_manager.llm.refine_chat_completion.assert_awaited_once()
        goal_manager.prompt_protection.sanitize_response.assert_not_called()
        goal_manager.guardrails.validate_and_clean_json.assert_not_called()
        goal_manager._parse_array_fallback.assert_not_called()

    @pytest.mark.parametrize("sanitized", [None, "", "   \n"])
    async def test_dynamic_stages_sanitized_to_empty_uses_base_without_json_parsing(
        self, goal_manager, sanitized
    ):
        goal_manager.llm.refine_chat_completion = AsyncMock(return_value="some reply")
        goal_manager.prompt_protection.sanitize_response.return_value = (sanitized, {})
        goal_manager.guardrails = MagicMock()
        goal_manager._parse_array_fallback = MagicMock()
        base_stages = ["了解话题", "自然交流"]

        result = await goal_manager._plan_dynamic_stages(
            "casual_chat", "日常", "你好", base_stages
        )

        assert result == base_stages
        goal_manager.guardrails.validate_and_clean_json.assert_not_called()
        goal_manager._parse_array_fallback.assert_not_called()

    async def test_dynamic_stages_valid_response_keeps_generated_stages(self, goal_manager):
        goal_manager.llm.refine_chat_completion = AsyncMock(return_value='["破冰", "交流"]')
        goal_manager.prompt_protection.sanitize_response.return_value = ('["破冰", "交流"]', {})
        goal_manager.guardrails = MagicMock()
        goal_manager.guardrails.validate_and_clean_json.return_value = ["破冰", "交流"]

        result = await goal_manager._plan_dynamic_stages(
            "casual_chat", "日常", "你好", ["基础阶段一", "基础阶段二"]
        )

        assert result == ["破冰", "交流"]

    async def test_initial_goal_whitespace_response(self, goal_manager):
        goal_manager.llm.refine_chat_completion = AsyncMock(return_value="   \n")
        result = await goal_manager._analyze_initial_goal("你好")
        assert result["goal_type"] == "casual_chat"
        goal_manager.prompt_protection.sanitize_response.assert_not_called()

    async def test_initial_goal_sanitized_to_empty(self, goal_manager):
        goal_manager.llm.refine_chat_completion = AsyncMock(return_value="some reply")
        goal_manager.prompt_protection.sanitize_response = MagicMock(
            return_value=("", {"leaks_removed": ["everything"]})
        )
        result = await goal_manager._analyze_initial_goal("你好")
        assert result["goal_type"] == "casual_chat"
        assert result["reasoning"] == "模型回复消毒后无有效内容"

    async def test_intent_analysis_none_response(self, goal_manager):
        goal = {
            "final_goal": {"type": "casual_chat", "name": "闲聊", "topic": "日常", "topic_status": "active"},
            "current_stage": {"task": "破冰"},
            "planned_stages": ["破冰", "深入"],
            "conversation_history": [],
        }
        goal_manager.llm.refine_chat_completion = AsyncMock(return_value=None)
        result = await goal_manager._analyze_conversation_intent(goal, "你好", "你好呀")
        assert result["goal_switch_needed"] is False
        assert result["reasoning"] == "模型未返回有效分析结果"
        goal_manager.prompt_protection.sanitize_response.assert_not_called()

    async def test_intent_analysis_sanitized_to_empty(self, goal_manager):
        goal = {
            "final_goal": {"type": "casual_chat", "name": "闲聊", "topic": "日常", "topic_status": "active"},
            "current_stage": {"task": "破冰"},
            "planned_stages": ["破冰", "深入"],
            "conversation_history": [],
        }
        goal_manager.llm.refine_chat_completion = AsyncMock(return_value="some reply")
        goal_manager.prompt_protection.sanitize_response = MagicMock(
            return_value=("", {"leaks_removed": ["everything"]})
        )
        result = await goal_manager._analyze_conversation_intent(goal, "你好", "你好呀")
        assert result["goal_switch_needed"] is False
        assert result["reasoning"] == "模型回复消毒后无有效内容"
