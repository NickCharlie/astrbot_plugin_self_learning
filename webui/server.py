"""
WebUI 服务器
采用独立守护线程运行 uvicorn（FastAPI/ASGI，与 AstrBot core 一致），
确保跨平台（Windows/macOS/CentOS/Ubuntu）端口可靠释放
"""
import os
import sys
import asyncio
import socket
import threading
from typing import Optional

import uvicorn

from astrbot.api import logger

from .app import create_app, register_blueprints
from .dependencies import get_container


class Server:
    """WebUI 服务器（守护线程模式）"""

    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Server, cls).__new__(cls)
        return cls._instance

    def __init__(self, host: str = "0.0.0.0", port: int = 7833, auto_find_port: bool = False):
        if hasattr(self, '_initialized') and self._initialized:
            return

        self._initialized = True
        self.host = host
        self.port = port
        self.server_thread: Optional[threading.Thread] = None
        self._thread_loop = None
        self._uvicorn_server: Optional[uvicorn.Server] = None
        self._asgi_app = None
        self.app = None

        logger.info(f"[WebUI] 初始化Web服务器 (固定端口: {port})...")

    def _run_thread(self):
        """在独立线程中运行 uvicorn 服务器"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._thread_loop = loop

            config = uvicorn.Config(
                self._asgi_app,
                host=self.host,
                port=self.port,
                log_level="warning",
                access_log=False,
                workers=1,
                lifespan="off",
            )
            server = uvicorn.Server(config)
            self._uvicorn_server = server
            server.run()
            loop.close()
            logger.debug("[WebUI] 服务器线程已退出")
        except Exception as e:
            logger.error(f"[WebUI] 服务器线程异常: {e}")

    async def start(self):
        """启动服务器"""
        try:
            if self.server_thread and self.server_thread.is_alive():
                logger.info("[WebUI] 服务器已在运行中")
                return

            # 检查端口是否可用，不可用则尝试清理
            if not self._is_port_available(self.port):
                logger.warning(f"[WebUI] 端口 {self.port} 被占用，尝试清理...")
                await self._kill_port_holder(self.port)

            # 获取配置并创建应用
            container = get_container()
            webui_config = container.webui_config
            self.app = create_app(webui_config)
            register_blueprints(self.app)
            self._asgi_app = self.app.get_asgi_app()

            # 在守护线程中启动服务器
            logger.info(f"[WebUI] 启动服务器: http://{self.host}:{self.port}")

            self.server_thread = threading.Thread(
                target=self._run_thread,
                daemon=True,
                name="SelfLearning_WebUI"
            )
            self.server_thread.start()

            # 验证服务器是否成功启动
            for _ in range(5):
                await asyncio.sleep(1.0)
                if await self._verify_tcp():
                    logger.info(f"[WebUI] Web服务器启动成功")
                    logger.info(f"[WebUI] 本地访问: http://127.0.0.1:{self.port}")
                    return

            logger.warning("[WebUI] 服务器线程已启动但端口无响应")

        except Exception as e:
            logger.error(f"[WebUI] 服务器启动失败: {e}", exc_info=True)
            raise

    async def stop(self):
        """停止服务器"""
        try:
            logger.info("[WebUI] 停止服务器...")

            # uvicorn 线程安全退出：置位 should_exit 后由事件循环自行收尾
            if self._uvicorn_server is not None:
                self._uvicorn_server.should_exit = True

            # 在线程池中等待线程退出，避免阻塞事件循环
            if self.server_thread:
                loop = asyncio.get_event_loop()
                try:
                    await asyncio.wait_for(
                        loop.run_in_executor(
                            None, self.server_thread.join, 5.0,
                        ),
                        timeout=6.0,
                    )
                except asyncio.TimeoutError:
                    logger.warning("[WebUI] 服务器线程退出超时，强制继续")
                self.server_thread = None

            self._thread_loop = None
            self._uvicorn_server = None
            self._asgi_app = None

            # 重置单例状态，确保下次重启可以重新初始化
            Server._instance = None
            self._initialized = False

            logger.info("[WebUI] 服务器已停止")

        except Exception as e:
            logger.error(f"[WebUI] 停止服务器失败: {e}", exc_info=True)

    def _is_port_available(self, port: int) -> bool:
        """检查端口是否已有监听者（connect 探测，避免绑定通配地址）"""
        check_host = "127.0.0.1" if self.host in ("0.0.0.0", "::", "") else self.host
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.2)
                # connect 失败 = 无人监听 = 可用；成功 = 已被占用
                return s.connect_ex((check_host, port)) != 0
        except OSError:
            # 无法探测时视为可用，真正绑定时如有冲突会由 uvicorn 报错
            return True

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
                                logger.warning(f"[WebUI] 清理占用进程 PID={pid}")
                                await asyncio.create_subprocess_shell(
                                    f'taskkill /F /PID {pid}',
                                    stdout=asyncio.subprocess.DEVNULL,
                                    stderr=asyncio.subprocess.DEVNULL
                                )
                                await asyncio.sleep(1.0)
            else:
                # macOS / Linux (CentOS, Ubuntu, etc.)
                cmd_find = f'lsof -ti tcp:{port}'
                process = await asyncio.create_subprocess_shell(
                    cmd_find,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await process.communicate()
                if stdout:
                    pids = stdout.decode().strip().split('\n')
                    current_pid = str(os.getpid())
                    for pid in pids:
                        pid = pid.strip()
                        if pid and pid != current_pid:
                            logger.warning(f"[WebUI] 清理占用进程 PID={pid}")
                            await asyncio.create_subprocess_shell(
                                f'kill -9 {pid}',
                                stdout=asyncio.subprocess.DEVNULL,
                                stderr=asyncio.subprocess.DEVNULL
                            )
                    await asyncio.sleep(0.5)
        except Exception:
            pass

    async def _verify_tcp(self) -> bool:
        """验证服务器端口是否已监听"""
        loop = asyncio.get_event_loop()

        def check():
            try:
                check_host = "127.0.0.1" if self.host == "0.0.0.0" else self.host
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(1)
                    return s.connect_ex((check_host, self.port)) == 0
            except Exception:
                return False

        return await loop.run_in_executor(None, check)
