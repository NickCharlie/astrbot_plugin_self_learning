"""
JSON 清洗工具类
用于清洗和验证 LLM 返回的 JSON 格式内容
"""
import json
import re
from typing import Any, Dict, List, Optional, Union
from astrbot.api import logger


class JSONCleaner:
    """
    JSON 清洗工具类

    功能:
    1. 清理 LLM 返回中的无效字符和格式
    2. 提取 JSON 内容(即使被其他文本包围)
    3. 修复常见的 JSON 格式错误
    4. 验证 JSON 结构
    5. 提供安全的默认值
    """

    @staticmethod
    def clean_and_parse(
        raw_text: str,
        expected_type: type = dict,
        default_value: Any = None,
        strict: bool = False
    ) -> Any:
        """
        清洗并解析 JSON 文本

        Args:
            raw_text: LLM 返回的原始文本
            expected_type: 期望的类型 (dict, list, str, int, float, bool)
            default_value: 解析失败时的默认值
            strict: 是否严格模式(严格模式下类型不匹配会返回默认值)

        Returns:
            解析后的 Python 对象,失败时返回 default_value

        Examples:
            >>> JSONCleaner.clean_and_parse('{"key": "value"}')
            {'key': 'value'}

            >>> JSONCleaner.clean_and_parse('```json\\n{"key": "value"}\\n```')
            {'key': 'value'}

            >>> JSONCleaner.clean_and_parse('invalid', default_value={})
            {}
        """
        if not raw_text or not isinstance(raw_text, str):
            logger.warning(f"[JSON清洗] 输入无效: {type(raw_text)}")
            return default_value if default_value is not None else {}

        try:
            # 1. 预处理: 移除前后空白
            text = raw_text.strip()

            # 2. 提取 JSON 内容
            json_text = JSONCleaner._extract_json(text)

            if not json_text:
                logger.warning(f"[JSON清洗] 无法提取 JSON 内容: {text[:100]}...")
                return default_value if default_value is not None else {}

            # 3. 清理 JSON 文本
            cleaned_text = JSONCleaner._clean_json_text(json_text)

            # 4. 解析 JSON
            parsed = json.loads(cleaned_text)

            # 5. 类型验证
            if strict and not isinstance(parsed, expected_type):
                logger.warning(
                    f"[JSON清洗] 类型不匹配: 期望 {expected_type}, 实际 {type(parsed)}"
                )
                return default_value if default_value is not None else {}

            logger.debug(f"[JSON清洗] 成功解析: {type(parsed)}")
            return parsed

        except json.JSONDecodeError as e:
            logger.error(f"[JSON清洗] JSON 解析失败: {e}")
            logger.debug(f"原始文本: {raw_text[:200]}...")
            return default_value if default_value is not None else {}

        except Exception as e:
            logger.error(f"[JSON清洗] 未知错误: {e}", exc_info=True)
            return default_value if default_value is not None else {}

    @staticmethod
    def _extract_json(text: str) -> Optional[str]:
        """
        从文本中提取 JSON 内容

        支持的格式:
        1. 纯 JSON: {"key": "value"}
        2. Markdown 代码块: ```json\\n{...}\\n```
        3. 代码块: ```{...}```
        4. 文本包围: Some text {"key": "value"} more text
        """
        # 尝试 1: 检查是否是纯 JSON (以 { 或 [ 开头)
        if text.startswith('{') or text.startswith('['):
            # 找到对应的结束位置
            if text.startswith('{'):
                end_idx = JSONCleaner._find_closing_brace(text, 0)
                if end_idx != -1:
                    return text[:end_idx + 1]
            elif text.startswith('['):
                end_idx = JSONCleaner._find_closing_bracket(text, 0)
                if end_idx != -1:
                    return text[:end_idx + 1]

        # 尝试 2: 提取 markdown 代码块中的 JSON
        # ```json\n{...}\n```
        json_code_block_pattern = r'```json\s*\n(.*?)\n```'
        match = re.search(json_code_block_pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # 尝试 3: 提取普通代码块中的 JSON
        # ```{...}```
        code_block_pattern = r'```\s*\n?(.*?)\n?```'
        match = re.search(code_block_pattern, text, re.DOTALL)
        if match:
            content = match.group(1).strip()
            if content.startswith('{') or content.startswith('['):
                return content

        # 尝试 4: 查找第一个 { 或 [ 并提取到对应的结束符
        for start_char, finder in [('{', JSONCleaner._find_closing_brace),
                                     ('[', JSONCleaner._find_closing_bracket)]:
            start_idx = text.find(start_char)
            if start_idx != -1:
                end_idx = finder(text, start_idx)
                if end_idx != -1:
                    return text[start_idx:end_idx + 1]

        # 无法提取
        return None

    @staticmethod
    def _find_closing_brace(text: str, start_idx: int) -> int:
        """找到与起始 { 对应的结束 }"""
        depth = 0
        in_string = False
        escape_next = False

        for i in range(start_idx, len(text)):
            char = text[i]

            if escape_next:
                escape_next = False
                continue

            if char == '\\':
                escape_next = True
                continue

            if char == '"' and not in_string:
                in_string = True
            elif char == '"' and in_string:
                in_string = False
            elif not in_string:
                if char == '{':
                    depth += 1
                elif char == '}':
                    depth -= 1
                    if depth == 0:
                        return i

        return -1

    @staticmethod
    def _find_closing_bracket(text: str, start_idx: int) -> int:
        """找到与起始 [ 对应的结束 ]"""
        depth = 0
        in_string = False
        escape_next = False

        for i in range(start_idx, len(text)):
            char = text[i]

            if escape_next:
                escape_next = False
                continue

            if char == '\\':
                escape_next = True
                continue

            if char == '"' and not in_string:
                in_string = True
            elif char == '"' and in_string:
                in_string = False
            elif not in_string:
                if char == '[':
                    depth += 1
                elif char == ']':
                    depth -= 1
                    if depth == 0:
                        return i

        return -1

    @staticmethod
    def _clean_json_text(text: str) -> str:
        """
        清理 JSON 文本中的常见问题

        修复:
        1. 单引号替换为双引号
        2. 移除尾随逗号
        3. 修复布尔值大小写
        4. 移除注释
        """
        # 1. 移除单行注释 (//...)
        text = re.sub(r'//.*?$', '', text, flags=re.MULTILINE)

        # 2. 移除多行注释 (/*...*/)
        text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)

        # 3. 修复布尔值 (True -> true, False -> false)
        text = re.sub(r'\bTrue\b', 'true', text)
        text = re.sub(r'\bFalse\b', 'false', text)
        text = re.sub(r'\bNone\b', 'null', text)

        # 4. 移除尾随逗号 (在 } 或 ] 之前的逗号)
        text = re.sub(r',(\s*[}\]])', r'\1', text)

        # 5. 尝试修复单引号为双引号 (谨慎处理)
        # 只替换键名的单引号: 'key' -> "key"
        text = re.sub(r"'([^']*)'(\s*):", r'"\1"\2:', text)

        return text

    @staticmethod
    def safe_get(
        data: Dict[str, Any],
        key: str,
        default: Any = None,
        expected_type: type = None
    ) -> Any:
        """
        安全地从字典获取值

        Args:
            data: 字典
            key: 键名
            default: 默认值
            expected_type: 期望的类型

        Returns:
            值或默认值

        Examples:
            >>> data = {'key': 'value', 'num': '123'}
            >>> JSONCleaner.safe_get(data, 'key')
            'value'
            >>> JSONCleaner.safe_get(data, 'missing', default='default')
            'default'
            >>> JSONCleaner.safe_get(data, 'num', expected_type=int, default=0)
            0  # 因为 '123' 不是 int 类型
        """
        if not isinstance(data, dict):
            return default

        value = data.get(key, default)

        if expected_type is not None and not isinstance(value, expected_type):
            logger.debug(
                f"[JSON清洗] 类型不匹配: 键 '{key}' 期望 {expected_type}, "
                f"实际 {type(value)}, 返回默认值"
            )
            return default

        return value

    @staticmethod
    def validate_schema(
        data: Dict[str, Any],
        required_keys: List[str],
        optional_keys: List[str] = None
    ) -> bool:
        """
        验证 JSON 数据的结构

        Args:
            data: 要验证的数据
            required_keys: 必需的键列表
            optional_keys: 可选的键列表

        Returns:
            是否有效

        Examples:
            >>> data = {'name': 'Alice', 'age': 30}
            >>> JSONCleaner.validate_schema(data, ['name', 'age'])
            True
            >>> JSONCleaner.validate_schema(data, ['name', 'email'])
            False
        """
        if not isinstance(data, dict):
            logger.warning("[JSON清洗] 数据不是字典类型")
            return False

        # 检查必需键
        for key in required_keys:
            if key not in data:
                logger.warning(f"[JSON清洗] 缺少必需键: {key}")
                return False

        # 检查是否有未预期的键 (如果提供了 optional_keys)
        if optional_keys is not None:
            all_allowed_keys = set(required_keys) | set(optional_keys)
            extra_keys = set(data.keys()) - all_allowed_keys
            if extra_keys:
                logger.debug(f"[JSON清洗] 存在额外的键: {extra_keys}")

        logger.debug("[JSON清洗] 结构验证通过")
        return True


