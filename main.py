"""
AstrBot 自学习插件 - 智能对话风格学习与人格优化
"""
import os
import json # 导入 json 模块
import asyncio
import time
import re # 导入正则表达式模块
from datetime import datetime
from typing import List, Dict, Optional, Any
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


@register("astrbot_plugin_self_learning", "NickMo", "智能自学习对话插件", "Next-1.1.0", "https://github.com/NickCharlie/astrbot_plugin_self_learning")
class SelfLearningPlugin(star.Star):
    """AstrBot 自学习插件 - 智能学习用户对话风格并优化人格设置"""

    def __init__(self, context: Context, config: AstrBotConfig = None) -> None:
        super().__init__(context)
        self.context = context
        self.config = config or {}
        
        # 初始化插件配置
        # 获取插件数据目录，并传递给 PluginConfig
        try:
            astrbot_data_path = get_astrbot_data_path()
            if astrbot_data_path is None:
                # 回退到当前目录下的 data 目录
                astrbot_data_path = os.path.join(os.path.dirname(__file__), "data")
                logger.warning("无法获取 AstrBot 数据路径，使用插件目录下的 data 目录")

            # 检查用户是否在配置中自定义了数据存储路径
            # 从 Storage_Settings.data_dir 读取配置
            storage_settings = self.config.get('Storage_Settings', {}) if self.config else {}
            user_data_dir = storage_settings.get('data_dir')

            if user_data_dir:
                # 用户自定义了数据路径，使用用户指定的路径
                logger.info(f"使用用户自定义数据路径 (从Storage_Settings.data_dir): {user_data_dir}")
                plugin_data_dir = user_data_dir
                # 确保路径是绝对路径
                if not os.path.isabs(plugin_data_dir):
                    plugin_data_dir = os.path.abspath(plugin_data_dir)
            else:
                # 使用 plugin_data 目录而不是 plugins 目录，这样数据不会在插件卸载时被删除
                # 根据 AstrBot 框架规范，插件持久化数据应存储在 data/plugin_data/{plugin_name}/
                plugin_data_dir = os.path.join(astrbot_data_path, "plugin_data", "astrbot_plugin_self_learning")
                logger.info(f"使用默认数据路径: {plugin_data_dir}")

            logger.info(f"最终插件数据目录: {plugin_data_dir}")
            self.plugin_config = PluginConfig.create_from_config(self.config, data_dir=plugin_data_dir)

            # ✅ 添加Provider配置加载日志
            logger.info(f"🔧 [插件初始化] Provider配置已加载：")
            logger.info(f"  - filter_provider_id: {self.plugin_config.filter_provider_id}")
            logger.info(f"  - refine_provider_id: {self.plugin_config.refine_provider_id}")
            logger.info(f"  - reinforce_provider_id: {self.plugin_config.reinforce_provider_id}")

        except Exception as e:
            logger.error(f"初始化插件配置失败: {e}")
            # 使用最保险的默认配置
            default_data_dir = os.path.join(os.path.dirname(__file__), "data")
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

        # ✅ group_id到unified_msg_origin的映射表 - 用于会话隔离
        # key: group_id, value: unified_msg_origin
        self.group_id_to_unified_origin: Dict[str, str] = {}

        # 设置增量更新回调 - 在服务初始化前设置，避免AttributeError
        self.update_system_prompt_callback = None

        # 初始化服务层
        self._initialize_services()

        # 初始化 Web 服务器（但不启动，等待 on_load）
        global server_instance
        if self.plugin_config.enable_web_interface:
            logger.info(f"Debug: 准备创建Server实例，端口: {self.plugin_config.web_interface_port}")
            try:
                # 检查是否已经有服务器实例在运行（处理插件重载场景）
                if server_instance is not None:
                    logger.warning("检测到已存在的Web服务器实例，可能是插件重载")
                    # 检查服务器是否仍在运行
                    if server_instance.server_task and not server_instance.server_task.done():
                        logger.warning("旧的Web服务器仍在运行，将复用该实例")
                        logger.info(f"Web服务器地址: http://{server_instance.host}:{server_instance.port}")
                    else:
                        logger.info("旧的Web服务器已停止，创建新实例")
                        server_instance = None  # 清除旧实例引用

                # 只有在没有运行中的服务器时才创建新实例
                if server_instance is None:
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
                db_started = await self.db_manager.start()
                if db_started:
                    logger.info("Debug: 数据库管理器启动成功")
                else:
                    logger.error("❌ 数据库管理器启动失败，但没有抛出异常")
                    raise RuntimeError("数据库管理器启动失败")
            except Exception as e:
                logger.error(f"启动数据库管理器失败: {e}", exc_info=True)
                raise  # 重新抛出异常，停止插件启动

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
                logger.error("提示: 端口可能仍被占用。AstrBot将尝试继续运行，但WebUI不可用。")
                # 将实例置空，防止后续错误调用
                server_instance = None
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
                db_started = await self.db_manager.start()
                if db_started:
                    logger.info(StatusMessages.DB_MANAGER_STARTED)
                else:
                    logger.error("❌ 数据库管理器启动失败，但没有抛出异常")
                    raise RuntimeError("数据库管理器启动失败")
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

            # ✅ 创建响应多样性管理器 - 用于防止LLM回复同质化
            self.diversity_manager = self.service_factory.create_response_diversity_manager()

            # 获取组件工厂并创建新的高级服务
            component_factory = self.factory_manager.get_component_factory()
            self.data_analytics = component_factory.create_data_analytics_service()
            self.advanced_learning = component_factory.create_advanced_learning_service()
            self.enhanced_interaction = component_factory.create_enhanced_interaction_service()
            self.intelligence_enhancement = component_factory.create_intelligence_enhancement_service()
            self.affection_manager = component_factory.create_affection_manager_service()

            # ✅ 创建社交上下文注入器（已整合心理状态、行为指导功能）
            # 包含：表达模式学习、深度心理状态、社交关系、好感度、行为指导
            # 必须在intelligent_responder之前创建，这样才能被正确注入
            self.social_context_injector = component_factory.create_social_context_injector()

            # ✅ 创建黑话查询服务 - 用于在LLM请求时注入黑话理解
            from .services.jargon_query import JargonQueryService
            self.jargon_query_service = JargonQueryService(
                db_manager=self.db_manager,
                cache_ttl=60  # 60秒缓存TTL
            )
            logger.info("黑话查询服务已初始化（带60秒缓存）")

            # ✅ 创建黑话挖掘管理器 - 用于后台学习黑话
            from .services.jargon_miner import JargonMinerManager
            self.jargon_miner_manager = JargonMinerManager(
                llm_adapter=self.service_factory.create_framework_llm_adapter(),
                db_manager=self.db_manager,
                config=self.plugin_config
            )
            logger.info("黑话挖掘管理器已初始化")

            # 在affection_manager和social_context_injector创建后再创建智能回复器
            self.intelligent_responder = self.service_factory.create_intelligent_responder()  # 重新启用智能回复器
            
            # 创建临时人格更新器
            self.temporary_persona_updater = self.service_factory.create_temporary_persona_updater()

            # ✅ 传递group_id到unified_origin映射表的引用
            if hasattr(self, 'group_id_to_unified_origin'):
                self.temporary_persona_updater.group_id_to_unified_origin = self.group_id_to_unified_origin
                logger.info("已将group_id映射表传递给temporary_persona_updater")

            # 创建并保存LLM适配器实例，用于状态报告
            self.llm_adapter = self.service_factory.create_framework_llm_adapter()

            # 初始化内部组件
            self._setup_internal_components()

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

    async def _check_and_migrate_database(self):
        """
        自动检查并执行数据库迁移

        功能：
        1. 检查是否存在迁移标记文件
        2. 检查数据库类型是否发生变化
        3. 如果不存在标记或数据库类型变化，执行自动数据库迁移
        4. 迁移成功后创建/更新标记文件，防止重复迁移
        """
        try:
            # 迁移标记文件路径
            migration_marker = os.path.join(self.plugin_config.data_dir, '.migration_completed')

            # 获取当前数据库URL和类型
            current_db_url = self._get_database_url()
            current_db_type = 'mysql' if 'mysql' in current_db_url else 'sqlite'

            # 检查是否需要迁移
            need_migration = False
            migration_reason = ""

            if not os.path.exists(migration_marker):
                need_migration = True
                migration_reason = "首次启动"
            else:
                # 读取迁移标记，检查数据库类型是否变化
                try:
                    with open(migration_marker, 'r', encoding='utf-8') as f:
                        marker_data = json.loads(f.read())
                        previous_db_type = marker_data.get('database_type', 'unknown')

                        if previous_db_type != current_db_type:
                            need_migration = True
                            migration_reason = f"数据库类型变化 ({previous_db_type} → {current_db_type})"
                            logger.warning(f"⚠️ 检测到数据库类型变化: {previous_db_type} → {current_db_type}")
                except Exception as e:
                    logger.warning(f"读取迁移标记失败: {e}，将重新迁移")
                    need_migration = True
                    migration_reason = "标记文件损坏"

            if need_migration:
                logger.info("=" * 70)
                logger.info(f"🔄 开始自动数据库迁移（原因: {migration_reason}）...")
                logger.info("=" * 70)

                try:
                    # 导入迁移工具
                    from .utils.migration_tool_v2 import auto_migrate

                    # 确定源数据库和目标数据库
                    source_db_url = None
                    target_db_url = current_db_url

                    # 如果是数据库类型变化，需要找到旧数据库
                    if "数据库类型变化" in migration_reason:
                        # 读取旧的数据库类型
                        try:
                            with open(migration_marker, 'r', encoding='utf-8') as f:
                                marker_data = json.loads(f.read())
                                previous_db_type = marker_data.get('database_type', 'unknown')

                            # 根据旧类型构建源数据库URL
                            if previous_db_type == 'sqlite':
                                # 旧数据库是SQLite
                                old_db_path = getattr(self.plugin_config, 'messages_db_path', None)
                                if not old_db_path:
                                    old_db_path = os.path.join(self.plugin_config.data_dir, 'messages.db')
                                if not os.path.isabs(old_db_path):
                                    old_db_path = os.path.abspath(old_db_path)
                                source_db_url = f"sqlite:///{old_db_path}"
                                logger.info(f"📂 源数据库 (SQLite): {old_db_path}")
                            elif previous_db_type == 'mysql':
                                # 旧数据库是MySQL（理论上不应该出现，但保留处理）
                                source_db_url = target_db_url
                                logger.warning("⚠️ 从MySQL迁移到MySQL，使用相同数据库")
                        except Exception as e:
                            logger.warning(f"读取旧数据库信息失败: {e}，将尝试从默认SQLite迁移")
                            # 默认从 SQLite 迁移
                            old_db_path = os.path.join(self.plugin_config.data_dir, 'messages.db')
                            source_db_url = f"sqlite:///{old_db_path}"

                        logger.info(f"🎯 目标数据库 ({current_db_type.upper()}): {self._mask_url(target_db_url)}")
                    else:
                        # 首次启动或其他情况，in-place 迁移
                        source_db_url = current_db_url

                    # 执行迁移
                    await auto_migrate(source_db_url, target_db_url if source_db_url != target_db_url else None)

                    # 创建/更新迁移标记文件
                    with open(migration_marker, 'w', encoding='utf-8') as f:
                        f.write(json.dumps({
                            'migrated_at': time.time(),
                            'migrated_date': datetime.now().isoformat(),
                            'plugin_version': '1.6.1',
                            'database_type': current_db_type,  # ✅ 记录数据库类型
                            'database_url': current_db_url.split('://')[-1].split('@')[-1] if '@' in current_db_url else current_db_url  # 隐藏密码
                        }, ensure_ascii=False, indent=2))

                    logger.info("=" * 70)
                    logger.info("✅ 数据库迁移完成！")
                    logger.info("=" * 70)

                except Exception as migrate_error:
                    logger.error("=" * 70)
                    logger.error(f"❌ 数据库迁移失败: {migrate_error}")
                    logger.error("=" * 70)
                    logger.error("故障排查:")
                    logger.error("  1. 检查数据库连接是否正常")
                    logger.error("  2. 确认数据库用户有足够权限")
                    logger.error("  3. 查看完整错误日志")
                    logger.error("  4. 如需重新迁移，请删除 .migration_completed 文件")
                    raise
            else:
                logger.info("✅ 数据库已完成迁移，跳过迁移步骤")

                # 可选：显示迁移信息
                try:
                    with open(migration_marker, 'r', encoding='utf-8') as f:
                        migration_info = json.load(f)
                        logger.debug(f"迁移时间: {migration_info.get('migrated_date', '未知')}")
                        logger.debug(f"插件版本: {migration_info.get('plugin_version', '未知')}")
                except Exception as read_error:
                    logger.debug(f"读取迁移信息失败: {read_error}")

        except Exception as e:
            logger.error(f"❌ 数据库迁移检查失败: {e}", exc_info=True)
            raise

    def _get_database_url(self) -> str:
        """
        获取数据库连接URL

        Returns:
            str: 数据库连接URL
        """
        try:
            db_config = self.plugin_config

            # 检查数据库类型
            if hasattr(db_config, 'db_type') and db_config.db_type.lower() == 'mysql':
                # MySQL数据库
                host = getattr(db_config, 'mysql_host', 'localhost')
                port = getattr(db_config, 'mysql_port', 3306)
                user = getattr(db_config, 'mysql_user', 'root')
                password = getattr(db_config, 'mysql_password', '')
                database = getattr(db_config, 'mysql_database', 'astrbot_self_learning')

                return f"mysql+aiomysql://{user}:{password}@{host}:{port}/{database}"
            else:
                # SQLite数据库（默认）
                db_path = getattr(db_config, 'messages_db_path', None)

                if not db_path:
                    # 使用默认路径
                    db_path = os.path.join(db_config.data_dir, 'messages.db')

                # 确保路径是绝对路径
                if not os.path.isabs(db_path):
                    db_path = os.path.abspath(db_path)

                return f"sqlite:///{db_path}"

        except Exception as e:
            logger.error(f"获取数据库URL失败: {e}")
            # 返回默认SQLite路径
            default_path = os.path.join(self.plugin_config.data_dir, 'messages.db')
            return f"sqlite:///{default_path}"

    def _mask_url(self, url: str) -> str:
        """隐藏数据库 URL 中的密码"""
        if '@' in url:
            # mysql+aiomysql://user:password@host:port/db
            parts = url.split('@')
            if ':' in parts[0]:
                prefix = parts[0].rsplit(':', 1)[0]
                return f"{prefix}:****@{parts[1]}"
        return url

    async def on_load(self):
        """插件加载时启动 Web 服务器和数据库管理器"""
        global server_instance
        logger.info(StatusMessages.ON_LOAD_START)
        logger.info(f"Debug: enable_web_interface = {self.plugin_config.enable_web_interface}")
        logger.info(f"Debug: server_instance = {server_instance}")
        logger.info(f"Debug: web_interface_port = {self.plugin_config.web_interface_port}")

        # ✅ 检查并执行数据库迁移（首次启动时）
        await self._check_and_migrate_database()

        # 启动数据库管理器，确保数据库表被创建
        db_started = False
        max_retries = 3
        retry_delay = 2  # 秒

        for attempt in range(max_retries):
            try:
                logger.info(f"尝试启动数据库管理器 (第 {attempt + 1}/{max_retries} 次)")
                db_started = await self.db_manager.start()

                if db_started:
                    logger.info(StatusMessages.DB_MANAGER_STARTED)
                    break
                else:
                    logger.warning(f"数据库管理器启动返回False (尝试 {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        logger.info(f"等待 {retry_delay} 秒后重试...")
                        await asyncio.sleep(retry_delay)

            except Exception as e:
                logger.error(f"数据库启动异常 (尝试 {attempt + 1}/{max_retries}): {e}", exc_info=True)
                if attempt < max_retries - 1:
                    logger.info(f"等待 {retry_delay} 秒后重试...")
                    await asyncio.sleep(retry_delay)

        # 检查数据库是否成功启动
        if not db_started:
            logger.error(StatusMessages.DB_MANAGER_START_FAILED.format(error="所有重试均失败"))
            logger.warning("⚠️ 插件将在数据库功能受限的情况下继续运行")
        
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
                logger.error(f"Debug: Web服务器启动异常详���: {type(e).__name__}: {str(e)}")
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
                    # ✅ 正确检查 AnalysisResult 的 success 属性
                    if style_result and (style_result.success if hasattr(style_result, 'success') else True):
                        logger.debug(f"实时风格分析完成，置信度: {style_result.confidence if hasattr(style_result, 'confidence') else 'N/A'}")
                except Exception as e:
                    logger.error(f"实时风格分析失败: {e}")

            # 4. 如果启用实时学习，立即进行深度分析
            if self.plugin_config.enable_realtime_learning:
                try:
                    await self._process_message_realtime(group_id, message_text, sender_id)
                    logger.debug(f"实时学习处理完成: {group_id}")
                except Exception as e:
                    logger.error(f"实时学习处理失败: {e}")
            
            logger.info(f"增量内容优先更新流程完成: {group_id}")
            
        except Exception as e:
            logger.error(f"优先更新增量内容异常: {e}", exc_info=True)

    def _is_astrbot_command(self, event: AstrMessageEvent) -> bool:
        """
        判断用户输入是否为AstrBot命令（包括插件命令和其他命令）

        融合了AstrBot框架的命令检测机制和插件特定的命令检测

        注意：唤醒词消息（is_at_or_wake_command）应该被收集用于学习，
        因为这些是最有价值的对话数据。只过滤明确的命令格式。

        Args:
            event: AstrBot消息事件

        Returns:
            bool: True表示是命令，False表示是普通消息
        """
        message_text = event.get_message_str()
        if not message_text:
            return False

        # 1. 检查是否为本插件的特定命令
        if self._is_plugin_command(message_text):
            return True

        # 2. 检查是否为其他AstrBot命令（以命令前缀开头）
        # 注意：不再使用 is_at_or_wake_command 来过滤，因为唤醒词消息应该被收集
        command_prefixes = ['/', '!', '#', '.']  # 常见命令前缀
        stripped_text = message_text.strip()
        if stripped_text and stripped_text[0] in command_prefixes:
            # 检查是否像命令格式（前缀+字母开头的命令名）
            if len(stripped_text) > 1 and stripped_text[1].isalpha():
                return True

        return False
    
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
        """监听所有消息，收集用户对话数据（非阻塞优化版）"""

        try:

            # 获取消息文本
            message_text = event.get_message_str()
            if not message_text or len(message_text.strip()) == 0:
                return

            group_id = event.get_group_id() or event.get_sender_id() # 使用群组ID或发送者ID作为会话ID
            sender_id = event.get_sender_id()

            # ⚡ 优化1: 好感度处理改为后台任务，不阻塞消息回复
            # 只对at消息和唤醒消息处理好感度（不包括插件命令）
            if event.is_at_or_wake_command and self.plugin_config.enable_affection_system:
                asyncio.create_task(self._process_affection_background(group_id, sender_id, message_text))

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

            # ⚡ 优化2: 所有学习相关操作改为后台任务，完全不阻塞消息回复
            asyncio.create_task(self._process_learning_background(
                group_id, sender_id, message_text, event
            ))

            # ⚡ 统计更新可以同步进行（非常快）
            self.learning_stats.total_messages_collected += 1
            self.plugin_config.total_messages_collected = self.learning_stats.total_messages_collected

        except Exception as e:
            logger.error(StatusMessages.MESSAGE_COLLECTION_ERROR.format(error=e), exc_info=True)

    async def _mine_jargon_background(self, group_id: str):
        """
        后台黑话挖掘 - 完全异步,不阻塞主流程

        工作流程:
        1. 检查是否应该触发挖掘（频率控制）
        2. 获取最近的消息
        3. 使用JargonMiner进行黑话提取和推断
        4. 保存到数据库
        """
        try:
            if not hasattr(self, 'jargon_miner_manager'):
                logger.debug("[黑话挖掘] JargonMinerManager未初始化，跳过")
                return

            # 获取或创建该群组的黑话挖掘器
            jargon_miner = self.jargon_miner_manager.get_or_create_miner(group_id)

            # 获取最近的消息用于挖掘
            stats = await self.message_collector.get_statistics(group_id)
            recent_message_count = stats.get('raw_messages', 0)

            # 检查是否应该触发学习（频率控制）
            if not jargon_miner.should_trigger(recent_message_count):
                logger.debug(f"[黑话挖掘] 群组 {group_id} 未达到触发条件")
                return

            # 获取最近20-50条消息用于黑话挖掘
            recent_messages = await self.db_manager.get_recent_raw_messages(
                group_id, limit=30
            )

            if len(recent_messages) < 10:
                logger.debug(f"[黑话挖掘] 群组 {group_id} 消息数量不足（{len(recent_messages)}<10）")
                return

            logger.info(f"🔍 [黑话挖掘] 开始分析群组 {group_id} 的 {len(recent_messages)} 条消息")

            # 将消息列表转换为聊天文本
            chat_messages = "\n".join([
                f"{msg.get('sender_id', 'unknown')}: {msg.get('message', '')}"
                for msg in recent_messages
            ])

            # 执行黑话学习（包括候选提取、推断、保存）
            await jargon_miner.run_once(chat_messages, len(recent_messages))

            logger.debug(f"[黑话挖掘] 群组 {group_id} 学习完成")

        except Exception as e:
            logger.error(f"❌ [黑话挖掘] 后台任务失败 (group={group_id}): {e}", exc_info=True)

    async def _process_affection_background(self, group_id: str, sender_id: str, message_text: str):
        """后台处理好感度更新（非阻塞）"""
        try:
            affection_result = await self.affection_manager.process_message_interaction(
                group_id, sender_id, message_text
            )
            if affection_result.get('success'):
                logger.debug(LogMessages.AFFECTION_PROCESSING_SUCCESS.format(result=affection_result))
        except Exception as e:
            logger.error(LogMessages.AFFECTION_PROCESSING_FAILED.format(error=e))

    async def _process_learning_background(self, group_id: str, sender_id: str, message_text: str, event: AstrMessageEvent):
        """后台处理学习相关操作（非阻塞）

        ⚠️ 注意：此函数通过 asyncio.create_task() 在后台运行
        为避免 'Future attached to different loop' 错误，数据库操作需要特殊处理
        """
        try:
            # 1. ✅ 修复事件循环问题：将数据库写入操作包装在异常处理中
            # 对于 MySQL，可能会遇到事件循环绑定问题，捕获并记录而不是崩溃
            try:
                await self.message_collector.collect_message({
                    'sender_id': sender_id,
                    'sender_name': event.get_sender_name(),
                    'message': message_text,
                    'group_id': group_id,
                    'timestamp': time.time(),
                    'platform': event.get_platform_name()
                })
            except RuntimeError as e:
                if "attached to a different loop" in str(e):
                    # 这是已知的事件循环问题，记录警告但不中断流程
                    logger.warning(f"消息收集遇到事件循环问题（已知MySQL限制），消息将被跳过: {str(e)[:100]}")
                else:
                    raise  # 其他 RuntimeError 继续抛出
            except Exception as e:
                # 其他异常也记录但不中断
                logger.error(f"消息收集失败: {e}")


            # 2. 处理增强交互（多轮对话管理）
            try:
                await self.enhanced_interaction.update_conversation_context(
                    group_id, sender_id, message_text
                )
            except Exception as e:
                logger.error(LogMessages.ENHANCED_INTERACTION_FAILED.format(error=e))

            # 3. ✅ 黑话挖掘 - 每收集10条消息触发一次（完全后台执行）
            stats = await self.message_collector.get_statistics(group_id)
            raw_message_count = stats.get('raw_messages', 0)
            if raw_message_count % 10 == 0 and raw_message_count >= 10:
                asyncio.create_task(self._mine_jargon_background(group_id))

            # 4. 如果启用实时学习，每条消息都学习（完全后台执行，不阻塞）
            if self.plugin_config.enable_realtime_learning:
                # ⚡ 使用 asyncio.create_task 确保完全后台执行
                asyncio.create_task(self._process_message_realtime_background(group_id, message_text, sender_id))

            # 5. 智能启动学习任务（基于消息活动，添加频率限制）
            await self._smart_start_learning_for_group(group_id)

            # 6. 对话目标管理（如果启用）
            if self.plugin_config.enable_goal_driven_chat:
                try:
                    if hasattr(self, 'conversation_goal_manager') and self.conversation_goal_manager:
                        # 创建或获取对话目标
                        goal = await self.conversation_goal_manager.get_or_create_conversation_goal(
                            user_id=sender_id,
                            group_id=group_id,
                            user_message=message_text
                        )
                        if goal:
                            goal_type = goal['final_goal'].get('type', 'unknown')
                            goal_name = goal['final_goal'].get('name', '未知目标')
                            topic = goal['final_goal'].get('topic', '未知话题')
                            current_stage = goal['current_stage'].get('task', '初始化')
                            logger.info(f"✅ [对话目标] 会话目标: {goal_name} (类型: {goal_type}), 话题: {topic}, 当前阶段: {current_stage}")
                except Exception as e:
                    logger.error(f"对话目标处理失败: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"后台学习处理失败: {e}", exc_info=True)

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
            
            # 检查群组消息数量是否达到学习阈值 (确保类型转换)
            stats = await self.message_collector.get_statistics(group_id)

            # 验证 stats 是否为字典
            if not isinstance(stats, dict):
                logger.warning(f"get_statistics 返回了非字典类型: {type(stats)}, 值: {stats}, 跳过学习启动")
                return

            # 安全获取并转换数值
            total_messages_raw = stats.get('total_messages', 0)
            min_messages_raw = self.plugin_config.min_messages_for_learning

            # 类型转换带详细日志
            try:
                if isinstance(total_messages_raw, str) and not total_messages_raw.replace('-', '').isdigit():
                    logger.warning(f"total_messages 是非数字字符串: '{total_messages_raw}', 跳过学习启动")
                    return
                total_messages = int(total_messages_raw) if total_messages_raw else 0
            except (ValueError, TypeError) as e:
                logger.warning(f"total_messages 转换失败: 原始值={total_messages_raw}, 类型={type(total_messages_raw)}, 错误={e}")
                return

            try:
                if isinstance(min_messages_raw, str) and not min_messages_raw.replace('-', '').isdigit():
                    logger.warning(f"min_messages_for_learning 是非数字字符串: '{min_messages_raw}', 使用默认值10")
                    min_messages = 10
                else:
                    min_messages = int(min_messages_raw) if min_messages_raw else 0
            except (ValueError, TypeError) as e:
                logger.warning(f"min_messages 转换失败: 原始值={min_messages_raw}, 类型={type(min_messages_raw)}, 错误={e}, 使用默认值10")
                min_messages = 10

            if total_messages < min_messages:
                logger.debug(f"群组 {group_id} 消息数量未达到学习阈值: {total_messages}/{min_messages}")
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
        """获取活跃群组列表（使用ORM）"""
        try:
            # 检查数据库管理器是否可用和已启动
            if not self.db_manager:
                logger.warning("数据库管理器未初始化，无法获取活跃群组")
                return []

            # 对于 SQLAlchemy 数据库管理器，检查是否已启动
            if hasattr(self.db_manager, '_started') and not self.db_manager._started:
                logger.warning("SQLAlchemy 数据库管理器未启动，无法获取活跃群组")
                return []

            # 使用 ORM 方式查询活跃群组
            async with self.db_manager.get_session() as session:
                from sqlalchemy import select, func
                from .models.orm import RawMessage

                # 首先尝试获取最近24小时内有消息的群组
                cutoff_time = int(time.time() - 86400)

                stmt = select(
                    RawMessage.group_id,
                    func.count(RawMessage.id).label('msg_count')
                ).where(
                    RawMessage.timestamp > cutoff_time,
                    RawMessage.group_id.isnot(None),
                    RawMessage.group_id != ''
                ).group_by(
                    RawMessage.group_id
                ).having(
                    func.count(RawMessage.id) >= self.plugin_config.min_messages_for_learning
                ).order_by(
                    func.count(RawMessage.id).desc()
                ).limit(10)

                result = await session.execute(stmt)
                active_groups = [row.group_id for row in result if row.group_id]

                # 如果最近24小时没有活跃群组，扩大时间范围到7天
                if not active_groups:
                    logger.warning("最近24小时内没有活跃群组，扩大搜索范围到7天...")
                    cutoff_time = int(time.time() - (86400 * 7))  # 7天

                    stmt = select(
                        RawMessage.group_id,
                        func.count(RawMessage.id).label('msg_count')
                    ).where(
                        RawMessage.timestamp > cutoff_time,
                        RawMessage.group_id.isnot(None),
                        RawMessage.group_id != ''
                    ).group_by(
                        RawMessage.group_id
                    ).having(
                        func.count(RawMessage.id) >= max(1, self.plugin_config.min_messages_for_learning // 2)
                    ).order_by(
                        func.count(RawMessage.id).desc()
                    ).limit(10)

                    result = await session.execute(stmt)
                    active_groups = [row.group_id for row in result if row.group_id]

                # 如果还是没有，获取所有有消息的群组（无时间限制）
                if not active_groups:
                    logger.warning("7天内也没有活跃群组，获取所有有消息记录的群组...")

                    stmt = select(
                        RawMessage.group_id,
                        func.count(RawMessage.id).label('msg_count')
                    ).where(
                        RawMessage.group_id.isnot(None),
                        RawMessage.group_id != ''
                    ).group_by(
                        RawMessage.group_id
                    ).order_by(
                        func.count(RawMessage.id).desc()
                    ).limit(10)

                    result = await session.execute(stmt)
                    active_groups = [row.group_id for row in result if row.group_id]

                logger.info(f"发现 {len(active_groups)} 个活跃群组: {active_groups if active_groups else '无'}")
                return active_groups

        except Exception as e:
            logger.error(f"获取活跃群组失败: {e}")
            return []

    async def _process_message_realtime_background(self, group_id: str, message_text: str, sender_id: str):
        """实时处理消息的后台包装方法 - 完全异步，不阻塞主流程"""
        try:
            await self._process_message_realtime(group_id, message_text, sender_id)
        except Exception as e:
            logger.error(f"实时学习后台处理失败 (group={group_id}): {e}", exc_info=True)

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
                self.learning_stats.filtered_messages += 1
                
                # 确保配置中的统计也得到更新，用于WebUI显示
                if not hasattr(self.plugin_config, 'filtered_messages'):
                    self.plugin_config.filtered_messages = 0
                self.plugin_config.filtered_messages = self.learning_stats.filtered_messages
                
        except Exception as e:
            logger.error(StatusMessages.REALTIME_PROCESSING_ERROR.format(error=e), exc_info=True)

    async def _process_expression_style_learning(self, group_id: str, message_text: str, sender_id: str):
        """处理表达风格学习 - 直接学习，无需消息筛选"""
        try:
            # 检查是否有足够的消息进行学习
            stats = await self.message_collector.get_statistics(group_id)
            raw_message_count = stats.get('raw_messages', 0)

            # 需要至少5条消息才开始表达风格学习
            if raw_message_count < 5:
                logger.debug(f"群组 {group_id} 原始消息数量不足，当前：{raw_message_count}，需要至少5条")
                return

            logger.info(f"群组 {group_id} 开始表达风格学习，当前消息数：{raw_message_count}")
            
            # 获取最近的原始消息用于学习（不使用筛选后的消息）
            recent_raw_messages = await self.db_manager.get_recent_raw_messages(group_id, limit=25)
            
            if not recent_raw_messages or len(recent_raw_messages) < 3:  # 降低阈值
                logger.debug(f"群组 {group_id} 原始消息数量不足，数据库中只有 {len(recent_raw_messages) if recent_raw_messages else 0} 条")
                return
            
            # 转换为 MessageData 格式，并应用正则表达式过滤
            from .core.interfaces import MessageData
            import re
            
            message_data_list = []
            for msg in recent_raw_messages:
                if msg.get('sender_id') != sender_id:  # 不学习自己的消息
                    message_content = msg.get('message', '')
                    
                    # 应用与webui.py相同的过滤逻辑
                    # 1. 基础过滤：长度检查
                    if len(message_content.strip()) < 5:
                        continue
                    if len(message_content) > 500:
                        continue
                        
                    # 2. 关键词过滤：无意义消息
                    if message_content.strip() in ['', '???', '。。。', '...', '嗯', '哦', '额']:
                        continue
                    
                    # 3. @符号处理：提取@用户名后的消息内容
                    processed_message = message_content
                    if '@' in message_content:
                        # 使用正则表达式匹配 @用户名 后的内容
                        at_pattern = r'@[^\s]+\s+'
                        processed_message = re.sub(at_pattern, '', message_content).strip()
                        
                        # 如果处理后消息为空或过短，跳过
                        if len(processed_message.strip()) < 5:
                            continue
                    
                    message_data = MessageData(
                        sender_id=msg.get('sender_id', ''),
                        sender_name=msg.get('sender_name', ''),
                        message=processed_message,  # 使用处理后的消息内容
                        group_id=group_id,
                        timestamp=msg.get('timestamp', time.time()),
                        platform=msg.get('platform', 'default'),
                        message_id=msg.get('id'),  # 使用id而不是message_id
                        reply_to=None  # raw_messages表中没有reply_to字段
                    )
                    message_data_list.append(message_data)
            
            if len(message_data_list) < 3:  # 降低阈值
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
        """生成Few Shots对话格式的内容 - 需要至少10条消息才调用LLM处理"""
        try:
            # 要求至少10条消息才进行Few Shots生成
            if len(message_data_list) < 10:
                logger.debug(f"群组 {group_id} 消息数量不足10条（当前{len(message_data_list)}条），跳过Few Shots生成")
                return ""

            # 筛选出有效的对话片段
            dialog_pairs = []

            # 将消息按时间排序
            sorted_messages = sorted(message_data_list, key=lambda x: x.timestamp)

            # 使用LLM智能识别真实的对话关系
            for i in range(len(sorted_messages) - 1):
                current_msg = sorted_messages[i]
                next_msg = sorted_messages[i + 1]

                # 1. 确保是不同用户的消息（排除同一人连续发送）
                if current_msg.sender_id == next_msg.sender_id:
                    continue

                # 2. 基础过滤：长度检查
                user_msg = current_msg.message.strip()
                bot_response = next_msg.message.strip()

                if (len(user_msg) < 5 or len(bot_response) < 5 or
                    user_msg in ['？', '？？', '...', '。。。'] or
                    bot_response in ['？', '？？', '...', '。。。']):
                    continue

                # 3. 过滤重复内容（A重复B的话不算对话）
                if user_msg == bot_response or user_msg in bot_response or bot_response in user_msg:
                    logger.debug(f"过滤重复内容: A='{user_msg[:30]}...' B='{bot_response[:30]}...'")
                    continue

                # 4. 调用专业的消息关系分析器判断两条消息是否构成真实对话关系
                if await self._is_valid_dialog_pair(current_msg, next_msg, group_id):
                    dialog_pairs.append({
                        'user': user_msg,
                        'assistant': bot_response
                    })

            # 选择最佳的对话片段（取前5个）
            if len(dialog_pairs) >= 3:
                selected_pairs = dialog_pairs[:5]

                # 生成Few Shots格式
                few_shots_lines = [
                    "*Here are few shots of dialogs, you need to imitate the tone of 'B' in the following dialogs to respond:"
                ]

                for pair in selected_pairs:
                    few_shots_lines.append(f"A: {pair['user']}")
                    few_shots_lines.append(f"B: {pair['assistant']}")

                logger.info(f"群组 {group_id} 生成了 {len(selected_pairs)} 组Few Shots对话")
                return '\n'.join(few_shots_lines)

            logger.debug(f"群组 {group_id} 未找到足够的有效对话片段（需要至少3组，当前{len(dialog_pairs)}组）")
            return ""

        except Exception as e:
            logger.error(f"生成Few Shots对话失败: {e}")
            return ""

    async def _is_valid_dialog_pair(self, msg1: Any, msg2: Any, group_id: str) -> bool:
        """
        使用专业的消息关系分析器判断两条消息是否构成真实的对话关系

        Args:
            msg1: 第一条消息（MessageData对象）
            msg2: 第二条消息（MessageData对象）
            group_id: 群组ID

        Returns:
            bool: True表示构成对话关系，False表示不构成
        """
        try:
            # 检查服务工厂是否已初始化
            if not self.factory_manager or not hasattr(self.factory_manager, '_service_factory') or not self.factory_manager._service_factory:
                # 服务工厂未初始化，使用简单规则
                return msg1.message != msg2.message

            # 获取消息关系分析器
            relationship_analyzer = self.factory_manager.get_service_factory().create_message_relationship_analyzer()

            if not relationship_analyzer:
                # 降级方案：简单规则
                return msg1.message != msg2.message

            # 构造分析器需要的消息格式
            msg1_dict = {
                'message_id': msg1.message_id or str(hash(f"{msg1.timestamp}{msg1.sender_id}")),
                'sender_id': msg1.sender_id,
                'message': msg1.message,
                'timestamp': msg1.timestamp
            }

            msg2_dict = {
                'message_id': msg2.message_id or str(hash(f"{msg2.timestamp}{msg2.sender_id}")),
                'sender_id': msg2.sender_id,
                'message': msg2.message,
                'timestamp': msg2.timestamp
            }

            # 调用专业分析器
            relationship = await relationship_analyzer._analyze_message_pair(msg1_dict, msg2_dict, group_id)

            # 判断结果
            if relationship:
                # 关系类型为direct_reply或topic_continuation，且置信度>0.5，则认为是有效对话
                is_valid = (
                    relationship.relationship_type in ['direct_reply', 'topic_continuation'] and
                    relationship.confidence > 0.5
                )

                if is_valid:
                    logger.debug(f"识别对话关系: {relationship.relationship_type} (置信度: {relationship.confidence:.2f})")

                return is_valid

            return False

        except Exception as e:
            logger.error(f"消息关系判断失败: {e}", exc_info=True)
            # 出错时保守判断，返回False
            return False

    async def _create_style_learning_review_request(self, group_id: str, learned_patterns: List[Any], few_shots_content: str):
        """创建对话风格学习结果的审查请求 - 包含去重逻辑"""
        try:
            # 1. 检查是否有重复的待审查记录（避免重复提交）
            existing_reviews = await self._get_pending_style_reviews(group_id)

            if existing_reviews:
                # 检查内容是否相似
                for existing in existing_reviews:
                    existing_content = existing.get('few_shots_content', '')
                    # 如果Few Shots内容完全相同，跳过创建
                    if existing_content == few_shots_content:
                        logger.info(f"群组 {group_id} 已存在相同的待审查风格学习记录，跳过重复创建")
                        return

            # 2. 构建审查内容
            review_data = {
                'type': 'style_learning',
                'group_id': group_id,
                'timestamp': time.time(),
                'learned_patterns': [pattern.to_dict() for pattern in learned_patterns],
                'few_shots_content': few_shots_content,
                'status': 'pending',  # pending, approved, rejected
                'description': f'群组 {group_id} 的对话风格学习结果（包含 {len(learned_patterns)} 个表达模式）'
            }

            # 3. 保存到数据库的审查表
            await self.db_manager.create_style_learning_review(review_data)

            logger.info(f"对话风格学习审查请求已创建: {group_id}")

        except Exception as e:
            logger.error(f"创建对话风格学习审查请求失败: {e}")

    async def _get_pending_style_reviews(self, group_id: str) -> List[Dict[str, Any]]:
        """获取指定群组的待审查风格学习记录"""
        try:
            async with self.db_manager.get_db_connection() as conn:
                cursor = await conn.cursor()

                # 查询该群组的pending状态的风格学习审查记录
                await cursor.execute('''
                    SELECT id, group_id, few_shots_content, timestamp
                    FROM style_learning_reviews
                    WHERE group_id = ? AND status = 'pending' AND type = 'style_learning'
                    ORDER BY timestamp DESC
                    LIMIT 10
                ''', (group_id,))

                rows = await cursor.fetchall()

                reviews = []
                for row in rows:
                    reviews.append({
                        'id': row[0],
                        'group_id': row[1],
                        'few_shots_content': row[2],
                        'timestamp': row[3]
                    })

                return reviews

        except Exception as e:
            logger.error(f"获取待审查风格学习记录失败: {e}")
            return []

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

    @filter.command("migrate_database")
    @filter.permission_type(PermissionType.ADMIN)
    async def migrate_database_command(self, event: AstrMessageEvent):
        """手动触发数据库迁移（支持 SQLite ↔ MySQL 双向迁移）

        用法:
        - migrate_database sqlite      # 从当前数据库迁移到 SQLite
        - migrate_database mysql       # 从当前数据库迁移到 MySQL
        - migrate_database auto        # 自动检测并迁移（推荐）
        """
        try:
            # 解析命令参数
            message = event.get_message_str().strip()
            parts = message.split(maxsplit=1)

            if len(parts) < 2:
                help_text = (
                    "📖 数据库迁移命令使用说明：\n\n"
                    "用法: migrate_database <target>\n\n"
                    "参数说明:\n"
                    "• sqlite - 迁移到 SQLite 数据库\n"
                    "• mysql  - 迁移到 MySQL 数据库\n"
                    "• auto   - 自动检测当前配置并迁移\n\n"
                    "示例:\n"
                    "migrate_database auto    # 自动迁移（推荐）\n"
                    "migrate_database mysql   # 强制迁移到 MySQL\n"
                    "migrate_database sqlite  # 强制迁移到 SQLite\n\n"
                    "⚠️ 注意事项:\n"
                    "1. 迁移会自动备份数据\n"
                    "2. 迁移过程可能需要几分钟\n"
                    "3. 迁移期间请勿关闭程序\n"
                    "4. 建议在低峰期执行迁移"
                )
                yield event.plain_result(help_text)
                return

            target_db_type = parts[1].lower()

            if target_db_type not in ['sqlite', 'mysql', 'auto']:
                yield event.plain_result("❌ 无效的目标数据库类型，请使用: sqlite, mysql 或 auto")
                return

            # 获取当前数据库配置
            current_db_url = self._get_database_url()
            current_db_type = 'mysql' if 'mysql' in current_db_url else 'sqlite'

            # 确定源数据库和目标数据库
            if target_db_type == 'auto':
                # 自动模式：使用配置中的数据库类型作为目标
                config_db_type = getattr(self.plugin_config, 'db_type', 'sqlite').lower()
                if config_db_type == current_db_type:
                    yield event.plain_result(f"ℹ️ 当前已使用 {current_db_type.upper()} 数据库，无需迁移")
                    return
                target_db_type = config_db_type

            # 检查是否需要迁移
            if target_db_type == current_db_type:
                yield event.plain_result(f"ℹ️ 当前已使用 {current_db_type.upper()} 数据库，无需迁移到 {target_db_type.upper()}")
                return

            # 构建目标数据库 URL
            if target_db_type == 'mysql':
                # 迁移到 MySQL
                host = getattr(self.plugin_config, 'mysql_host', 'localhost')
                port = getattr(self.plugin_config, 'mysql_port', 3306)
                user = getattr(self.plugin_config, 'mysql_user', 'root')
                password = getattr(self.plugin_config, 'mysql_password', '')
                database = getattr(self.plugin_config, 'mysql_database', 'astrbot_self_learning')

                if not password:
                    yield event.plain_result("❌ MySQL 密码未配置，请先在配置文件中设置 mysql_password")
                    return

                target_db_url = f"mysql+aiomysql://{user}:{password}@{host}:{port}/{database}"
                source_db_url = current_db_url

            else:  # target_db_type == 'sqlite'
                # 迁移到 SQLite
                db_path = getattr(self.plugin_config, 'messages_db_path', None)
                if not db_path:
                    db_path = os.path.join(self.plugin_config.data_dir, 'messages.db')
                if not os.path.isabs(db_path):
                    db_path = os.path.abspath(db_path)

                target_db_url = f"sqlite:///{db_path}"
                source_db_url = current_db_url

            # 显示迁移信息
            migration_info = (
                f"🔄 准备执行数据库迁移\n\n"
                f"源数据库: {current_db_type.upper()}\n"
                f"目标数据库: {target_db_type.upper()}\n"
                f"源URL: {self._mask_url(source_db_url)}\n"
                f"目标URL: {self._mask_url(target_db_url)}\n\n"
                f"⏳ 开始迁移，请稍候..."
            )
            yield event.plain_result(migration_info)

            # 执行迁移
            try:
                from .utils.migration_tool_v2 import auto_migrate

                logger.info(f"=" * 70)
                logger.info(f"[手动迁移] 开始从 {current_db_type.upper()} 迁移到 {target_db_type.upper()}")
                logger.info(f"[手动迁移] 源数据库: {self._mask_url(source_db_url)}")
                logger.info(f"[手动迁移] 目标数据库: {self._mask_url(target_db_url)}")
                logger.info(f"=" * 70)

                # 执行迁移
                await auto_migrate(source_db_url, target_db_url)

                # 更新迁移标记文件
                migration_marker = os.path.join(self.plugin_config.data_dir, '.migration_completed')
                with open(migration_marker, 'w', encoding='utf-8') as f:
                    f.write(json.dumps({
                        'migrated_at': time.time(),
                        'migrated_date': datetime.now().isoformat(),
                        'plugin_version': '1.6.1',
                        'database_type': target_db_type,
                        'database_url': target_db_url.split('://')[-1].split('@')[-1] if '@' in target_db_url else target_db_url,
                        'migration_method': 'manual_command'
                    }, ensure_ascii=False, indent=2))

                success_message = (
                    f"✅ 数据库迁移成功完成！\n\n"
                    f"📊 迁移详情:\n"
                    f"• 源数据库: {current_db_type.upper()}\n"
                    f"• 目标数据库: {target_db_type.upper()}\n"
                    f"• 迁移时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    f"⚠️ 重要提示:\n"
                    f"1. 数据已成功迁移到 {target_db_type.upper()}\n"
                    f"2. 请在配置文件中将 db_type 改为 '{target_db_type}'\n"
                    f"3. 重启插件后将使用新数据库\n"
                    f"4. 建议验证数据完整性后再删除旧数据库"
                )

                logger.info(f"=" * 70)
                logger.info(f"✅ [手动迁移] 数据库迁移成功完成")
                logger.info(f"=" * 70)

                yield event.plain_result(success_message)

            except Exception as migrate_error:
                error_message = (
                    f"❌ 数据库迁移失败\n\n"
                    f"错误信息: {str(migrate_error)}\n\n"
                    f"故障排查:\n"
                    f"1. 检查目标数据库连接是否正常\n"
                    f"2. 确认数据库用户有足够权限\n"
                    f"3. 查看完整错误日志\n"
                    f"4. 如果是 MySQL，检查密码和主机配置"
                )

                logger.error(f"=" * 70)
                logger.error(f"❌ [手动迁移] 数据库迁移失败: {migrate_error}")
                logger.error(f"=" * 70)
                logger.error("故障排查提示:", exc_info=True)

                yield event.plain_result(error_message)

        except Exception as e:
            logger.error(f"数据库迁移命令执行失败: {e}", exc_info=True)
            yield event.plain_result(f"❌ 数据库迁移命令执行失败: {str(e)}")

    @filter.command("db_status")
    @filter.permission_type(PermissionType.ADMIN)
    async def db_status_command(self, event: AstrMessageEvent):
        """查看当前数据库状态和统计信息"""
        try:
            # 获取当前数据库配置
            current_db_url = self._get_database_url()
            current_db_type = 'mysql' if 'mysql' in current_db_url else 'sqlite'

            # 构建状态信息
            status_info = "📊 数据库状态报告\n\n"
            status_info += f"🔗 当前数据库类型: {current_db_type.upper()}\n"
            status_info += f"📍 数据库URL: {self._mask_url(current_db_url)}\n\n"

            # 读取迁移标记
            migration_marker = os.path.join(self.plugin_config.data_dir, '.migration_completed')
            if os.path.exists(migration_marker):
                try:
                    with open(migration_marker, 'r', encoding='utf-8') as f:
                        migration_info = json.load(f)
                        migrated_date = migration_info.get('migrated_date', '未知')
                        migration_method = migration_info.get('migration_method', 'auto')
                        status_info += f"✅ 迁移状态: 已完成\n"
                        status_info += f"📅 迁移时间: {migrated_date}\n"
                        status_info += f"🔧 迁移方式: {'手动' if migration_method == 'manual_command' else '自动'}\n\n"
                except Exception as e:
                    status_info += f"⚠️ 迁移标记文件读取失败: {e}\n\n"
            else:
                status_info += f"ℹ️ 迁移状态: 未迁移或首次启动\n\n"

            # 获取数据库全局消息统计
            try:
                from sqlalchemy import text

                async with self.db_manager.get_session() as session:
                    # 统计所有群组的消息数据
                    raw_msg_result = await session.execute(text("SELECT COUNT(*) FROM raw_messages"))
                    raw_msg_count = raw_msg_result.scalar() or 0

                    filtered_msg_result = await session.execute(text("SELECT COUNT(*) FROM filtered_messages"))
                    filtered_msg_count = filtered_msg_result.scalar() or 0

                    bot_msg_result = await session.execute(text("SELECT COUNT(*) FROM bot_messages"))
                    bot_msg_count = bot_msg_result.scalar() or 0

                    # 统计群组数量
                    group_count_result = await session.execute(text("SELECT COUNT(DISTINCT group_id) FROM raw_messages"))
                    group_count = group_count_result.scalar() or 0

                status_info += "📈 消息统计 (全部数据库):\n"
                status_info += f"• 原始消息: {raw_msg_count} 条\n"
                status_info += f"• 筛选后消息: {filtered_msg_count} 条\n"
                status_info += f"• Bot消息: {bot_msg_count} 条\n"
                status_info += f"• 群组数量: {group_count} 个\n\n"
            except Exception as e:
                status_info += f"⚠️ 消息统计获取失败: {e}\n\n"

            # 数据库配置建议
            config_db_type = getattr(self.plugin_config, 'db_type', 'sqlite').lower()
            if config_db_type != current_db_type:
                status_info += f"⚠️ 配置不一致警告:\n"
                status_info += f"• 配置文件: {config_db_type.upper()}\n"
                status_info += f"• 实际使用: {current_db_type.upper()}\n"
                status_info += f"💡 建议使用 'migrate_database auto' 进行迁移\n\n"

            # 可用的迁移选项
            status_info += "🔄 可用迁移选项:\n"
            if current_db_type == 'sqlite':
                status_info += "• migrate_database mysql - 迁移到 MySQL\n"
            else:
                status_info += "• migrate_database sqlite - 迁移到 SQLite\n"
            status_info += "• migrate_database auto - 自动检测并迁移\n"

            yield event.plain_result(status_info.strip())

        except Exception as e:
            logger.error(f"获取数据库状态失败: {e}", exc_info=True)
            yield event.plain_result(f"❌ 获取数据库状态失败: {str(e)}")


    @filter.on_llm_request()
    async def inject_diversity_to_llm_request(self, event: AstrMessageEvent, req=None):
        """在所有LLM请求前注入多样性增强prompt - 框架层面Hook (始终生效,不需要开启自动学习)

        重要改进 (v1.1.1):
        - 将注入内容添加到 req.system_prompt 而不是 req.prompt
        - 解决对话历史膨胀问题：AstrBot 只保存 req.prompt 到对话历史，不保存 system_prompt
        - 避免 token 超限：每次对话不再累积注入的人格设定、社交上下文、多样性提示

        注入内容包括：
        1. 社交上下文（表达模式学习、社交关系、好感度、深度心理状态、行为指导）
        2. 多样性增强（语言风格、回复模式、表达变化、历史Bot消息避重）
        3. 黑话理解（如果用户消息中包含黑话）
        4. 会话级增量更新（临时人格调整）
        """
        try:
            # 检查 req 参数是否存在
            if req is None:
                logger.warning("[LLM Hook] req 参数为 None，跳过注入")
                return

            # 如果diversity_manager不存在,跳过注入
            if not hasattr(self, 'diversity_manager') or not self.diversity_manager:
                logger.debug("[LLM Hook] diversity_manager未初始化,跳过多样性注入")
                return

            group_id = event.get_group_id() or event.get_sender_id()
            user_id = event.get_sender_id()

            # ✅ 维护group_id到unified_msg_origin的映射
            if hasattr(event, 'unified_msg_origin') and event.unified_msg_origin:
                self.group_id_to_unified_origin[group_id] = event.unified_msg_origin
                logger.debug(f"[LLM Hook] 更新映射: {group_id} -> {event.unified_msg_origin}")

            # 检查是否有内容可注入
            if not req.prompt:
                logger.debug("[LLM Hook] req.prompt为空,跳过多样性注入")
                return

            original_prompt_length = len(req.prompt)
            logger.info(f"✅ [LLM Hook] 开始注入多样性增强 (group: {group_id}, 原prompt长度: {original_prompt_length})")

            # 收集要注入的内容 - 所有增量内容都注入到 req.prompt（用户消息上下文）
            prompt_injections = []

            # ❌ 移除重复的人格注入 - 框架已经在 req.system_prompt 中注入了 persona["prompt"]
            # 如果需要查看当前人格，可以通过 req.system_prompt 访问
            # session_persona_prompt = await self._get_active_persona_prompt(event)
            logger.debug("[LLM Hook] 跳过基础人格注入（框架已处理），专注于增量内容")

            # ✅ 1. 注入社交上下文（已整合所有功能）
            # SocialContextInjector 现在包含：
            # - 表达模式学习（原有）
            # - 社交关系（原有）
            # - 好感度（原有）
            # - 基础情绪（原有）
            # - 深度心理状态（整合自 PsychologicalSocialContextInjector）
            # - 行为模式指导（整合自 PsychologicalSocialContextInjector）

            if hasattr(self, 'social_context_injector') and self.social_context_injector:
                try:
                    social_context = await self.social_context_injector.format_complete_context(
                        group_id=group_id,
                        user_id=user_id,
                        include_social_relations=self.plugin_config.include_social_relations,  # 社交关系
                        include_affection=self.plugin_config.include_affection_info,  # 好感度
                        include_mood=False,  # 基础情绪（已被深度心理状态包含，避免重复）
                        include_expression_patterns=True,  # ⭐ 表达模式学习结果
                        include_psychological=True,  # ⭐ 深度心理状态分析
                        include_behavior_guidance=True,  # ⭐ 行为模式指导
                        include_conversation_goal=self.plugin_config.enable_goal_driven_chat,  # ⭐ 对话目标上下文
                        enable_protection=True
                    )
                    if social_context:
                        prompt_injections.append(social_context)
                        logger.info(f"✅ [LLM Hook] 已准备完整社交上下文 (长度: {len(social_context)})")
                    else:
                        logger.debug(f"[LLM Hook] 群组 {group_id} 暂无社交上下文")
                except Exception as e:
                    logger.warning(f"[LLM Hook] 注入社交上下文失败: {e}")
            else:
                logger.debug("[LLM Hook] social_context_injector未初始化，跳过社交上下文注入")

            # ✅ 2. 构建多样性增强内容 (不传入base_prompt，只生成注入内容) - 注入到 prompt
            diversity_content = await self.diversity_manager.build_diversity_prompt_injection(
                "",  # 传空字符串，只生成注入内容
                group_id=group_id,  # 传入group_id以获取历史消息
                inject_style=True,
                inject_pattern=True,
                inject_variation=True,
                inject_history=True  # 注入历史Bot消息，避免重复
            )

            # 提取纯注入内容（去除空的base_prompt）
            diversity_content = diversity_content.strip()
            if diversity_content:
                prompt_injections.append(diversity_content)
                logger.info(f"✅ [LLM Hook] 已准备多样性增强内容 (长度: {len(diversity_content)})")

            # ✅ 3. 注入黑话理解（如果用户消息中包含黑话）- 注入到 prompt
            if hasattr(self, 'jargon_query_service') and self.jargon_query_service:
                try:
                    # 获取用户消息文本
                    user_message = event.message_str if hasattr(event, 'message_str') else str(event.get_message())

                    # 检查消息中是否包含黑话，并获取解释
                    jargon_explanation = await self.jargon_query_service.check_and_explain_jargon(
                        text=user_message,
                        chat_id=group_id
                    )

                    if jargon_explanation:
                        prompt_injections.append(jargon_explanation)
                        logger.info(f"✅ [LLM Hook] 已准备黑话理解内容 (长度: {len(jargon_explanation)})")
                    else:
                        logger.debug(f"[LLM Hook] 用户消息中未检测到已知黑话")
                except Exception as e:
                    logger.warning(f"[LLM Hook] 注入黑话理解失败: {e}")
            else:
                logger.debug("[LLM Hook] jargon_query_service未初始化，跳过黑话注入")

            # ✅ 4. 注入会话级增量更新 (修复会话串流bug) - 注入到 prompt
            if hasattr(self, 'temporary_persona_updater') and self.temporary_persona_updater:
                try:
                    session_updates = self.temporary_persona_updater.session_updates.get(group_id, [])
                    if session_updates:
                        updates_text = '\n\n'.join(session_updates)
                        prompt_injections.append(updates_text)
                        logger.info(f"✅ [LLM Hook] 已准备会话级更新 (会话: {group_id}, 更新数: {len(session_updates)}, 长度: {len(updates_text)})")
                    else:
                        logger.debug(f"[LLM Hook] 会话 {group_id} 暂无增量更新")
                except Exception as e:
                    logger.warning(f"[LLM Hook] 注入会话级更新失败: {e}")
            else:
                logger.debug("[LLM Hook] temporary_persona_updater未初始化，跳过会话级更新注入")

            # ✅ 5. 注入所有增量内容（根据配置选择注入位置）
            # 关键改进 (v1.1.1)：支持将注入内容添加到 system_prompt 或 prompt
            # - system_prompt: 不会被 AstrBot 保存到对话历史，避免历史膨胀 (推荐)
            # - prompt: 会被保存到对话历史，导致 token 累积和超限 (旧版行为)
            if prompt_injections:
                prompt_injection_text = '\n\n'.join(prompt_injections)

                # 根据配置决定注入位置
                injection_target = getattr(self.plugin_config, 'llm_hook_injection_target', 'system_prompt')

                if injection_target == 'system_prompt':
                    # 注入到 system_prompt（推荐，不会被保存到对话历史）
                    if not req.system_prompt:
                        req.system_prompt = ""

                    original_length = len(req.system_prompt)
                    req.system_prompt += '\n\n' + prompt_injection_text
                    final_length = len(req.system_prompt)
                    injected_length = final_length - original_length

                    logger.info(f"✅ [LLM Hook] System Prompt 注入完成 - 原长度: {original_length}, 新增: {injected_length}, 总长度: {final_length}")
                    logger.info(f"💡 [LLM Hook] 注入位置: system_prompt (不会被保存到对话历史)")

                else:
                    # 注入到 prompt（旧版行为，会导致对话历史膨胀）
                    original_length = len(req.prompt)
                    req.prompt += '\n\n' + prompt_injection_text
                    final_length = len(req.prompt)
                    injected_length = final_length - original_length

                    logger.info(f"✅ [LLM Hook] Prompt 注入完成 - 原长度: {original_length}, 新增: {injected_length}, 总长度: {final_length}")
                    logger.warning(f"⚠️ [LLM Hook] 注入位置: prompt (会被保存到对话历史，可能导致token超限)")

                # 统计和日志
                current_language_style = self.diversity_manager.get_current_style()
                current_response_pattern = self.diversity_manager.get_current_pattern()

                logger.info(f"✅ [LLM Hook] 当前语言风格: {current_language_style}, 回复模式: {current_response_pattern}")
                logger.info(f"✅ [LLM Hook] 注入内容数量: {len(prompt_injections)}项")
                logger.debug(f"✅ [LLM Hook] 注入内容预览: {prompt_injection_text[:200]}...")
            else:
                logger.debug("[LLM Hook] 没有可注入的增量内容")

        except Exception as e:
            logger.error(f"❌ [LLM Hook] 框架层面注入多样性失败: {e}", exc_info=True)

    async def terminate(self):
        """插件卸载时的清理工作 - 增强后台任务管理"""
        try:
            logger.info("开始插件清理工作...")
            
            # 1. 停止所有学习任务
            logger.info("停止所有学习任务...")
            for group_id, task in list(self.learning_tasks.items()):
                try:
                    # 先停止学习流程
                    await self.progressive_learning.stop_learning()
                    
                    # 取消学习任务
                    if not task.done():
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
                    
                    logger.info(f"群组 {group_id} 学习任务已停止")
                except Exception as e:
                    logger.error(f"停止群组 {group_id} 学习任务失败: {e}")
            
            self.learning_tasks.clear()
            
            # 2. 停止学习调度器
            if hasattr(self, 'learning_scheduler'):
                try:
                    await self.learning_scheduler.stop()
                    logger.info("学习调度器已停止")
                except Exception as e:
                    logger.error(f"停止学习调度器失败: {e}")
                
            # 3. 取消所有后台任务
            logger.info("取消所有后台任务...")
            for task in list(self.background_tasks):
                try:
                    if not task.done():
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
                except Exception as e:
                    logger.error(LogMessages.BACKGROUND_TASK_CANCEL_ERROR.format(error=e))
            
            self.background_tasks.clear()
            
            # 4. 停止所有服务
            logger.info("停止所有服务...")
            if hasattr(self, 'factory_manager'):
                try:
                    await self.factory_manager.cleanup()
                    logger.info("服务工厂已清理")
                except Exception as e:
                    logger.error(f"清理服务工厂失败: {e}")
            
            # 5. 清理临时人格
            if hasattr(self, 'temporary_persona_updater'):
                try:
                    await self.temporary_persona_updater.cleanup_temp_personas()
                    logger.info("临时人格已清理")
                except Exception as e:
                    logger.error(f"清理临时人格失败: {e}")
                
            # 6. 保存最终状态
            if hasattr(self, 'message_collector'):
                try:
                    await self.message_collector.save_state()
                    logger.info("消息收集器状态已保存")
                except Exception as e:
                    logger.error(f"保存消息收集器状态失败: {e}")
                
            # 7. 停止 Web 服务器 (终极修正)
            global server_instance, _server_cleanup_lock
            async with _server_cleanup_lock:
                if server_instance:
                    try:
                        logger.info(f"正在停止Web服务器 (端口: {server_instance.port})...")
                        
                        # [A] 停止服务 (跨线程通知退出)
                        await server_instance.stop()
                        
                        # [B] 关键新增：强制垃圾回收
                        # 确保 Socket 句柄立即释放，而不是等待 Python 自动回收
                        # 这对 Windows 这种 Socket 敏感的系统至关重要
                        import gc
                        gc.collect()
                        
                        # [C] 平台差异化等待
                        import sys
                        if sys.platform == 'win32':
                            logger.info("Windows环境：等待端口资源释放...")
                            # Windows 需要给内核一点时间把 TIME_WAIT 清理掉
                            await asyncio.sleep(2.0)
                        
                        server_instance = None
                        logger.info("Web服务器实例已清理")
                    except Exception as e:
                        logger.error(f"停止Web服务器失败: {e}", exc_info=True)
                        server_instance = None

            # 8. 保存配置到文件
            try:
                config_path = os.path.join(self.plugin_config.data_dir, 'config.json')
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(self.plugin_config.to_dict(), f, ensure_ascii=False, indent=2)
                logger.info(LogMessages.PLUGIN_CONFIG_SAVED)
            except Exception as e:
                logger.error(f"保存配置失败: {e}")
            
            logger.info(LogMessages.PLUGIN_UNLOAD_SUCCESS)
            
        except Exception as e:
            logger.error(LogMessages.PLUGIN_UNLOAD_CLEANUP_FAILED.format(error=e), exc_info=True)

    async def _get_active_persona_prompt(self, event: AstrMessageEvent) -> Optional[str]:
        """
        获取当前会话配置的人格提示词

        优先读取 AstrBot 框架中的会话 -> 人格映射，回退到默认人格
        """
        try:
            if not event or not hasattr(self, "context"):
                return None

            conv_manager = getattr(self.context, "conversation_manager", None)
            astr_persona_manager = getattr(self.context, "persona_manager", None)
            if not conv_manager or not astr_persona_manager:
                return None

            unified_origin = getattr(event, "unified_msg_origin", None)
            if not unified_origin:
                return None

            conv_id = await conv_manager.get_curr_conversation_id(unified_origin)
            if not conv_id:
                conv_id = await conv_manager.new_conversation(unified_origin)

            conv = await conv_manager.get_conversation(
                unified_msg_origin=unified_origin,
                conversation_id=conv_id,
                create_if_not_exists=True,
            )

            persona_id = None
            if conv:
                conv_persona_id = getattr(conv, "persona_id", None)
                if conv_persona_id and conv_persona_id != "[%None]":
                    persona_id = conv_persona_id

            persona_data = None
            if persona_id:
                persona_data = await astr_persona_manager.get_persona(persona_id)
            else:
                persona_data = await astr_persona_manager.get_default_persona_v3(umo=unified_origin)

            if not persona_data:
                return None

            if isinstance(persona_data, dict):
                return persona_data.get("system_prompt") or persona_data.get("prompt")

            return getattr(persona_data, "system_prompt", None)

        except Exception as exc:
            logger.warning(f"获取会话人格失败: {exc}")
            return None
    
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
