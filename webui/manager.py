"""WebUI 服务器全生命周期管理 — 创建、启动、停止、服务注册"""
import asyncio
import gc
import sys
from typing import Optional, Any, Dict, TYPE_CHECKING

from astrbot.api import logger

from .server import Server
from .dependencies import get_container as _get_webui_container, set_plugin_services

if TYPE_CHECKING:
    from ..config import PluginConfig
    from ..core.factory import FactoryManager

# 模块级服务器实例（原 main.py 中的 global server_instance）
_server_instance: Optional[Server] = None
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
    ):
        self._config = plugin_config
        self._context = context
        self._factory_manager = factory_manager
        self._perf_tracker = perf_tracker
        self._group_id_to_unified_origin = group_id_to_unified_origin

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
                _server_instance = Server(port=self._config.web_interface_port)
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

        global _server_instance
        if not _server_instance or not self._config.enable_web_interface:
            logger.error("server_instance 为空或 web_interface 未启用")
            return

        # 启动数据库
        try:
            db_started = await db_manager.start()
            if not db_started:
                raise RuntimeError("数据库管理器启动失败")
        except Exception as e:
            logger.error(f"启动数据库管理器失败: {e}", exc_info=True)
            raise

        # 设置 WebUI 服务
        astrbot_pm = await self._acquire_persona_manager()
        try:
            await self._setup_services(astrbot_pm)
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
                logger.error("server_instance 为空，无法启动 Web 服务器")
            return

        # 设置 WebUI 服务
        astrbot_pm = await self._acquire_persona_manager()
        try:
            await self._setup_services(astrbot_pm)
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
                _server_cleanup_lock.acquire(), timeout=3.0,
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
                gc.collect()

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

    async def _setup_services(self, astrbot_persona_manager: Any) -> None:
        """调用 set_plugin_services 注册服务到 WebUI 容器"""
        await set_plugin_services(
            self._config,
            self._factory_manager,
            None,
            astrbot_persona_manager,
            self._group_id_to_unified_origin,
        )
        _get_webui_container().perf_collector = self._perf_tracker
