"""
学习功能蓝图 - 处理风格学习相关路由
"""
from quart import Blueprint, request, jsonify
from astrbot.api import logger

from ..dependencies import get_container
from ..services.learning_service import LearningService
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
        return error_response(str(e), 500)


@learning_bp.route("/style_learning/reviews", methods=["GET"])
@require_auth
async def get_style_learning_reviews():
    """获取对话风格学习审查列表"""
    try:
        container = get_container()
        learning_service = LearningService(container)
        reviews_data = await learning_service.get_style_learning_reviews(limit=50)

        return jsonify(reviews_data), 200

    except ValueError as e:
        return error_response(str(e), 500)
    except Exception as e:
        logger.error(f"获取风格学习审查列表失败: {e}", exc_info=True)
        return error_response(str(e), 500)


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
        return error_response(str(e), 500)
    except Exception as e:
        logger.error(f"批准风格学习审查失败: {e}", exc_info=True)
        return error_response(str(e), 500)


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
        return error_response(str(e), 500)
    except Exception as e:
        logger.error(f"拒绝风格学习审查失败: {e}", exc_info=True)
        return error_response(str(e), 500)


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
        return error_response(str(e), 500)


@learning_bp.route("/style_learning/content_text", methods=["GET"])
@require_auth
async def get_style_learning_content_text():
    """获取对话风格学习的内容文本"""
    try:
        container = get_container()
        database_manager = container.database_manager

        content_data = {
            'dialogues': [],
            'analysis': [],
            'features': [],
            'history': []
        }

        if database_manager and hasattr(database_manager, 'get_session'):
            from sqlalchemy import select, desc, func
            from ...models.orm import (
                RawMessage, StyleLearningReview,
                ExpressionPattern, LearningBatch,
            )
            from datetime import datetime
            import time as time_module
            import json as json_module

            try:
                async with database_manager.get_session() as session:
                    # 1. dialogues — 最近的原始消息
                    stmt = select(RawMessage).order_by(desc(RawMessage.timestamp)).limit(20)
                    result = await session.execute(stmt)
                    for msg in result.scalars().all():
                        message_text = msg.message if msg.message else ''
                        if len(message_text.strip()) < 5:
                            continue
                        content_data['dialogues'].append({
                            'timestamp': datetime.fromtimestamp(msg.timestamp if msg.timestamp else time_module.time()).strftime('%Y-%m-%d %H:%M:%S'),
                            'text': f"{msg.sender_name or msg.sender_id}: {message_text}",
                            'metadata': f"群组: {msg.group_id}, 平台: {msg.platform or '未知'}"
                        })

                    # 2. analysis — 已审批的风格学习分析结果
                    analysis_stmt = (
                        select(StyleLearningReview)
                        .where(StyleLearningReview.status.in_(['approved', 'pending']))
                        .order_by(desc(StyleLearningReview.timestamp))
                        .limit(20)
                    )
                    analysis_result = await session.execute(analysis_stmt)
                    for review in analysis_result.scalars().all():
                        patterns = []
                        if review.learned_patterns:
                            try:
                                patterns = json_module.loads(review.learned_patterns)
                            except (json_module.JSONDecodeError, TypeError):
                                pass
                        content_data['analysis'].append({
                            'timestamp': datetime.fromtimestamp(review.timestamp).strftime('%Y-%m-%d %H:%M:%S') if review.timestamp else '',
                            'text': review.description or review.few_shots_content or f"风格学习 ({review.type})",
                            'metadata': f"群组: {review.group_id}, 状态: {review.status}, 模式数: {len(patterns) if isinstance(patterns, list) else 0}"
                        })

                    # 3. features — 已学习的表达模式
                    features_stmt = (
                        select(ExpressionPattern)
                        .order_by(desc(ExpressionPattern.last_active_time))
                        .limit(20)
                    )
                    features_result = await session.execute(features_stmt)
                    for pattern in features_result.scalars().all():
                        content_data['features'].append({
                            'timestamp': datetime.fromtimestamp(pattern.last_active_time).strftime('%Y-%m-%d %H:%M:%S') if pattern.last_active_time else '',
                            'text': f"场景: {pattern.situation}\n表达: {pattern.expression}",
                            'metadata': f"群组: {pattern.group_id}, 权重: {pattern.weight:.2f}"
                        })

                    # 4. history — 学习批次历史
                    history_stmt = (
                        select(LearningBatch)
                        .order_by(desc(LearningBatch.start_time))
                        .limit(20)
                    )
                    history_result = await session.execute(history_stmt)
                    for batch in history_result.scalars().all():
                        duration = ''
                        if batch.start_time and batch.end_time:
                            duration = f", 耗时: {batch.end_time - batch.start_time:.1f}s"
                        content_data['history'].append({
                            'timestamp': datetime.fromtimestamp(batch.start_time).strftime('%Y-%m-%d %H:%M:%S') if batch.start_time else '',
                            'text': f"批次: {batch.batch_name or batch.batch_id}, 质量: {batch.quality_score or 0:.3f}",
                            'metadata': f"群组: {batch.group_id}, 消息: {batch.processed_messages or 0}, 成功: {'是' if batch.success else '否'}{duration}"
                        })
            except Exception as e:
                logger.warning(f"获取学习内容文本失败: {e}")

        return jsonify(content_data), 200
    except Exception as e:
        logger.error(f"获取学习内容文本失败: {e}", exc_info=True)
        return error_response(str(e), 500)


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
                return jsonify({"success": False, "error": f"启动失败: {str(e)}"}), 500
        else:
            return jsonify({"success": False, "error": "学习服务未初始化"}), 500
    except Exception as e:
        logger.error(f"重新学习失败: {e}", exc_info=True)
        return error_response(str(e), 500)
