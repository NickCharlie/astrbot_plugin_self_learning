"""
人格管理蓝图 - 处理人格CRUD操作
"""
from quart import Blueprint, request, jsonify
from astrbot.api import logger

from ..dependencies import get_container
from ..services.persona_service import PersonaService
from ..services.persona_backup_service import PersonaBackupService
from ..middleware.auth import require_auth
from ..utils.response import success_response, error_response

personas_bp = Blueprint('personas', __name__, url_prefix='/api')


@personas_bp.route("/persona_management/list", methods=["GET"])
@require_auth
async def get_personas_list():
    """获取所有人格列表"""
    try:
        container = get_container()
        persona_service = PersonaService(container)
        personas = await persona_service.get_all_personas()

        return jsonify({"personas": personas}), 200

    except Exception as e:
        logger.error(f"获取人格列表失败: {e}", exc_info=True)
        # 返回空列表而不是错误,避免前端显示错误
        return jsonify({"personas": []}), 200


@personas_bp.route("/persona_management/get/<persona_id>", methods=["GET"])
@require_auth
async def get_persona_details(persona_id: str):
    """获取特定人格详情"""
    try:
        container = get_container()
        persona_service = PersonaService(container)
        persona = await persona_service.get_persona_details(persona_id)

        if not persona:
            return error_response("人格不存在", 404)

        return jsonify(persona), 200

    except ValueError as e:
        return error_response(str(e), 500)
    except Exception as e:
        logger.error(f"获取人格详情失败: {e}", exc_info=True)
        return error_response(f"获取人格详情失败: {str(e)}", 500)


@personas_bp.route("/persona_management/create", methods=["POST"])
@require_auth
async def create_persona():
    """创建新人格"""
    try:
        data = await request.get_json()

        container = get_container()
        persona_service = PersonaService(container)
        success, message, persona_id = await persona_service.create_persona(data)

        if success:
            return jsonify({
                "message": message,
                "persona_id": persona_id
            }), 200
        else:
            return error_response(message, 400)

    except ValueError as e:
        return error_response(str(e), 503)
    except Exception as e:
        logger.error(f"创建人格失败: {e}", exc_info=True)
        return error_response(f"创建人格失败: {str(e)}", 500)


@personas_bp.route("/persona_management/update/<persona_id>", methods=["POST"])
@require_auth
async def update_persona(persona_id: str):
    """更新人格"""
    try:
        data = await request.get_json()

        container = get_container()
        persona_service = PersonaService(container)
        success, message = await persona_service.update_persona(persona_id, data)

        if success:
            return jsonify({"message": message}), 200
        else:
            return error_response(message, 400)

    except ValueError as e:
        return error_response(str(e), 503)
    except Exception as e:
        logger.error(f"更新人格失败: {e}", exc_info=True)
        return error_response(f"更新人格失败: {str(e)}", 500)


@personas_bp.route("/persona_management/delete/<persona_id>", methods=["POST"])
@require_auth
async def delete_persona(persona_id: str):
    """删除人格"""
    try:
        container = get_container()
        persona_service = PersonaService(container)
        success, message = await persona_service.delete_persona(persona_id)

        if success:
            return jsonify({"message": message}), 200
        else:
            return error_response(message, 400)

    except ValueError as e:
        return error_response(str(e), 503)
    except Exception as e:
        logger.error(f"删除人格失败: {e}", exc_info=True)
        return error_response(f"删除人格失败: {str(e)}", 500)


@personas_bp.route("/persona_management/default", methods=["GET"])
@require_auth
async def get_default_persona():
    """获取默认人格"""
    try:
        container = get_container()
        persona_service = PersonaService(container)
        group_id = request.args.get("group_id", "default")
        default_persona = await persona_service.get_default_persona(group_id)

        return jsonify(default_persona), 200

    except Exception as e:
        logger.error(f"获取默认人格失败: {e}", exc_info=True)
        # 返回基本默认人格而不是错误
        return jsonify({
            "persona_id": "default",
            "system_prompt": "You are a helpful assistant.",
            "begin_dialogs": [],
            "tools": []
        }), 200


@personas_bp.route("/persona_management/current", methods=["GET"])
@require_auth
async def get_current_persona_state():
    """获取当前生效人格状态预览"""
    try:
        container = get_container()
        persona_service = PersonaService(container)
        group_id = request.args.get("group_id", "default")
        current_state = await persona_service.get_current_persona_state(group_id)

        return jsonify(current_state), 200

    except Exception as e:
        logger.error(f"获取当前人格状态失败: {e}", exc_info=True)
        return error_response(f"获取当前人格状态失败: {str(e)}", 500)


