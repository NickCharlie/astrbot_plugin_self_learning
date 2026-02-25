"""
Unit tests for JSON utilities module

Tests LLM response parsing, markdown cleanup, and JSON validation:
- remove_thinking_content for various LLM thinking tags
- clean_markdown_blocks for code block removal
- clean_control_characters for sanitization
- extract_json_content for boundary detection
- fix_common_json_errors for auto-repair
- safe_parse_llm_json for end-to-end parsing
- validate_json_structure for schema validation
- detect_llm_provider for model name detection
"""
import pytest

from utils.json_utils import (
    remove_thinking_content,
    extract_thinking_content,
    clean_markdown_blocks,
    clean_control_characters,
    extract_json_content,
    fix_common_json_errors,
    clean_llm_json_response,
    safe_parse_llm_json,
    validate_json_structure,
    detect_llm_provider,
    LLMProvider,
    _convert_single_quotes,
)


@pytest.mark.unit
@pytest.mark.utils
class TestRemoveThinkingContent:
    """Test removal of LLM thinking tags."""

    def test_empty_input(self):
        """Test empty input returns as-is."""
        assert remove_thinking_content("") == ""
        assert remove_thinking_content(None) is None

    def test_remove_thinking_tags(self):
        """Test removal of <thinking> tags."""
        text = "<thinking>Internal reasoning</thinking>Final answer"
        result = remove_thinking_content(text)
        assert "Internal reasoning" not in result
        assert "Final answer" in result

    def test_remove_thought_tags(self):
        """Test removal of <thought> tags."""
        text = "<thought>Analysis here</thought>Result"
        result = remove_thinking_content(text)
        assert "Analysis here" not in result
        assert "Result" in result

    def test_remove_reasoning_tags(self):
        """Test removal of <reasoning> tags."""
        text = "<reasoning>Step 1, Step 2</reasoning>Output"
        result = remove_thinking_content(text)
        assert "Step 1" not in result
        assert "Output" in result

    def test_remove_think_tags(self):
        """Test removal of <think> tags."""
        text = "<think>Hmm let me think</think>Answer is 42"
        result = remove_thinking_content(text)
        assert "Hmm let me think" not in result
        assert "Answer is 42" in result

    def test_remove_chinese_thinking_tags(self):
        """Test removal of Chinese thinking tags."""
        text = "<思考>这是思考过程</思考>最终结果"
        result = remove_thinking_content(text)
        assert "这是思考过程" not in result
        assert "最终结果" in result

    def test_multiline_thinking_content(self):
        """Test removal of multiline thinking content."""
        text = "<thinking>\nLine 1\nLine 2\nLine 3\n</thinking>Final"
        result = remove_thinking_content(text)
        assert "Line 1" not in result
        assert "Final" in result

    def test_text_without_thinking_tags(self):
        """Test text without thinking tags is unchanged."""
        text = "Just a regular response without any tags"
        result = remove_thinking_content(text)
        assert result == text


@pytest.mark.unit
@pytest.mark.utils
class TestExtractThinkingContent:
    """Test extraction and separation of thinking content."""

    def test_extract_thinking(self):
        """Test extracting thinking content."""
        text = "<thinking>My thoughts</thinking>Answer"
        cleaned, thoughts = extract_thinking_content(text)

        assert "Answer" in cleaned
        assert len(thoughts) >= 1

    def test_no_thinking_content(self):
        """Test text without thinking content."""
        text = "Plain text response"
        cleaned, thoughts = extract_thinking_content(text)

        assert cleaned == "Plain text response"
        assert thoughts == []

    def test_empty_input(self):
        """Test empty input."""
        cleaned, thoughts = extract_thinking_content("")
        assert cleaned == ""
        assert thoughts == []


