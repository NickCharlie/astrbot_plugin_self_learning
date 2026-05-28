"""
配置蓝图 - 处理插件配置管理
"""
import asyncio
import os
import sys
from quart import Blueprint, current_app, request, jsonify, session
from astrbot.api import logger

from ..dependencies import get_container
from ..services.config_service import ConfigService
from ..middleware.auth import require_auth
from ..utils.response import error_response

config_bp = Blueprint('config', __name__, url_prefix='/api')

BASIC_DEPENDENCY_PACKAGES = [
    "aiohttp",
    "emoji==2.14.1",
    "hypercorn==0.17.3",
    "jieba",
    "quart",
    "quart_cors==0.8.0",
    "pydantic",
    "sqlalchemy[asyncio]",
    "aiosqlite",
    "asyncpg",
    "cachetools>=5.3.0",
    "apscheduler",
    "defusedxml>=0.7.1",
]

FULL_DEPENDENCY_PACKAGES = list(dict.fromkeys([
    *BASIC_DEPENDENCY_PACKAGES,
    "psutil",
    "aiomysql",
    "prometheus_client>=0.20.0",
    "prometheus-async>=22.2.0",
    "networkx>=3.2,<3.5",
    "numpy>=1.26,<2.3",
    "pandas>=2.1,<2.4",
    "scikit_learn>=1.4,<1.8",
    "lightrag-hku>=1.4.0",
    "mem0ai>=1.0.0",
]))

DEPENDENCY_PACKAGES = FULL_DEPENDENCY_PACKAGES
DEPENDENCY_TIERS = {
    "basic": {
        "label": "基础能力依赖",
        "packages": BASIC_DEPENDENCY_PACKAGES,
    },
    "full": {
        "label": "全能力依赖",
        "packages": FULL_DEPENDENCY_PACKAGES,
    },
}
_dependency_install_lock = asyncio.Lock()
MANUAL_DEPENDENCY_INSTALL_SOURCE = "system_settings"


@config_bp.route("/config", methods=["GET"])
@require_auth
async def get_plugin_config():
    """获取插件配置"""
    try:
        container = get_container()
        config_service = ConfigService(container)
        config = await config_service.get_config()
        return jsonify(config), 200
    except ValueError as e:
        return error_response(str(e), 500)
    except Exception as e:
        logger.error(f"获取配置失败: {e}", exc_info=True)
        return error_response(f"获取配置失败: {str(e)}", 500)


@config_bp.route("/config/schema", methods=["GET"])
@require_auth
async def get_plugin_config_schema():
    """获取 dashboard 全量设置 schema。"""
    try:
        container = get_container()
        config_service = ConfigService(container)
        schema = await config_service.get_config_schema()
        return jsonify(schema), 200
    except ValueError as e:
        return error_response(str(e), 500)
    except Exception as e:
        logger.error(f"获取配置 schema 失败: {e}", exc_info=True)
        return error_response(f"获取配置 schema 失败: {str(e)}", 500)


@config_bp.route("/config", methods=["POST"])
@require_auth
async def update_plugin_config():
    """更新插件配置"""
    try:
        # 获取请求数据
        new_config = await request.get_json()

        # 使用服务层更新配置
        container = get_container()
        config_service = ConfigService(container)
        success, message, updated_config = await config_service.update_config(new_config)

        if success:
            return jsonify({
                "message": message,
                "new_config": updated_config
            }), 200
        else:
            return error_response(message, 500)

    except ValueError as e:
        return error_response(str(e), 500)
    except Exception as e:
        logger.error(f"更新配置失败: {e}", exc_info=True)
        return error_response(f"更新配置失败: {str(e)}", 500)


