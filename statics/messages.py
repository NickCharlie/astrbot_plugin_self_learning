"""
消息和字符串常量模块
用于集中管理插件中所有的硬编码字符串
"""


class StatusMessages:
    """状态和信息提示消息"""
    WEB_INTERFACE_ENABLED = "Web 界面已启用，将在 http://{host}:{port} 启动"
    WEB_SERVER_STARTING = "开始启动 Web 服务器..."
    WEB_SERVER_STARTED = "Web 服务器启动成功"
    WEB_SERVER_TASK_CREATED = "Web 服务器启动任务已创建"
    WEB_INTERFACE_INIT_FAILED = "Web 界面初始化失败"
    WEB_INTERFACE_DISABLED = "Web 界面未启用"
    PLUGIN_INITIALIZED = "自学习插件初始化完成"
    PLUGIN_LOAD_COMPLETE = "自学习插件加载完成"
    DB_MANAGER_STARTED = "数据库管理器启动完成"
    FACTORY_SERVICES_INIT_COMPLETE = "自学习插件工厂模式服务层初始化完成"
    
    # 错误消息
    WEB_SERVER_START_FAILED = "Web 服务器启动失败: {error}"
    DB_MANAGER_START_FAILED = "数据库管理器启动失败: {error}"
    SERVICES_INIT_FAILED = "自学习服务初始化失败: {error}"
    CONFIG_TYPE_ERROR = "服务层初始化过程中发生配置或类型错误: {error}"
    UNKNOWN_INIT_ERROR = "服务层初始化过程中发生未知错误: {error}"
    INIT_FAILED_GENERIC = "插件初始化失败: {error}"
    LEARNING_SERVICE_START_FAILED = "启动学习服务失败 for group {group_id}: {error}"
    AUTO_LEARNING_SCHEDULER_STARTED = "自动学习调度器已启动 for group {group_id}"
    MESSAGE_COLLECTION_ERROR = "消息收集过程中发生未知错误: {error}"
    REALTIME_PROCESSING_ERROR = "实时消息处理过程中发生未知错误: {error}"
    
    # on_load 相关消息
    ON_LOAD_START = "开始执行 on_load 方法"
    WEB_SERVER_PREPARE = "准备启动 Web 服务器，地址: {host}:{port}"
    WEB_INTERFACE_DISABLED_SKIP = "Web 界面被禁用，跳过服务器启动"
    SERVER_INSTANCE_NULL = "Server 实例为 None，无法启动 Web 服务器"