@pytest.mark.unit
@pytest.mark.utils
class TestCleanMarkdownBlocks:
    """Test markdown code block cleaning."""

    def test_clean_json_code_block(self):
        """Test cleaning ```json code block."""
        text = '```json\n{"key": "value"}\n```'
        result = clean_markdown_blocks(text)
        assert result == '{"key": "value"}'

    def test_clean_plain_code_block(self):
        """Test cleaning plain ``` code block."""
        text = '```\n{"key": "value"}\n```'
        result = clean_markdown_blocks(text)
        assert result == '{"key": "value"}'

    def test_no_code_blocks(self):
        """Test text without code blocks is unchanged."""
        text = '{"key": "value"}'
        result = clean_markdown_blocks(text)
        assert result == text

    def test_empty_input(self):
        """Test empty input returns as-is."""
        assert clean_markdown_blocks("") == ""
        assert clean_markdown_blocks(None) is None


@pytest.mark.unit
@pytest.mark.utils
class TestCleanControlCharacters:
    """Test control character cleaning."""

    def test_remove_null_bytes(self):
        """Test removal of null bytes."""
        text = "hello\x00world"
        result = clean_control_characters(text)
        assert result == "helloworld"

    def test_preserve_tabs_and_newlines(self):
        """Test preservation of tabs and newlines."""
        text = "hello\tworld\nfoo"
        result = clean_control_characters(text)
        assert result == text

    def test_empty_input(self):
        """Test empty input."""
        assert clean_control_characters("") == ""
        assert clean_control_characters(None) is None


@pytest.mark.unit
@pytest.mark.utils
class TestExtractJsonContent:
    """Test JSON content extraction from mixed text."""

    def test_extract_json_object(self):
        """Test extracting JSON object from text."""
        text = 'Some text {"key": "value"} more text'
        result = extract_json_content(text)
        assert result == '{"key": "value"}'

    def test_extract_json_array(self):
        """Test extracting JSON array from text."""
        text = 'Prefix [1, 2, 3] suffix'
        result = extract_json_content(text)
        assert result == '[1, 2, 3]'

    def test_no_json_content(self):
        """Test text without JSON returns original."""
        text = "no json here"
        result = extract_json_content(text)
        assert result == text

    def test_nested_json(self):
        """Test extracting nested JSON object."""
        text = '{"outer": {"inner": "value"}}'
        result = extract_json_content(text)
        assert result == text

    def test_empty_input(self):
        """Test empty input."""
        assert extract_json_content("") == ""


@pytest.mark.unit
@pytest.mark.utils
class TestFixCommonJsonErrors:
    """Test JSON error auto-repair."""

    def test_fix_trailing_comma_object(self):
        """Test fixing trailing comma in object."""
        text = '{"key": "value",}'
        result = fix_common_json_errors(text)
        assert result == '{"key": "value"}'

    def test_fix_trailing_comma_array(self):
        """Test fixing trailing comma in array."""
        text = '[1, 2, 3,]'
        result = fix_common_json_errors(text)
        assert result == '[1, 2, 3]'

    def test_fix_python_true_false(self):
        """Test fixing Python True/False/None to JSON equivalents."""
        text = '{"flag": True, "empty": None, "off": False}'
        result = fix_common_json_errors(text)
        assert ": true" in result
        assert ": null" in result
        assert ": false" in result

    def test_fix_nan_value(self):
        """Test fixing NaN to null."""
        text = '{"score": nan}'
        result = fix_common_json_errors(text)
        assert ": null" in result

    def test_empty_input(self):
        """Test empty input."""
        assert fix_common_json_errors("") == ""


