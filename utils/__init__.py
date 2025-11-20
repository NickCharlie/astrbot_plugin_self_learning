"""
工具模块 - 提供通用工具函数
"""
from .json_utils import (
    # 核心函数
    clean_llm_json_response,
    safe_parse_llm_json,
    safe_json_loads_with_fallback,

    # 思考内容处理
    remove_thinking_content,
    extract_thinking_content,

    # 清理和修复函数
    clean_markdown_blocks,
    clean_control_characters,
    extract_json_content,
    fix_common_json_errors,

    # Provider相关
    parse_llm_json_with_provider,
    detect_llm_provider,

    # 验证函数
    validate_json_structure,

    # 类和枚举
    LLMProvider,
    ThinkingTagPattern,
)

__all__ = [
    # 核心函数
    'clean_llm_json_response',
    'safe_parse_llm_json',
    'safe_json_loads_with_fallback',

    # 思考内容处理
    'remove_thinking_content',
    'extract_thinking_content',

    # 清理和修复函数
    'clean_markdown_blocks',
    'clean_control_characters',
    'extract_json_content',
    'fix_common_json_errors',

    # Provider相关
    'parse_llm_json_with_provider',
    'detect_llm_provider',

    # 验证函数
    'validate_json_structure',

    # 类和枚举
    'LLMProvider',
    'ThinkingTagPattern',

    # 安全工具
    'PasswordHasher',
    'LoginAttemptTracker',
    'SecurityValidator',
    'login_attempt_tracker',
    'migrate_password_to_hashed',
    'verify_password_with_migration',
]

# 导入安全工具
from .security_utils import (
    PasswordHasher,
    LoginAttemptTracker,
    SecurityValidator,
    login_attempt_tracker,
    migrate_password_to_hashed,
    verify_password_with_migration,
)
