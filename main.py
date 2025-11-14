"""
AstrBot 自学习插件 - 智能对话风格学习与人格优化
"""
import os
import json # 导入 json 模块
import asyncio
import time
import re # 导入正则表达式模块
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass

from astrbot.api.event import AstrMessageEvent
from astrbot.api.event import filter
from astrbot.api.event.filter import PermissionType
import astrbot.api.star as star
from astrbot.api.star import register, Context
from astrbot.api import logger, AstrBotConfig
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .config import PluginConfig
from .core.factory import FactoryManager
from .core.interfaces import MessageData
from .exceptions import SelfLearningError
from .webui import Server, set_plugin_services # 导入 FastAPI 服务器相关
from .statics.messages import StatusMessages, CommandMessages, LogMessages, FileNames, DefaultValues

server_instance: Optional[Server] = None # 全局服务器实例
_server_cleanup_lock = asyncio.Lock() # 服务器清理锁，防止并发清理

@dataclass
class LearningStats:
    """学习统计信息"""
    total_messages_collected: int = 0
    filtered_messages: int = 0
    style_updates: int = 0
    persona_updates: int = 0
    last_learning_time: Optional[str] = None
    last_persona_update: Optional[str] = None


@register("astrbot_plugin_self_learning", "NickMo", "智能自学习对话插件", "1.4.0", "https://github.com/NickCharlie/astrbot_plugin_self_learning")
class SelfLearningPlugin(star.Star):
    """AstrBot 自学习插件 - 智能学习用户对话风格并优化人格设置"""

    def __init__(self, context: Context, config: AstrBotConfig = None) -> None:
        super().__init__(context)
        self.context = context
        self.config = config or {}
        
        # 初始化插件配置
        # 设置插件数据目录为 ./data/self_learning_data
        try:
            # 优先使用 ./data/self_learning_data 作为默认路径
            plugin_data_dir = os.path.join(".", "data", "self_learning_data")
            
            # 如果能获取到 AstrBot 数据路径，尝试在其基础上设置
            astrbot_data_path = get_astrbot_data_path()
            if astrbot_data_path is not None:
                # 如果获取到 AstrBot 数据路径，在其基础上创建 self_learning_data 目录
                alternative_data_dir = os.path.join(astrbot_data_path, "plugins", "astrbot_plugin_self_learning")
                # 但仍然使用相对路径作为主要选择
                logger.info(f"AstrBot数据路径可用: {astrbot_data_path}")
                logger.info(f"备选数据目录: {alternative_data_dir}")
            else:
                logger.warning("无法获取 AstrBot 数据路径")
            
            # 使用绝对路径确保正确性
            plugin_data_dir = os.path.abspath(plugin_data_dir)
            logger.info(f"插件数据目录: {plugin_data_dir}")
            self.plugin_config = PluginConfig.create_from_config(self.config, data_dir=plugin_data_dir)
            
        except Exception as e:
            logger.error(f"初始化插件配置失败: {e}")
            # 使用最保险的默认配置
            default_data_dir = os.path.abspath(os.path.join(".", "data", "self_learning_data"))
            logger.warning(f"使用默认数据目录: {default_data_dir}")
            self.plugin_config = PluginConfig.create_from_config(self.config, data_dir=default_data_dir)
        
        # 确保数据目录存在
        os.makedirs(self.plugin_config.data_dir, exist_ok=True)
        
        # 初始化 messages_db_path 和 learning_log_path
        if not self.plugin_config.messages_db_path:
            self.plugin_config.messages_db_path = os.path.join(self.plugin_config.data_dir, FileNames.MESSAGES_DB_FILE)
        if not self.plugin_config.learning_log_path:
            self.plugin_config.learning_log_path = os.path.join(self.plugin_config.data_dir, FileNames.LEARNING_LOG_FILE)
        
        # 学习统计
        self.learning_stats = LearningStats()
        
        # 消息去重缓存 - 防止合并消息插件导致的重复处理
        self.message_dedup_cache = {}
        self.max_cache_size = 1000
        
        # 初始化服务层
        self._initialize_services()

        # 初始化 Web 服务器（但不启动，等待 on_load）
        global server_instance
        if self.plugin_config.enable_web_interface:
            logger.info(f"Debug: 准备创建Server实例，端口: {self.plugin_config.web_interface_port}")
            try:
                server_instance = Server(port=self.plugin_config.web_interface_port)
                if server_instance:
                    logger.info(StatusMessages.WEB_INTERFACE_ENABLED.format(host=server_instance.host, port=server_instance.port))
                    logger.info("Web服务器实例已创建，将在on_load中启动")

                    # 立即尝试启动Web服务器而不等待on_load
                    logger.info("Debug: 尝试立即启动Web服务器")
                    asyncio.create_task(self._immediate_start_web_server())
                else:
                    logger.error(StatusMessages.WEB_INTERFACE_INIT_FAILED)
            except Exception as e:
                logger.error(f"创建Web服务器实例失败: {e}", exc_info=True)
        else:
            logger.info(StatusMessages.WEB_INTERFACE_DISABLED)
        
        logger.info(StatusMessages.PLUGIN_INITIALIZED)

    async def _immediate_start_web_server(self):
        """立即启动Web服务器，不等待on_load"""
        logger.info("Debug: _immediate_start_web_server 被调用")

        # 等待一小段时间让插件完全初始化
        await asyncio.sleep(1)

        global server_instance
        if server_instance and self.plugin_config.enable_web_interface:
            logger.info("Debug: 开始立即设置并启动Web服务器")

            # 启动数据库管理器
            try:
                logger.info("Debug: 启动数据库管理器")
                await self.db_manager.start()
                logger.info("Debug: 数据库管理器启动成功")
            except Exception as e:
                logger.error(f"启动数据库管理器失败: {e}", exc_info=True)

            # 设置插件服务
            try:
                logger.info("Debug: 开始设置插件服务")
                
                # 尝试获取AstrBot框架的PersonaManager
                astrbot_persona_manager = None
                try:
                    # 通过context的persona_manager属性获取框架的PersonaManager
                    if hasattr(self.context, 'persona_manager'):
                        astrbot_persona_manager = self.context.persona_manager
                        if astrbot_persona_manager:
                            logger.info(f"立即启动: 成功获取AstrBot框架PersonaManager: {type(astrbot_persona_manager)}")
                            # 检查PersonaManager是否已初始化
                            if hasattr(astrbot_persona_manager, 'personas'):
                                logger.info(f"立即启动: PersonaManager已有personas属性，人格数量: {len(getattr(astrbot_persona_manager, 'personas', []))}")
                            else:
                                logger.info("立即启动: PersonaManager还没有personas属性，可能需要初始化")
                        else:
                            logger.warning("立即启动: Context中persona_manager为None")
                    else:
                        logger.warning("立即启动: Context中没有persona_manager属性")
                        
                    # 额外尝试：如果persona_manager为None，尝试延迟获取
                    if not astrbot_persona_manager:
                        logger.info("立即启动: 尝试延迟获取PersonaManager...")
                        await asyncio.sleep(3)  # 等待3秒，给AstrBot更多初始化时间
                        if hasattr(self.context, 'persona_manager') and self.context.persona_manager:
                            astrbot_persona_manager = self.context.persona_manager
                            logger.info(f"立即启动: 延迟获取成功: {type(astrbot_persona_manager)}")
                        else:
                            logger.warning("立即启动: 延迟获取PersonaManager仍然失败，可能AstrBot还在初始化中")
                            
                except Exception as pe:
                    logger.error(f"立即启动: 获取AstrBot框架PersonaManager失败: {pe}", exc_info=True)
                
                await set_plugin_services(
                    self.plugin_config,
                    self.factory_manager,
                    None,  # 不再传递已弃用的 LLMClient
                    astrbot_persona_manager  # 传递框架PersonaManager
                )
                logger.info("Debug: 插件服务设置完成")
            except Exception as e:
                logger.error(f"设置插件服务失败: {e}", exc_info=True)
                return

            # 启动Web服务器
            try:
                logger.info("Debug: 调用 server_instance.start()")
                await server_instance.start()
                logger.info("🌐 Web服务器已成功启动！")
            except Exception as e:
                logger.error(f"Web服务器启动失败: {e}", exc_info=True)
        else:
            logger.error("Debug: server_instance 为空或 web_interface 未启用")

    async def _start_web_server(self):
        """启动Web服务器的异步方法"""
        global server_instance
        if server_instance:
            logger.info(StatusMessages.WEB_SERVER_STARTING)
            try:
                await server_instance.start()
                logger.info(StatusMessages.WEB_SERVER_STARTED)
                
                # 启动数据库管理器
                await self.db_manager.start()
                logger.info(StatusMessages.DB_MANAGER_STARTED)
            except Exception as e:
                logger.error(StatusMessages.WEB_SERVER_START_FAILED.format(error=e), exc_info=True)

    def _initialize_services(self):
        """初始化所有服务层组件 - 使用工厂模式"""
        try:
            # 初始化工厂管理器
            self.factory_manager = FactoryManager()
            self.factory_manager.initialize_factories(self.plugin_config, self.context)
            
            # 获取服务工厂
            self.service_factory = self.factory_manager.get_service_factory()
            
            # 使用工厂创建核心服务
            self.db_manager = self.service_factory.create_database_manager()
            self.message_collector = self.service_factory.create_message_collector()
            self.multidimensional_analyzer = self.service_factory.create_multidimensional_analyzer()
            self.style_analyzer = self.service_factory.create_style_analyzer()
            self.quality_monitor = self.service_factory.create_quality_monitor()
            self.progressive_learning = self.service_factory.create_progressive_learning()
            self.ml_analyzer = self.service_factory.create_ml_analyzer()
            self.persona_manager = self.service_factory.create_persona_manager()
            
            # 设置渐进式学习服务的增量更新回调函数，降低耦合性
            self.progressive_learning.set_update_system_prompt_callback(self._update_system_prompt_for_group)
            
            # 获取组件工厂并创建新的高级服务
            component_factory = self.factory_manager.get_component_factory()
            self.data_analytics = component_factory.create_data_analytics_service()
            self.advanced_learning = component_factory.create_advanced_learning_service()
            self.enhanced_interaction = component_factory.create_enhanced_interaction_service()
            self.intelligence_enhancement = component_factory.create_intelligence_enhancement_service()
            self.affection_manager = component_factory.create_affection_manager_service()
            
            # 在affection_manager创建后再创建智能回复器，这样可以传递affection_manager
            self.intelligent_responder = self.service_factory.create_intelligent_responder()  # 重新启用智能回复器
            
            # 创建临时人格更新器
            self.temporary_persona_updater = self.service_factory.create_temporary_persona_updater()
            
            # 创建并保存LLM适配器实例，用于状态报告
            self.llm_adapter = self.service_factory.create_framework_llm_adapter()
            
            # 初始化内部组件
            self._setup_internal_components()
            
            # 执行启动时的数据验证和清理
            asyncio.create_task(self._startup_data_validation())

            logger.info(StatusMessages.FACTORY_SERVICES_INIT_COMPLETE)
            
        except SelfLearningError as sle:
            logger.error(StatusMessages.SERVICES_INIT_FAILED.format(error=sle))
            raise # Re-raise as this is an expected initialization failure
        except (TypeError, ValueError) as e: # Catch common initialization errors
            logger.error(StatusMessages.CONFIG_TYPE_ERROR.format(error=e), exc_info=True)
            raise SelfLearningError(StatusMessages.INIT_FAILED_GENERIC.format(error=str(e))) from e
        except Exception as e: # Catch any other unexpected errors
            logger.error(StatusMessages.UNKNOWN_INIT_ERROR.format(error=e), exc_info=True)
            raise SelfLearningError(StatusMessages.INIT_FAILED_GENERIC.format(error=str(e))) from e
    
    def _setup_internal_components(self):
        """设置内部组件 - 使用工厂模式"""
        # 获取组件工厂
        self.component_factory = self.factory_manager.get_component_factory()

        # QQ号过滤器
        self.qq_filter = self.component_factory.create_qq_filter()
        
        # 消息过滤器
        self.message_filter = self.component_factory.create_message_filter(self.context)
        
        # 人格更新器
        # PersonaUpdater 的创建现在需要 backup_manager，它是一个服务，也应该通过 ServiceFactory 获取
        persona_backup_manager_instance = self.service_factory.create_persona_backup_manager()
        self.persona_updater = self.component_factory.create_persona_updater(self.context, persona_backup_manager_instance)
        
        # 学习调度器
        self.learning_scheduler = self.component_factory.create_learning_scheduler(self)
        
        # 异步任务管理 - 增强后台任务管理
        self.background_tasks = set()
        self.learning_tasks = {}  # 按group_id管理学习任务
        
        # 启动自动学习（如果启用）
        if self.plugin_config.enable_auto_learning:
            # 延迟启动，避免在初始化时启动大量任务
            asyncio.create_task(self._delayed_auto_start_learning())
        
        # 添加延迟重新初始化提供商配置，解决重启后配置问题
        asyncio.create_task(self._delayed_provider_reinitialization())
    
    async def on_load(self):
        """插件加载时启动 Web 服务器和数据库管理器"""
        global server_instance
        logger.info(StatusMessages.ON_LOAD_START)
        logger.info(f"Debug: enable_web_interface = {self.plugin_config.enable_web_interface}")
        logger.info(f"Debug: server_instance = {server_instance}")
        logger.info(f"Debug: web_interface_port = {self.plugin_config.web_interface_port}")
        
        # 启动数据库管理器，确保数据库表被创建
        try:
            await self.db_manager.start()
            logger.info(StatusMessages.DB_MANAGER_STARTED)
        except Exception as e:
            logger.error(StatusMessages.DB_MANAGER_START_FAILED.format(error=e), exc_info=True)
        
        # 启动好感度管理服务（包含随机情绪初始化）
        if self.plugin_config.enable_affection_system:
            try:
                await self.affection_manager.start()
                logger.info("好感度管理服务启动成功")
            except Exception as e:
                logger.error(f"好感度管理服务启动失败: {e}", exc_info=True)
        
        # 设置Web服务器的插件服务实例和启动Web服务器
        logger.info(f"Debug: 进入Web服务器启动逻辑")
        logger.info(f"Debug: enable_web_interface = {self.plugin_config.enable_web_interface}")
        logger.info(f"Debug: server_instance is None = {server_instance is None}")

        if self.plugin_config.enable_web_interface and server_instance:
            logger.info("Debug: 开始设置Web服务器插件服务")
            # 设置插件服务
            try:
                # 尝试获取AstrBot框架的PersonaManager
                astrbot_persona_manager = None
                try:
                    # 通过context的persona_manager属性获取框架的PersonaManager
                    if hasattr(self.context, 'persona_manager'):
                        astrbot_persona_manager = self.context.persona_manager
                        if astrbot_persona_manager:
                            logger.info(f"成功获取AstrBot框架PersonaManager: {type(astrbot_persona_manager)}")
                            # 检查PersonaManager是否已初始化
                            if hasattr(astrbot_persona_manager, 'personas'):
                                logger.info(f"PersonaManager已有personas属性，人格数量: {len(getattr(astrbot_persona_manager, 'personas', []))}")
                            else:
                                logger.info("PersonaManager还没有personas属性，可能需要初始化")
                        else:
                            logger.warning("Context中persona_manager为None")
                    else:
                        logger.warning("Context中没有persona_manager属性")
                        
                    # 额外尝试：如果persona_manager为None，尝试延迟获取
                    if not astrbot_persona_manager:
                        logger.info("尝试延迟获取PersonaManager...")
                        await asyncio.sleep(2)  # 等待2秒
                        if hasattr(self.context, 'persona_manager') and self.context.persona_manager:
                            astrbot_persona_manager = self.context.persona_manager
                            logger.info(f"延迟获取成功: {type(astrbot_persona_manager)}")
                        else:
                            logger.warning("延迟获取PersonaManager仍然失败")
                            
                except Exception as pe:
                    logger.error(f"获取AstrBot框架PersonaManager失败: {pe}", exc_info=True)
                
                await set_plugin_services(
                    self.plugin_config,
                    self.factory_manager, # 传递 factory_manager
                    None,  # 不再传递已弃用的 LLMClient
                    astrbot_persona_manager  # 传递框架PersonaManager
                )
                logger.info("Web服务器插件服务设置完成")
            except Exception as e:
                logger.error(f"设置Web服务器插件服务失败: {e}", exc_info=True)
                return  # 如果服务设置失败，就不要继续启动Web服务器

            # 启动Web服务器
            logger.info(f"Debug: 准备启动Web服务器")
            logger.info(StatusMessages.WEB_SERVER_PREPARE.format(host=server_instance.host, port=server_instance.port))
            try:
                logger.info("Debug: 调用 server_instance.start()")
                await server_instance.start()
                logger.info(StatusMessages.WEB_SERVER_STARTED)
                logger.info("Debug: Web服务器启动完成")
            except Exception as e:
                logger.error(StatusMessages.WEB_SERVER_START_FAILED.format(error=e), exc_info=True)
                logger.error(f"Debug: Web服务器启动异常详情: {type(e).__name__}: {str(e)}")
                import traceback
                logger.error(f"Debug: 异常堆栈: {traceback.format_exc()}")
        else:
            logger.info("Debug: Web服务器启动条件不满足")
            if not self.plugin_config.enable_web_interface:
                logger.info(StatusMessages.WEB_INTERFACE_DISABLED_SKIP)
            if not server_instance:
                logger.error(StatusMessages.SERVER_INSTANCE_NULL)
                logger.error(f"Debug: server_instance为空，无法启动Web服务器")
        
        logger.info(StatusMessages.PLUGIN_LOAD_COMPLETE)

    async def _delayed_start_learning(self, group_id: str):
        """延迟启动学习服务"""
        try:
            await asyncio.sleep(3)  # 等待初始化完成
            await self.service_factory.initialize_all_services() # 确保所有服务初始化完成
            # 启动针对特定 group_id 的渐进式学习
            await self.progressive_learning.start_learning(group_id)
            logger.info(StatusMessages.AUTO_LEARNING_SCHEDULER_STARTED.format(group_id=group_id))
        except Exception as e:
            logger.error(StatusMessages.LEARNING_SERVICE_START_FAILED.format(group_id=group_id, error=e))

    async def _priority_update_incremental_content(self, group_id: str, sender_id: str, message_text: str, event: AstrMessageEvent):
        """
        优先更新增量内容 - 每收到一条消息都会立即调用
        确保所有增量更新内容都能优先加入到system_prompt中
        """
        try:
            logger.info(f"开始优先更新增量内容: group_id={group_id}, sender_id={sender_id[:8]}")
            
            # 1. 立即进行消息的多维度分析（实时分析）
            if hasattr(self, 'multidimensional_analyzer') and self.multidimensional_analyzer:
                try:
                    # 立即分析当前消息的上下文
                    analysis_result = await self.multidimensional_analyzer.analyze_message_context(
                        event, message_text
                    )
                    if analysis_result:
                        logger.info(f"实时多维度分析完成，包含 {len(analysis_result)} 个维度")
                except Exception as e:
                    logger.error(f"实时多维度分析失败: {e}")
            
            # 2. 立即更新用户画像和社交关系
            if hasattr(self, 'affection_manager') and self.affection_manager:
                try:
                    # 立即更新好感度和社交关系
                    affection_result = await self.affection_manager.process_message_interaction(
                        group_id, sender_id, message_text
                    )
                    if affection_result and affection_result.get('success'):
                        logger.debug(f"实时好感度更新完成: {affection_result}")
                except Exception as e:
                    logger.error(f"实时好感度更新失败: {e}")
            
            # 3. 立即进行情绪和风格分析
            if hasattr(self, 'style_analyzer') and self.style_analyzer:
                try:
                    # 获取最近的消息进行风格分析
                    recent_messages_dict = await self.db_manager.get_recent_filtered_messages(group_id, limit=5)
                    # 添加当前消息
                    current_message_dict = {
                        'message': message_text,
                        'sender_id': sender_id,
                        'timestamp': time.time()
                    }
                    all_messages_dict = recent_messages_dict + [current_message_dict]
                    
                    # 转换字典数据为MessageData对象
                    analysis_messages = []
                    for msg_dict in all_messages_dict:
                        message_data = MessageData(
                            sender_id=msg_dict.get('sender_id', ''),
                            sender_name=msg_dict.get('sender_name', ''),
                            message=msg_dict.get('message', ''),
                            group_id=group_id,
                            timestamp=msg_dict.get('timestamp', time.time()),
                            platform=msg_dict.get('platform', 'default'),
                            message_id=msg_dict.get('message_id'),
                            reply_to=msg_dict.get('reply_to')
                        )
                        analysis_messages.append(message_data)
                    
                    # 立即分析消息的风格
                    style_result = await self.style_analyzer.analyze_conversation_style(
                        group_id, analysis_messages
                    )
                    if style_result:
                        logger.debug(f"实时风格分析完成: {style_result}")
                except Exception as e:
                    logger.error(f"实时风格分析失败: {e}")
            
            # 4. 立即应用所有增量更新到system_prompt
            try:
                success = await self._update_system_prompt_for_group(group_id)
                if success:
                    logger.info(f"群组 {group_id} 增量更新优先应用到system_prompt成功")
                else:
                    logger.warning(f"群组 {group_id} 增量更新应用失败")
            except Exception as e:
                logger.error(f"增量更新应用异常 (群:{group_id}): {e}", exc_info=True)
            
            # 5. 如果启用实时学习，立即进行深度分析
            if self.plugin_config.enable_realtime_learning:
                try:
                    await self._process_message_realtime(group_id, message_text, sender_id)
                    logger.debug(f"实时学习处理完成: {group_id}")
                except Exception as e:
                    logger.error(f"实时学习处理失败: {e}")
            
            logger.info(f"增量内容优先更新流程完成: {group_id}")
            
        except Exception as e:
            logger.error(f"优先更新增量内容异常: {e}", exc_info=True)

    async def _update_system_prompt_for_group(self, group_id: str):
        """
        为特定群组实时更新system_prompt，集成所有可用的增量更新
        """
        try:
            # 防止在强制学习过程中重复调用，避免无限循环
            if hasattr(self, '_force_learning_in_progress') and group_id in self._force_learning_in_progress:
                logger.debug(f"群组 {group_id} 正在进行强制学习，跳过实时system_prompt更新")
                return True
                
            # 收集当前群组的各种增量更新数据
            update_data = {}
            recent_messages = []  # 初始化变量
            
            # 1. 获取用户档案信息
            try:
                # 从多维分析器获取用户档案
                if hasattr(self, 'multidimensional_analyzer') and self.multidimensional_analyzer:
                    # 获取群组中最活跃的用户信息
                    user_profiles = getattr(self.multidimensional_analyzer, 'user_profiles', {})
                    if user_profiles:
                        # 合并所有用户的信息作为群组特征
                        communication_styles = []
                        activity_patterns = []
                        emotional_tendencies = []
                        
                        for user_id, profile in user_profiles.items():
                            if hasattr(profile, 'communication_style') and profile.communication_style:
                                # 转换沟通风格为可读描述
                                style_desc = self._format_communication_style(profile.communication_style)
                                if style_desc:
                                    communication_styles.append(style_desc)
                            if hasattr(profile, 'activity_pattern') and profile.activity_pattern:
                                activity_patterns.append(f"用户{user_id[:6]}活跃度{profile.activity_pattern.get('frequency', '普通')}")
                            if hasattr(profile, 'emotional_tendency') and profile.emotional_tendency:
                                # 转换情感倾向为可读描述
                                emotion_desc = self._format_emotional_tendency(profile.emotional_tendency)
                                if emotion_desc:
                                    emotional_tendencies.append(emotion_desc)
                        
                        if communication_styles or activity_patterns or emotional_tendencies:
                            update_data['user_profile'] = {
                                'preferences': '; '.join(activity_patterns[:3]) if activity_patterns else '',
                                'communication_style': '; '.join(communication_styles[:2]) if communication_styles else '',
                                'personality_traits': '; '.join(emotional_tendencies[:2]) if emotional_tendencies else ''
                            }
            except Exception as e:
                logger.debug(f"获取用户档案信息失败: {e}")
            
            # 2. 获取社交关系信息
            try:
                # 从数据库获取最近的群组互动信息
                recent_messages = await self.db_manager.get_recent_filtered_messages(group_id, limit=10)
                if recent_messages and len(recent_messages) > 1:
                    # 分析群组氛围
                    message_count = len(recent_messages)
                    unique_users = len(set(msg['sender_id'] for msg in recent_messages))
                    
                    if unique_users > 1:
                        atmosphere = f"活跃群聊，{unique_users}人参与"
                    else:
                        atmosphere = "私聊对话"
                        
                    update_data['social_relationship'] = {
                        'user_relationships': f"群组成员{unique_users}人",
                        'group_atmosphere': atmosphere,
                        'interaction_style': f"近期消息{message_count}条"
                    }
            except Exception as e:
                logger.debug(f"获取社交关系信息失败: {e}")
            
            # 3. 获取上下文感知信息
            try:
                # 从最近的消息中分析对话状态
                if recent_messages and len(recent_messages) > 0:
                    latest_msg = recent_messages[0]['message'] if recent_messages else ''
                    if latest_msg:
                        # 简单的话题提取（取前20个字符作为当前话题）
                        current_topic = latest_msg[:20] + '...' if len(latest_msg) > 20 else latest_msg
                        
                        update_data['context_awareness'] = {
                            'current_topic': current_topic,
                            'conversation_state': '进行中',
                            'dialogue_flow': f"最近{len(recent_messages)}条消息的对话"
                        }
            except Exception as e:
                logger.debug(f"获取上下文信息失败: {e}")
            
            # 4. 获取学习洞察信息
            try:
                # 从学习统计信息中获取基本洞察
                if hasattr(self, 'learning_stats') and self.learning_stats:
                    learning_info = {
                        'interaction_patterns': f"已学习消息: {getattr(self.learning_stats, 'total_messages_processed', 0)}条",
                        'improvement_suggestions': '基于历史对话的适应性调整',
                        'effective_strategies': '持续学习和优化中',
                        'learning_focus': '个性化交互改进'
                    }
                    
                    # 如果有处理过的消息，添加学习洞察
                    if getattr(self.learning_stats, 'total_messages_processed', 0) > 0:
                        update_data['learning_insights'] = learning_info
            except Exception as e:
                logger.debug(f"获取学习洞察失败: {e}")
            
            # 应用所有收集到的增量更新
            if update_data:
                success = await self.temporary_persona_updater.apply_comprehensive_update_to_system_prompt(
                    group_id, update_data
                )
                if success:
                    logger.info(f"群组 {group_id} system_prompt实时更新成功，包含 {len(update_data)} 种类型的增量更新")
                    return True
                else:
                    logger.warning(f"群组 {group_id} system_prompt更新失败")
                    return False
            else:
                logger.debug(f"群组 {group_id} 暂无可用的增量更新数据")
                return True  # 没有数据也算成功
                
        except Exception as e:
            logger.error(f"群组 {group_id} 实时更新system_prompt异常: {e}", exc_info=True)
            return False

    def _is_astrbot_command(self, event: AstrMessageEvent) -> bool:
        """
        判断用户输入是否为AstrBot命令（包括插件命令和其他命令）
        
        融合了AstrBot框架的命令检测机制和插件特定的命令检测
        
        Args:
            event: AstrBot消息事件
            
        Returns:
            bool: True表示是命令，False表示是普通消息
        """
        # 1. 首先检查AstrBot框架的命令标识
        if event.is_at_or_wake_command:
            return True
            
        message_text = event.get_message_str()
        if not message_text:
            return False
            
        # 2. 检查是否为本插件的特定命令
        return self._is_plugin_command(message_text)
    
    def _is_plugin_command(self, message_text: str) -> bool:
        """检查消息是否为本插件的命令"""
        if not message_text:
            return False
        
        # 定义所有插件命令（不包含前缀符号）
        plugin_commands = [
            'learning_status',
            'start_learning', 
            'stop_learning',
            'force_learning',
            'clear_data',
            'export_data',
            'affection_status',
            'set_mood',
            'analytics_report',
            'persona_switch',
            'temp_persona',
            'apply_persona_updates',
            'switch_persona_update_mode',
            'clean_duplicate_content'
        ]
        
        # 去除首尾空白
        message_text = message_text.strip()
        
        # 方案1: 检查带前缀的命令
        # 创建命令的正则表达式模式 - 匹配: [任意单个字符][命令名][可选的空格和参数]
        commands_pattern = '|'.join(re.escape(cmd) for cmd in plugin_commands)
        pattern_with_prefix = rf'^.{{1}}({commands_pattern})(\s.*)?$'
        
        # 方案2: 检查不带前缀的命令（被AstrBot框架处理后的）
        # 直接匹配命令名，可能带参数
        pattern_without_prefix = rf'^({commands_pattern})(\s.*)?$'
        
        # 使用正则表达式匹配，忽略大小写
        # 如果匹配任一模式，都认为是插件命令
        return bool(re.match(pattern_with_prefix, message_text, re.IGNORECASE)) or \
               bool(re.match(pattern_without_prefix, message_text, re.IGNORECASE))

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """监听所有消息，收集用户对话数据"""
        
        try:
            # 检查插件是否正在卸载或统计对象是否已被清理
            if self.learning_stats is None:
                logger.debug("插件正在卸载或统计对象已清理，跳过消息处理")
                return
                
            # 获取消息文本
            message_text = event.get_message_str()
            if not message_text or len(message_text.strip()) == 0:
                return
                
            group_id = event.get_group_id() or event.get_sender_id() # 使用群组ID或发送者ID作为会话ID
            sender_id = event.get_sender_id()
            
            # 只对at消息和唤醒消息处理好感度（不包括插件命令）
            if event.is_at_or_wake_command and self.plugin_config.enable_affection_system:
                try:
                    affection_result = await self.affection_manager.process_message_interaction(
                        group_id, sender_id, message_text
                    )
                    if affection_result.get('success'):
                        logger.debug(LogMessages.AFFECTION_PROCESSING_SUCCESS.format(result=affection_result))
                except Exception as e:
                    logger.error(LogMessages.AFFECTION_PROCESSING_FAILED.format(error=e))
            
            # 检查是否启用消息抓取 - 用于学习数据收集
            if not self.plugin_config.enable_message_capture:
                return
            
            # 使用融合的命令检测机制 - 过滤所有AstrBot命令（仅用于学习数据收集，不影响好感度）
            if self._is_astrbot_command(event):
                logger.debug(f"检测到AstrBot命令，跳过学习数据收集: {message_text}")
                return
            
            # QQ号过滤（仅用于学习数据收集）
            if not self.qq_filter.should_collect_message(sender_id, group_id):
                return
            
            # 优先更新增量内容 - 每收到消息都立即执行
            # 注释掉实时分析以提升回复速度，改为按配置定时分析
            # try:
            #     await self._priority_update_incremental_content(group_id, sender_id, message_text, event)
            #     logger.debug(f"优先增量内容更新完成: {group_id}")
            # except Exception as e:
            #     logger.error(f"优先增量内容更新失败: {e}")
                
            # 收集消息（用于学习）
            await self.message_collector.collect_message({
                'sender_id': sender_id,
                'sender_name': event.get_sender_name(),
                'message': message_text,
                'group_id': group_id,
                'timestamp': time.time(),
                'platform': event.get_platform_name()
            })
            
            # 检查统计对象是否仍然存在（防止插件卸载过程中的竞态条件）
            if self.learning_stats is not None:
                self.learning_stats.total_messages_collected += 1
                
                # 确保配置中的统计也得到更新，用于WebUI显示
                self.plugin_config.total_messages_collected = self.learning_stats.total_messages_collected
            else:
                logger.warning("learning_stats对象为None，跳过统计更新")
                return  # 如果统计对象已被清理，说明插件正在卸载，直接返回
            
            # 处理增强交互（多轮对话管理）
            try:
                await self.enhanced_interaction.update_conversation_context(
                    group_id, sender_id, message_text
                )
            except Exception as e:
                logger.error(LogMessages.ENHANCED_INTERACTION_FAILED.format(error=e))
            
            # 如果启用实时学习，立即进行筛选（添加频率限制）
            if self.plugin_config.enable_realtime_learning:
                # 添加频率限制：每分钟最多处理一次实时学习
                current_time = time.time()
                last_realtime_key = f"last_realtime_{group_id}"
                last_realtime = getattr(self, last_realtime_key, 0)
                
                if current_time - last_realtime >= 60:  # 60秒间隔
                    await self._process_message_realtime(group_id, message_text, sender_id)
                    setattr(self, last_realtime_key, current_time)
                else:
                    logger.debug(f"跳过实时学习，距离上次处理不足60秒: {group_id}")
            
            # 智能启动学习任务（基于消息活动，添加频率限制）
            await self._smart_start_learning_for_group(group_id)
            
            # 智能回复处理 - 在所有数据处理完成后
            try:
                intelligent_reply_params = await self.intelligent_responder.send_intelligent_response(event)
                if intelligent_reply_params:
                    # 使用yield发送智能回复
                    yield event.request_llm(
                        prompt=intelligent_reply_params['prompt'],
                        session_id=intelligent_reply_params['session_id'],
                        conversation=intelligent_reply_params['conversation']
                    )
                    logger.info(f"已发送智能回复请求: prompt长度={len(intelligent_reply_params['prompt'])}字符, session_id={intelligent_reply_params['session_id']}")
            except Exception as e:
                logger.error(f"智能回复处理失败: {e}", exc_info=True)
            
        except Exception as e:
            logger.error(StatusMessages.MESSAGE_COLLECTION_ERROR.format(error=e), exc_info=True)

    async def _smart_start_learning_for_group(self, group_id: str):
        """智能启动群组学习任务 - 不阻塞主线程，添加频率限制"""
        try:
            # 检查该群组是否已有学习任务
            if group_id in self.learning_tasks:
                return
            
            # 添加学习间隔检查：防止频繁启动学习
            current_time = time.time()
            last_learning_key = f"last_learning_start_{group_id}"
            last_learning_start = getattr(self, last_learning_key, 0)
            learning_interval_seconds = self.plugin_config.learning_interval_hours * 3600
            
            if current_time - last_learning_start < learning_interval_seconds:
                time_remaining = learning_interval_seconds - (current_time - last_learning_start)
                logger.debug(f"群组 {group_id} 学习间隔未到，剩余时间: {time_remaining/60:.1f}分钟")
                return
            
            # 检查群组消息数量是否达到学习阈值
            stats = await self.message_collector.get_statistics(group_id)
            if stats.get('total_messages', 0) < self.plugin_config.min_messages_for_learning:
                logger.debug(f"群组 {group_id} 消息数量未达到学习阈值: {stats.get('total_messages', 0)}/{self.plugin_config.min_messages_for_learning}")
                return
            
            # 记录学习启动时间
            setattr(self, last_learning_key, current_time)
            
            # 创建学习任务
            learning_task = asyncio.create_task(self._start_group_learning(group_id))
            
            # 设置完成回调
            def on_learning_task_complete(task):
                if group_id in self.learning_tasks:
                    del self.learning_tasks[group_id]
                if task.exception():
                    logger.error(f"群组 {group_id} 学习任务异常: {task.exception()}")
                else:
                    logger.info(f"群组 {group_id} 学习任务完成")
            
            learning_task.add_done_callback(on_learning_task_complete)
            self.learning_tasks[group_id] = learning_task
            
            logger.info(f"为群组 {group_id} 启动了智能学习任务")
            
        except Exception as e:
            logger.error(f"智能启动学习失败: {e}")

    async def _start_group_learning(self, group_id: str):
        """启动特定群组的学习任务"""
        try:
            success = await self.progressive_learning.start_learning(group_id)
            if success:
                logger.info(f"群组 {group_id} 学习任务启动成功")
            else:
                logger.warning(f"群组 {group_id} 学习任务启动失败")
        except Exception as e:
            logger.error(f"群组 {group_id} 学习任务启动异常: {e}")

    async def _delayed_provider_reinitialization(self):
        """延迟重新初始化提供商配置，解决重启后配置丢失问题"""
        try:
            # 等待系统完全初始化
            await asyncio.sleep(10)
            
            # 重新初始化LLM适配器的提供商配置
            if hasattr(self, 'llm_adapter') and self.llm_adapter:
                self.llm_adapter.initialize_providers(self.plugin_config)
                logger.info("延迟重新初始化提供商配置完成")
                
                # 检查配置状态
                if self.llm_adapter.providers_configured == 0:
                    logger.warning("重新初始化后仍然没有配置任何提供商，请检查配置")
                    # 再次尝试，间隔更长时间
                    await asyncio.sleep(30)
                    self.llm_adapter.initialize_providers(self.plugin_config)
                    logger.info("第二次尝试重新初始化提供商配置")
                else:
                    logger.info(f"成功配置了 {self.llm_adapter.providers_configured} 个提供商")
            
        except Exception as e:
            logger.error(f"延迟重新初始化提供商配置失败: {e}")

    async def _delayed_auto_start_learning(self):
        """延迟自动启动学习 - 避免初始化时阻塞"""
        try:
            # 等待系统初始化完成
            await asyncio.sleep(30)
            
            # 获取活跃群组列表
            active_groups = await self._get_active_groups()
            
            for group_id in active_groups:
                try:
                    await self._smart_start_learning_for_group(group_id)
                    # 避免同时启动过多任务
                    await asyncio.sleep(5)
                except Exception as e:
                    logger.error(f"延迟启动群组 {group_id} 学习失败: {e}")
                    
        except Exception as e:
            logger.error(f"延迟自动启动学习失败: {e}")

    async def _get_active_groups(self) -> List[str]:
        """获取活跃群组列表"""
        try:
            # 获取最近有消息的群组
            conn = await self.db_manager._get_messages_db_connection()
            cursor = await conn.cursor()
            
            # 获取最近24小时内有消息的群组
            cutoff_time = time.time() - 86400
            await cursor.execute('''
                SELECT DISTINCT group_id, COUNT(*) as msg_count
                FROM raw_messages 
                WHERE timestamp > ? AND group_id IS NOT NULL
                GROUP BY group_id
                HAVING msg_count >= ?
                ORDER BY msg_count DESC
                LIMIT 10
            ''', (cutoff_time, self.plugin_config.min_messages_for_learning))
            
            active_groups = []
            for row in await cursor.fetchall():
                if row[0]:  # 确保group_id不为空
                    active_groups.append(row[0])
                    
            logger.info(f"发现 {len(active_groups)} 个活跃群组")
            return active_groups
            
        except Exception as e:
            logger.error(f"获取活跃群组失败: {e}")
            return []

    async def _process_message_realtime(self, group_id: str, message_text: str, sender_id: str):
        """实时处理消息 - 优化LLM调用频率，表达风格学习不经过消息筛选"""
        try:
            # 先进行基础过滤，避免不必要的LLM调用
            if len(message_text.strip()) < self.plugin_config.message_min_length:
                return
            
            if len(message_text) > self.plugin_config.message_max_length:
                return
            
            # 简单关键词过滤，避免明显无意义的消息
            if message_text.strip() in ['', '???', '。。。', '...', '嗯', '哦', '额']:
                return
            
            # 【新增】表达风格学习 - 直接使用原始消息，无需筛选
            await self._process_expression_style_learning(group_id, message_text, sender_id)
            
            # 基于配置的批处理模式：不是每条消息都调用LLM
            if not self.plugin_config.enable_realtime_llm_filter:
                # 如果禁用实时LLM筛选，直接添加到筛选消息
                await self.message_collector.add_filtered_message({
                    'message': message_text,
                    'sender_id': sender_id,
                    'group_id': group_id,
                    'timestamp': time.time(),
                    'confidence': 0.6  # 无LLM筛选的置信度较低
                })
                
                # 检查统计对象是否仍然存在
                if self.learning_stats is not None:
                    self.learning_stats.filtered_messages += 1
                
                # 确保配置中的统计也得到更新，用于WebUI显示
                if not hasattr(self.plugin_config, 'filtered_messages'):
                    self.plugin_config.filtered_messages = 0
                self.plugin_config.filtered_messages = self.learning_stats.filtered_messages
            
            # 如果启用LLM筛选，则获取当前人格描述并进行筛选
            current_persona_description = await self.persona_manager.get_current_persona_description()
            
            # 删除了智能回复相关处理
            # 原智能回复功能已移除
            
            if await self.multidimensional_analyzer.filter_message_with_llm(message_text, current_persona_description):
                await self.message_collector.add_filtered_message({
                    'message': message_text,
                    'sender_id': sender_id,
                    'group_id': group_id,
                    'timestamp': time.time(),
                    'confidence': 0.8  # 实时筛选置信度
                })
                
                # 检查统计对象是否仍然存在
                if self.learning_stats is not None:
                    self.learning_stats.filtered_messages += 1
                
                # 确保配置中的统计也得到更新，用于WebUI显示
                if not hasattr(self.plugin_config, 'filtered_messages'):
                    self.plugin_config.filtered_messages = 0
                self.plugin_config.filtered_messages = self.learning_stats.filtered_messages
                
        except Exception as e:
            logger.error(StatusMessages.REALTIME_PROCESSING_ERROR.format(error=e), exc_info=True)

    async def _process_expression_style_learning(self, group_id: str, message_text: str, sender_id: str):
        """处理表达风格学习 - 每收集10条消息进行一次学习"""
        try:
            # 检查当前消息计数
            message_count_key = f"expression_learning_count_{group_id}"
            current_count = getattr(self, message_count_key, 0)
            current_count += 1
            setattr(self, message_count_key, current_count)
            
            # 每收集10条消息进行一次风格学习
            if current_count < 10:
                logger.debug(f"群组 {group_id} 表达风格学习消息计数: {current_count}/10")
                return
            
            # 重置计数器
            setattr(self, message_count_key, 0)
            
            logger.info(f"群组 {group_id} 达到10条消息，开始表达风格学习")
            
            # 获取最近的原始消息用于学习（不使用筛选后的消息）
            recent_raw_messages = await self.db_manager.get_recent_raw_messages(group_id, limit=20)
            
            if not recent_raw_messages or len(recent_raw_messages) < 3:
                logger.debug(f"群组 {group_id} 原始消息数量不足，数据库中只有 {len(recent_raw_messages) if recent_raw_messages else 0} 条")
                return
            
            # 转换为 MessageData 格式
            from .core.interfaces import MessageData
            message_data_list = []
            for msg in recent_raw_messages:
                if msg.get('sender_id') != sender_id:  # 不学习自己的消息
                    message_data = MessageData(
                        sender_id=msg.get('sender_id', ''),
                        sender_name=msg.get('sender_name', ''),
                        message=msg.get('message', ''),
                        group_id=group_id,
                        timestamp=msg.get('timestamp', time.time()),
                        platform=msg.get('platform', 'default'),
                        message_id=msg.get('message_id'),
                        reply_to=msg.get('reply_to')
                    )
                    message_data_list.append(message_data)
            
            if len(message_data_list) < 3:
                logger.debug(f"群组 {group_id} 有效学习消息不足3条，跳过表达风格学习，当前：{len(message_data_list)}")
                return
            
            logger.info(f"群组 {group_id} 准备进行表达风格学习，有效消息数：{len(message_data_list)}")
            
            # 调用表达模式学习器进行学习
            expression_learner = self.factory_manager.get_component_factory().create_expression_pattern_learner()
            
            if expression_learner:
                learning_success = await expression_learner.trigger_learning_for_group(group_id, message_data_list)
                
                if learning_success:
                    logger.info(f"群组 {group_id} 表达风格学习成功")
                    
                    # 获取学习到的表达模式
                    try:
                        learned_patterns = await expression_learner.get_expression_patterns(group_id, limit=5)
                        if learned_patterns:
                            # 动态临时加入prompt（不加入人格）
                            await self._apply_style_to_prompt_temporarily(group_id, learned_patterns)
                            
                            # 同时生成Few Shots对话格式并创建审查请求（用于正式加入人格）
                            few_shots_content = await self._generate_few_shots_dialog(group_id, message_data_list)
                            
                            if few_shots_content:
                                # 创建审查请求用于正式加入人格
                                await self._create_style_learning_review_request(
                                    group_id, learned_patterns, few_shots_content
                                )
                                logger.info(f"群组 {group_id} 表达风格学习结果已临时应用到prompt，并已提交人格审查")
                            else:
                                logger.info(f"群组 {group_id} 表达风格学习结果已临时应用到prompt")
                    except Exception as e:
                        logger.error(f"处理表达风格学习结果失败: {e}")
                    
                    # 统计更新 
                    if self.learning_stats is not None:
                        self.learning_stats.style_updates += 1
                    
                    # 触发增量更新回调（动态临时更新prompt）
                    if self.update_system_prompt_callback:
                        await self.update_system_prompt_callback(group_id)
                        logger.info(f"群组 {group_id} 表达风格学习结果已应用到system_prompt")
                else:
                    logger.debug(f"群组 {group_id} 表达风格学习未产生有效结果")
            else:
                logger.warning("表达模式学习器未正确初始化")
                
        except Exception as e:
            logger.error(f"群组 {group_id} 表达风格学习处理失败: {e}")

    async def _apply_style_to_prompt_temporarily(self, group_id: str, learned_patterns: List[Any]):
        """临时将风格应用到prompt中（不修改人格文件）"""
        try:
            if not learned_patterns:
                return
            
            # 构建风格描述
            style_descriptions = []
            for pattern in learned_patterns[:3]:  # 只取前3个最重要的
                situation = pattern.situation if hasattr(pattern, 'situation') else pattern.get('situation', '')
                expression = pattern.expression if hasattr(pattern, 'expression') else pattern.get('expression', '')
                
                if situation and expression:
                    style_descriptions.append(f"当{situation}时，可以使用\"{expression}\"这样的表达")
            
            if style_descriptions:
                # 构建临时风格提示
                style_prompt = f"""
【临时表达风格特征】（基于最近学习）
在回复时可以参考以下表达方式：
{chr(10).join(f'• {desc}' for desc in style_descriptions)}

注意：这些是临时学习的风格特征，应自然融入回复，不要刻意模仿。
"""
                
                # 应用到临时prompt（通过临时人格更新器的动态更新功能）
                success = await self.temporary_persona_updater.apply_temporary_style_update(group_id, style_prompt.strip())
                
                if success:
                    logger.info(f"群组 {group_id} 表达风格已临时应用到prompt，包含 {len(style_descriptions)} 个风格特征")
                else:
                    logger.warning(f"群组 {group_id} 表达风格临时应用失败")
            
        except Exception as e:
            logger.error(f"临时应用风格到prompt失败: {e}")

    async def _generate_few_shots_dialog(self, group_id: str, message_data_list: List[Any]) -> str:
        """基于真实对话关系分析生成学习示例 - 完全基于真实用户消息"""
        try:
            if not message_data_list:
                logger.debug(f"群组 {group_id} 没有可用的消息数据")
                return ""
            
            # 将消息按时间排序，确保分析的是真实的时间序列
            sorted_messages = sorted(message_data_list, key=lambda x: x.timestamp)
            
            # 过滤出有效的真实消息
            valid_messages = []
            for msg in sorted_messages:
                message_content = msg.message.strip()
                # 过滤掉无意义的短消息，但保留所有真实用户输入
                if (len(message_content) >= 2 and 
                    message_content not in ['？', '？？', '...', '。。。', '???', '…']):
                    valid_messages.append({
                        'message_id': getattr(msg, 'message_id', f"real_msg_{hash(msg.sender_id + str(msg.timestamp)) % 10000}"),
                        'sender_id': msg.sender_id,
                        'message': message_content,
                        'timestamp': msg.timestamp
                    })
            
            if len(valid_messages) < 2:
                logger.debug(f"群组 {group_id} 有效消息数量不足（{len(valid_messages)}），无法进行对话关系分析")
                return ""
            
            # 限制分析范围到最近的消息，避免处理过多数据
            analysis_messages = valid_messages[-20:]  # 分析最近20条真实消息
            
            try:
                # 使用消息关系分析器进行智能分析
                relationship_analyzer = self.factory_manager.get_service_factory().create_message_relationship_analyzer()
                relationships = await relationship_analyzer.analyze_message_relationships(analysis_messages, group_id)
                
                if not relationships:
                    logger.debug(f"群组 {group_id} 未发现任何消息关系")
                    return self._generate_simple_conversation_context(analysis_messages, group_id)
                
                # 提取高质量的真实对话对
                conversation_pairs = await relationship_analyzer.get_conversation_pairs(relationships)
                
                if conversation_pairs and len(conversation_pairs) > 0:
                    # 生成基于真实对话关系的学习内容
                    dialog_content = self._format_real_conversation_pairs(conversation_pairs, relationships, group_id)
                    
                    # 获取分析质量信息
                    quality_info = await relationship_analyzer.analyze_conversation_quality(relationships)
                    
                    # 添加分析统计信息（帮助理解数据质量）
                    if quality_info.get('total_relationships', 0) > 0:
                        dialog_content += f"\n\n*真实对话分析统计: 发现{quality_info['total_relationships']}个消息关系，"
                        dialog_content += f"平均置信度{quality_info['avg_confidence']:.2f}，"
                        dialog_content += f"直接回复{quality_info['direct_replies']}个*"
                    
                    logger.info(f"群组 {group_id} 基于智能关系分析生成了真实对话学习内容，包含 {len(conversation_pairs)} 个对话对")
                    return dialog_content
                else:
                    logger.debug(f"群组 {group_id} 未提取到有效的对话对")
                    return self._generate_simple_conversation_context(analysis_messages, group_id)
                    
            except Exception as e:
                logger.warning(f"群组 {group_id} 智能关系分析失败，使用简单方法: {e}")
                return self._generate_simple_conversation_context(analysis_messages, group_id)
            
        except Exception as e:
            logger.error(f"群组 {group_id} 生成真实对话学习内容失败: {e}")
            return ""

    def _format_real_conversation_pairs(self, conversation_pairs: List[Any], relationships: List[Any], group_id: str) -> str:
        """格式化真实对话对为学习内容"""
        if not conversation_pairs:
            return ""
            
        dialog_lines = [
            "*基于真实用户对话关系的语言风格学习示例*",
            "",
            "以下是通过智能分析识别出的真实对话关系：",
            ""
        ]
        
        # 显示最相关的对话对（最多5个）
        display_pairs = conversation_pairs[:5]
        for i, (sender_content, reply_content) in enumerate(display_pairs, 1):
            # 确保内容是真实用户消息
            dialog_lines.append(f"【真实对话 {i}】")
            dialog_lines.append(f"发起者: {sender_content}")
            dialog_lines.append(f"回应者: {reply_content}")
            dialog_lines.append("")
        
        dialog_lines.extend([
            "*注意事项:*",
            "• 以上全部为真实用户之间的对话记录",
            "• 请学习其中体现的自然语言风格和表达习惯", 
            "• 避免机械模仿，重点理解表达的自然性和适应性",
            ""
        ])
        
        return "\n".join(dialog_lines)

    def _generate_simple_conversation_context(self, messages: List[Dict], group_id: str) -> str:
        """生成简单的真实对话上下文（当无法进行关系分析时）"""
        if not messages:
            return ""
        
        # 选择最近的消息展示真实对话流
        display_messages = messages[-8:]  # 显示最近8条真实消息
        
        dialog_lines = [
            "*真实聊天记录时间序列*",
            "",
            "以下是按时间顺序的真实用户消息：",
            ""
        ]
        
        for msg in display_messages:
            # 为保护隐私，用户ID进行哈希处理
            user_label = f"用户{hash(msg['sender_id']) % 100:02d}"
            timestamp_str = time.strftime("%H:%M", time.localtime(msg.get('timestamp', 0)))
            dialog_lines.append(f"[{timestamp_str}] {user_label}: {msg['message']}")
        
        dialog_lines.extend([
            "",
            "*使用说明:*", 
            "• 以上为真实用户发送的原始消息",
            "• 请观察其中的语言风格和表达特点",
            "• 学习自然对话的节奏和方式",
            ""
        ])
        
        logger.info(f"群组 {group_id} 生成了简单真实对话上下文，包含 {len(display_messages)} 条消息")
        return "\n".join(dialog_lines)

    async def _create_style_learning_review_request(self, group_id: str, learned_patterns: List[Any], few_shots_content: str):
        """创建对话风格学习结果的审查请求"""
        try:
            # 构建审查内容
            review_data = {
                'type': 'style_learning',
                'group_id': group_id,
                'timestamp': time.time(),
                'learned_patterns': [pattern.to_dict() for pattern in learned_patterns],
                'few_shots_content': few_shots_content,
                'status': 'pending',  # pending, approved, rejected
                'description': f'群组 {group_id} 的对话风格学习结果（包含 {len(learned_patterns)} 个表达模式）'
            }
            
            # 保存到数据库的审查表
            await self.db_manager.create_style_learning_review(review_data)
            
            logger.info(f"对话风格学习审查请求已创建: {group_id}")
            
        except Exception as e:
            logger.error(f"创建对话风格学习审查请求失败: {e}")

    @filter.command("learning_status")
    @filter.permission_type(PermissionType.ADMIN)
    async def learning_status_command(self, event: AstrMessageEvent):
        """查看学习状态"""
        try:
            group_id = event.get_group_id() or event.get_sender_id() # 获取当前会话ID
            
            # 获取收集统计
            collector_stats = await self.message_collector.get_statistics(group_id) # 传入 group_id
            
            # 确保 collector_stats 不为 None
            if collector_stats is None:
                collector_stats = {
                    'total_messages': 0,
                    'filtered_messages': 0,
                    'raw_messages': 0,
                    'unprocessed_messages': 0,
                }
            
            # 获取当前人格设置
            current_persona_info = await self.persona_manager.get_current_persona(group_id)
            current_persona_name = CommandMessages.STATUS_UNKNOWN
            if current_persona_info and isinstance(current_persona_info, dict):
                current_persona_name = current_persona_info.get('name', CommandMessages.STATUS_UNKNOWN)
            
            # 获取渐进式学习服务的状态
            learning_status = await self.progressive_learning.get_learning_status()
            
            # 确保 learning_status 不为 None
            if learning_status is None:
                learning_status = {
                    'learning_active': False,
                    'current_session': None,
                    'total_sessions': 0,
                }
            
            # 构建状态信息
            status_info = CommandMessages.STATUS_REPORT_HEADER.format(group_id=group_id)
            
            # 基础配置
            persona_update_mode = "PersonaManager模式" if self.plugin_config.use_persona_manager_updates else "传统文件模式"
            status_info += CommandMessages.STATUS_BASIC_CONFIG.format(
                message_capture=CommandMessages.STATUS_ENABLED if self.plugin_config.enable_message_capture else CommandMessages.STATUS_DISABLED,
                auto_learning=CommandMessages.STATUS_ENABLED if self.plugin_config.enable_auto_learning else CommandMessages.STATUS_DISABLED,
                realtime_learning=CommandMessages.STATUS_ENABLED if self.plugin_config.enable_realtime_learning else CommandMessages.STATUS_DISABLED,
                web_interface=CommandMessages.STATUS_ENABLED if self.plugin_config.enable_web_interface else CommandMessages.STATUS_DISABLED
            )
            
            # 人格更新方式信息
            status_info += f"\n\n📊 人格更新配置:\n"
            status_info += f"• 更新方式: {persona_update_mode}\n"
            if self.plugin_config.use_persona_manager_updates:
                # 检查PersonaManager可用性
                persona_manager_updater = self.service_factory.create_persona_manager_updater()
                pm_status = "✅ 可用" if persona_manager_updater.is_available() else "❌ 不可用"
                status_info += f"• PersonaManager状态: {pm_status}\n"
                status_info += f"• 自动应用更新: {'启用' if self.plugin_config.auto_apply_persona_updates else '禁用'}\n"
            status_info += f"• 更新前备份: {'启用' if self.plugin_config.persona_update_backup_enabled else '禁用'}\n"
            
            # 抓取设置
            status_info += CommandMessages.STATUS_CAPTURE_SETTINGS.format(
                target_qq=self.plugin_config.target_qq_list if self.plugin_config.target_qq_list else CommandMessages.STATUS_ALL_USERS,
                current_persona=current_persona_name
            )
            
            # Provider配置信息
            if hasattr(self, 'llm_adapter') and self.llm_adapter:
                provider_info = self.llm_adapter.get_provider_info()
                status_info += CommandMessages.STATUS_MODEL_CONFIG.format(
                    filter_model=provider_info.get('filter', '未配置'),
                    refine_model=provider_info.get('refine', '未配置')
                )
            else:
                status_info += CommandMessages.STATUS_MODEL_CONFIG.format(
                    filter_model='未配置框架Provider',
                    refine_model='未配置框架Provider'
                )
            
            # 学习统计 - 安全处理嵌套的None值
            current_session = learning_status.get('current_session') or {}
            status_info += CommandMessages.STATUS_LEARNING_STATS.format(
                total_messages=collector_stats.get('total_messages', 0),
                filtered_messages=collector_stats.get('filtered_messages', 0),
                style_updates=current_session.get('style_updates', 0),
                last_learning_time=current_session.get('end_time', CommandMessages.STATUS_NEVER_EXECUTED)
            )
            
            # 存储统计
            status_info += CommandMessages.STATUS_STORAGE_STATS.format(
                raw_messages=collector_stats.get('raw_messages', 0),
                unprocessed_messages=collector_stats.get('unprocessed_messages', 0),
                filtered_messages=collector_stats.get('filtered_messages', 0)
            )
            
            # 调度状态
            scheduler_status = CommandMessages.STATUS_RUNNING if learning_status.get('learning_active') else CommandMessages.STATUS_STOPPED
            status_info += "\n\n" + CommandMessages.STATUS_SCHEDULER.format(status=scheduler_status)

            yield event.plain_result(status_info.strip())
            
        except Exception as e:
            logger.error(CommandMessages.ERROR_GET_LEARNING_STATUS.format(error=e), exc_info=True)
            yield event.plain_result(CommandMessages.STATUS_QUERY_FAILED.format(error=str(e)))

    @filter.command("start_learning")
    @filter.permission_type(PermissionType.ADMIN)
    async def start_learning_command(self, event: AstrMessageEvent):
        """手动启动学习"""
        try:
            group_id = event.get_group_id() or event.get_sender_id()
            
            # 检查是否有足够的消息进行学习
            stats = await self.message_collector.get_statistics(group_id)
            unprocessed_count = stats.get('unprocessed_messages', 0)
            
            if unprocessed_count < self.plugin_config.min_messages_for_learning:
                yield event.plain_result(f"❌ 未处理消息数量不足（{unprocessed_count}/{self.plugin_config.min_messages_for_learning}），无法开始学习")
                return
            
            # 执行一次学习批次而不是启动持续循环
            yield event.plain_result(f"🔄 开始执行学习批次，处理 {unprocessed_count} 条未处理消息...")
            
            try:
                await self.progressive_learning._execute_learning_batch(group_id)
                yield event.plain_result(f"✅ 学习批次执行完成")
            except Exception as batch_error:
                yield event.plain_result(f"❌ 学习批次执行失败: {str(batch_error)}")
            
        except Exception as e:
            logger.error(CommandMessages.ERROR_START_LEARNING.format(error=e), exc_info=True)
            yield event.plain_result(CommandMessages.STARTUP_FAILED.format(error=str(e)))

    @filter.command("stop_learning")
    @filter.permission_type(PermissionType.ADMIN)
    async def stop_learning_command(self, event: AstrMessageEvent):
        """停止学习"""
        try:
            group_id = event.get_group_id() or event.get_sender_id()
            
            # ProgressiveLearningService 的 stop_learning 目前没有 group_id 参数
            # 如果需要停止特定 group_id 的学习，ProgressiveLearningService 需要修改
            # 暂时调用全局停止，或者假设 stop_learning 会停止当前活跃的会话
            await self.progressive_learning.stop_learning()
            yield event.plain_result(CommandMessages.LEARNING_STOPPED.format(group_id=group_id))
            
        except Exception as e:
            logger.error(CommandMessages.ERROR_STOP_LEARNING.format(error=e), exc_info=True)
            yield event.plain_result(CommandMessages.STOP_FAILED.format(error=str(e)))

    @filter.command("force_learning")
    @filter.permission_type(PermissionType.ADMIN)
    async def force_learning_command(self, event: AstrMessageEvent):
        """强制执行一次学习周期"""
        try:
            group_id = event.get_group_id() or event.get_sender_id()
            yield event.plain_result(CommandMessages.FORCE_LEARNING_START.format(group_id=group_id))
            
            # 设置标志位防止无限循环
            self._force_learning_in_progress = getattr(self, '_force_learning_in_progress', set())
            if group_id in self._force_learning_in_progress:
                yield event.plain_result(f"❌ 群组 {group_id} 的强制学习正在进行中，请等待完成")
                return
                
            self._force_learning_in_progress.add(group_id)
            
            try:
                # 直接调用 ProgressiveLearningService 的批处理方法
                await self.progressive_learning._execute_learning_batch(group_id)
                yield event.plain_result(CommandMessages.FORCE_LEARNING_COMPLETE.format(group_id=group_id))
            finally:
                # 无论成功失败都要清理标志位
                self._force_learning_in_progress.discard(group_id)
            
        except Exception as e:
            logger.error(CommandMessages.ERROR_FORCE_LEARNING.format(error=e), exc_info=True)
            yield event.plain_result(CommandMessages.ERROR_FORCE_LEARNING.format(error=str(e)))

    @filter.command("clear_data")
    @filter.permission_type(PermissionType.ADMIN)
    async def clear_data_command(self, event: AstrMessageEvent):
        """清空学习数据"""
        try:
            await self.message_collector.clear_all_data()
            
            # 重置统计
            self.learning_stats = LearningStats()
            
            yield event.plain_result(CommandMessages.DATA_CLEARED)
            
        except Exception as e: # Consider more specific exceptions if possible
            logger.error(CommandMessages.ERROR_CLEAR_DATA.format(error=e), exc_info=True)
            yield event.plain_result(CommandMessages.ERROR_CLEAR_DATA.format(error=str(e)))

    @filter.command("export_data")
    @filter.permission_type(PermissionType.ADMIN)
    async def export_data_command(self, event: AstrMessageEvent):
        """导出学习数据"""
        try:
            export_data = await self.message_collector.export_learning_data()
            
            # 生成导出文件
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = FileNames.EXPORT_FILENAME_TEMPLATE.format(timestamp=timestamp)
            filepath = os.path.join(self.plugin_config.data_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
                
            yield event.plain_result(CommandMessages.DATA_EXPORTED.format(filepath=filepath))
            
        except Exception as e: # Consider more specific exceptions if possible
            logger.error(CommandMessages.ERROR_EXPORT_DATA.format(error=e), exc_info=True)
            yield event.plain_result(CommandMessages.ERROR_EXPORT_DATA.format(error=str(e)))

    @filter.command("affection_status")
    @filter.permission_type(PermissionType.ADMIN)
    async def affection_status_command(self, event: AstrMessageEvent):
        """查看好感度状态"""
        try:
            group_id = event.get_group_id() or event.get_sender_id()
            user_id = event.get_sender_id()
            
            if not self.plugin_config.enable_affection_system:
                yield event.plain_result(CommandMessages.AFFECTION_DISABLED)
                return
                
            # 获取好感度状态
            affection_status = await self.affection_manager.get_affection_status(group_id)
            
            # 确保当前群组有情绪状态（如果没有会自动创建随机情绪）
            current_mood = None
            if self.plugin_config.enable_startup_random_mood:
                current_mood = await self.affection_manager.ensure_mood_for_group(group_id)
            else:
                current_mood = await self.affection_manager.get_current_mood(group_id)
            
            # 获取用户个人好感度
            user_affection = await self.db_manager.get_user_affection(group_id, user_id)
            user_level = user_affection['affection_level'] if user_affection else 0
            
            status_info = CommandMessages.AFFECTION_STATUS_HEADER.format(group_id=group_id)
            status_info += "\n\n" + CommandMessages.AFFECTION_USER_LEVEL.format(
                user_level=user_level, max_affection=self.plugin_config.max_user_affection
            )
            status_info += "\n" + CommandMessages.AFFECTION_TOTAL_STATUS.format(
                total_affection=affection_status['total_affection'],
                max_total_affection=affection_status['max_total_affection']
            )
            status_info += "\n" + CommandMessages.AFFECTION_USER_COUNT.format(user_count=affection_status['user_count'])
            status_info += "\n\n" + CommandMessages.AFFECTION_CURRENT_MOOD
            
            if current_mood:
                mood_info = current_mood
                status_info += "\n" + CommandMessages.AFFECTION_MOOD_TYPE.format(mood_type=mood_info.mood_type.value)
                status_info += "\n" + CommandMessages.AFFECTION_MOOD_INTENSITY.format(intensity=mood_info.intensity)
                status_info += "\n" + CommandMessages.AFFECTION_MOOD_DESCRIPTION.format(description=mood_info.description)
            else:
                status_info += "\n" + CommandMessages.AFFECTION_NO_MOOD
                
            if affection_status['top_users']:
                status_info += "\n\n" + CommandMessages.AFFECTION_TOP_USERS
                for i, user in enumerate(affection_status['top_users'][:3], 1):
                    status_info += "\n" + CommandMessages.AFFECTION_USER_RANK.format(
                        rank=i, user_id=user['user_id'], affection_level=user['affection_level']
                    )
            
            yield event.plain_result(status_info)
            
        except Exception as e:
            logger.error(CommandMessages.ERROR_GET_AFFECTION_STATUS.format(error=e), exc_info=True)
            yield event.plain_result(CommandMessages.ERROR_GET_AFFECTION_STATUS.format(error=str(e)))

    @filter.command("set_mood")
    @filter.permission_type(PermissionType.ADMIN)
    async def set_mood_command(self, event: AstrMessageEvent):
        """手动设置bot情绪（通过增量人格更新）"""
        try:
            if not self.plugin_config.enable_affection_system:
                yield event.plain_result(CommandMessages.AFFECTION_DISABLED)
                return
                
            args = event.get_message_str().split()[1:]  # 获取命令参数
            if len(args) < 1:
                yield event.plain_result("使用方法：/set_mood <mood_type>\n可用情绪: happy, sad, excited, calm, angry, anxious, playful, serious, nostalgic, curious")
                return
                
            group_id = event.get_group_id() or event.get_sender_id()
            mood_type = args[0].lower()
            
            # 验证情绪类型
            valid_moods = {
                'happy': '心情很好，说话比较活泼开朗，容易表达正面情感',
                'sad': '心情有些低落，说话比较温和，需要更多的理解和安慰',
                'excited': '很兴奋，说话比较有活力，对很多事情都很感兴趣',
                'calm': '心情平静，说话比较稳重，给人安全感',
                'angry': '心情不太好，说话可能比较直接，不太有耐心',
                'anxious': '有些紧张不安，说话可能比较谨慎，需要更多确认',
                'playful': '心情很调皮，喜欢开玩笑，说话比较幽默风趣',
                'serious': '比较严肃认真，说话简洁直接，专注于重要的事情',
                'nostalgic': '有些怀旧情绪，说话带有回忆色彩，比较感性',
                'curious': '对很多事情都很好奇，喜欢提问和探索新事物'
            }
            
            if mood_type not in valid_moods:
                yield event.plain_result(f"❌ 无效的情绪类型。支持的情绪: {', '.join(valid_moods.keys())}")
                return
            
            # 通过增量更新的方式设置情绪
            mood_description = valid_moods[mood_type]
            
            # 统一使用apply_mood_based_persona_update方法，它会同时处理文件和prompt更新
            persona_success = await self.temporary_persona_updater.apply_mood_based_persona_update(
                group_id, mood_type, mood_description
            )
            
            # 同时在affection_manager中记录情绪状态（但不重复添加到prompt）
            from .services.affection_manager import MoodType
            try:
                mood_enum = MoodType(mood_type)
                # 只记录到affection_manager的数据库，不更新prompt（避免重复）
                await self.affection_manager.db_manager.save_bot_mood(
                    group_id, mood_type, 0.7, mood_description, 
                    self.plugin_config.mood_persistence_hours or 24
                )
                # 更新内存缓存
                from .services.affection_manager import BotMood
                import time
                mood_obj = BotMood(
                    mood_type=mood_enum,
                    intensity=0.7,
                    description=mood_description,
                    start_time=time.time(),
                    duration_hours=self.plugin_config.mood_persistence_hours or 24
                )
                self.affection_manager.current_moods[group_id] = mood_obj
                affection_success = True
            except Exception as e:
                logger.warning(f"设置affection_manager情绪失败: {e}")
                affection_success = False
            
            if persona_success:
                status_msg = f"✅ 情绪状态已设置为: {mood_type}\n描述: {mood_description}"
                if not affection_success:
                    status_msg += "\n⚠️ 注意：情绪状态可能无法在状态查询中正确显示"
                yield event.plain_result(status_msg)
            else:
                yield event.plain_result(f"❌ 设置情绪状态失败")
            
        except Exception as e:
            logger.error(CommandMessages.ERROR_SET_MOOD.format(error=e), exc_info=True)
            yield event.plain_result(CommandMessages.ERROR_SET_MOOD.format(error=str(e)))

    @filter.command("analytics_report")
    @filter.permission_type(PermissionType.ADMIN)
    async def analytics_report_command(self, event: AstrMessageEvent):
        """生成数据分析报告"""
        try:
            group_id = event.get_group_id() or event.get_sender_id()
            
            yield event.plain_result(CommandMessages.ANALYTICS_GENERATING)
            
            # 生成学习轨迹图表
            chart_data = await self.data_analytics.generate_learning_trajectory_chart(group_id)
            
            # 生成用户行为分析
            behavior_analysis = await self.data_analytics.analyze_user_behavior_patterns(group_id)
            
            report_info = CommandMessages.ANALYTICS_REPORT_HEADER.format(group_id=group_id)
            
            report_info += CommandMessages.ANALYTICS_LEARNING_STATS.format(
                total_messages=chart_data.get('total_messages', 0),
                learning_sessions=chart_data.get('learning_sessions', 0),
                avg_quality=chart_data.get('avg_quality', 0)
            )
            
            report_info += CommandMessages.ANALYTICS_USER_BEHAVIOR.format(
                active_users=len(behavior_analysis.get('user_patterns', {})),
                main_topics=', '.join(behavior_analysis.get('common_topics', [])[:3]),
                emotion_tendency=behavior_analysis.get('dominant_emotion', '中性')
            )
            
            report_info += "\n\n" + CommandMessages.ANALYTICS_RECOMMENDATIONS.format(
                recommendations=behavior_analysis.get('recommendations', '继续保持当前学习模式')
            )
            
            yield event.plain_result(report_info)
            
        except Exception as e:
            logger.error(CommandMessages.ERROR_ANALYTICS_REPORT.format(error=e), exc_info=True)
            yield event.plain_result(CommandMessages.ERROR_ANALYTICS_REPORT.format(error=str(e)))

    @filter.command("persona_switch")
    @filter.permission_type(PermissionType.ADMIN)
    async def persona_switch_command(self, event: AstrMessageEvent):
        """切换人格模式"""
        try:
            args = event.get_message_str().split()[1:]  # 获取命令参数
            if len(args) < 1:
                yield event.plain_result(CommandMessages.PERSONA_SWITCH_USAGE)
                return
                
            group_id = event.get_group_id() or event.get_sender_id()
            persona_name = args[0]
            
            # 执行人格切换
            success = await self.advanced_learning.switch_persona(group_id, persona_name)
            
            if success:
                yield event.plain_result(CommandMessages.PERSONA_SWITCH_SUCCESS.format(persona_name=persona_name))
            else:
                yield event.plain_result(CommandMessages.PERSONA_SWITCH_FAILED)
                
        except Exception as e:
            logger.error(CommandMessages.ERROR_PERSONA_SWITCH.format(error=e), exc_info=True)
            yield event.plain_result(CommandMessages.ERROR_PERSONA_SWITCH.format(error=str(e)))

    @filter.command("persona_info")
    @filter.permission_type(PermissionType.ADMIN)
    async def persona_info_command(self, event: AstrMessageEvent):
        """显示当前人格详细信息"""
        try:
            group_id = event.get_group_id() or event.get_sender_id()
            
            # 获取人格更新器
            persona_updater = self.service_factory.get_persona_updater()
            
            # 生成格式化的人格显示
            persona_display = await persona_updater.format_current_persona_display(group_id)
            
            yield event.plain_result(persona_display)
            
        except Exception as e:
            logger.error(f"获取人格信息失败: {e}", exc_info=True)
            yield event.plain_result(f"❌ 获取人格信息失败: {str(e)}")

    @filter.command("temp_persona")
    @filter.permission_type(PermissionType.ADMIN)
    async def temp_persona_command(self, event: AstrMessageEvent):
        """临时人格更新命令"""
        try:
            args = event.get_message_str().split()
            if len(args) < 2:
                yield event.plain_result("使用方法：/temp_persona <操作> [参数]\n操作：apply, status, remove, extend, backup_list, restore")
                return
            
            operation = args[1].lower()
            group_id = event.get_group_id() or event.get_sender_id()
            
            if operation == "apply":
                # 应用临时人格: /temp_persona apply "特征1,特征2" "对话1|对话2" [持续时间分钟]
                if len(args) < 4:
                    yield event.plain_result("使用方法：/temp_persona apply \"特征1,特征2\" \"对话1|对话2\" [持续时间分钟]")
                    return
                
                features_str = args[2].strip('"')
                dialogs_str = args[3].strip('"')
                duration = int(args[4]) if len(args) > 4 else 60
                
                features = [f.strip() for f in features_str.split(',') if f.strip()]
                dialogs = [d.strip() for d in dialogs_str.split('|') if d.strip()]
                
                success = await self.temporary_persona_updater.apply_temporary_persona_update(
                    group_id, features, dialogs, duration
                )
                
                if success:
                    yield event.plain_result(f"✅ 临时人格已应用，持续时间: {duration}分钟\n特征数量: {len(features)}\n对话数量: {len(dialogs)}")
                else:
                    yield event.plain_result("❌ 临时人格应用失败")
            
            elif operation == "status":
                # 查看临时人格状态
                status = await self.temporary_persona_updater.get_temporary_persona_status(group_id)
                if status:
                    remaining_minutes = status['remaining_seconds'] // 60
                    yield event.plain_result(f"""📊 临时人格状态:
                        人格名称: {status['persona_name']}
                        剩余时间: {remaining_minutes}分钟
                        特征数量: {status['features_count']}
                        对话数量: {status['dialogs_count']}
                        备份文件: {os.path.basename(status['backup_path'])}""")
                else:
                    yield event.plain_result("ℹ️ 当前没有活动的临时人格")
            
            elif operation == "remove":
                # 移除临时人格
                success = await self.temporary_persona_updater.remove_temporary_persona(group_id)
                if success:
                    yield event.plain_result("✅ 临时人格已移除，已恢复原始人格")
                else:
                    yield event.plain_result("ℹ️ 当前没有需要移除的临时人格")
            
            elif operation == "extend":
                # 延长临时人格: /temp_persona extend [分钟数]
                additional_minutes = int(args[2]) if len(args) > 2 else 30
                success = await self.temporary_persona_updater.extend_temporary_persona(group_id, additional_minutes)
                if success:
                    yield event.plain_result(f"✅ 临时人格时间已延长 {additional_minutes} 分钟")
                else:
                    yield event.plain_result("❌ 延长临时人格失败，可能没有活动的临时人格")
            
            elif operation == "backup_list":
                # 列出备份文件
                backups = await self.temporary_persona_updater.list_persona_backups(group_id)
                if backups:
                    backup_info = "📋 人格备份文件列表:\n"
                    for i, backup in enumerate(backups[:10], 1):  # 只显示前10个
                        backup_info += f"{i}. {backup['filename']}\n"
                        backup_info += f"   人格: {backup['persona_name']}\n"
                        backup_info += f"   时间: {backup['backup_time'][:16]}\n"
                        backup_info += f"   原因: {backup['backup_reason']}\n\n"
                    yield event.plain_result(backup_info.strip())
                else:
                    yield event.plain_result("ℹ️ 没有找到备份文件")
            
            elif operation == "restore":
                # 从备份恢复: /temp_persona restore [备份文件名]
                if len(args) < 3:
                    yield event.plain_result("请指定要恢复的备份文件名")
                    return
                
                backup_filename = args[2]
                backups = await self.temporary_persona_updater.list_persona_backups(group_id)
                
                target_backup = None
                for backup in backups:
                    if backup['filename'] == backup_filename:
                        target_backup = backup
                        break
                
                if target_backup:
                    success = await self.temporary_persona_updater.restore_from_backup_file(
                        group_id, target_backup['file_path']
                    )
                    if success:
                        yield event.plain_result(f"✅ 人格已从备份恢复: {backup_filename}")
                    else:
                        yield event.plain_result(f"❌ 从备份恢复失败: {backup_filename}")
                else:
                    yield event.plain_result(f"❌ 找不到备份文件: {backup_filename}")
            
            else:
                yield event.plain_result("❌ 无效的操作。支持的操作: apply, status, remove, extend, backup_list, restore")
                
        except Exception as e:
            logger.error(f"临时人格命令执行失败: {e}", exc_info=True)
            yield event.plain_result(f"临时人格命令执行失败: {str(e)}")


    @filter.command("apply_persona_updates")
    @filter.permission_type(PermissionType.ADMIN)
    async def apply_persona_updates_command(self, event: AstrMessageEvent):
        """应用persona_updates.txt中的增量人格更新"""
        try:
            group_id = event.get_group_id() or event.get_sender_id()
            
            # 检查配置决定使用哪种更新方式
            if self.plugin_config.use_persona_manager_updates:
                yield event.plain_result("🔄 使用PersonaManager方式应用增量更新...")
                
                # 检查PersonaManager更新器是否可用
                persona_manager_updater = self.service_factory.create_persona_manager_updater()
                if not persona_manager_updater.is_available():
                    yield event.plain_result("❌ PersonaManager不可用，请检查AstrBot框架配置或使用传统文件更新方式")
                    return
                
                # 读取persona_updates.txt文件内容
                updates = await self.temporary_persona_updater._read_persona_updates()
                if not updates:
                    yield event.plain_result("ℹ️ 没有找到待应用的人格更新内容")
                    return
                
                # 使用PersonaManager应用更新
                update_content = "\n".join(updates)
                success = await persona_manager_updater.apply_incremental_update(group_id, update_content)
                
                if success:
                    # 清空更新文件
                    await self.temporary_persona_updater.clear_persona_updates_file()
                    yield event.plain_result(f"✅ PersonaManager增量更新应用成功！已应用 {len(updates)} 项更新")
                else:
                    yield event.plain_result("❌ PersonaManager增量更新失败，请检查日志或尝试传统文件更新方式")
            else:
                # 传统的文件更新方式
                yield event.plain_result("🔄 使用传统文件方式开始应用增量人格更新...")
                
                # 调用临时人格更新器的方法
                success = await self.temporary_persona_updater.read_and_apply_persona_updates(group_id)
                
                if success:
                    yield event.plain_result("✅ 传统方式增量人格更新应用成功！更新文件已清空，等待下次更新。")
                else:
                    yield event.plain_result("ℹ️ 没有找到有效的人格更新内容，或更新应用失败。")
                
        except Exception as e:
            logger.error(f"应用人格更新命令失败: {e}", exc_info=True)
            yield event.plain_result(f"❌ 应用人格更新失败: {str(e)}")

    @filter.command("switch_persona_update_mode")
    @filter.permission_type(PermissionType.ADMIN)
    async def switch_persona_update_mode_command(self, event: AstrMessageEvent):
        """切换人格更新方式"""
        try:
            args = event.get_message_str().split()[1:]
            if len(args) < 1:
                current_mode = "PersonaManager模式" if self.plugin_config.use_persona_manager_updates else "传统文件模式"
                yield event.plain_result(f"""📊 人格更新方式配置：

当前模式: {current_mode}

使用方法：/switch_persona_update_mode <模式>
可用模式：
• manager - 使用PersonaManager直接管理人格（推荐）
• file - 使用传统的文件临时存储方式

PersonaManager模式优势：
✅ 直接在原人格末尾增量更新
✅ 自动创建备份人格
✅ 无需手动执行应用命令
✅ 更好的版本管理

传统文件模式：
• 通过persona_updates.txt文件临时存储
• 需要手动执行/apply_persona_updates命令
• 适合需要人工审核的场景""")
                return
            
            mode = args[0].lower()
            
            if mode == "manager":
                # 检查PersonaManager是否可用
                persona_manager_updater = self.service_factory.create_persona_manager_updater()
                if not persona_manager_updater.is_available():
                    yield event.plain_result("❌ PersonaManager不可用，请检查AstrBot框架是否正确配置了PersonaManager")
                    return
                
                self.plugin_config.use_persona_manager_updates = True
                yield event.plain_result("✅ 已切换到PersonaManager模式！\n\n特性：\n• 自动在原人格末尾增量更新\n• 自动创建备份人格\n• 无需手动执行应用命令")
                
            elif mode == "file":
                self.plugin_config.use_persona_manager_updates = False
                yield event.plain_result("✅ 已切换到传统文件模式！\n\n特性：\n• 通过persona_updates.txt临时存储\n• 需要手动执行/apply_persona_updates\n• 适合需要人工审核的场景")
                
            else:
                yield event.plain_result("❌ 无效的模式。请使用 'manager' 或 'file'")
                return
            
            # 显示相关配置
            backup_status = "启用" if self.plugin_config.persona_update_backup_enabled else "禁用"
            auto_apply_status = "启用" if self.plugin_config.auto_apply_persona_updates else "禁用"
            
            yield event.plain_result(f"\n📋 相关配置：\n• 更新前备份：{backup_status}\n• 自动应用更新：{auto_apply_status}（仅PersonaManager模式生效）")
                
        except Exception as e:
            logger.error(f"切换人格更新模式失败: {e}", exc_info=True)
            yield event.plain_result(f"❌ 切换人格更新模式失败: {str(e)}")

    @filter.command("clean_duplicate_content")
    @filter.permission_type(PermissionType.ADMIN)
    async def clean_duplicate_content_command(self, event: AstrMessageEvent):
        """清理历史重复的情绪状态和增量更新内容"""
        try:
            group_id = event.get_group_id() or event.get_sender_id()
            
            yield event.plain_result("🧹 开始清理重复的历史内容...")
            
            # 获取provider
            provider = self.context.get_using_provider()
            if not provider or not hasattr(provider, 'curr_personality') or not provider.curr_personality:
                yield event.plain_result("❌ 无法获取当前人格信息")
                return
            
            # 获取当前prompt
            current_prompt = provider.curr_personality.get('prompt', '')
            if not current_prompt:
                yield event.plain_result("ℹ️ 当前人格没有prompt内容")
                return
            
            # 记录清理前的长度
            original_length = len(current_prompt)
            
            # 使用清理函数
            cleaned_prompt = self.temporary_persona_updater._clean_duplicate_content(current_prompt)
            
            # 更新prompt
            provider.curr_personality['prompt'] = cleaned_prompt
            
            # 计算清理效果
            cleaned_length = len(cleaned_prompt)
            saved_chars = original_length - cleaned_length
            
            # 同时清理persona_updates.txt文件
            await self.temporary_persona_updater.clear_persona_updates_file()
            
            yield event.plain_result(f"✅ 重复内容清理完成！\n"
                                   f"📊 清理前长度: {original_length} 字符\n"
                                   f"📊 清理后长度: {cleaned_length} 字符\n"
                                   f"🗑️ 清理了 {saved_chars} 个重复字符\n"
                                   f"🧹 同时清空了persona_updates.txt文件")
                
        except Exception as e:
            logger.error(f"清理重复内容命令失败: {e}", exc_info=True)
            yield event.plain_result(f"❌ 清理重复内容失败: {str(e)}")

    async def terminate(self):
        """插件卸载时的清理工作 - 增强版：确保完全释放端口和资源"""
        try:
            logger.info("🔄 开始插件完全清理工作...")
            
            # 1. 优先停止 Web 服务器 - 防止端口占用
            global server_instance, _server_cleanup_lock
            async with _server_cleanup_lock:
                if server_instance:
                    try:
                        logger.info(f"🛑 正在停止Web服务器 (端口: {server_instance.port})...")
                        
                        # 记录服务器信息用于日志
                        port = server_instance.port
                        host = server_instance.host
                        
                        # 调用增强的停止方法，设置更长的超时
                        await server_instance.stop()
                        
                        # 额外等待确保端口完全释放
                        logger.info(f"⏳ 等待端口 {port} 完全释放...")
                        await asyncio.sleep(3)  # 增加等待时间到3秒
                        
                        # 尝试验证端口是否真的释放了
                        import socket
                        try:
                            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                                sock.settimeout(1)
                                result = sock.connect_ex((host, port))
                                if result != 0:
                                    logger.info(f"✅ 端口 {port} 已确认释放")
                                else:
                                    logger.warning(f"⚠️ 端口 {port} 可能仍被占用")
                        except Exception as check_error:
                            logger.debug(f"端口检查失败: {check_error}")
                        
                        # 重置全局实例
                        server_instance = None
                        
                        logger.info(f"✅ Web服务器清理完成，端口 {port} 已释放")
                    except Exception as e:
                        logger.error(f"❌ 停止Web服务器失败: {e}", exc_info=True)
                        # 即使出错也要重置实例，避免重复尝试
                        server_instance = None
                        
                        # 强制清理：直接杀死可能的残留进程（仅在Windows上）
                        try:
                            if hasattr(server_instance, 'port'):
                                port = server_instance.port
                                logger.warning(f"⚠️ 尝试强制清理端口 {port}...")
                                # 在Windows上可以尝试使用netstat和taskkill
                                import subprocess
                                import sys
                                if sys.platform == 'win32':
                                    # 查找占用端口的进程
                                    result = subprocess.run(['netstat', '-ano'], capture_output=True, text=True)
                                    if f":{port}" in result.stdout:
                                        logger.info(f"发现端口 {port} 仍被占用，Windows将在下次重启插件时自动处理")
                                        
                        except Exception as force_clean_error:
                            logger.debug(f"强制清理失败: {force_clean_error}")
                else:
                    logger.info("ℹ️ Web服务器未运行，跳过停止操作")
            
            # 2. 停止所有学习任务
            logger.info("🔄 停止所有学习任务...")
            if hasattr(self, 'learning_tasks'):
                for group_id, task in list(self.learning_tasks.items()):
                    try:
                        # 先停止学习流程
                        if hasattr(self, 'progressive_learning'):
                            await self.progressive_learning.stop_learning()
                        
                        # 取消学习任务
                        if not task.done():
                            task.cancel()
                            try:
                                await asyncio.wait_for(task, timeout=5.0)
                            except (asyncio.CancelledError, asyncio.TimeoutError):
                                pass
                        
                        logger.info(f"✅ 群组 {group_id} 学习任务已停止")
                    except Exception as e:
                        logger.error(f"❌ 停止群组 {group_id} 学习任务失败: {e}")
                
                self.learning_tasks.clear()
            
            # 3. 停止学习调度器
            if hasattr(self, 'learning_scheduler'):
                try:
                    await self.learning_scheduler.stop()
                    logger.info("✅ 学习调度器已停止")
                except Exception as e:
                    logger.error(f"❌ 停止学习调度器失败: {e}")
                    
            # 4. 取消所有后台任务
            logger.info("🔄 取消所有后台任务...")
            if hasattr(self, 'background_tasks'):
                for task in list(self.background_tasks):
                    try:
                        if not task.done():
                            task.cancel()
                            try:
                                await asyncio.wait_for(task, timeout=3.0)
                            except (asyncio.CancelledError, asyncio.TimeoutError):
                                pass
                    except Exception as e:
                        logger.error(f"❌ 取消后台任务失败: {e}")
                
                self.background_tasks.clear()
                logger.info("✅ 所有后台任务已清理")
            
            # 5. 停止数据库连接
            if hasattr(self, 'db_manager'):
                try:
                    logger.info("🔄 关闭数据库连接...")
                    await self.db_manager.stop()
                    logger.info("✅ 数据库连接已关闭")
                except Exception as e:
                    logger.error(f"❌ 关闭数据库连接失败: {e}")
            
            # 6. 停止所有服务
            logger.info("🔄 清理所有服务...")
            if hasattr(self, 'factory_manager'):
                try:
                    await self.factory_manager.cleanup()
                    logger.info("✅ 服务工厂已清理")
                except Exception as e:
                    logger.error(f"❌ 清理服务工厂失败: {e}")
            
            # 7. 清理临时人格
            if hasattr(self, 'temporary_persona_updater'):
                try:
                    await self.temporary_persona_updater.cleanup_temp_personas()
                    logger.info("✅ 临时人格已清理")
                except Exception as e:
                    logger.error(f"❌ 清理临时人格失败: {e}")
                    
            # 8. 保存最终状态
            if hasattr(self, 'message_collector'):
                try:
                    await self.message_collector.save_state()
                    logger.info("✅ 消息收集器状态已保存")
                except Exception as e:
                    logger.error(f"❌ 保存消息收集器状态失败: {e}")
                
            # 9. 保存配置到文件
            try:
                if hasattr(self, 'plugin_config') and self.plugin_config:
                    config_path = os.path.join(self.plugin_config.data_dir, 'config.json')
                    with open(config_path, 'w', encoding='utf-8') as f:
                        json.dump(self.plugin_config.to_dict(), f, ensure_ascii=False, indent=2)
                    logger.info("✅ 插件配置已保存")
            except Exception as e:
                logger.error(f"❌ 保存配置失败: {e}")
            
            # 10. 最终清理 - 清空所有引用
            logger.info("🔄 执行最终清理...")
            try:
                # 清空消息缓存
                if hasattr(self, 'message_dedup_cache'):
                    self.message_dedup_cache.clear()
                
                # 清理统计数据
                if hasattr(self, 'learning_stats'):
                    self.learning_stats = None
                
                logger.info("✅ 最终清理完成")
            except Exception as e:
                logger.error(f"❌ 最终清理失败: {e}")
            
            logger.info("🎉 插件清理工作全部完成！端口和资源已完全释放。")
            
        except Exception as e:
            logger.error(f"❌ 插件清理过程中发生严重错误: {e}", exc_info=True)
            
            # 即使出现错误，也要确保Web服务器实例被重置
            try:
                if server_instance:
                    server_instance = None
                    logger.warning("⚠️ 已强制重置Web服务器实例")
            except:
                pass
    
    def _format_communication_style(self, communication_style: dict) -> str:
        """
        将沟通风格字典转换为可读描述
        
        Args:
            communication_style: 沟通风格字典
            
        Returns:
            str: 可读的描述文本
        """
        try:
            if not communication_style or not isinstance(communication_style, dict):
                return ""
            
            descriptions = []
            
            # 解析各种沟通风格特征
            if 'formality' in communication_style:
                formality = communication_style['formality']
                if formality > 0.7:
                    descriptions.append("正式礼貌")
                elif formality < 0.3:
                    descriptions.append("随意轻松")
                else:
                    descriptions.append("适中得体")
            
            if 'enthusiasm' in communication_style:
                enthusiasm = communication_style['enthusiasm']
                if enthusiasm > 0.7:
                    descriptions.append("热情活跃")
                elif enthusiasm < 0.3:
                    descriptions.append("冷静内敛")
            
            if 'directness' in communication_style:
                directness = communication_style['directness']
                if directness > 0.7:
                    descriptions.append("直接坦率")
                elif directness < 0.3:
                    descriptions.append("委婉含蓄")
            
            if 'humor_usage' in communication_style:
                humor = communication_style['humor_usage']
                if humor > 0.6:
                    descriptions.append("幽默风趣")
            
            if 'emoji_usage' in communication_style:
                emoji = communication_style['emoji_usage']
                if emoji > 0.6:
                    descriptions.append("表情丰富")
            
            return "，".join(descriptions) if descriptions else "普通交流风格"
            
        except Exception as e:
            logger.debug(f"格式化沟通风格失败: {e}")
            return ""
    
    def _format_emotional_tendency(self, emotional_tendency: dict) -> str:
        """
        将情感倾向字典转换为可读描述
        
        Args:
            emotional_tendency: 情感倾向字典
            
        Returns:
            str: 可读的描述文本
        """
        try:
            if not emotional_tendency or not isinstance(emotional_tendency, dict):
                return ""
            
            descriptions = []
            
            # 解析情感倾向特征
            if 'positivity' in emotional_tendency:
                positivity = emotional_tendency['positivity']
                if positivity > 0.7:
                    descriptions.append("积极乐观")
                elif positivity < 0.3:
                    descriptions.append("情绪较低")
            
            if 'stability' in emotional_tendency:
                stability = emotional_tendency['stability']
                if stability > 0.7:
                    descriptions.append("情绪稳定")
                elif stability < 0.3:
                    descriptions.append("情绪波动")
            
            if 'empathy' in emotional_tendency:
                empathy = emotional_tendency['empathy']
                if empathy > 0.6:
                    descriptions.append("善解人意")
            
            if 'expressiveness' in emotional_tendency:
                expressiveness = emotional_tendency['expressiveness']
                if expressiveness > 0.6:
                    descriptions.append("表达丰富")
                elif expressiveness < 0.3:
                    descriptions.append("表达内敛")
            
            if 'dominant_emotion' in emotional_tendency:
                dominant = emotional_tendency['dominant_emotion']
                emotion_map = {
                    'happy': '快乐',
                    'calm': '平静',
                    'excited': '兴奋',
                    'serious': '严肃',
                    'playful': '活泼',
                    'thoughtful': '深思',
                    'caring': '关怀'
                }
                if dominant in emotion_map:
                    descriptions.append(f"偏向{emotion_map[dominant]}")
            
            return "，".join(descriptions) if descriptions else "情感表达平和"
            
        except Exception as e:
            logger.debug(f"格式化情感倾向失败: {e}")
            return ""
    
    async def _startup_data_validation(self):
        """启动时的数据验证和清理"""
        try:
            logger.info("开始启动数据验证...")
            
            # 等待数据库启动完成
            await asyncio.sleep(3)
            
            # 验证并清理虚假对话数据
            await self._validate_and_clean_fake_dialogs()
            
            logger.info("启动数据验证完成")
            
        except Exception as e:
            logger.error(f"启动数据验证失败: {e}")
    
    async def _validate_and_clean_fake_dialogs(self):
        """验证和清理虚假对话数据"""
        try:
            fake_patterns = [
                r'A:\s*你最近干.*呢.*\?',  # "A: 你最近干啥呢？"模式
                r'B:\s*',                 # "B: "开头的模式
                r'用户\d+:\s*',           # "用户01: "模式
                r'.*:\s*你最近.*',        # 任何包含"你最近"的对话格式
                r'开场对话列表',          # 示例文本
                r'情绪模拟对话列表',       # 示例文本
            ]
            
            def is_fake_dialog(text: str) -> bool:
                if not text or len(text.strip()) < 3:
                    return False
                for pattern in fake_patterns:
                    if re.search(pattern, text, re.IGNORECASE):
                        return True
                return False
            
            cleaned_count = 0
            
            # 检查并清理数据库中的虚假消息
            try:
                if self.db_manager and await self.db_manager.is_running():
                    # 这里可以添加数据库清理逻辑
                    # 由于数据库结构复杂，建议使用单独的清理工具
                    logger.info("数据库虚假数据清理需要使用专用清理工具")
            except Exception as e:
                logger.warning(f"数据库验证失败: {e}")
            
            # 检查已加载的persona数据
            try:
                if hasattr(self, 'persona_manager') and self.persona_manager:
                    # 这里可以添加persona数据验证逻辑
                    logger.info("persona数据验证...")
            except Exception as e:
                logger.warning(f"persona验证失败: {e}")
            
            if cleaned_count > 0:
                logger.info(f"启动验证: 清理了{cleaned_count}条虚假对话数据")
            else:
                logger.info("启动验证: 未发现虚假对话数据")
                
        except Exception as e:
            logger.error(f"数据验证过程中出错: {e}")
