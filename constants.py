"""
常量定义 - 人格审查更新类型
避免字符串匹配混淆，使用明确的枚举常量
"""

# ============= 人格审查更新类型常量 =============

# 渐进式人格学习（从对话中学习的人格更新）
UPDATE_TYPE_PROGRESSIVE_PERSONA_LEARNING = "progressive_persona_learning"

# Few-shot风格学习（基于样本的风格学习）
UPDATE_TYPE_STYLE_LEARNING = "style_learning"

# 表达学习（表达模式学习）
UPDATE_TYPE_EXPRESSION_LEARNING = "expression_learning"

# 传统人格更新（其他类型）
UPDATE_TYPE_TRADITIONAL = "traditional"

# 兼容性：旧的update_type值映射
# 用于数据库中已存在的旧记录
LEGACY_UPDATE_TYPE_MAPPING = {
    "渐进式学习-风格分析": UPDATE_TYPE_PROGRESSIVE_PERSONA_LEARNING,
    "渐进式学习-人格更新": UPDATE_TYPE_PROGRESSIVE_PERSONA_LEARNING,
    "progressive_learning": UPDATE_TYPE_PROGRESSIVE_PERSONA_LEARNING,
    "style_learning": UPDATE_TYPE_STYLE_LEARNING,
    "expression_learning": UPDATE_TYPE_EXPRESSION_LEARNING,
}


def normalize_update_type(raw_update_type: str) -> str:
    """
    标准化update_type，处理旧格式兼容性

    Args:
        raw_update_type: 原始的update_type字符串

    Returns:
        标准化后的update_type常量
    """
    if not raw_update_type:
        return UPDATE_TYPE_TRADITIONAL

    # 精确匹配
    if raw_update_type in LEGACY_UPDATE_TYPE_MAPPING:
        return LEGACY_UPDATE_TYPE_MAPPING[raw_update_type]

    # 模糊匹配（兼容性处理）
    raw_lower = raw_update_type.lower()

    # 渐进式学习判断
    if '渐进式学习' in raw_update_type or 'progressive' in raw_lower:
        return UPDATE_TYPE_PROGRESSIVE_PERSONA_LEARNING

    # 风格学习判断（必须精确匹配，避免误判）
    if raw_update_type == 'style_learning' or raw_update_type == UPDATE_TYPE_STYLE_LEARNING:
        return UPDATE_TYPE_STYLE_LEARNING

    # 表达学习判断
    if 'expression_learning' in raw_lower:
        return UPDATE_TYPE_EXPRESSION_LEARNING

    # 默认为传统类型
    return UPDATE_TYPE_TRADITIONAL


def get_review_source_from_update_type(update_type: str) -> str:
    """
    根据update_type获取review_source分类

    Args:
        update_type: 标准化后的update_type

    Returns:
        review_source: 'persona_learning', 'style_learning', 'traditional'
    """
    normalized = normalize_update_type(update_type)

    if normalized == UPDATE_TYPE_PROGRESSIVE_PERSONA_LEARNING:
        return 'persona_learning'
    elif normalized == UPDATE_TYPE_STYLE_LEARNING:
        return 'style_learning'
    elif normalized == UPDATE_TYPE_EXPRESSION_LEARNING:
        return 'persona_learning'  # 表达学习也归类为persona_learning
    else:
        return 'traditional'