class CommandMessages:
    """命令响应消息"""
    LEARNING_STARTED = "✅ 自动学习已启动 for group {group_id}"
    LEARNING_RUNNING = "📚 自动学习已在运行中 for group {group_id}"
    LEARNING_STOPPED = "⏹️ 自动学习已停止 for group {group_id}"
    FORCE_LEARNING_START = "🔄 开始强制学习周期 for group {group_id}..."
    FORCE_LEARNING_COMPLETE = "✅ 强制学习周期完成 for group {group_id}"
    DATA_CLEARED = "🗑️ 所有学习数据已清空"
    DATA_EXPORTED = "📤 学习数据已导出到: {filepath}"
    
    # 状态报告模板
    STATUS_REPORT_HEADER = "📚 自学习插件状态报告 (会话ID: {group_id}):"
    STATUS_BASIC_CONFIG = """
🔧 基础配置:
- 消息抓取: {message_capture}
- 自主学习: {auto_learning}
- 实时学习: {realtime_learning}
- Web界面: {web_interface}"""
    
    STATUS_CAPTURE_SETTINGS = """
👥 抓取设置:
- 目标QQ: {target_qq}
- 当前人格: {current_persona}"""
    
    STATUS_MODEL_CONFIG = """
🤖 模型配置:
- 筛选模型: {filter_model}
- 提炼模型: {refine_model}"""
    
    STATUS_LEARNING_STATS = """
📊 学习统计 (当前会话):
- 总收集消息: {total_messages}
- 筛选消息: {filtered_messages}
- 风格更新次数: {style_updates}
- 最后学习时间: {last_learning_time}"""
    
    STATUS_STORAGE_STATS = """
💾 存储统计 (当前会话):
- 原始消息: {raw_messages} 条
- 待处理消息: {unprocessed_messages} 条
- 筛选过的消息: {filtered_messages} 条"""
    
    STATUS_SCHEDULER = "⏰ 调度状态 (当前会话): {status}"
    
    # 好感度系统消息
    AFFECTION_DISABLED = "❌ 好感度系统未启用"
    AFFECTION_STATUS_HEADER = "💝 好感度系统状态 (群组: {group_id}):"
    AFFECTION_USER_LEVEL = "👤 您的好感度: {user_level}/{max_affection}"
    AFFECTION_TOTAL_STATUS = "📊 总好感度: {total_affection}/{max_total_affection}"
    AFFECTION_USER_COUNT = "👥 用户数量: {user_count}"
    AFFECTION_CURRENT_MOOD = "🎭 当前情绪:"
    AFFECTION_MOOD_TYPE = "- 类型: {mood_type}"
    AFFECTION_MOOD_INTENSITY = "- 强度: {intensity:.2f}"
    AFFECTION_MOOD_DESCRIPTION = "- 描述: {description}"
    AFFECTION_NO_MOOD = "- 无当前情绪状态"
    AFFECTION_TOP_USERS = "🏆 好感度排行榜:"
    AFFECTION_USER_RANK = "{rank}. 用户 {user_id}: {affection_level}点"
    
    # 设置情绪命令
    SET_MOOD_USAGE = "请指定情绪类型，如: /set_mood happy"
    SET_MOOD_INVALID = "无效的情绪类型。有效选项: {valid_moods}"
    SET_MOOD_SUCCESS = "🎭 已设置新的情绪状态:\n类型: {mood_type}\n强度: {intensity:.2f}\n描述: {description}"
    
    # 分析报告消息
    ANALYTICS_GENERATING = "📊 正在生成数据分析报告..."
    ANALYTICS_REPORT_HEADER = "📈 数据分析报告 (群组: {group_id}):"
    ANALYTICS_LEARNING_STATS = """
📚 学习统计:
- 处理消息数: {total_messages}
- 学习会话数: {learning_sessions}
- 平均质量分: {avg_quality:.2f}"""
    
    ANALYTICS_USER_BEHAVIOR = """
👥 用户行为模式:
- 活跃用户数: {active_users}
- 主要话题: {main_topics}
- 情感倾向: {emotion_tendency}"""
    
    ANALYTICS_RECOMMENDATIONS = "💡 建议:\n- {recommendations}"
    
    # 人格切换消息
    PERSONA_SWITCH_USAGE = "请指定人格名称，如: /persona_switch friendly"
    PERSONA_SWITCH_SUCCESS = "✅ 已切换到人格: {persona_name}"
    PERSONA_SWITCH_FAILED = "❌ 人格切换失败，请检查人格名称是否正确"
    
    # 人格更新和显示消息
    PERSONA_UPDATE_HEADER = "🎭 人格更新报告 (群组: {group_id}):"
    PERSONA_UPDATE_SUCCESS = "✅ 人格更新成功完成"
    PERSONA_UPDATE_FAILED = "❌ 人格更新失败: {error}"
    PERSONA_BEFORE_AFTER = """
📝 人格变化对比:

【更新前】
{before_content}

【更新后】
{after_content}

📊 变化摘要:
{change_summary}"""
    
    PERSONA_CURRENT_DISPLAY = """
🎭 当前人格信息:

📛 人格名称: {persona_name}
📝 人格描述:
{persona_prompt}

📈 学习统计:
- 更新次数: {update_count}
- 最后更新: {last_update}
- 学习质量: {quality_score:.2f}/10"""
    
    PERSONA_BACKUP_STATUS = """
💾 备份状态:
- 总备份数: {total_backups}
- 最新备份: {latest_backup}
- 自动备份: {auto_backup_status}"""
    
    PERSONA_STYLE_FEATURES = """
🎨 学习到的风格特征:
{style_features}"""
    
    PERSONA_CHANGE_SUMMARY = """
📊 本次更新内容:
- Prompt长度: {prompt_length_before} → {prompt_length_after} ({length_change})
- 新增特征: {new_features_count} 项
- 风格调整: {style_adjustments}
- 更新原因: {update_reason}"""
    
    # 错误消息
    ERROR_GET_LEARNING_STATUS = "获取学习状态失败: {error}"
    ERROR_START_LEARNING = "启动学习失败: {error}"
    ERROR_STOP_LEARNING = "停止学习失败: {error}"
    ERROR_FORCE_LEARNING = "强制学习失败: {error}"
    ERROR_CLEAR_DATA = "清空数据失败: {error}"
    ERROR_EXPORT_DATA = "导出数据失败: {error}"
    ERROR_GET_AFFECTION_STATUS = "获取好感度状态失败: {error}"
    ERROR_SET_MOOD = "设置情绪失败: {error}"
    ERROR_ANALYTICS_REPORT = "生成分析报告失败: {error}"
    ERROR_PERSONA_SWITCH = "人格切换失败: {error}"
    
    # 状态查询失败
    STATUS_QUERY_FAILED = "状态查询失败: {error}"
    STARTUP_FAILED = "启动失败: {error}"
    STOP_FAILED = "停止失败: {error}"
    
    # 状态指示符
    STATUS_ENABLED = "✅ 启用"
    STATUS_DISABLED = "❌ 禁用"
    STATUS_RUNNING = "🟢 运行中"
    STATUS_STOPPED = "🔴 已停止"
    STATUS_ALL_USERS = "全部用户"
    STATUS_UNKNOWN = "未知"
    STATUS_NEVER_EXECUTED = "从未执行"


