"""
学习功能蓝图 - 处理风格学习相关路由
"""
from astrbot.api import logger
from ..compat import Blueprint, request, jsonify

from ..dependencies import get_container
from ..services.learning_service import LearningService
from ..services.learning_content_service import LearningContentService
from ..middleware.auth import require_auth
from ..utils.response import success_response, error_response

learning_bp = Blueprint('learning', __name__, url_prefix='/api')


@learning_bp.route("/style_learning/results", methods=["GET"])
@require_auth
async def get_style_learning_results():
    """获取风格学习结果"""
    try:
        container = get_container()
        learning_service = LearningService(container)
        results_data = await learning_service.get_style_learning_results()

        return jsonify(results_data), 200

    except Exception as e:
        logger.error(f"获取风格学习结果失败: {e}", exc_info=True)
        return error_response("请求处理失败，请稍后重试", 500)


@learning_bp.route("/style_learning/reviews", methods=["GET"])
@require_auth
async def get_style_learning_reviews():
    """获取对话风格学习审查列表"""
    try:
        limit = int(request.args.get('limit', 50))
        keyword = request.args.get('keyword', '').strip()
        container = get_container()
        learning_service = LearningService(container)
        reviews_data = await learning_service.get_style_learning_reviews(
            limit=limit,
            keyword=keyword,
        )

        return jsonify(reviews_data), 200

    except ValueError as e:
        return error_response("请求处理失败，请稍后重试", 500)
    except Exception as e:
        logger.error(f"获取风格学习审查列表失败: {e}", exc_info=True)
        return error_response("请求处理失败，请稍后重试", 500)


@learning_bp.route("/style_learning/reviews/<int:review_id>/approve", methods=["POST"])
@require_auth
async def approve_style_learning_review(review_id: int):
    """批准对话风格学习审查 - 使用与人格学习审查相同的备份逻辑"""
    try:
        container = get_container()
        learning_service = LearningService(container)
        success, message = await learning_service.approve_style_learning_review(review_id)

        if success:
            return jsonify({
                'success': True,
                'message': message
            }), 200
        else:
            if '不存在' in message:
                return error_response(message, 404)
            return error_response(message, 500)

    except ValueError as e:
        return error_response("请求处理失败，请稍后重试", 500)
    except Exception as e:
        logger.error(f"批准风格学习审查失败: {e}", exc_info=True)
        return error_response("请求处理失败，请稍后重试", 500)


@learning_bp.route("/style_learning/reviews/<int:review_id>/reject", methods=["POST"])
@require_auth
async def reject_style_learning_review(review_id: int):
    """拒绝对话风格学习审查"""
    try:
        container = get_container()
        learning_service = LearningService(container)
        success, message = await learning_service.reject_style_learning_review(review_id)

        if success:
            return jsonify({
                'success': True,
                'message': message
            }), 200
        else:
            return error_response(message, 500)

    except ValueError as e:
        return error_response("请求处理失败，请稍后重试", 500)
    except Exception as e:
        logger.error(f"拒绝风格学习审查失败: {e}", exc_info=True)
        return error_response("请求处理失败，请稍后重试", 500)


@learning_bp.route("/style_learning/reviews/<int:review_id>", methods=["DELETE"])
@require_auth
async def delete_style_learning_review(review_id: int):
    """删除对话风格学习审查"""
    try:
        container = get_container()
        learning_service = LearningService(container)
        success, message = await learning_service.delete_style_learning_review(review_id)

        if success:
            return jsonify({
                'success': True,
                'message': message
            }), 200
        return error_response(message, 404 if '不存在' in message or '未找到' in message else 500)

    except ValueError as e:
        return error_response("请求处理失败，请稍后重试", 500)
    except Exception as e:
        logger.error(f"删除风格学习审查失败: {e}", exc_info=True)
        return error_response("请求处理失败，请稍后重试", 500)


@learning_bp.route("/style_learning/reviews/<int:review_id>", methods=["PUT"])
@require_auth
async def update_style_learning_review(review_id: int):
    """编辑待审的对话风格学习（描述 / Few-shot 示例 / 学习模式）"""
    try:
        data = await request.get_json() or {}
        if not isinstance(data, dict):
            return error_response("请求体必须是 JSON 对象", 400)

        container = get_container()
        learning_service = LearningService(container)
        success, message, item = await learning_service.update_style_learning_review(review_id, data)

        if success:
            return jsonify({
                'success': True,
                'message': message,
                'item': item,
            }), 200
        if '不存在' in message:
            return error_response(message, 404)
        return error_response(message, 400 if '没有可保存' in message else 500)

    except ValueError as e:
        return error_response("请求处理失败，请稍后重试", 500)
    except Exception as e:
        logger.error(f"编辑风格学习审查失败: {e}", exc_info=True)
        return error_response("请求处理失败，请稍后重试", 500)


