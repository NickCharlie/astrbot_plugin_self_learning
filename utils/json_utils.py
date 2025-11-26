"""
JSON解析工具 - 处理LLM返回结果的markdown清理和格式化
支持多种主流LLM模型的返回格式处理，包括思考型模型
"""
import json
import re
from typing import Any, Optional, List, Tuple
from enum import Enum

from astrbot.api import logger


class LLMProvider(Enum):
    """LLM提供商枚举"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"
    GENERIC = "generic"


class ThinkingTagPattern:
    """思考标签模式配置"""

    # 各种思考型模型的标签模式
    PATTERNS = [
        # DeepSeek-Reasoner 思考标签
        (r'<thinking>.*?</thinking>', re.DOTALL | re.IGNORECASE),
        (r'<思考>.*?</思考>', re.DOTALL),

        # Claude 思考标签
        (r'<thought>.*?</thought>', re.DOTALL | re.IGNORECASE),
        (r'<reasoning>.*?</reasoning>', re.DOTALL | re.IGNORECASE),

        # 通用思考模式标签
        (r'<think>.*?</think>', re.DOTALL | re.IGNORECASE),
        (r'\[thinking\].*?\[/thinking\]', re.DOTALL | re.IGNORECASE),
        (r'\[thought\].*?\[/thought\]', re.DOTALL | re.IGNORECASE),

        # 其他可能的思考内容格式
        (r'【思考过程】.*?【/思考过程】', re.DOTALL),
        (r'---思考开始---.*?---思考结束---', re.DOTALL),
    ]


def remove_thinking_content(text: str) -> str:
    """
    移除LLM返回中的思考内容标签

    支持多种思考型模型的标签格式：
    - DeepSeek-Reasoner: <thinking>...</thinking>
    - Claude: <thought>...</thought>, <reasoning>...</reasoning>
    - 通用格式: <think>...</think>, [thinking]...[/thinking]

    Args:
        text: 包含可能的思考内容的文本

    Returns:
        移除思考内容后的文本
    """
    if not text:
        return text

    cleaned_text = text

    for pattern, flags in ThinkingTagPattern.PATTERNS:
        try:
            cleaned_text = re.sub(pattern, '', cleaned_text, flags=flags)
        except re.error as e:
            logger.warning(f"移除思考标签时正则表达式错误: {pattern}, {e}")
            continue

    # 清理移除后可能产生的多余空白
    cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text)
    cleaned_text = cleaned_text.strip()

    return cleaned_text


def extract_thinking_content(text: str) -> Tuple[str, List[str]]:
    """
    提取并返回思考内容和清理后的文本

    Args:
        text: 原始文本

    Returns:
        (清理后的文本, 提取的思考内容列表)
    """
    if not text:
        return text, []

    thinking_contents = []
    cleaned_text = text

    for pattern, flags in ThinkingTagPattern.PATTERNS:
        try:
            matches = re.findall(pattern, cleaned_text, flags=flags)
            for match in matches:
                thinking_contents.append(match)
            cleaned_text = re.sub(pattern, '', cleaned_text, flags=flags)
        except re.error as e:
            logger.warning(f"提取思考内容时正则表达式错误: {pattern}, {e}")
            continue

    # 清理多余空白
    cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text)
    cleaned_text = cleaned_text.strip()

    return cleaned_text, thinking_contents


def clean_markdown_blocks(text: str) -> str:
    """
    清理markdown代码块标记

    支持格式：
    - ```json ... ```
    - ``` ... ```
    - 多行代码块

    Args:
        text: 包含markdown代码块的文本

    Returns:
        清理后的文本
    """
    if not text:
        return text

    cleaned_text = text.strip()

    # 去除开头的markdown代码块标记
    # 支持 ```json, ```JSON, ```Javascript 等各种语言标记
    if cleaned_text.startswith("```"):
        # 查找第一个换行符的位置
        first_newline = cleaned_text.find('\n')
        if first_newline != -1:
            # 检查第一行是否只是语言标记
            first_line = cleaned_text[:first_newline].strip()
            if first_line.startswith("```"):
                cleaned_text = cleaned_text[first_newline + 1:]
        else:
            # 没有换行符，尝试直接移除开头的 ``` 或 ```json
            cleaned_text = re.sub(r'^```\w*\s*', '', cleaned_text)

    # 去除结尾的 ```
    if cleaned_text.endswith("```"):
        cleaned_text = cleaned_text[:-3]

    cleaned_text = cleaned_text.strip()

    # 移除其他可能嵌入的markdown标识符
    cleaned_text = re.sub(r'^\s*```\w*\s*', '', cleaned_text, flags=re.MULTILINE)
    cleaned_text = re.sub(r'```\s*$', '', cleaned_text, flags=re.MULTILINE)

    return cleaned_text


def clean_control_characters(text: str) -> str:
    """
    移除或转义无效的控制字符

    保留有效的控制字符：\\t \\n \\r
    移除其他控制字符

    Args:
        text: 可能包含控制字符的文本

    Returns:
        清理后的文本
    """
    if not text:
        return text

    # 移除无效的控制字符（保留 \t \n \r）
    cleaned_text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

    return cleaned_text


def extract_json_content(text: str) -> str:
    """
    从文本中提取JSON内容

    自动识别JSON对象或数组的边界

    Args:
        text: 可能包含JSON的文本

    Returns:
        提取的JSON字符串
    """
    if not text:
        return text

    cleaned_text = text.strip()

    # 首先尝试查找JSON对象 {...}
    json_start = cleaned_text.find('{')
    json_end = cleaned_text.rfind('}')

    if json_start != -1 and json_end != -1 and json_end > json_start:
        return cleaned_text[json_start:json_end + 1]

    # 如果找不到JSON对象，尝试查找JSON数组 [...]
    array_start = cleaned_text.find('[')
    array_end = cleaned_text.rfind(']')

    if array_start != -1 and array_end != -1 and array_end > array_start:
        return cleaned_text[array_start:array_end + 1]

    # 如果都找不到，返回原文本
    return cleaned_text


def fix_common_json_errors(text: str) -> str:
    """
    修复常见的JSON格式错误

    修复项：
    - 尾随逗号
    - 单引号替换为双引号
    - 未转义的特殊字符
    - 布尔值和null的大小写

    Args:
        text: 可能有格式错误的JSON文本

    Returns:
        修复后的JSON文本
    """
    if not text:
        return text

    fixed_text = text

    # 修复尾随逗号（数组和对象中）
    fixed_text = re.sub(r',\s*}', '}', fixed_text)
    fixed_text = re.sub(r',\s*]', ']', fixed_text)

    # 修复布尔值和null的大小写
    # 使用更精确的模式避免误替换字符串内容
    fixed_text = re.sub(r':\s*True\b', ': true', fixed_text)
    fixed_text = re.sub(r':\s*False\b', ': false', fixed_text)
    fixed_text = re.sub(r':\s*None\b', ': null', fixed_text)
    fixed_text = re.sub(r':\s*NULL\b', ': null', fixed_text)

    # 修复可能的NaN和Infinity（Python特有）
    fixed_text = re.sub(r':\s*nan\b', ': null', fixed_text, flags=re.IGNORECASE)
    fixed_text = re.sub(r':\s*infinity\b', ': null', fixed_text, flags=re.IGNORECASE)
    fixed_text = re.sub(r':\s*-infinity\b', ': null', fixed_text, flags=re.IGNORECASE)

    return fixed_text


def clean_llm_json_response(response_text: str, remove_thinking: bool = True) -> str:
    """
    清理LLM响应中的markdown标识符和其他格式化字符

    支持多种主流LLM模型的返回格式：
    - OpenAI GPT系列
    - Anthropic Claude系列
    - DeepSeek（包括Reasoner思考型模型）
    - 其他OpenAI兼容API

    Args:
        response_text: LLM的原始响应文本
        remove_thinking: 是否移除思考内容标签，默认True

    Returns:
        清理后的JSON字符串
    """
    if not response_text:
        return response_text

    # 清理流程：
    # 1. 移除思考内容（如果启用）
    if remove_thinking:
        cleaned_text = remove_thinking_content(response_text)
    else:
        cleaned_text = response_text

    # 2. 清理markdown代码块
    cleaned_text = clean_markdown_blocks(cleaned_text)

    # 3. 清理控制字符
    cleaned_text = clean_control_characters(cleaned_text)

    # 4. 提取JSON内容
    cleaned_text = extract_json_content(cleaned_text)

    # 5. 修复常见JSON错误
    cleaned_text = fix_common_json_errors(cleaned_text)

    return cleaned_text


def safe_parse_llm_json(
    response_text: str,
    fallback_result: Any = None,
    remove_thinking: bool = True,
    auto_fix: bool = True
) -> Any:
    """
    安全解析LLM响应中的JSON，处理markdown代码块和额外文本

    支持特性：
    - 自动移除思考内容标签
    - 清理markdown格式
    - 修复常见JSON错误
    - 多次解析尝试

    Args:
        response_text: LLM的原始响应文本
        fallback_result: 解析失败时的备用结果
        remove_thinking: 是否移除思考内容标签，默认True
        auto_fix: 是否自动修复常见JSON错误，默认True

    Returns:
        解析成功的JSON对象，或者备用结果
    """
    if not response_text:
        return fallback_result

    try:
        # 清理响应文本
        cleaned_text = clean_llm_json_response(response_text, remove_thinking)

        # 第一次尝试：直接解析
        try:
            return json.loads(cleaned_text)
        except json.JSONDecodeError:
            pass

        # 第二次尝试：如果启用了自动修复，尝试修复后再解析
        if auto_fix:
            fixed_text = fix_common_json_errors(cleaned_text)
            try:
                return json.loads(fixed_text)
            except json.JSONDecodeError:
                pass

        # 第三次尝试：尝试使用更宽松的解析
        # 处理可能的单引号问题
        try:
            # 只在字符串外部替换单引号为双引号
            relaxed_text = _convert_single_quotes(cleaned_text)
            return json.loads(relaxed_text)
        except (json.JSONDecodeError, Exception):
            pass

        # 所有尝试都失败了
        logger.debug(f"JSON解析失败，原始响应（前200字符）: {response_text[:200]}...")
        return fallback_result

    except Exception as e:
        logger.warning(f"JSON解析异常: {e}")
        return fallback_result


def _convert_single_quotes(text: str) -> str:
    """
    谨慎地将JSON中的单引号转换为双引号

    注意：这是一个简化实现，可能在复杂情况下不完全准确

    Args:
        text: JSON文本

    Returns:
        转换后的文本
    """
    if not text:
        return text

    result = []
    in_string = False
    escape_next = False
    string_char = None

    for char in text:
        if escape_next:
            result.append(char)
            escape_next = False
            continue

        if char == '\\':
            result.append(char)
            escape_next = True
            continue

        if not in_string:
            if char in ('"', "'"):
                in_string = True
                string_char = char
                result.append('"')  # 统一使用双引号
            else:
                result.append(char)
        else:
            if char == string_char:
                in_string = False
                string_char = None
                result.append('"')  # 统一使用双引号
            elif char == '"' and string_char == "'":
                # 在单引号字符串中遇到双引号，需要转义
                result.append('\\"')
            else:
                result.append(char)

    return ''.join(result)


def safe_json_loads_with_fallback(response_text: str, fallback: Any = None) -> Any:
    """
    带备用结果的安全JSON解析（简化版本，向后兼容）

    Args:
        response_text: 响应文本
        fallback: 备用结果

    Returns:
        解析结果或备用结果
    """
    return safe_parse_llm_json(response_text, fallback_result=fallback)


def parse_llm_json_with_provider(
    response_text: str,
    provider: LLMProvider = LLMProvider.GENERIC,
    fallback_result: Any = None
) -> Any:
    """
    根据LLM提供商类型解析JSON响应

    不同提供商可能有不同的响应格式特点：
    - OpenAI: 标准markdown代码块
    - Anthropic: 可能包含<thought>标签
    - DeepSeek: 可能包含<thinking>标签

    Args:
        response_text: LLM响应文本
        provider: LLM提供商类型
        fallback_result: 备用结果

    Returns:
        解析后的JSON对象
    """
    # 根据提供商类型决定是否移除思考内容
    # 对于思考型模型，默认移除思考内容
    remove_thinking = True

    if provider == LLMProvider.DEEPSEEK:
        # DeepSeek可能有Reasoner模型，始终移除思考内容
        remove_thinking = True
    elif provider == LLMProvider.ANTHROPIC:
        # Claude可能有thought标签
        remove_thinking = True
    elif provider == LLMProvider.OPENAI:
        # OpenAI通常没有思考标签，但为了安全起见也移除
        remove_thinking = True

    return safe_parse_llm_json(
        response_text,
        fallback_result=fallback_result,
        remove_thinking=remove_thinking
    )


def detect_llm_provider(model_name: str) -> LLMProvider:
    """
    根据模型名称检测LLM提供商

    Args:
        model_name: 模型名称

    Returns:
        LLM提供商枚举
    """
    if not model_name:
        return LLMProvider.GENERIC

    model_lower = model_name.lower()

    if 'deepseek' in model_lower:
        return LLMProvider.DEEPSEEK
    elif 'claude' in model_lower:
        return LLMProvider.ANTHROPIC
    elif any(model in model_lower for model in ['gpt-', 'text-', 'davinci', 'openai']):
        return LLMProvider.OPENAI
    else:
        return LLMProvider.GENERIC


def validate_json_structure(
    data: Any,
    required_fields: Optional[List[str]] = None,
    expected_type: Optional[type] = None
) -> Tuple[bool, str]:
    """
    验证JSON数据结构

    Args:
        data: 要验证的数据
        required_fields: 必需的字段列表
        expected_type: 期望的数据类型

    Returns:
        (是否有效, 错误消息)
    """
    if data is None:
        return False, "数据为空"

    if expected_type and not isinstance(data, expected_type):
        return False, f"期望类型 {expected_type.__name__}，实际类型 {type(data).__name__}"

    if required_fields and isinstance(data, dict):
        missing = [field for field in required_fields if field not in data]
        if missing:
            return False, f"缺少必需字段: {', '.join(missing)}"

    return True, ""


# 导出的公共函数
__all__ = [
    'clean_llm_json_response',
    'safe_parse_llm_json',
    'safe_json_loads_with_fallback',
    'remove_thinking_content',
    'extract_thinking_content',
    'clean_markdown_blocks',
    'fix_common_json_errors',
    'parse_llm_json_with_provider',
    'detect_llm_provider',
    'validate_json_structure',
    'LLMProvider',
    'ThinkingTagPattern',
]