class DatabaseMessages:
    """数据库相关消息"""
    MANAGER_INITIALIZED = "数据库管理器初始化完成"
    GLOBAL_INIT_SUCCESS = "全局消息数据库初始化成功"
    GLOBAL_INIT_FAILED = "全局消息数据库初始化失败: {error}"
    CONNECTIONS_CLOSED = "所有数据库连接已关闭"
    GLOBAL_INIT_COMPLETE = "全局消息数据库初始化完成"


class ServiceMessages:
    """服务相关消息"""
    PERSONA_MANAGER_STARTED = "PersonaManagerService started."
    PERSONA_MANAGER_STOPPED = "PersonaManagerService stopped."
    PERSONA_UPDATING = "PersonaManagerService: Updating persona for group {group_id}..."
    PERSONA_UPDATE_SUCCESS = "PersonaManagerService: Persona updated successfully for group {group_id}."
    PERSONA_UPDATE_FAILED = "PersonaManagerService: Persona update failed via PersonaUpdater for group {group_id}."


class WebUIMessages:
    """Web UI 相关消息"""
    AUTH_REQUIRED = "Authentication required"
    LOGIN_SUCCESS = "Login successful"
    LOGIN_SUCCESS_MUST_CHANGE = "Login successful, but password must be changed"
    PASSWORD_CHANGED = "Password changed successfully"
    LOGOUT_SUCCESS = "Logged out successfully"
    INVALID_PASSWORD = "Invalid password"
    INVALID_OLD_PASSWORD = "Invalid old password"
    
    # API 错误消息
    ERROR_PLUGIN_CONFIG_NOT_INIT = "Plugin config not initialized"
    ERROR_PERSONA_UPDATER_NOT_INIT = "Persona updater not initialized"
    ERROR_FAILED_UPDATE_REVIEW = "Failed to update persona review status"


