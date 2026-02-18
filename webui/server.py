"""
WebUI 服务器
"""
import os
import sys
import gc
import asyncio
import socket
from typing import Optional
import hypercorn.asyncio
from hypercorn.config import Config as HypercornConfig
try:
    from hypercorn.config import Sockets
except ImportError:
    class Sockets:
        def __init__(self, secure_sockets, insecure_sockets, quic_sockets):
            self.secure_sockets = secure_sockets
            self.insecure_sockets = insecure_sockets
            self.quic_sockets = quic_sockets

from astrbot.api import logger

from .app import create_app, register_blueprints
from .dependencies import get_container


# Hypercorn 安全配置（避免 create_sockets 绑定失败）
class SecureConfig(HypercornConfig):
    """安全的 Hypercorn 配置，处理端口绑定问题"""

    def create_sockets(self):
        try:
            return super().create_sockets()
        except Exception:
            insecure = []
            for bind_str in self.bind:
                parts = bind_str.rsplit(":", 1)
                host = parts[0] if len(parts) > 1 else "0.0.0.0"
                port = int(parts[1]) if len(parts) > 1 else 7833
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                if hasattr(socket, 'SO_REUSEPORT'):
                    try:
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                    except (AttributeError, OSError):
                        pass
                sock.bind((host, port))
                sock.listen(5)
                sock.setblocking(False)
                insecure.append(sock)
            return Sockets([], insecure, [])


class Server:
    """WebUI 服务器"""

    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Server, cls).__new__(cls)
        return cls._instance

    def __init__(self, host: str = "0.0.0.0", port: int = 7833, auto_find_port: bool = False):
        """
        初始化服务器

        Args:
            host: 监听地址
            port: 监听端口
            auto_find_port: 兼容参数（未使用）
        """
        if hasattr(self, '_initialized') and self._initialized:
            return

        self._initialized = True
        self.host = host
        self.port = port
        self.server_task: Optional[asyncio.Task] = None
        self.shutdown_trigger = asyncio.Event()
        self.app = None

        logger.info(f"🔧 [WebUI] 初始化Web服务器 (固定端口: {port})...")

    async def start(self):
        """启动服务器"""
        try:
            # 如果已经有运行中的任务，跳过
            if self.server_task and not self.server_task.done():
                logger.info("[WebUI] 服务器已在运行中")
                return

            # 重置 shutdown 触发器（处理重启场景）
            self.shutdown_trigger = asyncio.Event()

            # 检查端口是否可用，不可用则尝试清理
            if not self._is_port_available(self.port):
                logger.warning(f"⚠️ [WebUI] 端口 {self.port} 被占用，尝试清理...")
                await self._kill_port_holder(self.port)

            # 获取配置
            container = get_container()
            webui_config = container.webui_config

            # 创建应用
            self.app = create_app(webui_config)

            # 注册蓝图
            register_blueprints(self.app)

            # 配置 Hypercorn
            config = SecureConfig()
            config.bind = [f"{self.host}:{self.port}"]
            config.accesslog = None
            config.errorlog = None
            config.loglevel = "WARNING"
            config.workers = 1
            config.worker_class = "asyncio"

            # 启动服务器
            logger.info(f"🚀 [WebUI] 启动服务器: http://{self.host}:{self.port}")

            self.server_task = asyncio.create_task(
                hypercorn.asyncio.serve(
                    self.app,
                    config,
                    shutdown_trigger=self.shutdown_trigger.wait
                )
            )

            # 验证服务器是否成功启动
            for _ in range(5):
                await asyncio.sleep(1.0)
                if await self._verify_tcp():
                    logger.info(f"✅ [WebUI] Web服务器启动成功")
                    logger.info(f"🔗 [WebUI] 本地访问: http://127.0.0.1:{self.port}")
                    return

            logger.warning("⚠️ [WebUI] 服务器任务已启动但端口无响应")

        except Exception as e:
            logger.error(f"❌ [WebUI] 服务器启动失败: {e}", exc_info=True)
            raise

    async def stop(self):
        """停止服务器"""
        try:
            logger.info("🛑 [WebUI] 停止服务器...")

            if self.server_task:
                self.shutdown_trigger.set()
                try:
                    await asyncio.wait_for(self.server_task, timeout=5.0)
                except asyncio.TimeoutError:
                    self.server_task.cancel()
                    try:
                        await self.server_task
                    except asyncio.CancelledError:
                        pass
                self.server_task = None

            gc.collect()
            logger.info("✅ [WebUI] 服务器已停止")

        except Exception as e:
            logger.error(f"❌ [WebUI] 停止服务器失败: {e}", exc_info=True)

    def _is_port_available(self, port: int) -> bool:
        """检查端口是否可用"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.2)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((self.host, port))
                return True
        except Exception:
            return False

    async def _verify_tcp(self) -> bool:
        """验证服务器端口是否已监听"""
        loop = asyncio.get_event_loop()

        def check():
            try:
                # 连接验证时需要用可达地址，0.0.0.0 不可连接，用 127.0.0.1 代替
                check_host = "127.0.0.1" if self.host == "0.0.0.0" else self.host
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(1)
                    return s.connect_ex((check_host, self.port)) == 0
            except Exception:
                return False

        return await loop.run_in_executor(None, check)

    async def _kill_port_holder(self, port: int):
        """清理占用端口的进程"""
        try:
            if sys.platform == 'win32':
                cmd_find = f'netstat -ano | findstr :{port}'
                process = await asyncio.create_subprocess_shell(
                    cmd_find,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await process.communicate()
                if stdout:
                    lines = stdout.decode('gbk', errors='ignore').strip().split('\n')
                    for line in lines:
                        parts = line.strip().split()
                        if len(parts) > 4 and 'LISTENING' in line:
                            pid = parts[-1]
                            if pid and pid != str(os.getpid()):
                                logger.warning(f"🔫 [WebUI] 清理占用进程 PID={pid}")
                                await asyncio.create_subprocess_shell(
                                    f'taskkill /F /PID {pid}',
                                    stdout=asyncio.subprocess.DEVNULL,
                                    stderr=asyncio.subprocess.DEVNULL
                                )
                                await asyncio.sleep(1.0)
        except Exception:
            pass