@config_bp.route("/dependencies/install", methods=["POST"])
@require_auth
async def install_plugin_dependencies():
    """手动安装插件的可选依赖。"""
    client_ip = request.remote_addr or "unknown"
    user_id = "authenticated" if session.get("authenticated") else "unknown"
    payload = await request.get_json(silent=True) or {}

    if (
        not isinstance(payload, dict)
        or payload.get("manual_confirmed") is not True
        or payload.get("source") != MANUAL_DEPENDENCY_INSTALL_SOURCE
    ):
        logger.warning(
            f"[WebUI] 拒绝插件依赖安装请求：缺少设置页手动确认，"
            f"user={user_id}, remote_addr={client_ip}"
        )
        return error_response("依赖安装只能在设置界面手动确认后触发", 400)

    if not current_app.config.get("ENABLE_WEB_DEP_INSTALL", True):
        logger.warning(
            f"[WebUI] 拒绝插件依赖安装请求：功能未启用，user={user_id}, remote_addr={client_ip}"
        )
        return error_response("当前环境未启用依赖安装功能", 403)

    tier = str(payload.get("tier") or "full").strip().lower()
    tier_definition = DEPENDENCY_TIERS.get(tier)
    if not tier_definition:
        logger.warning(
            f"[WebUI] 拒绝插件依赖安装请求：未知依赖档位 {tier!r}，"
            f"user={user_id}, remote_addr={client_ip}"
        )
        return error_response("未知依赖安装档位，请选择基础能力依赖或全能力依赖", 400)

    tier_label = tier_definition["label"]
    selected_packages = tier_definition["packages"]
    allowed_packages = current_app.config.get("ALLOWED_DEPENDENCY_PACKAGES")
    if allowed_packages:
        allowed_set = set(allowed_packages)
        packages_to_install = [pkg for pkg in selected_packages if pkg in allowed_set]
    else:
        packages_to_install = selected_packages

    if not packages_to_install:
        logger.warning(
            f"[WebUI] 插件依赖安装请求被拒绝：依赖列表为空，tier={tier}, "
            f"user={user_id}, remote_addr={client_ip}"
        )
        return error_response("依赖列表为空，无法安装", 400)

    logger.info(
        f"[WebUI] 收到插件依赖安装请求，tier={tier}, label={tier_label}, "
        f"user={user_id}, remote_addr={client_ip}, "
        f"packages={packages_to_install}"
    )

    if _dependency_install_lock.locked():
        logger.info(
            f"[WebUI] 插件依赖安装请求被拒绝：已有安装任务进行中，tier={tier}, "
            f"user={user_id}, remote_addr={client_ip}"
        )
        return error_response("依赖安装正在进行中，请稍后再试", 409)

    async with _dependency_install_lock:
        cmd = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-input",
            *packages_to_install,
        ]
        logger.info(
            f"[WebUI] 开始手动安装插件依赖，tier={tier}, label={tier_label}, "
            f"user={user_id}, packages={packages_to_install}"
        )
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            output = stdout.decode("utf-8", errors="replace")
            error = stderr.decode("utf-8", errors="replace")
            combined_output = (output + "\n" + error).strip()

            if process.returncode == 0:
                logger.info(f"[WebUI] 插件依赖安装完成，tier={tier}, label={tier_label}")
                return jsonify({
                    "message": f"{tier_label}安装完成",
                    "tier": tier,
                    "tier_label": tier_label,
                    "packages": packages_to_install,
                    "output": combined_output[-8000:],
                }), 200

            logger.error(
                f"[WebUI] 插件依赖安装失败，tier={tier}, label={tier_label}, "
                f"退出码: {process.returncode}\n{combined_output}"
            )
            return jsonify({
                "message": f"{tier_label}安装失败，退出码: {process.returncode}",
                "tier": tier,
                "tier_label": tier_label,
                "packages": packages_to_install,
                "output": combined_output[-8000:],
            }), 500
        except Exception as e:
            logger.error(f"[WebUI] 插件依赖安装异常: {e}", exc_info=True)
            return error_response(f"依赖安装异常: {str(e)}", 500)
