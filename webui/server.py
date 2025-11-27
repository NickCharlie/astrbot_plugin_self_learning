"""
WebUI 服务器
"""
import asyncio
from typing import Optional
import hypercorn.asyncio
from hypercorn.config import Config as HypercornConfig
from astrbot.api import logger

from .app import create_app, register_blueprints
from .dependencies import get_container


class Server:
    """WebUI 服务器"""

    def __init__(self, host: str = "0.0.0.0", port: int = 7833):
        """
        初始化服务器

        Args:
            host: 监听地址
            port: 监听端口
        """
        self.host = host
        self.port = port
        self.server_task: Optional[asyncio.Task] = None
        self.shutdown_trigger = asyncio.Event()
        self.app = None

        logger.info(f"🌐 [WebUI] 服务器初始化: {host}:{port}")

    async def start(self):
        """启动服务器"""
        try:
            # 获取配置
            container = get_container()
            webui_config = container.webui_config

            # 创建应用
            self.app = create_app(webui_config)

            # 注册蓝图
            register_blueprints(self.app)

            # 配置 Hypercorn
            config = HypercornConfig()
            config.bind = [f"{self.host}:{self.port}"]

            # 启动服务器
            logger.info(f"🚀 [WebUI] 启动服务器: http://{self.host}:{self.port}")

            self.server_task = asyncio.create_task(
                hypercorn.asyncio.serve(
                    self.app,
                    config,
                    shutdown_trigger=self.shutdown_trigger.wait
                )
            )

            logger.info("✅ [WebUI] 服务器启动成功")

        except Exception as e:
            logger.error(f"❌ [WebUI] 服务器启动失败: {e}", exc_info=True)
            raise

    async def stop(self):
        """停止服务器"""
        try:
            logger.info("🛑 [WebUI] 停止服务器...")

            if self.server_task:
                self.shutdown_trigger.set()
                await self.server_task

            logger.info("✅ [WebUI] 服务器已停止")

        except Exception as e:
            logger.error(f"❌ [WebUI] 停止服务器失败: {e}", exc_info=True)
