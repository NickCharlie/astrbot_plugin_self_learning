"""
学习功能蓝图 - 处理风格学习相关路由
"""
from quart import Blueprint, request, jsonify

try:
    from ...utils.logging_utils import get_astrbot_logger
except ImportError:
    from utils.logging_utils import get_astrbot_logger

from ..dependencies import get_container
from ..services.learning_service import LearningService
from ..middleware.auth import require_auth
from ..utils.response import success_response, error_response

learning_bp = Blueprint('learning', __name__, url_prefix='/api')
logger = get_astrbot_logger("self_learning.webui.learning")


def _clamp_quality_score(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _optional_float(value):
    if value is None:
        return None
    try:
        return _clamp_quality_score(value)
    except (TypeError, ValueError):
        return None


def _non_negative_int(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _effective_batch_quality(batch, max_batch_size=200) -> float:
    """Return stored quality, or a conservative display fallback for legacy zero rows."""
    stored_quality = _optional_float(getattr(batch, 'quality_score', None))
    if stored_quality is not None and stored_quality > 0:
        return stored_quality

    if getattr(batch, 'success', None) is False:
        return stored_quality if stored_quality is not None else 0.0

    processed = max(
        _non_negative_int(getattr(batch, 'processed_messages', 0)),
        _non_negative_int(getattr(batch, 'message_count', 0)),
    )
    filtered = _non_negative_int(getattr(batch, 'filtered_count', 0))
    if processed <= 0 and filtered <= 0:
        return stored_quality if stored_quality is not None else 0.0

    try:
        batch_size = max(1, int(max_batch_size or 200))
    except (TypeError, ValueError):
        batch_size = 200

    volume_score = min(processed / batch_size, 1.0)
    filtered_score = min(filtered / max(processed, filtered, 1), 1.0) if filtered else 0.0
    success_score = 0.10 if getattr(batch, 'success', True) else 0.0
    return _clamp_quality_score(0.25 + (volume_score * 0.45) + (filtered_score * 0.20) + success_score)


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
        return error_response(str(e), 500)
    except Exception as e:
        logger.error(f"删除风格学习审查失败: {e}", exc_info=True)
        return error_response(str(e), 500)


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
        return error_response(str(e), 500)
    except Exception as e:
        logger.error(f"批量审查风格学习失败: {e}", exc_info=True)
        return error_response(str(e), 500)


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
        return error_response(str(e), 500)
    except Exception as e:
        logger.error(f"批量删除风格学习失败: {e}", exc_info=True)
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
        max_batch_size = getattr(getattr(container, 'config', None), 'max_messages_per_batch', 200)

        content_data = {
            'dialogues': [],
            'analysis': [],
            'features': [],
            'history': []
        }

        if database_manager and hasattr(database_manager, 'get_session'):
            from sqlalchemy import select, desc, func
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
            from datetime import datetime
            import time as time_module
            import json as json_module

            def format_ts(value):
                if not value:
                    return ''
                return datetime.fromtimestamp(value).strftime('%Y-%m-%d %H:%M:%S')

            def parse_json(value, fallback):
                if not value:
                    return fallback
                if isinstance(value, (list, dict)):
                    return value
                try:
                    return json_module.loads(value)
                except (json_module.JSONDecodeError, TypeError):
                    return fallback

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
                            'id': msg.id,
                            'type': 'dialogue',
                            'title': msg.sender_name or msg.sender_id or '未知发送者',
                            'timestamp': format_ts(msg.timestamp if msg.timestamp else time_module.time()),
                            'text': f"{msg.sender_name or msg.sender_id}: {message_text}",
                            'detail': message_text,
                            'metadata': f"群组: {msg.group_id}, 平台: {msg.platform or '未知'}",
                            'raw': {
                                'sender_id': msg.sender_id,
                                'sender_name': msg.sender_name,
                                'group_id': msg.group_id,
                                'platform': msg.platform,
                                'message_id': getattr(msg, 'message_id', None),
                                'reply_to': getattr(msg, 'reply_to', None),
                                'processed': bool(getattr(msg, 'processed', False)),
                            },
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
                        patterns = parse_json(review.learned_patterns, [])
                        few_shots_content = review.few_shots_content or ''
                        description = review.description or ''
                        content_data['analysis'].append({
                            'id': review.id,
                            'type': review.type or 'style_learning',
                            'title': description or f"风格学习 ({review.type})",
                            'timestamp': format_ts(review.timestamp),
                            'text': description or few_shots_content or f"风格学习 ({review.type})",
                            'detail': few_shots_content or description,
                            'status': review.status,
                            'patterns': patterns,
                            'metadata': f"群组: {review.group_id}, 状态: {review.status}, 模式数: {len(patterns) if isinstance(patterns, list) else 0}",
                            'raw': {
                                'group_id': review.group_id,
                                'reviewer_comment': review.reviewer_comment,
                                'review_time': review.review_time,
                                'created_at': review.created_at.isoformat() if review.created_at else None,
                                'updated_at': review.updated_at.isoformat() if review.updated_at else None,
                            },
                        })

                    # 3. features — 已学习的表达模式
                    features_stmt = (
                        select(ExpressionPattern)
                        .order_by(desc(ExpressionPattern.last_active_time))
                        .limit(20)
                    )
                    features_result = await session.execute(features_stmt)
                    for pattern in features_result.scalars().all():
                        weight = pattern.weight if pattern.weight is not None else 0
                        content_data['features'].append({
                            'id': pattern.id,
                            'type': 'expression_pattern',
                            'title': pattern.situation,
                            'timestamp': format_ts(pattern.last_active_time),
                            'text': f"场景: {pattern.situation}\n表达: {pattern.expression}",
                            'detail': pattern.expression,
                            'metadata': f"群组: {pattern.group_id}, 权重: {weight:.2f}",
                            'raw': {
                                'group_id': pattern.group_id,
                                'situation': pattern.situation,
                                'expression': pattern.expression,
                                'weight': weight,
                                'create_time': pattern.create_time,
                                'last_active_time': pattern.last_active_time,
                            },
                        })

                    # 4. history — 学习批次历史
                    history_stmt = (
                        select(LearningBatch)
                        .order_by(desc(LearningBatch.start_time))
                        .limit(20)
                    )
                    history_result = await session.execute(history_stmt)
                    for batch in history_result.scalars().all():
                        quality_score = _effective_batch_quality(batch, max_batch_size)
                        duration = ''
                        if batch.start_time and batch.end_time:
                            duration = f", 耗时: {batch.end_time - batch.start_time:.1f}s"
                        content_data['history'].append({
                            'id': batch.id,
                            'type': 'learning_batch',
                            'title': batch.batch_name or batch.batch_id or '学习批次',
                            'timestamp': format_ts(batch.start_time),
                            'text': f"批次: {batch.batch_name or batch.batch_id}, 质量: {quality_score:.3f}",
                            'detail': batch.error_message or f"状态: {batch.status or 'unknown'}",
                            'status': batch.status,
                            'metadata': f"群组: {batch.group_id}, 消息: {batch.processed_messages or 0}, 成功: {'是' if batch.success else '否'}{duration}",
                            'raw': {
                                'batch_id': batch.batch_id,
                                'batch_name': batch.batch_name,
                                'group_id': batch.group_id,
                                'start_time': batch.start_time,
                                'end_time': batch.end_time,
                                'quality_score': quality_score,
                                'raw_quality_score': batch.quality_score,
                                'processed_messages': batch.processed_messages,
                                'message_count': batch.message_count,
                                'filtered_count': batch.filtered_count,
                                'success': batch.success,
                                'error_message': batch.error_message,
                                'status': batch.status,
                            },
                        })
            except Exception as e:
                logger.warning(f"获取学习内容文本失败: {e}")

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
        return error_response(str(e), 500)


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
        return error_response(str(e), 500)
    except Exception as e:
        logger.error(f"删除学习内容失败: {e}", exc_info=True)
        return error_response(str(e), 500)


@learning_bp.route("/batches", methods=["GET"])
@require_auth
async def get_learning_batches():
    """获取学习批次列表（分页）"""
    try:
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('page_size', 10, type=int)
        page = max(1, page)
        page_size = max(1, min(100, page_size))

        container = get_container()
        database_manager = container.database_manager
        max_batch_size = getattr(getattr(container, 'config', None), 'max_messages_per_batch', 200)

        if not database_manager or not hasattr(database_manager, 'get_session'):
            return error_response("数据库管理器未初始化", 500)

        try:
            from ...models.orm import LearningBatch
        except ImportError:
            from models.orm import LearningBatch

        from sqlalchemy import select, func, desc

        async with database_manager.get_session() as session:
            # 总数
            count_stmt = select(func.count()).select_from(LearningBatch)
            total = (await session.execute(count_stmt)).scalar() or 0

            # 分页查询
            offset = (page - 1) * page_size
            stmt = (
                select(LearningBatch)
                .order_by(desc(LearningBatch.start_time))
                .offset(offset)
                .limit(page_size)
            )
            result = await session.execute(stmt)
            batches = []
            for batch in result.scalars().all():
                quality_score = _effective_batch_quality(batch, max_batch_size)
                batches.append({
                    'id': batch.id,
                    'batch_id': batch.batch_id,
                    'batch_name': batch.batch_name,
                    'group_id': batch.group_id,
                    'start_time': batch.start_time,
                    'end_time': batch.end_time,
                    'quality_score': quality_score,
                    'raw_quality_score': batch.quality_score,
                    'processed_messages': batch.processed_messages,
                    'message_count': batch.message_count,
                    'filtered_count': batch.filtered_count,
                    'success': batch.success,
                    'status': batch.status,
                    'error_message': batch.error_message,
                })

        return jsonify({
            'success': True,
            'data': {
                'batches': batches,
                'total': total,
                'page': page,
                'page_size': page_size,
                'total_pages': max(1, (total + page_size - 1) // page_size),
            },
        }), 200

    except ValueError as e:
        return error_response(str(e), 500)
    except Exception as e:
        logger.error(f"获取学习批次列表失败: {e}", exc_info=True)
        return error_response(str(e), 500)


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
        return error_response(str(e), 500)
    except Exception as e:
        logger.error(f"删除学习批次失败: {e}", exc_info=True)
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
