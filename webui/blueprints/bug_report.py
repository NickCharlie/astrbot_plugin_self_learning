"""
Bug报告蓝图 - 处理Bug报告相关路由
"""
from quart import Blueprint, request, jsonify
from astrbot.api import logger

from ..dependencies import get_container
from ..services.bug_report_service import BugReportService
from ..middleware.auth import require_auth
from ..utils.response import success_response, error_response

bug_report_bp = Blueprint('bug_report', __name__, url_prefix='/api')


@bug_report_bp.route("/bug_report/config", methods=["GET"])
@require_auth
async def get_bug_report_config():
    """获取Bug自助提交配置与日志预览"""
    try:
        container = get_container()
        bug_service = BugReportService(container)
        config = bug_service.get_bug_report_config()

        return jsonify(config), 200

    except Exception as e:
        logger.error(f"获取Bug报告配置失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@bug_report_bp.route("/bug_report", methods=["POST"])
@require_auth
async def submit_bug_report():
    """提交Bug到禅道接口"""
    try:
        bug_data = await request.get_json()

        container = get_container()
        bug_service = BugReportService(container)
        success, message, response_data = await bug_service.submit_bug_report(bug_data)

        if success:
            return jsonify({
                'success': True,
                'message': message,
                'data': response_data
            }), 200
        else:
            return error_response(message, 400)

    except Exception as e:
        logger.error(f"提交Bug报告失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@bug_report_bp.route("/bug_report/history", methods=["GET"])
@require_auth
async def get_bug_history():
    """获取Bug报告历史"""
    try:
        limit = request.args.get('limit', 20, type=int)

        container = get_container()
        bug_service = BugReportService(container)
        history = await bug_service.get_bug_history(limit)

        return jsonify({
            'history': history,
            'total': len(history)
        }), 200

    except Exception as e:
        logger.error(f"获取Bug历史失败: {e}", exc_info=True)
        return error_response(str(e), 500)
