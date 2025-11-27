"""
配置蓝图 - 处理插件配置管理
"""
from quart import Blueprint, request, jsonify
from astrbot.api import logger

from ..dependencies import get_container
from ..services.config_service import ConfigService
from ..middleware.auth import require_auth
from ..utils.response import success_response, error_response

config_bp = Blueprint('config', __name__, url_prefix='/api')


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