class FileNames:
    """文件和路径名称"""
    PASSWORD_CONFIG_FILE = "password.json"
    CONFIG_FILE = "config.json"
    EXPORT_FILENAME_TEMPLATE = "learning_data_export_{timestamp}.json"
    DB_GROUP_FILE_TEMPLATE = "{group_id}_ID.db"
    MESSAGES_DB_FILE = "messages.db"
    LEARNING_LOG_FILE = "learning.log"


class TemplateNames:
    """HTML 模板名称"""
    LOGIN = "login.html"
    INDEX = "index.html"
    CHANGE_PASSWORD = "change_password.html"


class RouteNames:
    """路由路径"""
    API_LOGIN = "/api/login"
    API_INDEX = "/api/index"
    API_CHANGE_PASSWORD = "/api/plugin_change_password"
    API_LOGOUT = "/api/logout"


class ConfigSections:
    """配置文件分组名称"""
    BASIC_SETTINGS = 'Self_Learning_Basic'
    TARGET_SETTINGS = 'Target_Settings'
    MODEL_CONFIG = 'Model_Configuration'
    LEARNING_PARAMS = 'Learning_Parameters'
    FILTER_PARAMS = 'Filter_Parameters'
    STYLE_ANALYSIS = 'Style_Analysis'
    ADVANCED_SETTINGS = 'Advanced_Settings'
    ML_SETTINGS = 'Machine_Learning_Settings'
    INTELLIGENT_REPLY_SETTINGS = 'Intelligent_Reply_Settings'
    PERSONA_BACKUP_SETTINGS = 'Persona_Backup_Settings'


class ValidationMessages:
    """配置验证错误消息"""
    LEARNING_INTERVAL_ERROR = "学习间隔必须大于0小时"
    MIN_MESSAGES_ERROR = "最少学习消息数量必须大于0"
    MAX_MESSAGES_ERROR = "每批最大消息数量必须大于0"
    MESSAGE_LENGTH_ERROR = "消息最小长度必须小于最大长度"
    CONFIDENCE_THRESHOLD_ERROR = "置信度阈值必须在0-1之间"
    STYLE_THRESHOLD_ERROR = "风格更新阈值必须在0-1之间"
    FILTER_MODEL_ERROR = "筛选模型名称不能为空"
    REFINE_MODEL_ERROR = "提炼模型名称不能为空"
    REINFORCE_MODEL_ERROR = "强化模型名称不能为空"


class DefaultValues:
    """默认值"""
    DEFAULT_PASSWORD_CONFIG = {"password": "self_learning_pwd", "must_change": True}
    VALID_MOOD_TYPES = ['happy', 'sad', 'excited', 'calm', 'angry', 'anxious', 'playful', 'serious', 'nostalgic', 'curious']


class LogMessages:
    """日志消息"""
    WEB_INTERFACE_ENABLED_LOG = "Web 界面已启用，将在 http://{host}:{port} 启动"
    INTELLIGENT_REPLY_DETECTED = "检测到需要智能回复，增强提示词: {prompt_preview}..."
    AFFECTION_PROCESSING_SUCCESS = "好感度处理成功: {result}"
    AFFECTION_PROCESSING_FAILED = "好感度系统处理失败: {error}"
    ENHANCED_INTERACTION_FAILED = "增强交互处理失败: {error}"
    LLM_REQUEST_HOOK_SUCCESS = "已注入情绪状态到system_prompt，群组: {group_id}"
    LLM_REQUEST_HOOK_FAILED = "LLM请求hook处理失败: {error}"
    PLUGIN_CONFIG_SAVED = "插件配置已保存"
    PLUGIN_UNLOAD_SUCCESS = "自学习插件已安全卸载"
    PLUGIN_UNLOAD_CLEANUP_FAILED = "插件卸载清理失败: {error}"
    BACKGROUND_TASK_CANCEL_ERROR = "取消后台任务时发生错误: {error}"