@learning_bp.route("/style_learning/reviews/batch_review", methods=["POST"])
@require_auth
async def batch_review_style_learning_reviews():
    """批量批准或拒绝对话风格学习审查"""
    try:
        data = await request.get_json() or {}
        review_ids = data.get("review_ids") or data.get("ids") or []
        action = data.get("action")
        comment = data.get("comment", "")

        if not review_ids or not isinstance(review_ids, list):
            return error_response("review_ids is required and must be a list", 400)
        if action not in ["approve", "reject"]:
            return error_response("action must be 'approve' or 'reject'", 400)

        container = get_container()
        learning_service = LearningService(container)
        result = await learning_service.batch_review_style_learning_reviews(
            review_ids,
            action,
            comment,
        )

        if result.get("success"):
            return jsonify(result), 200
        return error_response(result.get("error") or "批量审查失败", 500)

    except ValueError as e:
        return error_response("请求处理失败，请稍后重试", 500)
    except Exception as e:
        logger.error(f"批量审查风格学习失败: {e}", exc_info=True)
        return error_response("请求处理失败，请稍后重试", 500)


@learning_bp.route("/style_learning/reviews/batch_delete", methods=["POST"])
@require_auth
async def batch_delete_style_learning_reviews():
    """批量删除对话风格学习审查"""
    try:
        data = await request.get_json() or {}
        review_ids = data.get("review_ids") or data.get("ids") or []

        if not review_ids or not isinstance(review_ids, list):
            return error_response("review_ids is required and must be a list", 400)

        container = get_container()
        learning_service = LearningService(container)
        result = await learning_service.batch_delete_style_learning_reviews(review_ids)

        if result.get("success"):
            return jsonify(result), 200
        return error_response(result.get("error") or "批量删除失败", 500)

    except ValueError as e:
        return error_response("请求处理失败，请稍后重试", 500)
    except Exception as e:
        logger.error(f"批量删除风格学习失败: {e}", exc_info=True)
        return error_response("请求处理失败，请稍后重试", 500)


@learning_bp.route("/style_learning/patterns", methods=["GET"])
@require_auth
async def get_style_learning_patterns():
    """获取风格学习模式"""
    try:
        container = get_container()
        learning_service = LearningService(container)
        patterns_data = await learning_service.get_style_learning_patterns()

        return jsonify(patterns_data), 200

    except Exception as e:
        logger.error(f"获取学习模式失败: {e}", exc_info=True)
        return error_response("请求处理失败，请稍后重试", 500)


@learning_bp.route("/style_learning/content_text", methods=["GET"])
@require_auth
async def get_style_learning_content_text():
    """获取对话风格学习的内容文本（与内嵌插件页桥接共用 LearningContentService）"""
    try:
        container = get_container()
        content_data = await LearningContentService(container).get_content_text()

        logger.debug(
            "学习内容文本已获取: dialogues=%s, analysis=%s, features=%s, history=%s",
            len(content_data['dialogues']),
            len(content_data['analysis']),
            len(content_data['features']),
            len(content_data['history']),
        )
        return jsonify(content_data), 200
    except Exception as e:
        logger.error(f"获取学习内容文本失败: {e}", exc_info=True)
        return error_response("请求处理失败，请稍后重试", 500)


@learning_bp.route("/style_learning/content_text/<bucket>/<int:item_id>", methods=["DELETE"])
@require_auth
async def delete_style_learning_content_text(bucket: str, item_id: int):
    """删除学习内容浏览页中的单条记录。"""
    try:
        container = get_container()
        database_manager = container.database_manager

        if not database_manager or not hasattr(database_manager, 'get_session'):
            return error_response("数据库管理器未初始化", 500)

        try:
            from ...models.orm import (
                RawMessage, StyleLearningReview,
                ExpressionPattern, LearningBatch,
            )
        except ImportError:
            from models.orm import (
                RawMessage, StyleLearningReview,
                ExpressionPattern, LearningBatch,
            )

        bucket_models = {
            'dialogues': (RawMessage, '原始对话'),
            'analysis': (StyleLearningReview, '分析结果'),
            'features': (ExpressionPattern, '表达模式'),
            'history': (LearningBatch, '学习批次'),
        }
        model_info = bucket_models.get(bucket)
        if model_info is None:
            return error_response(f"不支持的学习内容类型: {bucket}", 400)

        model, label = model_info
        from sqlalchemy import delete as sql_delete

        async with database_manager.get_session() as session:
            stmt = sql_delete(model).where(model.id == item_id)
            result = await session.execute(stmt)
            await session.commit()

            if result.rowcount > 0:
                return jsonify({
                    'success': True,
                    'message': f'{label} {item_id} 已删除',
                }), 200
            return error_response(f'{label} {item_id} 不存在', 404)

    except ValueError as e:
        return error_response("请求处理失败，请稍后重试", 500)
    except Exception as e:
        logger.error(f"删除学习内容失败: {e}", exc_info=True)
        return error_response("请求处理失败，请稍后重试", 500)


