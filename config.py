"""
自学习插件配置管理
"""
import os
from typing import List, Optional
from dataclasses import dataclass, field, asdict # 导入 asdict
from astrbot.api import logger
# from astrbot.core.utils.astrbot_path import get_astrbot_data_path # 不再直接使用


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
    style_update_threshold: float = 0.8     # 风格更新阈值
    
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
    data_dir: str = "./data/plugins/astrabot_plugin_self_learning"  # 插件数据存储目录
    
    def __post_init__(self):
        """初始化后处理"""
        # 这些路径的默认值和目录创建应在外部（如主插件类）处理
        pass

    @classmethod
    def create_from_config(cls, config: dict, data_dir: Optional[str] = None) -> 'PluginConfig':
        """从AstrBot配置创建插件配置"""
        
        # 确保 data_dir 不为空
        if not data_dir:
            data_dir = "./data/plugins/astrbot_plugin_self_learning"
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
        
        return cls(
            enable_message_capture=basic_settings.get('enable_message_capture', True),
            enable_auto_learning=basic_settings.get('enable_auto_learning', True),
            enable_realtime_learning=basic_settings.get('enable_realtime_learning', False),
            enable_web_interface=basic_settings.get('enable_web_interface', True),
            web_interface_port=basic_settings.get('web_interface_port', 7833), # Web 界面端口配置
            
            target_qq_list=target_settings.get('target_qq_list', []),
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
            
            # 传入数据目录 - 优先级：外部传入 > 配置文件 > 存储设置 > 默认值
            data_dir=data_dir if data_dir else storage_settings.get('data_dir', "./data/plugins/astrabot_plugin_self_learning")
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
            
        if not self.filter_provider_id:
            errors.append("筛选模型提供商ID不能为空")
            
        if not self.refine_provider_id:
            errors.append("提炼模型提供商ID不能为空")
        
        if not self.reinforce_provider_id:
            errors.append("强化模型提供商ID不能为空")
            
        return errors