class LLMJSONParser:
    """
    LLM JSON 解析器 - 针对 LLM 返回的特定格式进行优化
    """

    @staticmethod
    def parse_state_analysis(raw_text: str) -> Optional[str]:
        """
        解析心理状态分析结果

        期望格式: LLM 返回一个状态名称(字符串)

        Returns:
            状态名称字符串,失败返回 None
        """
        # 尝试直接作为字符串
        cleaned = raw_text.strip().strip('"\'')

        # 移除可能的前缀
        cleaned = re.sub(r'^(状态[:：]|新状态[:：])', '', cleaned)

        if cleaned and len(cleaned) < 50:  # 状态名称不应太长
            return cleaned

        # 尝试作为 JSON 解析
        result = JSONCleaner.clean_and_parse(raw_text, expected_type=str, default_value=None)
        if result:
            return result

        return None

    @staticmethod
    def parse_relation_analysis(raw_text: str) -> Dict[str, float]:
        """
        解析社交关系分析结果

        期望格式: {"关系类型1": 0.03, "关系类型2": 0.05}

        Returns:
            关系类型到数值变化的映射,失败返回空字典
        """
        result = JSONCleaner.clean_and_parse(
            raw_text,
            expected_type=dict,
            default_value={},
            strict=False
        )

        if not result:
            return {}

        # 清理和验证值
        cleaned_result = {}
        for key, value in result.items():
            # 确保键是字符串
            if not isinstance(key, str):
                key = str(key)

            # 确保值是数字
            try:
                if isinstance(value, (int, float)):
                    cleaned_result[key] = float(value)
                elif isinstance(value, str):
                    # 尝试转换字符串为数字
                    cleaned_result[key] = float(value)
            except (ValueError, TypeError):
                logger.warning(f"[JSON清洗] 无法转换关系值: {key} = {value}")
                continue

        return cleaned_result

    @staticmethod
    def parse_event_analysis(raw_text: str) -> Dict[str, Any]:
        """
        解析事件分析结果

        期望格式: {"event_type": "...", "intensity": 0.5, "description": "..."}

        Returns:
            事件分析结果字典,失败返回空字典
        """
        result = JSONCleaner.clean_and_parse(
            raw_text,
            expected_type=dict,
            default_value={},
            strict=False
        )

        # 验证必需字段
        if not JSONCleaner.validate_schema(
            result,
            required_keys=[],  # 没有严格必需的键
            optional_keys=['event_type', 'intensity', 'description', 'impact']
        ):
            return {}

        return result
