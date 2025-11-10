"""
JSON解析工具 - 处理LLM返回结果的markdown清理
"""
import json
import re
from typing import Any, Optional

from astrbot.api import logger


def clean_llm_json_response(response_text: str) -> str:
    """
    清理LLM响应中的markdown标识符和其他格式化字符
    
    Args:
        response_text: LLM的原始响应文本
        
    Returns:
        清理后的JSON字符串
    """
    import re
    
    # 清理响应文本
    cleaned_text = response_text.strip()
    
    # 去除markdown代码块标记
    if cleaned_text.startswith("```json"):
        cleaned_text = cleaned_text[7:]
    elif cleaned_text.startswith("```"):
        cleaned_text = cleaned_text[3:]
    
    if cleaned_text.endswith("```"):
        cleaned_text = cleaned_text[:-3]
    
    cleaned_text = cleaned_text.strip()
    
    # 移除其他常见的markdown标识符
    cleaned_text = re.sub(r'^\s*```\w*\s*', '', cleaned_text, flags=re.MULTILINE)
    cleaned_text = re.sub(r'```\s*$', '', cleaned_text, flags=re.MULTILINE)
    
    # 移除或转义无效的控制字符
    # 保留有效的控制字符：\t \n \r，移除其他控制字符
    cleaned_text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', cleaned_text)
    
    # 寻找JSON对象的开始和结束位置
    json_start = cleaned_text.find('{')
    json_end = cleaned_text.rfind('}')
    
    if json_start != -1 and json_end != -1 and json_end > json_start:
        # 提取JSON部分
        cleaned_text = cleaned_text[json_start:json_end+1]
    else:
        # 如果找不到JSON对象，尝试寻找数组
        array_start = cleaned_text.find('[')
        array_end = cleaned_text.rfind(']')
        
        if array_start != -1 and array_end != -1 and array_end > array_start:
            cleaned_text = cleaned_text[array_start:array_end+1]
    
    return cleaned_text


def safe_parse_llm_json(response_text: str, fallback_result: Any = None) -> Any:
    """
    安全解析LLM响应中的JSON，处理markdown代码块和额外文本
    
    Args:
        response_text: LLM的原始响应文本
        fallback_result: 解析失败时的备用结果
        
    Returns:
        解析成功的JSON对象，或者备用结果
    """
    try:
        # 清理响应文本
        cleaned_text = clean_llm_json_response(response_text)
        
        # 尝试解析JSON
        return json.loads(cleaned_text)
        
    except json.JSONDecodeError as e:
        logger.debug(f"JSON解析失败: {e}，原始响应: {response_text[:200]}...")
        return fallback_result
    except Exception as e:
        logger.warning(f"JSON解析异常: {e}")
        return fallback_result


def safe_json_loads_with_fallback(response_text: str, fallback: Any = None) -> Any:
    """
    带备用结果的安全JSON解析（简化版本）
    
    Args:
        response_text: 响应文本
        fallback: 备用结果
        
    Returns:
        解析结果或备用结果
    """
    try:
        cleaned_text = clean_llm_json_response(response_text)
        return json.loads(cleaned_text)
    except:
        return fallback