@pytest.mark.unit
@pytest.mark.utils
class TestSafeParseLlmJson:
    """Test end-to-end safe JSON parsing."""

    def test_parse_clean_json(self):
        """Test parsing clean JSON."""
        result = safe_parse_llm_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parse_json_in_markdown(self):
        """Test parsing JSON wrapped in markdown code block."""
        text = '```json\n{"key": "value"}\n```'
        result = safe_parse_llm_json(text)
        assert result == {"key": "value"}

    def test_parse_json_with_thinking_tags(self):
        """Test parsing JSON with thinking tags."""
        text = '<thinking>Analysis</thinking>{"result": 42}'
        result = safe_parse_llm_json(text)
        assert result == {"result": 42}

    def test_parse_json_with_trailing_comma(self):
        """Test parsing JSON with trailing comma."""
        text = '{"key": "value",}'
        result = safe_parse_llm_json(text)
        assert result == {"key": "value"}

    def test_parse_invalid_json_returns_fallback(self):
        """Test invalid JSON returns fallback result."""
        result = safe_parse_llm_json("not json at all", fallback_result={"default": True})
        assert result == {"default": True}

    def test_parse_empty_input(self):
        """Test empty input returns fallback."""
        result = safe_parse_llm_json("", fallback_result=None)
        assert result is None

    def test_parse_json_array(self):
        """Test parsing JSON array."""
        result = safe_parse_llm_json('[1, 2, 3]')
        assert result == [1, 2, 3]

    def test_parse_with_single_quotes(self):
        """Test parsing JSON with single quotes."""
        text = "{'key': 'value'}"
        result = safe_parse_llm_json(text)
        assert result == {"key": "value"}

    def test_parse_nested_json(self):
        """Test parsing nested JSON structure."""
        text = '{"outer": {"inner": [1, 2, 3]}, "flag": true}'
        result = safe_parse_llm_json(text)
        assert result["outer"]["inner"] == [1, 2, 3]
        assert result["flag"] is True


@pytest.mark.unit
@pytest.mark.utils
class TestValidateJsonStructure:
    """Test JSON structure validation."""

    def test_valid_with_required_fields(self):
        """Test validation with all required fields present."""
        data = {"name": "Alice", "age": 30}
        valid, msg = validate_json_structure(
            data, required_fields=["name", "age"]
        )
        assert valid is True
        assert msg == ""

    def test_missing_required_fields(self):
        """Test validation with missing required fields."""
        data = {"name": "Alice"}
        valid, msg = validate_json_structure(
            data, required_fields=["name", "age"]
        )
        assert valid is False
        assert "age" in msg

    def test_none_data(self):
        """Test validation with None data."""
        valid, msg = validate_json_structure(None)
        assert valid is False

    def test_type_check_success(self):
        """Test validation with correct expected type."""
        valid, msg = validate_json_structure(
            {"key": "value"}, expected_type=dict
        )
        assert valid is True

    def test_type_check_failure(self):
        """Test validation with incorrect expected type."""
        valid, msg = validate_json_structure(
            [1, 2, 3], expected_type=dict
        )
        assert valid is False
        assert "dict" in msg


@pytest.mark.unit
@pytest.mark.utils
class TestDetectLlmProvider:
    """Test LLM provider detection from model names."""

    def test_detect_deepseek(self):
        """Test detecting DeepSeek provider."""
        assert detect_llm_provider("deepseek-chat") == LLMProvider.DEEPSEEK
        assert detect_llm_provider("deepseek-reasoner") == LLMProvider.DEEPSEEK

    def test_detect_anthropic(self):
        """Test detecting Anthropic provider."""
        assert detect_llm_provider("claude-3-opus") == LLMProvider.ANTHROPIC
        assert detect_llm_provider("claude-3.5-sonnet") == LLMProvider.ANTHROPIC

    def test_detect_openai(self):
        """Test detecting OpenAI provider."""
        assert detect_llm_provider("gpt-4") == LLMProvider.OPENAI
        assert detect_llm_provider("gpt-4o-mini") == LLMProvider.OPENAI

    def test_detect_unknown(self):
        """Test detecting unknown provider."""
        assert detect_llm_provider("some-custom-model") == LLMProvider.GENERIC

    def test_detect_empty_input(self):
        """Test detecting from empty input."""
        assert detect_llm_provider("") == LLMProvider.GENERIC
        assert detect_llm_provider(None) == LLMProvider.GENERIC


@pytest.mark.unit
@pytest.mark.utils
class TestConvertSingleQuotes:
    """Test single-to-double quote conversion."""

    def test_basic_conversion(self):
        """Test basic single quote to double quote conversion."""
        result = _convert_single_quotes("{'key': 'value'}")
        assert result == '{"key": "value"}'

    def test_already_double_quotes(self):
        """Test text with double quotes is unchanged."""
        text = '{"key": "value"}'
        result = _convert_single_quotes(text)
        assert result == text

    def test_empty_input(self):
        """Test empty input."""
        assert _convert_single_quotes("") == ""
        assert _convert_single_quotes(None) is None