class SQLQueries:
    """SQL 查询模板"""
    CREATE_RAW_MESSAGES = '''
    CREATE TABLE IF NOT EXISTS raw_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id TEXT NOT NULL,
        sender_name TEXT,
        message TEXT NOT NULL,
        timestamp REAL NOT NULL,
        platform TEXT,
        processed BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    '''
    
    CREATE_FILTERED_MESSAGES = '''
    CREATE TABLE IF NOT EXISTS filtered_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        raw_message_id INTEGER,
        message TEXT NOT NULL,
        sender_id TEXT NOT NULL,
        timestamp REAL NOT NULL,
        confidence REAL,
        quality_score REAL,
        style_features TEXT,
        used_in_learning BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (raw_message_id) REFERENCES raw_messages (id)
    )
    '''
    
    CREATE_LEARNING_BATCHES = '''
    CREATE TABLE IF NOT EXISTS learning_batches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id TEXT UNIQUE NOT NULL,
        start_time TIMESTAMP,
        end_time TIMESTAMP,
        messages_count INTEGER,
        style_updates INTEGER DEFAULT 0,
        persona_updated BOOLEAN DEFAULT FALSE,
        batch_quality REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    '''
    
    CREATE_PERSONA_UPDATE_RECORDS = '''
    CREATE TABLE IF NOT EXISTS persona_update_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id TEXT NOT NULL,
        old_persona TEXT,
        new_persona TEXT,
        update_reason TEXT,
        confidence REAL,
        approved BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (batch_id) REFERENCES learning_batches (batch_id)
    )
    '''


# ============================================================
# 更新类型常量和辅助函数（用于人格审查服务的统一类型标准化）
# ============================================================

UPDATE_TYPE_STYLE_LEARNING = 'style_learning'
UPDATE_TYPE_PERSONA_LEARNING = 'persona_learning'
UPDATE_TYPE_PROGRESSIVE_LEARNING = 'progressive_learning'
UPDATE_TYPE_EXPRESSION_LEARNING = 'expression_learning'


def normalize_update_type(raw_type: str) -> str:
    """
    标准化更新类型名称

    Args:
        raw_type: 原始更新类型字符串

    Returns:
        标准化后的更新类型
    """
    if not raw_type:
        return 'unknown'

    raw_lower = raw_type.lower().strip()

    # 风格学习相关
    if any(k in raw_lower for k in ['style', 'few_shot', 'few-shot', 'fewshot']):
        return UPDATE_TYPE_STYLE_LEARNING

    # 表达学习相关
    if any(k in raw_lower for k in ['expression', '表达']):
        return UPDATE_TYPE_EXPRESSION_LEARNING

    # 渐进式学习相关
    if any(k in raw_lower for k in ['progressive', '渐进']):
        return UPDATE_TYPE_PROGRESSIVE_LEARNING

    # 人格学习相关（兜底）
    if any(k in raw_lower for k in ['persona', 'learning', '人格', '学习']):
        return UPDATE_TYPE_PERSONA_LEARNING

    return raw_type


def get_review_source_from_update_type(raw_type: str) -> str:
    """
    根据更新类型获取审查来源分类

    Args:
        raw_type: 原始更新类型字符串

    Returns:
        审查来源: 'style_learning', 'persona_learning', 或 'traditional'
    """
    normalized = normalize_update_type(raw_type)

    if normalized == UPDATE_TYPE_STYLE_LEARNING:
        return 'style_learning'

    if normalized in (
        UPDATE_TYPE_PERSONA_LEARNING,
        UPDATE_TYPE_PROGRESSIVE_LEARNING,
        UPDATE_TYPE_EXPRESSION_LEARNING,
    ):
        return 'persona_learning'

    return 'traditional'


class TerminateMessages:
    """插件卸载相关消息"""
    LEARNING_SCHEDULER_STOP = "停止学习调度器"
    BACKGROUND_TASKS_CANCEL = "取消所有后台任务"
    SERVICES_CLEANUP = "停止所有服务"
    STATE_SAVE = "保存最终状态"
    WEB_SERVER_STOP = "停止 Web 服务器"
    CONFIG_SAVE = "保存配置到文件"