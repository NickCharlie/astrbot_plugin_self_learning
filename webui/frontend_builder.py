"""Dashboard 前端自动构建器。

在插件加载时检测 Solid.js Dashboard 构建产物是否就绪；若缺失且本机存在
Node.js 工具链，则后台自动执行依赖安装与构建，让普通用户无需手动运行
``pnpm build`` 即可使用 WebUI 监控面板。

设计要点：
- **永不阻塞插件启动**：由调用方以 ``asyncio.create_task`` 在后台执行。
- **永不抛异常**：任何失败都仅记录日志并降级，绝不让插件加载失败。
- **进程级防并发**：插件热重载时不重复触发构建。
"""
from __future__ import annotations

import asyncio
import contextlib
import os
import re
import shutil
import threading
from typing import Optional, Tuple

from astrbot.api import logger

# Dashboard SPA 构建产物入口（相对于插件根目录）。
_DASHBOARD_INDEX = os.path.join("web_res", "static", "dashboard", "index.html")
_DASHBOARD_ASSETS = os.path.join("web_res", "static", "dashboard", "assets")
# 构建超时（秒）：install + build，覆盖慢网络环境下的依赖下载。
_BUILD_TIMEOUT = 300

# 进程级防并发标记，避免插件热重载时并发构建。
_build_lock = threading.Lock()
_building = False


def dashboard_artifact_exists(plugin_root: str) -> bool:
    """检查 Dashboard SPA 构建产物（index.html 及其引用资源）是否就绪。"""
    index_path = os.path.join(plugin_root, _DASHBOARD_INDEX)
    if not os.path.isfile(index_path):
        return False
    try:
        with open(index_path, "r", encoding="utf-8") as file:
            html = file.read()
    except OSError:
        return False

    asset_names = re.findall(r'["\']/static/dashboard/assets/([^"\']+)["\']', html)
    if not asset_names:
        return False
    assets_dir = os.path.join(plugin_root, _DASHBOARD_ASSETS)
    return all(os.path.isfile(os.path.join(assets_dir, name)) for name in asset_names)


def detect_build_tool() -> Optional[str]:
    """探测可用的前端构建工具，返回可执行文件绝对路径。

    优先级：pnpm > npm。Node.js 本身缺失则返回 ``None``。
    """
    if shutil.which("node") is None:
        return None
    pnpm = shutil.which("pnpm")
    if pnpm:
        return pnpm
    return shutil.which("npm")


def _tool_name(tool_path: str) -> str:
    """根据可执行文件路径判断工具名（pnpm / npm）。"""
    base = tool_path.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return "pnpm" if base.startswith("pnpm") else "npm"


async def _run_build_subprocess(plugin_root: str) -> Tuple[bool, str]:
    """执行 install + build 两步，返回 (是否成功, 说明)。"""
    tool_path = detect_build_tool()
    if tool_path is None:
        return False, "未检测到 Node.js / pnpm / npm，无法自动构建前端"

    tool = _tool_name(tool_path)
    web_src = os.path.join(plugin_root, "web_src")
    if not os.path.isdir(web_src):
        return False, f"web_src 源码目录不存在：{web_src}"

    logger.info(f"[WebUI] 检测到 Dashboard 前端产物缺失，开始自动构建（{tool}）...")

    steps = [
        ([tool_path, "install"], "安装依赖"),
        ([tool_path, "run", "build"], "构建前端"),
    ]
    for cmd, label in steps:
        logger.info(f"[WebUI] 自动构建 - {label}：{' '.join(os.path.basename(c) for c in cmd)}")
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=web_src,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except Exception as exc:
            return False, f"{label} 启动失败：{exc}"

        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=_BUILD_TIMEOUT)
        except asyncio.TimeoutError:
            with contextlib.suppress(Exception):
                proc.kill()
            with contextlib.suppress(Exception):
                await proc.wait()
            return False, f"{label} 超时（{_BUILD_TIMEOUT}s）"

        if proc.returncode != 0:
            tail = ""
            if stdout:
                tail = stdout.decode("utf-8", errors="replace")[-1500:]
            return False, f"{label} 失败（exit={proc.returncode}）\n{tail}"

    if dashboard_artifact_exists(plugin_root):
        logger.info("[WebUI] Dashboard 前端自动构建成功，刷新页面即可使用")
        return True, "构建成功"
    return False, "构建流程完成但产物仍缺失，请检查 web_src 源码"


async def ensure_dashboard_built(plugin_root: str) -> bool:
    """确保 Dashboard 产物就绪：已存在则跳过，缺失则后台自动构建。

    永不抛异常。返回 ``True`` 表示产物就绪（已存在或本次构建成功）。
    """
    global _building

    if dashboard_artifact_exists(plugin_root):
        return True

    with _build_lock:
        if _building:
            logger.info("[WebUI] Dashboard 自动构建已在进行中，本次跳过")
            return False
        _building = True

    try:
        ok, message = await _run_build_subprocess(plugin_root)
        if not ok:
            logger.warning(f"[WebUI] Dashboard 前端自动构建未完成：{message}")
        return ok
    except Exception as exc:
        logger.warning(f"[WebUI] Dashboard 前端自动构建发生异常：{exc}", exc_info=True)
        return False
    finally:
        with _build_lock:
            _building = False