@learning_bp.route("/batches", methods=["GET"])
@require_auth
async def get_learning_batches():
    """获取学习批次列表（分页，与内嵌插件页桥接共用 LearningContentService）"""
    try:
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('page_size', 10, type=int)

        container = get_container()
        database_manager = container.database_manager
        if not database_manager or not hasattr(database_manager, 'get_session'):
            return error_response("数据库管理器未初始化", 500)

        data = await LearningContentService(container).list_batches(page, page_size)
        return jsonify({
            'success': True,
            'data': data,
        }), 200

    except ValueError as e:
        return error_response("请求处理失败，请稍后重试", 500)
    except Exception as e:
        logger.error(f"获取学习批次列表失败: {e}", exc_info=True)
        return error_response("请求处理失败，请稍后重试", 500)


@learning_bp.route("/batches/<int:batch_id>", methods=["DELETE"])
@require_auth
async def delete_learning_batch(batch_id: int):
    """删除单个学习批次"""
    try:
        container = get_container()
        database_manager = container.database_manager

        if not database_manager or not hasattr(database_manager, 'get_session'):
            return error_response("数据库管理器未初始化", 500)

        try:
            from ...models.orm import LearningBatch
        except ImportError:
            from models.orm import LearningBatch

        from sqlalchemy import delete as sql_delete

        async with database_manager.get_session() as session:
            stmt = sql_delete(LearningBatch).where(LearningBatch.id == batch_id)
            result = await session.execute(stmt)
            await session.commit()

            if result.rowcount > 0:
                return jsonify({
                    'success': True,
                    'message': f'批次 {batch_id} 已删除',
                }), 200
            else:
                return error_response(f'批次 {batch_id} 不存在', 404)

    except ValueError as e:
        return error_response("请求处理失败，请稍后重试", 500)
    except Exception as e:
        logger.error(f"删除学习批次失败: {e}", exc_info=True)
        return error_response("请求处理失败，请稍后重试", 500)


@learning_bp.route("/relearn", methods=["POST"])
@require_auth
async def relearn_all():
    """重新学习 - 重新处理所有历史消息"""
    try:
        container = get_container()
        database_manager = container.database_manager
        factory_manager = container.factory_manager

        if not factory_manager:
            return jsonify({"success": False, "error": "工厂管理器未初始化"}), 500

        # Get request data
        data = {}
        try:
            if request.is_json:
                data = await request.get_json()
        except Exception:
            data = {}

        group_id = data.get('group_id')

        # Auto-detect group with most messages if not specified
        if not group_id or group_id == 'default':
            if database_manager:
                try:
                    stats = await database_manager.get_messages_statistics()
                    total_count = stats.get('total_messages', 0)

                    if total_count > 0 and hasattr(database_manager, 'get_session'):
                        from sqlalchemy import select, func, and_
                        from ...models.orm import RawMessage

                        async with database_manager.get_session() as session:
                            stmt = select(
                                RawMessage.group_id,
                                func.count().label('message_count')
                            ).where(
                                and_(
                                    RawMessage.group_id.isnot(None),
                                    RawMessage.group_id != ''
                                )
                            ).group_by(
                                RawMessage.group_id
                            ).order_by(
                                func.count().desc()
                            )
                            result = await session.execute(stmt)
                            all_results = result.all()

                        if all_results:
                            group_id = all_results[0][0]
                except Exception as e:
                    logger.warning(f"自动检测群组失败: {e}")

        if not group_id:
            return jsonify({"success": False, "error": "没有可用的群组数据"}), 400

        # Get message count
        total_messages = 0
        if database_manager:
            try:
                stats = await database_manager.get_messages_statistics()
                total_messages = stats.get('total_messages', 0)
            except Exception:
                pass

        # Trigger relearning via progressive_learning service
        progressive_learning = container.progressive_learning
        if progressive_learning:
            try:
                import asyncio
                asyncio.create_task(progressive_learning.start_learning(group_id))
                return jsonify({
                    "success": True,
                    "message": f"重新学习已启动，群组: {group_id}",
                    "group_id": group_id,
                    "total_messages": total_messages
                }), 200
            except Exception as e:
                logger.error(f"触发重新学习失败: {e}", exc_info=True)
                return jsonify({"success": False, "error": "请求处理失败，请稍后重试"}), 500
        else:
            return jsonify({"success": False, "error": "学习服务未初始化"}), 500
    except Exception as e:
        logger.error(f"重新学习失败: {e}", exc_info=True)
        return error_response("请求处理失败，请稍后重试", 500)
