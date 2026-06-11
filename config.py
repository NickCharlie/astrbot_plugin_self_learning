"""
自学习插件配置管理
"""
import os
import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict, ValidationError, field_validator

try:
    from .utils.logging_utils import apply_astrbot_log_level, get_astrbot_logger, normalize_log_level
except ImportError:
    from utils.logging_utils import apply_astrbot_log_level, get_astrbot_logger, normalize_log_level

logger = get_astrbot_logger("self_learning.config")

FULL_LEARNING_TARGET_MARKERS = {"*", "all", "all_users", "all_groups", "全部", "全量", "全体", "所有"}
DEFAULT_DATA_DIR = "./data/plugin_data/astrbot_plugin_self_learning"
DEFAULT_DB_TYPE = "postgresql"
SUPPORTED_DB_TYPES = {"sqlite", "mysql", "postgresql"}
POSTGRESQL_DB_TYPE_ALIASES = {"postgres", "pg", "pgsql"}
HIGH_COST_LIGHTRAG_QUERY_MODES = {"hybrid", "mix"}
LIGHTRAG_LIVINGMEMORY_COST_WARNING = (
    "当前配置选择 LightRAG 的 hybrid/mix 查询，并允许记忆委托给 LivingMemory；"
    "当 LivingMemory 插件已加载时，会叠加 LightRAG 全局/混合检索与 LivingMemory 记忆检索，"
    "可能显著增加 LLM 调用与 token 消耗。建议优先改为 local/naive，或只保留一种记忆/检索策略。"
)


def normalize_db_type(db_type: Any) -> Optional[str]:
    """Normalize configured database type, including PostgreSQL aliases."""
    value = str(db_type or DEFAULT_DB_TYPE).strip().lower()
    if value in POSTGRESQL_DB_TYPE_ALIASES:
        value = DEFAULT_DB_TYPE
    if value not in SUPPORTED_DB_TYPES:
        return None
    return value


def _read_config_value(config_like: Any, key: str, default: Any = None) -> Any:
    if isinstance(config_like, dict):
        if key in config_like:
            return config_like.get(key, default)
        for group_key in ("V2_Architecture_Settings", "Integration_Settings"):
            group = config_like.get(group_key)
            if isinstance(group, dict) and key in group:
                return group.get(key, default)
        return default
    return getattr(config_like, key, default)


def _read_config_bool(config_like: Any, key: str, default: bool = False) -> bool:
    value = _read_config_value(config_like, key, default)
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def is_lightrag_livingmemory_high_cost_config(config_like: Any) -> bool:
    """Return True for the known high-cost LightRAG + LivingMemory combination."""
    knowledge_engine = str(
        _read_config_value(config_like, "knowledge_engine", "legacy") or "legacy"
    ).strip().lower()
    query_mode = str(
        _read_config_value(config_like, "lightrag_query_mode", "local") or "local"
    ).strip().lower()
    delegate_memory = _read_config_bool(config_like, "delegate_memory_to_livingmemory")

    return (
        knowledge_engine == "lightrag"
        and query_mode in HIGH_COST_LIGHTRAG_QUERY_MODES
        and delegate_memory
    )


def get_config_cost_warnings(config_like: Any) -> List[str]:
    """Return non-blocking warnings for expensive cross-feature config combinations."""
    if is_lightrag_livingmemory_high_cost_config(config_like):
        return [LIGHTRAG_LIVINGMEMORY_COST_WARNING]
    return []


def normalize_identifier_list(value: Any, *, full_learning_markers: bool = False) -> List[str]:
    """Normalize user/group identifier lists from AstrBot settings."""
    if value is None:
        return []

    if isinstance(value, str):
        raw_items = value.replace(",", "\n").splitlines()
    elif isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        raw_items = [value]

    normalized: List[str] = []
    for item in raw_items:
        text = str(item).strip()
        if not text:
            continue
        if full_learning_markers and text.lower() in FULL_LEARNING_TARGET_MARKERS:
            return []
        normalized.append(text)

    return normalized


