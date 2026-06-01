"""WebUI 服务器全生命周期管理 — 创建、启动、停止、服务注册"""
from __future__ import annotations

import asyncio
import inspect
import sys
from typing import Optional, Any, Dict, TYPE_CHECKING

from astrbot.api import logger

if TYPE_CHECKING:
    from ..config import PluginConfig
    from ..core.factory import FactoryManager
    from .server import Server

# 模块级服务器实例（原 main.py 中的 global server_instance）
_server_instance: Optional["Server"] = None
_server_cleanup_lock = asyncio.Lock()


def get_server_instance() -> Optional[Server]:
    return _server_instance


class WebUIManager:
    """WebUI 服务器全生命周期管理"""

    def __init__(
        self,
        plugin_config: "PluginConfig",
        context: Any,
        factory_manager: "FactoryManager",
        perf_tracker: Any,
        group_id_to_unified_origin: Dict[str, str],
        feature_delegation: Any = None,
        astrbot_config: Any = None,
        plugin_instance: Any = None,
        v2_integration: Any = None,
    ):
        self._config = plugin_config
        self._context = context
        self._factory_manager = factory_manager
        self._perf_tracker = perf_tracker
        self._group_id_to_unified_origin = group_id_to_unified_origin
        self._feature_delegation = feature_delegation
        self._astrbot_config = astrbot_config
        self._plugin_instance = plugin_instance
        self._v2_integration = v2_integration or getattr(plugin_instance, "v2_integration", None)
        self._database_manager = getattr(plugin_instance, "db_manager", None)
        self._database_degraded = False
        self._database_start_error: Optional[str] = None
        self._database_start_attempted = False

    # 创建

    def create_server(self) -> bool:
        """创建 Server 实例（不启动）。返回 True 表示需要立即启动。"""
        global _server_instance

        if not self._config.enable_web_interface:
            logger.info("WebUI 未启用")
            return False

        logger.info(f"准备创建 Server 实例，端口: {self._config.web_interface_port}")
        try:
            if _server_instance is not None:
                logger.warning("检测到已存在的 Web 服务器实例，可能是插件重载")
                if (
                    hasattr(_server_instance, "server_thread")
                    and _server_instance.server_thread
                    and _server_instance.server_thread.is_alive()
                ):
                    logger.warning("旧的 Web 服务器仍在运行，将复用该实例")
                    logger.info(
                        f"Web 服务器地址: http://{_server_instance.host}:{_server_instance.port}"
                    )
                    return False
                else:
                    logger.info("旧的 Web 服务器已停止，创建新实例")
                    _server_instance = None

            if _server_instance is None:
                try:
                    from .server import Server
                except ImportError as e:
                    logger.warning(
                        f"WebUI 依赖未安装，跳过 Web 服务器创建；请在插件设置页面手动安装依赖: {e}"
                    )
                    return False

                _server_instance = Server(
                    host=self._config.web_interface_host,
                    port=self._config.web_interface_port,
                )
                if _server_instance:
                    logger.info(
                        f"Web 服务器实例已创建 "
                        f"({_server_instance.host}:{_server_instance.port})，将在 on_load 中启动"
                    )
                    return True # 需要立即启动
                else:
                    logger.error("Web 服务器实例创建失败")
        except Exception as e:
            logger.error(f"创建 Web 服务器实例失败: {e}", exc_info=True)

        return False

    # 启动

    async def immediate_start(self, db_manager: Any) -> None:
        """__init__ 阶段立即启动 WebUI（通过 asyncio.create_task 调用）"""
        await asyncio.sleep(1) # 等待插件完全初始化
        self._database_manager = db_manager

        global _server_instance
        if not _server_instance or not self._config.enable_web_interface:
            if not self._config.enable_web_interface:
                logger.info("WebUI 未启用，跳过立即启动")
            else:
                logger.info("WebUI 服务器未创建，跳过立即启动；如需使用请在插件设置页面手动安装 WebUI 依赖")
            return

        # 设置 WebUI 服务
        db_manager = await self._ensure_database_manager_started(db_manager)
        astrbot_pm = await self._acquire_persona_manager()
        try:
            await self._setup_services(astrbot_pm, db_manager)
        except Exception as e:
            logger.error(f"设置插件服务失败: {e}", exc_info=True)
            return

        # 启动服务器
        try:
            await _server_instance.start()
            logger.info("Web 服务器已成功启动")
        except Exception as e:
            logger.error(f"Web 服务器启动失败: {e}", exc_info=True)
            logger.error("端口可能仍被占用，WebUI 不可用")
            _server_instance = None

    async def setup_and_start(self) -> None:
        """on_load 阶段设置服务并启动。"""
        global _server_instance

        if not self._config.enable_web_interface or not _server_instance:
            if not self._config.enable_web_interface:
                logger.info("WebUI 未启用，跳过启动")
            if not _server_instance:
                logger.info("WebUI 服务器未创建，跳过启动；如需使用请在插件设置页面手动安装 WebUI 依赖")
            return

        # 设置 WebUI 服务
        astrbot_pm = await self._acquire_persona_manager()
        try:
            await self._setup_services(astrbot_pm, self._database_manager)
            logger.info("Web 服务器插件服务设置完成")
        except Exception as e:
            logger.error(f"设置 Web 服务器插件服务失败: {e}", exc_info=True)
            return

        # 启动服务器
        try:
            logger.info(
                f"准备启动 Web 服务器: "
                f"http://{_server_instance.host}:{_server_instance.port}"
            )
            await _server_instance.start()
            logger.info("Web 服务器启动完成")
        except Exception as e:
            logger.error(f"Web 服务器启动失败: {e}", exc_info=True)

    # 停止

    async def stop(self) -> None:
        """有序停止 WebUI 服务器"""
        global _server_instance, _server_cleanup_lock

        try:
            await asyncio.wait_for(
                _server_cleanup_lock.acquire(),
                timeout=self._config.task_cancel_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("[WebUI] 获取清理锁超时，强制继续清理")
            # 拿不到锁也要继续清理
            if _server_instance:
                try:
                    await _server_instance.stop()
                except Exception:
                    pass
                _server_instance = None
            return

        try:
            if not _server_instance:
                return
            try:
                logger.info(f"正在停止 Web 服务器 (端口: {_server_instance.port})...")
                await _server_instance.stop()

                if sys.platform == "win32":
                    logger.info("Windows 环境：等待端口资源释放...")
                    await asyncio.sleep(2.0)

                _server_instance = None
                logger.info("Web 服务器实例已清理")
            except Exception as e:
                logger.error(f"停止 Web 服务器失败: {e}", exc_info=True)
                _server_instance = None
        finally:
            _server_cleanup_lock.release()

    # 内部方法

    async def _acquire_persona_manager(self) -> Any:
        """获取 AstrBot 框架 PersonaManager（带延迟重试）"""
        astrbot_persona_manager = None
        try:
            if hasattr(self._context, "persona_manager"):
                astrbot_persona_manager = self._context.persona_manager
                if astrbot_persona_manager:
                    logger.info(
                        f"成功获取 AstrBot 框架 PersonaManager: "
                        f"{type(astrbot_persona_manager)}"
                    )
                else:
                    logger.warning("Context 中 persona_manager 为 None")
            else:
                logger.warning("Context 中没有 persona_manager 属性")

            if not astrbot_persona_manager:
                logger.info("尝试延迟获取 PersonaManager...")
                await asyncio.sleep(3)
                if (
                    hasattr(self._context, "persona_manager")
                    and self._context.persona_manager
                ):
                    astrbot_persona_manager = self._context.persona_manager
                    logger.info(
                        f"延迟获取成功: {type(astrbot_persona_manager)}"
                    )
                else:
                    logger.warning("延迟获取 PersonaManager 仍然失败")
        except Exception as e:
            logger.error(f"获取 AstrBot 框架 PersonaManager 失败: {e}", exc_info=True)

        return astrbot_persona_manager

    async def _setup_services(
        self,
        astrbot_persona_manager: Any,
        database_manager: Any = None,
    ) -> None:
        """调用 set_plugin_services 注册服务到 WebUI 容器"""
        from .dependencies import get_container as _get_webui_container, set_plugin_services

        database_manager = database_manager or getattr(
            self._plugin_instance,
            "db_manager",
            None,
        )
        database_manager = await self._ensure_database_manager_started(database_manager)
        self._database_manager = database_manager

        await set_plugin_services(
            plugin_config=self._config,
            factory_manager=self._factory_manager,
            llm_client=None,
            astrbot_persona_manager=astrbot_persona_manager,
            group_id_to_unified_origin=self._group_id_to_unified_origin,
            feature_delegation=self._feature_delegation,
            astrbot_config=self._astrbot_config,
            plugin_instance=self._plugin_instance,
            database_manager=database_manager,
            database_degraded=self._database_degraded,
            database_start_error=self._database_start_error,
            v2_integration=self._v2_integration,
        )
        _get_webui_container().perf_collector = self._perf_tracker

    def _mark_database_degraded(self, message: str) -> None:
        self._database_degraded = True
        self._database_start_error = message

    def _mark_database_available(self) -> None:
        self._database_degraded = False
        self._database_start_error = None

    async def _ensure_database_manager_started(self, database_manager: Any) -> Any:
        """Reuse the plugin database manager and keep WebUI available if it fails."""
        if database_manager is None:
            self._mark_database_degraded("数据库管理器不可用")
            return None

        has_engine_attr = hasattr(database_manager, "engine")
        needs_start = not getattr(database_manager, "_started", False) or (
            has_engine_attr and getattr(database_manager, "engine", None) is None
        )
        start = getattr(database_manager, "start", None)
        if not needs_start:
            self._mark_database_available()
            return database_manager
        if not callable(start):
            self._mark_database_degraded("数据库管理器没有可调用的 start 方法")
            return database_manager

        if self._database_start_attempted and self._database_degraded:
            return database_manager

        logger.info("[WebUI] 数据库管理器尚未启动，注册服务前先启动")
        self._database_start_attempted = True
        try:
            started = start()
            if inspect.isawaitable(started):
                started = await started
        except Exception as e:
            error_message = str(e) or type(e).__name__
            self._mark_database_degraded(error_message)
            logger.warning(
                f"[WebUI] 数据库管理器启动异常，WebUI 将以数据库受限模式继续启动: {e}",
                exc_info=True,
            )
            return database_manager
        if started is False:
            self._mark_database_degraded("数据库管理器启动返回 False")
            logger.warning("[WebUI] 数据库管理器启动失败，WebUI 将以数据库受限模式继续启动")
            return database_manager

        self._mark_database_available()
        return database_manager
