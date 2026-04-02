"""
社交图谱公开分享蓝图（只读）
"""
from quart import Blueprint, jsonify, render_template
from astrbot.api import logger

from ..dependencies import get_container
from ..services.social_service import SocialService
from ..services.graph_share_service import GraphShareService

graph_share_bp = Blueprint("graph_share", __name__)


@graph_share_bp.route("/graph/share/<token>", methods=["GET"])
async def graph_share_page(token: str):
    """公开图谱分享页面（无需登录）。"""
    return await render_template("graph_share.html", share_token=token)

@graph_share_bp.route("/api/public/social_graph/<token>", methods=["GET"])
async def get_shared_social_graph(token: str):
    """公开图谱数据接口（只读，基于分享 token）。"""
    try:
        container = get_container()
        share_service = GraphShareService(container)
        share, reason = share_service.get_share(token, increment_view=True)

        if not share:
            status = 410 if reason in {"expired", "revoked"} else 404
            return jsonify(
                {"success": False, "error": "分享链接无效或已过期"}
            ), status

        group_id = str(share.get("group_id", ""))
        social_service = SocialService(container)
        relations_data = await social_service.get_social_relations(group_id)

        if not relations_data.get("success", False):
            return jsonify({"success": False, "error": "图谱数据不可用"}), 404

        members = relations_data.get("members", [])
        relations = relations_data.get("relations", [])

        sanitized_members = [
            {
                "user_id": m.get("user_id"),
                "nickname": m.get("nickname"),
                "message_count": m.get("message_count", 0),
            }
            for m in members
        ]
        sanitized_relations = [
            {
                "source": r.get("source"),
                "target": r.get("target"),
                "source_name": r.get("source_name"),
                "target_name": r.get("target_name"),
                "strength": r.get("strength", 0),
                "type": r.get("type"),
                "type_text": r.get("type_text"),
                "frequency": r.get("frequency", 0),
            }
            for r in relations
        ]

        return jsonify(
            {
                "success": True,
                "share": {
                    "group_id": group_id,
                    "created_at": share.get("created_at"),
                    "expires_at": share.get("expires_at_iso"),
                    "view_count": share.get("view_count", 0),
                },
                "graph": {
                    "group_id": group_id,
                    "members": sanitized_members,
                    "relations": sanitized_relations,
                    "member_count": relations_data.get(
                        "member_count", len(sanitized_members)
                    ),
                    "relation_count": relations_data.get(
                        "relation_count", len(sanitized_relations)
                    ),
                },
            }
        ), 200

    except Exception as e:
        logger.error(f"获取分享图谱失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": "服务器错误"}), 500