class PluginConfig(BaseModel):
    """插件配置类"""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    # 基础开关
    enable_message_capture: bool = True
    enable_auto_learning: bool = True
    enable_realtime_learning: bool = False
    enable_realtime_llm_filter: bool = False # 新增：控制实时LLM筛选
    enable_jargon_learning: bool = True # 启用黑话学习
    enable_style_learning: bool = True # 启用对话风格学习
    enable_web_interface: bool = True
    enable_webui_password: bool = False # 启用 WebUI 登录密码，默认免密
    webui_initial_password: str = "" # WebUI 密码首次启用时的一次性初始密码
    web_interface_port: int = 7833 # 新增 Web 界面端口配置
    web_interface_host: str = "0.0.0.0" # Web 界面监听地址

    # MaiBot增强功能（默认启用）
    enable_maibot_features: bool = True # 启用MaiBot增强功能
    enable_expression_patterns: bool = True # 启用表达模式学习
    enable_realtime_expression_learning: bool = False # 实时学习关闭时是否仍按消息触发表达学习
    enable_memory_graph: bool = True # 启用记忆图系统
    enable_knowledge_graph: bool = True # 启用知识图谱
    enable_time_decay: bool = True # 启用时间衰减机制

    # QQ号设置
    target_qq_list: List[str] = Field(default_factory=list)
    target_blacklist: List[str] = Field(default_factory=list) # 学习黑名单

    # LLM 提供商 ID（使用 AstrBot 框架的 Provider 系统）
    filter_provider_id: Optional[str] = None # 筛选模型使用的提供商ID
    refine_provider_id: Optional[str] = None # 提炼模型使用的提供商ID
    reinforce_provider_id: Optional[str] = None # 强化模型使用的提供商ID

    # v2 Architecture: Embedding provider (framework-managed)
    embedding_provider_id: Optional[str] = None

    # v2 Architecture: Reranker provider (framework-managed)
    rerank_provider_id: Optional[str] = None
    rerank_top_k: int = 5
    rerank_min_candidates: int = 3 # 候选文档数低于此阈值时跳过 rerank 以节省延迟
    provider_retry_interval_seconds: float = 10.0 # Provider 注册表未就绪时的重试间隔

    # v2 Architecture: Knowledge engine
    knowledge_engine: str = "legacy" # "lightrag" | "legacy"
    lightrag_query_mode: str = "local" # "naive" | "local" | "global" | "hybrid" | "mix"

    # v2 Architecture: Memory engine
    memory_engine: str = "legacy" # "mem0" | "legacy"

    # 功能融合：将重叠能力委托给专门插件
    delegate_memory_to_livingmemory: bool = True # 将长期记忆交给 LivingMemory
    livingmemory_plugin_name: str = "LivingMemory" # LivingMemory 插件名
    disable_local_memory_when_delegated: bool = True # 检测到 LivingMemory 时禁用本地长期记忆写入/注入
    delegate_reply_to_group_chat_plus: bool = True # 将回复决策和生成交给 Group Chat Plus
    group_chat_plus_plugin_name: str = "astrbot_plugin_group_chat_plus" # Group Chat Plus 插件名
    disable_local_reply_when_delegated: bool = True # 检测到 Group Chat Plus 时禁用本地回复器

    # 当前人格设置
    current_persona_name: str = ""

    # 学习参数
    learning_interval_hours: int = 6 # 学习间隔（小时）
    min_messages_for_learning: int = 50 # 最少消息数量才开始学习
    max_messages_per_batch: int = 200 # 每批处理的最大消息数量
    expression_learning_trigger_messages: int = 10 # 表达方式学习触发消息增量
    expression_learning_min_interval_seconds: int = 3600 # 表达方式学习最小触发间隔（秒）
    topic_detection_interval_messages: int = 10 # 话题检测触发消息增量

    # 筛选参数
    message_min_length: int = 5 # 消息最小长度
    message_max_length: int = 500 # 消息最大长度
    confidence_threshold: float = 0.7 # 筛选置信度阈值
    relevance_threshold: float = 0.6 # 相关性阈值

    # 风格分析参数
    style_analysis_batch_size: int = 100 # 风格分析批次大小
    style_update_threshold: float = 0.6 # 风格更新阈值 (降低阈值，从0.8改为0.6)

    # 消息统计
    total_messages_collected: int = 0 # 收集到的消息总数

    # 机器学习设置
    enable_ml_analysis: bool = True # 启用ML分析
    max_ml_sample_size: int = 100 # ML样本最大数量
    ml_cache_timeout_hours: int = 1 # ML缓存超时

    # 人格备份设置
    auto_backup_enabled: bool = True # 启用自动备份
    backup_interval_hours: int = 24 # 备份间隔
    max_backups_per_group: int = 10 # 每群最大备份数
    auto_apply_approved_persona: bool = False # 审查批准后自动应用到默认人格（危险功能，默认关闭）

    # 高级设置
    debug_mode: bool = False # 调试模式
    log_level: str = "info" # AstrBot日志等级: error, warning, info, debug
    save_raw_messages: bool = True # 保存原始消息
    auto_backup_interval_days: int = 7 # 自动备份间隔

    # 关停超时（秒）
    shutdown_step_timeout: int = 8       # 每个关停步骤的超时
    task_cancel_timeout: int = 3         # 后台任务取消等待超时
    service_stop_timeout: int = 5        # 单个服务停止超时
    enable_llm_hooks: bool = False       # 启用 LLM Hook 上下文注入，默认关闭以避免高频调用
    llm_hook_context_timeout: float = 3.0  # LLM Hook 单个上下文源超时（秒）

    # PersonaUpdater配置
    persona_merge_strategy: str = "smart" # 人格合并策略: "replace", "append", "prepend", "smart"
    max_mood_imitation_dialogs: int = 20 # 最大对话风格模仿数量
    enable_persona_evolution: bool = True # 启用人格演化跟踪
    persona_compatibility_threshold: float = 0.6 # 人格兼容性阈值

    # 人格更新方式配置
    use_persona_manager_updates: bool = True # 使用PersonaManager进行增量更新（False=使用文件临时存储，True=使用PersonaManager）
    auto_apply_persona_updates: bool = True # 自动应用人格更新（仅在use_persona_manager_updates=True时生效）
    persona_update_backup_enabled: bool = True # 启用更新前备份

    # 好感度系统配置
    enable_affection_system: bool = True # 启用好感度系统
    max_total_affection: int = 250 # bot总好感度满分值
    max_user_affection: int = 100 # 单个用户最大好感度
    affection_decay_rate: float = 0.95 # 好感度衰减比例
    daily_mood_change: bool = True # 启用每日情绪变化
    mood_affect_affection: bool = True # 情绪影响好感度变化

    # 情绪系统配置
    enable_daily_mood: bool = True # 启用每日情绪
    enable_startup_random_mood: bool = True # 启用启动时随机情绪初始化
    mood_change_hour: int = 6 # 情绪更新时间（24小时制）
    mood_persistence_hours: int = 24 # 情绪持续时间

    # 存储路径（内部配置，用户通常不需要修改）
    messages_db_path: Optional[str] = None
    learning_log_path: Optional[str] = None

    # 用户可配置的存储路径（放在最后，用户可以自定义）
    data_dir: str = DEFAULT_DATA_DIR # 插件数据存储目录

    # 表达模式统计时间窗口
    expression_patterns_hours: int = 24 # 表达模式统计的小时数

    # API设置
    api_key: str = "" # 外部API访问密钥
    enable_api_auth: bool = False # 是否启用API密钥认证

    # 数据库设置
    db_type: str = DEFAULT_DB_TYPE # 数据库类型: postgresql、sqlite 或 mysql

    # MySQL 配置
    mysql_host: str = "localhost" # MySQL主机地址
    mysql_port: int = 3306 # MySQL端口
    mysql_user: str = "root" # MySQL用户名
    mysql_password: str = "" # MySQL密码
    mysql_database: str = "astrbot_self_learning" # MySQL数据库名

    # PostgreSQL 配置
    postgresql_host: str = "localhost" # PostgreSQL主机地址
    postgresql_port: int = 5432 # PostgreSQL端口
    postgresql_user: str = "postgres" # PostgreSQL用户名
    postgresql_password: str = "" # PostgreSQL密码
    postgresql_database: str = "astrbot_self_learning" # PostgreSQL数据库名
    postgresql_schema: str = "public" # PostgreSQL Schema

    # 连接池配置
    max_connections: int = 10 # 数据库连接池最大连接数
    min_connections: int = 2 # 数据库连接池最小连接数

    # 社交关系注入设置（与_conf_schema.json一致）
    enable_social_context_injection: bool = True # 启用社交关系上下文注入到prompt
    include_social_relations: bool = True # 注入用户社交关系网络信息
    include_affection_info: bool = True # 注入好感度信息
    include_mood_info: bool = True # 注入Bot情绪信息
    context_injection_position: str = "start" # 上下文注入位置: "start" 或 "end"

    # LLM Hook 注入位置设置（v1.1.1新增）
    # 控制注入内容添加到 req.system_prompt 还是 req.prompt
    # - "system_prompt": 注入到系统提示（推荐，不会被保存到对话历史）
    # - "prompt": 注入到用户消息（旧版行为，会导致对话历史膨胀）
    llm_hook_injection_target: str = "system_prompt" # 可选值: "system_prompt" 或 "prompt"

    # 目标驱动对话配置
    enable_goal_driven_chat: bool = False # 启用目标驱动对话
    goal_session_timeout_hours: int = 24 # 会话超时时间（小时）
    goal_auto_detect: bool = True # 自动检测对话目标
    goal_max_conversation_history: int = 40 # 最大对话历史（轮次*2）

    # 重构功能配置（新增）
    # 强制使用 SQLAlchemy ORM：统一 PostgreSQL、SQLite 和 MySQL 的表结构定义
    use_sqlalchemy: bool = True # 硬编码为 True，确保所有数据库操作使用 ORM 模型
    enable_memory_cleanup: bool = True # 启用记忆自动清理（每天凌晨3点）
    memory_cleanup_days: int = 30 # 记忆保留天数（低于阈值的旧记忆会被清理）
    memory_importance_threshold: float = 0.3 # 记忆重要性阈值（低于此值的会被清理）

    # Repository数据访问层配置（新增）
    default_review_limit: int = 50 # 默认审查记录查询数量
    default_pattern_limit: int = 10 # 默认表达模式查询数量
    default_memory_limit: int = 50 # 默认记忆查询数量
    default_affection_limit: int = 50 # 默认好感度记录查询数量
    default_social_limit: int = 50 # 默认社交记录查询数量
    default_psychological_limit: int = 20 # 默认心理状态记录查询数量
    max_interaction_batch_size: int = 100 # 最大交互批处理数量
    top_patterns_limit: int = 10 # 顶级模式查询数量
    recent_interactions_limit: int = 20 # 近期交互查询数量
    trend_analysis_days: int = 7 # 趋势分析天数

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level_field(cls, value) -> str:
        normalized = normalize_log_level(value, fallback="")
        if normalized not in {"error", "warning", "info", "debug"}:
            raise ValueError("日志等级必须是 error、warning、info 或 debug")
        return normalized

    @field_validator("target_qq_list", mode="before")
    @classmethod
    def _normalize_target_qq_list(cls, value) -> List[str]:
        return normalize_identifier_list(value, full_learning_markers=True)

    @field_validator("target_blacklist", mode="before")
    @classmethod
    def _normalize_target_blacklist(cls, value) -> List[str]:
        return normalize_identifier_list(value)

    def model_post_init(self, __context) -> None:
        """Normalize and apply the configured AstrBot log level."""
        normalized_level = normalize_log_level(
            self.log_level,
            debug_mode=self.debug_mode,
            fallback="info",
        )
        self.log_level = normalized_level
        apply_astrbot_log_level(
            normalized_level,
            debug_mode=self.debug_mode,
            fallback="info",
        )

    @classmethod
    def create_from_config(cls, config: dict, data_dir: Optional[str] = None) -> 'PluginConfig':
        """从AstrBot配置创建插件配置"""

        # 确保 data_dir 不为空
        if not data_dir:
            data_dir = DEFAULT_DATA_DIR
            logger.warning(f"data_dir 为空，使用默认值: {data_dir}")

        # 从配置中提取各个配置组
        # 根据 _conf_schema.json 的结构，配置项是直接在顶层，而不是嵌套在 'self_learning_settings' 下
        basic_settings = config.get('Self_Learning_Basic', {})
        target_settings = config.get('Target_Settings', {})
        model_configuration = config.get('Model_Configuration', {})

        # 添加调试日志：显示原始配置数据
        logger.info(f" [配置加载] Model_Configuration原始数据: {model_configuration}")
        logger.info(f" [配置加载] filter_provider_id: {model_configuration.get('filter_provider_id', 'NOT_FOUND')}")
        logger.info(f" [配置加载] refine_provider_id: {model_configuration.get('refine_provider_id', 'NOT_FOUND')}")
        logger.info(f" [配置加载] reinforce_provider_id: {model_configuration.get('reinforce_provider_id', 'NOT_FOUND')}")

        learning_params = config.get('Learning_Parameters', {})
        filter_params = config.get('Filter_Parameters', {})
        style_analysis = config.get('Style_Analysis', {})
        advanced_settings = config.get('Advanced_Settings', {})
        debug_mode = advanced_settings.get('debug_mode', False)
        ml_settings = config.get('Machine_Learning_Settings', {})
        persona_backup_settings = config.get('Persona_Backup_Settings', {})
        affection_settings = config.get('Affection_System_Settings', {})
        mood_settings = config.get('Mood_System_Settings', {})
        storage_settings = config.get('Storage_Settings', {})
        api_settings = config.get('API_Settings', {})
        database_settings = config.get('Database_Settings', {}) # 新增：数据库设置
        social_context_settings = config.get('Social_Context_Settings', {}) # 新增：社交上下文设置
        repository_settings = config.get('Repository_Settings', {}) # 新增：Repository配置
        goal_driven_chat_settings = config.get('Goal_Driven_Chat_Settings', {}) # 新增：目标驱动对话设置
        v2_settings = config.get('V2_Architecture_Settings', {}) # v2架构升级设置
        integration_settings = config.get('Integration_Settings', {}) # 功能融合设置
        maibot_enhancement = config.get('MaiBot_Enhancement', {})
        persona_evolution_settings = config.get('Persona_Evolution_Settings', {})
        runtime_internal_settings = config.get('Runtime_Internal_Settings', {})

        # 添加调试日志：显示目标驱动对话配置数据
        logger.info(f" [配置加载] Goal_Driven_Chat_Settings原始数据: {goal_driven_chat_settings}")
        logger.info(f" [配置加载] enable_goal_driven_chat: {goal_driven_chat_settings.get('enable_goal_driven_chat', 'NOT_FOUND')}")

        return cls(
            enable_message_capture=basic_settings.get('enable_message_capture', True),
            enable_auto_learning=basic_settings.get('enable_auto_learning', True),
            enable_realtime_learning=basic_settings.get('enable_realtime_learning', False),
            enable_realtime_llm_filter=basic_settings.get('enable_realtime_llm_filter', False),
            enable_jargon_learning=basic_settings.get('enable_jargon_learning', True),
            enable_style_learning=basic_settings.get('enable_style_learning', True),
            enable_web_interface=basic_settings.get('enable_web_interface', True),
            enable_webui_password=basic_settings.get('enable_webui_password', False),
            webui_initial_password=basic_settings.get('webui_initial_password', ''),
            web_interface_port=basic_settings.get('web_interface_port', 7833),
            web_interface_host=basic_settings.get('web_interface_host', '0.0.0.0'),

            enable_maibot_features=maibot_enhancement.get('enable_maibot_features', True),
            enable_expression_patterns=maibot_enhancement.get('enable_expression_patterns', True),
            enable_realtime_expression_learning=maibot_enhancement.get('enable_realtime_expression_learning', False),
            enable_memory_graph=maibot_enhancement.get('enable_memory_graph', True),
            enable_knowledge_graph=maibot_enhancement.get('enable_knowledge_graph', True),
            enable_time_decay=maibot_enhancement.get('enable_time_decay', True),

            target_qq_list=target_settings.get('target_qq_list', []),
            target_blacklist=target_settings.get('target_blacklist', []),
            current_persona_name=target_settings.get('current_persona_name', ''),

            filter_provider_id=model_configuration.get('filter_provider_id', None),
            refine_provider_id=model_configuration.get('refine_provider_id', None),
            reinforce_provider_id=model_configuration.get('reinforce_provider_id', None),

            # v2 Architecture
            embedding_provider_id=v2_settings.get('embedding_provider_id', None),
            rerank_provider_id=v2_settings.get('rerank_provider_id', None),
            rerank_top_k=v2_settings.get('rerank_top_k', 5),
            rerank_min_candidates=v2_settings.get('rerank_min_candidates', 3),
            provider_retry_interval_seconds=v2_settings.get(
                'provider_retry_interval_seconds', 10.0
            ),
            knowledge_engine=v2_settings.get('knowledge_engine', 'legacy'),
            lightrag_query_mode=v2_settings.get('lightrag_query_mode', 'local'),
            memory_engine=v2_settings.get('memory_engine', 'legacy'),

            # 功能融合设置
            delegate_memory_to_livingmemory=integration_settings.get('delegate_memory_to_livingmemory', True),
            livingmemory_plugin_name=integration_settings.get('livingmemory_plugin_name', 'LivingMemory'),
            disable_local_memory_when_delegated=integration_settings.get('disable_local_memory_when_delegated', True),
            delegate_reply_to_group_chat_plus=integration_settings.get('delegate_reply_to_group_chat_plus', True),
            group_chat_plus_plugin_name=integration_settings.get('group_chat_plus_plugin_name', 'astrbot_plugin_group_chat_plus'),
            disable_local_reply_when_delegated=integration_settings.get('disable_local_reply_when_delegated', True),

            learning_interval_hours=learning_params.get('learning_interval_hours', 6),
            min_messages_for_learning=learning_params.get('min_messages_for_learning', 50),
            max_messages_per_batch=learning_params.get('max_messages_per_batch', 200),
            expression_learning_trigger_messages=learning_params.get('expression_learning_trigger_messages', 10),
            expression_learning_min_interval_seconds=learning_params.get('expression_learning_min_interval_seconds', 3600),
            topic_detection_interval_messages=learning_params.get('topic_detection_interval_messages', 10),

            message_min_length=filter_params.get('message_min_length', 5),
            message_max_length=filter_params.get('message_max_length', 500),
            confidence_threshold=filter_params.get('confidence_threshold', 0.7),
            relevance_threshold=filter_params.get('relevance_threshold', 0.6),

            style_analysis_batch_size=style_analysis.get('style_analysis_batch_size', 100),
            style_update_threshold=style_analysis.get('style_update_threshold', 0.6),

            # 消息统计 (这个字段通常不是从外部配置加载，而是内部维护的，这里保留默认值)
            total_messages_collected=0,

            enable_ml_analysis=ml_settings.get('enable_ml_analysis', True),
            max_ml_sample_size=ml_settings.get('max_ml_sample_size', 100),
            ml_cache_timeout_hours=ml_settings.get('ml_cache_timeout_hours', 1),

            auto_backup_enabled=persona_backup_settings.get('auto_backup_enabled', True),
            backup_interval_hours=persona_backup_settings.get('backup_interval_hours', 24),
            max_backups_per_group=persona_backup_settings.get('max_backups_per_group', 10),
            auto_apply_approved_persona=advanced_settings.get('auto_apply_approved_persona', False),

            debug_mode=debug_mode,
            log_level=advanced_settings.get('log_level', 'debug' if debug_mode else 'info'),
            save_raw_messages=advanced_settings.get('save_raw_messages', True),
            auto_backup_interval_days=advanced_settings.get('auto_backup_interval_days', 7),

            # 好感度系统配置
            enable_affection_system=affection_settings.get('enable_affection_system', True),
            max_total_affection=affection_settings.get('max_total_affection', 250),
            max_user_affection=affection_settings.get('max_user_affection', 100),
            affection_decay_rate=affection_settings.get('affection_decay_rate', 0.95),
            daily_mood_change=affection_settings.get('daily_mood_change', True),
            mood_affect_affection=affection_settings.get('mood_affect_affection', True),

            # 情绪系统配置
            enable_daily_mood=mood_settings.get('enable_daily_mood', True),
            enable_startup_random_mood=mood_settings.get('enable_startup_random_mood', True),
            mood_change_hour=mood_settings.get('mood_change_hour', 6),
            mood_persistence_hours=mood_settings.get('mood_persistence_hours', 24),

            # PersonaUpdater配置
            persona_merge_strategy=persona_evolution_settings.get(
                'persona_merge_strategy',
                config.get('persona_merge_strategy', 'smart'),
            ),
            max_mood_imitation_dialogs=persona_evolution_settings.get(
                'max_mood_imitation_dialogs',
                config.get('max_mood_imitation_dialogs', 20),
            ),
            enable_persona_evolution=persona_evolution_settings.get(
                'enable_persona_evolution',
                config.get('enable_persona_evolution', True),
            ),
            persona_compatibility_threshold=persona_evolution_settings.get(
                'persona_compatibility_threshold',
                config.get('persona_compatibility_threshold', 0.6),
            ),
            use_persona_manager_updates=persona_evolution_settings.get('use_persona_manager_updates', True),
            auto_apply_persona_updates=persona_evolution_settings.get('auto_apply_persona_updates', True),
            persona_update_backup_enabled=persona_evolution_settings.get('persona_update_backup_enabled', True),

            # API设置
            api_key=api_settings.get('api_key', ''),
            enable_api_auth=api_settings.get('enable_api_auth', False),

            # 数据库设置
            db_type=database_settings.get('db_type', DEFAULT_DB_TYPE),
            mysql_host=database_settings.get('mysql_host', 'localhost'),
            mysql_port=database_settings.get('mysql_port', 3306),
            mysql_user=database_settings.get('mysql_user', 'root'),
            mysql_password=database_settings.get('mysql_password', ''),
            mysql_database=database_settings.get('mysql_database', 'astrbot_self_learning'),
            postgresql_host=database_settings.get('postgresql_host', 'localhost'),
            postgresql_port=database_settings.get('postgresql_port', 5432),
            postgresql_user=database_settings.get('postgresql_user', 'postgres'),
            postgresql_password=database_settings.get('postgresql_password', ''),
            postgresql_database=database_settings.get('postgresql_database', 'astrbot_self_learning'),
            postgresql_schema=database_settings.get('postgresql_schema', 'public'),
            max_connections=database_settings.get('max_connections', 10),
            min_connections=database_settings.get('min_connections', 2),

            # 重构功能配置
            # 强制使用 SQLAlchemy ORM，忽略配置文件中的设置
            use_sqlalchemy=True, # 硬编码为 True
            enable_memory_cleanup=runtime_internal_settings.get(
                'enable_memory_cleanup',
                advanced_settings.get('enable_memory_cleanup', True),
            ),
            memory_cleanup_days=runtime_internal_settings.get(
                'memory_cleanup_days',
                advanced_settings.get('memory_cleanup_days', 30),
            ),
            memory_importance_threshold=runtime_internal_settings.get(
                'memory_importance_threshold',
                advanced_settings.get('memory_importance_threshold', 0.3),
            ),
            shutdown_step_timeout=runtime_internal_settings.get('shutdown_step_timeout', 8),
            task_cancel_timeout=runtime_internal_settings.get('task_cancel_timeout', 3),
            service_stop_timeout=runtime_internal_settings.get('service_stop_timeout', 5),
            enable_llm_hooks=runtime_internal_settings.get('enable_llm_hooks', False),
            llm_hook_context_timeout=float(runtime_internal_settings.get('llm_hook_context_timeout', 3.0)),
            llm_hook_injection_target=runtime_internal_settings.get(
                'llm_hook_injection_target',
                'system_prompt',
            ),

            # 社交上下文注入设置
            enable_social_context_injection=social_context_settings.get('enable_social_context_injection', True),
            include_social_relations=social_context_settings.get('include_social_relations', True),
            include_affection_info=social_context_settings.get('include_affection_info', True),
            include_mood_info=social_context_settings.get('include_mood_info', True),
            context_injection_position=social_context_settings.get('context_injection_position', 'start'),
            expression_patterns_hours=social_context_settings.get('expression_patterns_hours', 24),

            # 目标驱动对话设置
            enable_goal_driven_chat=goal_driven_chat_settings.get('enable_goal_driven_chat', False),
            goal_session_timeout_hours=goal_driven_chat_settings.get('goal_session_timeout_hours', 24),
            goal_auto_detect=goal_driven_chat_settings.get('goal_auto_detect', True),
            goal_max_conversation_history=goal_driven_chat_settings.get('goal_max_conversation_history', 40),

            # Repository数据访问层配置
            default_review_limit=repository_settings.get('default_review_limit', 50),
            default_pattern_limit=repository_settings.get('default_pattern_limit', 10),
            default_memory_limit=repository_settings.get('default_memory_limit', 50),
            default_affection_limit=repository_settings.get('default_affection_limit', 50),
            default_social_limit=repository_settings.get('default_social_limit', 50),
            default_psychological_limit=repository_settings.get('default_psychological_limit', 20),
            max_interaction_batch_size=repository_settings.get('max_interaction_batch_size', 100),
            top_patterns_limit=repository_settings.get('top_patterns_limit', 10),
            recent_interactions_limit=repository_settings.get('recent_interactions_limit', 20),
            trend_analysis_days=repository_settings.get('trend_analysis_days', 7),

            # 传入数据目录 - 优先级：外部传入 > 配置文件 > 存储设置 > 默认值
            data_dir=data_dir if data_dir else storage_settings.get('data_dir', DEFAULT_DATA_DIR)
        )

    @classmethod
    def _flatten_config_payload(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Flatten grouped config with direct fields taking precedence."""
        grouped: Dict[str, Any] = {}
        direct: Dict[str, Any] = {}
        for key, value in payload.items():
            if isinstance(value, dict) and key not in cls.model_fields:
                nested = cls._flatten_config_payload(value)
                duplicated = sorted(set(grouped) & set(nested))
                if duplicated:
                    logger.info(
                        "持久化配置分组字段覆盖较早分组字段: "
                        f"{', '.join(duplicated)}"
                    )
                grouped.update(nested)
            else:
                direct[key] = value

        duplicated = sorted(set(grouped) & set(direct))
        if duplicated:
            logger.info(
                "持久化配置顶层字段覆盖分组字段: "
                f"{', '.join(duplicated)}"
            )

        return {**grouped, **direct}

    @classmethod
    def create_from_runtime_sources(
        cls,
        config: dict,
        data_dir: Optional[str] = None,
        config_file: Optional[str] = None,
    ) -> 'PluginConfig':
        """Create config from AstrBot settings and optional persisted WebUI config."""
        runtime_config = cls.create_from_config(config or {}, data_dir=data_dir)
        if not config_file or not os.path.exists(config_file):
            return runtime_config

        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                persisted_data = json.load(f)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
            logger.warning(f"读取持久化配置失败，继续使用AstrBot配置: {e}")
            return runtime_config

        if not isinstance(persisted_data, dict):
            logger.warning("持久化配置格式无效，继续使用AstrBot配置")
            return runtime_config

        merged = runtime_config.to_dict()
        persisted_config = cls._flatten_config_payload(persisted_data)
        overridden = sorted(
            key
            for key, value in persisted_config.items()
            if key in merged and merged[key] != value
        )
        if overridden:
            logger.info(
                "持久化配置覆盖AstrBot运行时字段: "
                f"{', '.join(overridden)}"
            )
        merged.update(persisted_config)

        try:
            loaded_config = cls.model_validate(merged)
        except ValidationError as e:
            logger.warning(f"持久化配置校验失败，继续使用AstrBot配置: {e}")
            return runtime_config

        logger.info(f"已加载持久化插件配置: {config_file}")
        return loaded_config

    @classmethod
    def create_default(cls) -> 'PluginConfig':
        """创建默认配置"""
        return cls()

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return self.model_dump()

    def validate_config(self) -> List[str]:
        """验证配置有效性，返回错误信息列表"""
        errors = []

        if self.learning_interval_hours <= 0:
            errors.append("学习间隔必须大于0小时")

        if self.min_messages_for_learning <= 0:
            errors.append("最少学习消息数量必须大于0")

        if self.max_messages_per_batch <= 0:
            errors.append("每批最大消息数量必须大于0")

        if self.expression_learning_trigger_messages <= 0:
            errors.append("表达方式学习触发消息数必须大于0")

        if self.expression_learning_min_interval_seconds < 0:
            errors.append("表达方式学习最小触发间隔不能小于0秒")

        if self.topic_detection_interval_messages <= 0:
            errors.append("话题检测触发消息数必须大于0")

        if self.provider_retry_interval_seconds <= 0:
            errors.append("Provider重试间隔必须大于0秒")

        if self.message_min_length >= self.message_max_length:
            errors.append("消息最小长度必须小于最大长度")

        if not 0 <= self.confidence_threshold <= 1:
            errors.append("置信度阈值必须在0-1之间")

        if not 0 <= self.style_update_threshold <= 1:
            errors.append("风格更新阈值必须在0-1之间")

        if normalize_log_level(self.log_level, fallback="") not in {'error', 'warning', 'info', 'debug'}:
            errors.append("日志等级必须是 error、warning、info 或 debug")

        db_type = normalize_db_type(self.db_type)
        if db_type is None:
            errors.append("数据库类型必须是 postgresql、sqlite 或 mysql")
        if db_type == 'mysql' and self.mysql_port <= 0:
            errors.append("MySQL 端口必须大于0")
        if db_type == 'postgresql':
            if self.postgresql_port <= 0:
                errors.append("PostgreSQL 端口必须大于0")
            if not (self.postgresql_schema or '').strip():
                errors.append("PostgreSQL schema 不能为空")

        # 提示性警告而非错误
        errors.extend(f" {warning}" for warning in get_config_cost_warnings(self))

        provider_warnings = []
        if not self.filter_provider_id:
            provider_warnings.append("未配置筛选模型提供商ID，将尝试自动配置或使用备选模型")

        if not self.refine_provider_id:
            provider_warnings.append("未配置提炼模型提供商ID，将尝试自动配置或使用备选模型")

        if not self.reinforce_provider_id:
            provider_warnings.append("未配置强化模型提供商ID，将尝试自动配置或使用备选模型")

        # 只有当没有配置任何Provider时才作为错误
        if not self.filter_provider_id and not self.refine_provider_id and not self.reinforce_provider_id:
            errors.append("至少需要配置一个模型提供商ID，建议在AstrBot中配置Provider并在插件配置中指定")
        elif provider_warnings:
            # 将警告添加到错误列表用于信息展示（但不会阻止插件运行）
            errors.extend([f" {warning}" for warning in provider_warnings])

        return errors

    def save_to_file(self, filepath: str) -> bool:
        """保存配置到文件"""
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(self.model_dump_json(indent=2))
            logger.info(f"配置已保存到: {filepath}")
            return True
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            return False

    @classmethod
    def load_from_file(cls, filepath: str, data_dir: Optional[str] = None) -> 'PluginConfig':
        """从文件加载配置"""
        try:
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)

                # 设置 data_dir
                if data_dir:
                    config_data['data_dir'] = data_dir

                # 创建配置实例（extra="ignore" 会忽略未知字段）
                config = cls.model_validate(config_data)
                logger.info(f"配置已从文件加载: {filepath}")
                return config
            else:
                logger.info(f"配置文件不存在，使用默认配置: {filepath}")
                config = cls()
                if data_dir:
                    config.data_dir = data_dir
                return config
        except Exception as e:
            logger.error(f"加载配置失败: {e}，使用默认配置")
            config = cls()
            if data_dir:
                config.data_dir = data_dir
            return config
