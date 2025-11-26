"""
自学习插件配置管理
"""
import os
import json
from typing import List, Optional
from dataclasses import dataclass, field, asdict
from astrbot.api import logger


@dataclass
class PluginConfig:
    """插件配置类"""
    
    # 基础开关
    enable_message_capture: bool = True
    enable_auto_learning: bool = True  
    enable_realtime_learning: bool = False
    enable_realtime_llm_filter: bool = False  # 新增：控制实时LLM筛选
    enable_web_interface: bool = True
    web_interface_port: int = 7833 # 新增 Web 界面端口配置
    
    # MaiBot增强功能（默认启用）
    enable_maibot_features: bool = True  # 启用MaiBot增强功能
    enable_expression_patterns: bool = True  # 启用表达模式学习
    enable_memory_graph: bool = True  # 启用记忆图系统
    enable_knowledge_graph: bool = True  # 启用知识图谱
    enable_time_decay: bool = True  # 启用时间衰减机制
    
    # QQ号设置
    target_qq_list: List[str] = field(default_factory=list)
    target_blacklist: List[str] = field(default_factory=list)  # 学习黑名单
    
    # LLM 提供商 ID（使用 AstrBot 框架的 Provider 系统）
    filter_provider_id: Optional[str] = None  # 筛选模型使用的提供商ID
    refine_provider_id: Optional[str] = None  # 提炼模型使用的提供商ID
    reinforce_provider_id: Optional[str] = None # 强化模型使用的提供商ID
    
    # 当前人格设置
    current_persona_name: str = "default"
    
    # 学习参数
    learning_interval_hours: int = 6        # 学习间隔（小时）
    min_messages_for_learning: int = 50     # 最少消息数量才开始学习
    max_messages_per_batch: int = 200       # 每批处理的最大消息数量
    
    # 筛选参数
    message_min_length: int = 5             # 消息最小长度
    message_max_length: int = 500           # 消息最大长度
    confidence_threshold: float = 0.7       # 筛选置信度阈值
    relevance_threshold: float = 0.6        # 相关性阈值
    
    # 风格分析参数
    style_analysis_batch_size: int = 100    # 风格分析批次大小
    style_update_threshold: float = 0.6     # 风格更新阈值 (降低阈值，从0.8改为0.6)
    
    # 消息统计
    total_messages_collected: int = 0       # 收集到的消息总数
    
    # 机器学习设置
    enable_ml_analysis: bool = True          # 启用ML分析
    max_ml_sample_size: int = 100           # ML样本最大数量
    ml_cache_timeout_hours: int = 1         # ML缓存超时
    
    # 人格备份设置
    auto_backup_enabled: bool = True        # 启用自动备份
    backup_interval_hours: int = 24         # 备份间隔
    max_backups_per_group: int = 10         # 每群最大备份数
    
    # 高级设置
    debug_mode: bool = False                # 调试模式
    save_raw_messages: bool = True          # 保存原始消息
    auto_backup_interval_days: int = 7      # 自动备份间隔
    
    # PersonaUpdater配置
    persona_merge_strategy: str = "smart"   # 人格合并策略: "replace", "append", "prepend", "smart"
    max_mood_imitation_dialogs: int = 20    # 最大对话风格模仿数量
    enable_persona_evolution: bool = True   # 启用人格演化跟踪
    persona_compatibility_threshold: float = 0.6  # 人格兼容性阈值
    
    # 人格更新方式配置
    use_persona_manager_updates: bool = True  # 使用PersonaManager进行增量更新（False=使用文件临时存储，True=使用PersonaManager）
    auto_apply_persona_updates: bool = True   # 自动应用人格更新（仅在use_persona_manager_updates=True时生效）
    persona_update_backup_enabled: bool = True  # 启用更新前备份
    
    # 好感度系统配置
    enable_affection_system: bool = True    # 启用好感度系统
    max_total_affection: int = 250          # bot总好感度满分值
    max_user_affection: int = 100           # 单个用户最大好感度
    affection_decay_rate: float = 0.95      # 好感度衰减比例
    daily_mood_change: bool = True          # 启用每日情绪变化
    mood_affect_affection: bool = True      # 情绪影响好感度变化
    
    # 情绪系统配置
    enable_daily_mood: bool = True          # 启用每日情绪
    enable_startup_random_mood: bool = True # 启用启动时随机情绪初始化
    mood_change_hour: int = 6               # 情绪更新时间（24小时制）
    mood_persistence_hours: int = 24        # 情绪持续时间
    
    # 存储路径（内部配置，用户通常不需要修改）
    messages_db_path: Optional[str] = None
    learning_log_path: Optional[str] = None
    
    # 用户可配置的存储路径（放在最后，用户可以自定义）
    data_dir: str = "./data/self_learning_data"  # 插件数据存储目录

    # API设置
    api_key: str = ""  # 外部API访问密钥
    enable_api_auth: bool = False  # 是否启用API密钥认证

    # 数据库设置
    db_type: str = "sqlite"  # 数据库类型: sqlite 或 mysql
    mysql_host: str = "localhost"  # MySQL主机地址
    mysql_port: int = 3306  # MySQL端口
    mysql_user: str = "root"  # MySQL用户名
    mysql_password: str = ""  # MySQL密码
    mysql_database: str = "astrbot_self_learning"  # MySQL数据库名
    max_connections: int = 10  # 数据库连接池最大连接数
    min_connections: int = 2  # 数据库连接池最小连接数

    # 社交关系注入设置（与_conf_schema.json一致）
    enable_social_context_injection: bool = True  # 启用社交关系上下文注入到prompt
    include_social_relations: bool = True  # 注入用户社交关系网络信息
    include_affection_info: bool = True  # 注入好感度信息
    include_mood_info: bool = True  # 注入Bot情绪信息
    context_injection_position: str = "start"  # 上下文注入位置: "start" 或 "end"
    

    def __post_init__(self):
        """初始化后处理"""
        # 这些路径的默认值和目录创建应在外部（如主插件类）处理
        pass

    @classmethod
    def create_from_config(cls, config: dict, data_dir: Optional[str] = None) -> 'PluginConfig':
        """从AstrBot配置创建插件配置"""
        
        # 确保 data_dir 不为空
        if not data_dir:
            data_dir = "./data/self_learning_data"
            logger.warning(f"data_dir 为空，使用默认值: {data_dir}")
        
        # 从配置中提取各个配置组
        # 根据 _conf_schema.json 的结构，配置项是直接在顶层，而不是嵌套在 'self_learning_settings' 下
        basic_settings = config.get('Self_Learning_Basic', {})
        target_settings = config.get('Target_Settings', {})
        model_config = config.get('Model_Configuration', {})
        learning_params = config.get('Learning_Parameters', {})
        filter_params = config.get('Filter_Parameters', {})
        style_analysis = config.get('Style_Analysis', {})
        advanced_settings = config.get('Advanced_Settings', {})
        ml_settings = config.get('Machine_Learning_Settings', {})
        # 删除智能回复设置的获取
        # intelligent_reply_settings = config.get('Intelligent_Reply_Settings', {})
        persona_backup_settings = config.get('Persona_Backup_Settings', {})
        affection_settings = config.get('Affection_System_Settings', {})
        mood_settings = config.get('Mood_System_Settings', {})
        storage_settings = config.get('Storage_Settings', {})
        api_settings = config.get('API_Settings', {})
        database_settings = config.get('Database_Settings', {})  # 新增：数据库设置
        social_context_settings = config.get('Social_Context_Settings', {})  # 新增：社交上下文设置

        return cls(
            enable_message_capture=basic_settings.get('enable_message_capture', True),
            enable_auto_learning=basic_settings.get('enable_auto_learning', True),
            enable_realtime_learning=basic_settings.get('enable_realtime_learning', False),
            enable_web_interface=basic_settings.get('enable_web_interface', True),
            web_interface_port=basic_settings.get('web_interface_port', 7833), # Web 界面端口配置
            
            target_qq_list=target_settings.get('target_qq_list', []),
            target_blacklist=target_settings.get('target_blacklist', []),
            current_persona_name=target_settings.get('current_persona_name', 'default'),
            
            filter_provider_id=model_config.get('filter_provider_id', None),
            refine_provider_id=model_config.get('refine_provider_id', None),
            reinforce_provider_id=model_config.get('reinforce_provider_id', None),
            
            learning_interval_hours=learning_params.get('learning_interval_hours', 6),
            min_messages_for_learning=learning_params.get('min_messages_for_learning', 50),
            max_messages_per_batch=learning_params.get('max_messages_per_batch', 200),
            
            message_min_length=filter_params.get('message_min_length', 5),
            message_max_length=filter_params.get('message_max_length', 500),
            confidence_threshold=filter_params.get('confidence_threshold', 0.7),
            relevance_threshold=filter_params.get('relevance_threshold', 0.6),
            
            style_analysis_batch_size=style_analysis.get('style_analysis_batch_size', 100),
            style_update_threshold=style_analysis.get('style_update_threshold', 0.8),
            
            # 消息统计 (这个字段通常不是从外部配置加载，而是内部维护的，这里保留默认值)
            total_messages_collected=0, 
            
            enable_ml_analysis=ml_settings.get('enable_ml_analysis', True),
            max_ml_sample_size=ml_settings.get('max_ml_sample_size', 100),
            ml_cache_timeout_hours=ml_settings.get('ml_cache_timeout_hours', 1),
            
            # 删除了智能回复相关配置
            
            auto_backup_enabled=persona_backup_settings.get('auto_backup_enabled', True),
            backup_interval_hours=persona_backup_settings.get('backup_interval_hours', 24),
            max_backups_per_group=persona_backup_settings.get('max_backups_per_group', 10),
            
            debug_mode=advanced_settings.get('debug_mode', False),
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
            
            # PersonaUpdater配置 (这些可能不是直接从 _conf_schema.json 的顶层获取，而是从其他地方或默认值)
            persona_merge_strategy=config.get('persona_merge_strategy', 'smart'),
            max_mood_imitation_dialogs=config.get('max_mood_imitation_dialogs', 20),
            enable_persona_evolution=config.get('enable_persona_evolution', True),
            persona_compatibility_threshold=config.get('persona_compatibility_threshold', 0.6),

            # API设置
            api_key=api_settings.get('api_key', ''),
            enable_api_auth=api_settings.get('enable_api_auth', False),

            # 数据库设置
            db_type=database_settings.get('db_type', 'sqlite'),
            mysql_host=database_settings.get('mysql_host', 'localhost'),
            mysql_port=database_settings.get('mysql_port', 3306),
            mysql_user=database_settings.get('mysql_user', 'root'),
            mysql_password=database_settings.get('mysql_password', ''),
            mysql_database=database_settings.get('mysql_database', 'astrbot_self_learning'),
            max_connections=database_settings.get('max_connections', 10),
            min_connections=database_settings.get('min_connections', 2),

            # 社交上下文注入设置
            enable_social_context_injection=social_context_settings.get('enable_social_context_injection', True),
            include_social_relations=social_context_settings.get('include_social_relations', True),
            include_affection_info=social_context_settings.get('include_affection_info', True),
            include_mood_info=social_context_settings.get('include_mood_info', True),
            context_injection_position=social_context_settings.get('context_injection_position', 'start'),

            # 传入数据目录 - 优先级：外部传入 > 配置文件 > 存储设置 > 默认值
            data_dir=data_dir if data_dir else storage_settings.get('data_dir', "./data/self_learning_data")
        )

    @classmethod
    def create_default(cls) -> 'PluginConfig':
        """创建默认配置"""
        return cls()

    def to_dict(self) -> dict:
        """转换为字典格式"""
        # 使用 asdict 可以确保所有字段都被包含
        return asdict(self)

    def validate(self) -> List[str]:
        """验证配置有效性，返回错误信息列表"""
        errors = []
        
        if self.learning_interval_hours <= 0:
            errors.append("学习间隔必须大于0小时")
            
        if self.min_messages_for_learning <= 0:
            errors.append("最少学习消息数量必须大于0")
            
        if self.max_messages_per_batch <= 0:
            errors.append("每批最大消息数量必须大于0")
            
        if self.message_min_length >= self.message_max_length:
            errors.append("消息最小长度必须小于最大长度")
            
        if not 0 <= self.confidence_threshold <= 1:
            errors.append("置信度阈值必须在0-1之间")
            
        if not 0 <= self.style_update_threshold <= 1:
            errors.append("风格更新阈值必须在0-1之间")
        
        # 提示性警告而非错误
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
            errors.extend([f"⚠️ {warning}" for warning in provider_warnings])
            
        return errors
    
    def save_to_file(self, filepath: str) -> bool:
        """保存配置到文件"""
        try:
            config_data = asdict(self)
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
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
                
                # 创建配置实例
                config = cls(**config_data)
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