@personas_bp.route("/persona_backups/list", methods=["GET"])
@require_auth
async def list_persona_backups():
    """获取人格备份列表"""
    group_id = request.args.get("group_id", "default")
    limit = request.args.get("limit", 20)
    try:
        container = get_container()
        backup_service = PersonaBackupService(container)
        result = await backup_service.list_backups(group_id=group_id, limit=limit)
        return jsonify(result), 200

    except ValueError as e:
        return jsonify({
            "group_id": group_id,
            "backups": [],
            "total": 0,
            "available": False,
            "message": str(e),
        }), 200
    except Exception as e:
        logger.error(f"获取人格备份列表失败: {e}", exc_info=True)
        return error_response(f"获取人格备份列表失败: {str(e)}", 500)


@personas_bp.route("/persona_backups/<int:backup_id>", methods=["GET"])
@require_auth
async def get_persona_backup(backup_id: int):
    """获取人格备份详情"""
    try:
        container = get_container()
        backup_service = PersonaBackupService(container)
        group_id = request.args.get("group_id", "default")
        backup = await backup_service.get_backup(backup_id, group_id=group_id)
        return jsonify(backup), 200

    except ValueError as e:
        return error_response(str(e), 404)
    except Exception as e:
        logger.error(f"获取人格备份详情失败: {e}", exc_info=True)
        return error_response(f"获取人格备份详情失败: {str(e)}", 500)


@personas_bp.route("/persona_backups/<int:backup_id>/restore", methods=["POST"])
@require_auth
async def restore_persona_backup(backup_id: int):
    """恢复人格备份"""
    try:
        data = await request.get_json(silent=True) or {}
        group_id = data.get("group_id") or request.args.get("group_id", "default")

        container = get_container()
        backup_service = PersonaBackupService(container)
        success, message = await backup_service.restore_backup(backup_id, group_id=group_id)

        if success:
            return jsonify({"message": message}), 200
        return error_response(message, 400)

    except ValueError as e:
        return error_response(str(e), 404)
    except Exception as e:
        logger.error(f"恢复人格备份失败: {e}", exc_info=True)
        return error_response(f"恢复人格备份失败: {str(e)}", 500)


@personas_bp.route("/persona_backups/<int:backup_id>", methods=["DELETE"])
@require_auth
async def delete_persona_backup(backup_id: int):
    """删除人格备份"""
    try:
        container = get_container()
        backup_service = PersonaBackupService(container)
        group_id = request.args.get("group_id", "default")
        success, message = await backup_service.delete_backup(backup_id, group_id=group_id)

        if success:
            return jsonify({"message": message}), 200
        return error_response(message, 404)

    except ValueError as e:
        return error_response(str(e), 503)
    except Exception as e:
        logger.error(f"删除人格备份失败: {e}", exc_info=True)
        return error_response(f"删除人格备份失败: {str(e)}", 500)


@personas_bp.route("/persona_management/export/<persona_id>", methods=["GET"])
@require_auth
async def export_persona(persona_id: str):
    """导出人格配置"""
    try:
        container = get_container()
        persona_service = PersonaService(container)
        persona_export = await persona_service.export_persona(persona_id)

        return jsonify(persona_export), 200

    except ValueError as e:
        if "不存在" in str(e):
            return error_response(str(e), 404)
        return error_response(str(e), 500)
    except Exception as e:
        logger.error(f"导出人格失败: {e}", exc_info=True)
        return error_response(f"导出人格失败: {str(e)}", 500)


@personas_bp.route("/persona_management/import", methods=["POST"])
@require_auth
async def import_persona():
    """导入人格配置"""
    try:
        data = await request.get_json()

        container = get_container()
        persona_service = PersonaService(container)
        success, message, persona_id = await persona_service.import_persona(data)

        if success:
            return jsonify({
                "message": message,
                "persona_id": persona_id
            }), 200
        else:
            return error_response(message, 400)

    except ValueError as e:
        return error_response(str(e), 500)
    except Exception as e:
        logger.error(f"导入人格失败: {e}", exc_info=True)
        return error_response(f"导入人格失败: {str(e)}", 500)
