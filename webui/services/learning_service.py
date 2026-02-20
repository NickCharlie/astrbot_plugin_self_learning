"""
学习功能服务 - 处理风格学习相关业务逻辑
"""
from typing import Dict, Any, List, Tuple
from astrbot.api import logger


class LearningService:
    """学习功能服务"""

    def __init__(self, container):
        """
        初始化学习功能服务

        Args:
            container: ServiceContainer 依赖注入容器
        """
        self.container = container
        self.database_manager = container.database_manager
        self.db_manager = container.database_manager # 兼容别名
        self.persona_updater = getattr(container, 'persona_updater', None)

    async def get_style_learning_results(self) -> Dict[str, Any]:
        """
        获取风格学习结果

        Returns:
            Dict: 风格学习统计和进度数据
        """
        # 初始化空数据结构
        results_data = {
            'statistics': {
                'unique_styles': 0,
                'avg_confidence': 0,
                'total_samples': 0,
                'latest_update': None
            },
            'style_progress': []
        }

        if self.db_manager:
            try:
                # 优先使用ORM Repository获取统计数据
                if hasattr(self.db_manager, 'get_session'):
                    # 使用ORM方式获取统计
                    from ...repositories.learning_repository import StyleLearningReviewRepository

                    async with self.db_manager.get_session() as session:
                        style_repo = StyleLearningReviewRepository(session)
                        real_stats = await style_repo.get_statistics()
                        if real_stats:
                            results_data['statistics'].update(real_stats)

                    logger.debug(f"使用ORM获取风格学习统计: {real_stats}")
                else:
                    # 降级到传统数据库方法
                    real_stats = await self.db_manager.get_style_learning_statistics()
                    if real_stats:
                        results_data['statistics'].update(real_stats)

                # 获取进度数据（保持原有逻辑）
                real_progress = await self.db_manager.get_style_progress_data()
                if real_progress and isinstance(real_progress, list):
                    results_data['style_progress'] = real_progress
            except Exception as e:
                logger.warning(f"无法从数据库获取风格学习数据: {e}", exc_info=True)

        return results_data

    async def get_style_learning_reviews(self, limit: int = 50) -> Dict[str, Any]:
        """
        获取对话风格学习审查列表

        Args:
            limit: 最大返回数量

        Returns:
            Dict: 审查列表和总数
        """
        if not self.database_manager:
            raise ValueError('数据库管理器未初始化')

        pending_reviews = await self.database_manager.get_pending_style_reviews(limit=limit)

        # 格式化审查数据
        formatted_reviews = []
        for review in pending_reviews:
            formatted_review = {
                'id': review['id'],
                'type': '对话风格学习',
                'group_id': review['group_id'],
                'description': review['description'],
                'timestamp': review['timestamp'],
                'created_at': review['created_at'],
                'status': review['status'],
                'learned_patterns': review['learned_patterns'],
                'few_shots_content': review['few_shots_content']
            }
            formatted_reviews.append(formatted_review)

        return {
            'reviews': formatted_reviews,
            'total': len(formatted_reviews)
        }

    async def approve_style_learning_review(self, review_id: int) -> Tuple[bool, str]:
        """
        批准对话风格学习审查

        Args:
            review_id: 审查ID

        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        if not self.database_manager:
            raise ValueError('数据库管理器未初始化')

        # 获取审查详情
        pending_reviews = await self.database_manager.get_pending_style_reviews()
        target_review = None
        for review in pending_reviews:
            if review['id'] == review_id:
                target_review = review
                break

        if not target_review:
            return False, '审查记录不存在'

        # 更新状态为approved
        success = await self.database_manager.update_style_review_status(
            review_id, 'approved', target_review['group_id']
        )

        if not success:
            return False, '批准失败，请检查审查记录状态'

        # 应用到人格（使用与人格学习审查相同的逻辑：备份+应用）
        if target_review['few_shots_content']:
            # 通过persona_updater应用到人格
            persona_update_content = target_review['few_shots_content']

            if self.persona_updater:
                try:
                    logger.info(f"开始应用风格学习审查 {review_id}，群组: {target_review.get('group_id', 'default')}")
                    logger.info(f"待应用内容长度: {len(persona_update_content)} 字符")

                    # 将few_shots_content转换为style_analysis格式
                    style_analysis = {
                        'enhanced_prompt': persona_update_content,
                        'style_features': [],
                        'style_attributes': {},
                        'confidence': 0.8,
                        'source': f'风格学习审查{review_id}'
                    }
                    logger.info(f"构建style_analysis: {style_analysis['source']}")

                    # 使用空的filtered_messages（因为我们直接有学习内容）
                    filtered_messages = []

                    # 调用框架API方式的人格更新方法（包含自动备份）
                    logger.info("调用update_persona_with_style方法...")
                    success_apply = await self.persona_updater.update_persona_with_style(
                        target_review.get('group_id', 'default'),
                        style_analysis,
                        filtered_messages
                    )
                    logger.info(f"update_persona_with_style返回结果: {success_apply}")

                    if success_apply:
                        logger.info(f" 风格学习审查 {review_id} 已成功应用到人格（使用框架API方式，包含备份）")
                        return True, f'风格学习审查 {review_id} 已批准并应用到人格'
                    else:
                        logger.warning(f" 风格学习审查 {review_id} 批准成功但应用失败")
                        return True, f'风格学习审查 {review_id} 已批准，但人格应用失败'

                except Exception as e:
                    logger.error(f"应用风格学习到人格失败: {e}", exc_info=True)
                    return False, f'批准成功，但应用到人格失败: {str(e)}'
            else:
                logger.warning("PersonaUpdater未初始化，无法应用风格学习")
                return True, f'风格学习审查 {review_id} 已批准，但无法应用人格更新'
        else:
            return True, f'风格学习审查 {review_id} 已批准（无内容需要应用）'

    async def reject_style_learning_review(self, review_id: int) -> Tuple[bool, str]:
        """
        拒绝对话风格学习审查

        Args:
            review_id: 审查ID

        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        if not self.database_manager:
            raise ValueError('数据库管理器未初始化')

        # 更新状态为rejected
        success = await self.database_manager.update_style_review_status(review_id, 'rejected')

        if success:
            logger.info(f"风格学习审查 {review_id} 已拒绝")
            return True, f'风格学习审查 {review_id} 已拒绝'
        else:
            return False, '拒绝失败，请检查审查记录状态'

    async def get_style_learning_patterns(self) -> Dict[str, Any]:
        """
        获取风格学习模式

        Returns:
            Dict: 学习模式数据，包含 emotion_patterns, language_patterns, topic_patterns
        """
        patterns_data = {
            'emotion_patterns': [],
            'language_patterns': [],
            'topic_patterns': [],
        }

        if not self.db_manager:
            return patterns_data

        try:
            if hasattr(self.db_manager, 'get_session'):
                import json
                from sqlalchemy import select, desc
                from ...models.orm.learning import StyleLearningPattern, StyleLearningReview

                pattern_type_map = {
                    'emotion': 'emotion_patterns',
                    'sentiment': 'emotion_patterns',
                    'language': 'language_patterns',
                    'expression': 'language_patterns',
                    'vocabulary': 'language_patterns',
                    'habit': 'language_patterns',
                    'topic': 'topic_patterns',
                    'interest': 'topic_patterns',
                    'theme': 'topic_patterns',
                }

                async with self.db_manager.get_session() as session:
                    # 1. 从 style_learning_patterns 表获取已确认的模式
                    try:
                        stmt = select(StyleLearningPattern).order_by(
                            desc(StyleLearningPattern.usage_count)
                        ).limit(100)
                        result = await session.execute(stmt)
                        db_patterns = result.scalars().all()

                        for p in db_patterns:
                            pt = (p.pattern_type or '').lower()
                            target_key = pattern_type_map.get(pt)
                            if target_key:
                                patterns_data[target_key].append({
                                    'name': p.pattern,
                                    'confidence': p.confidence or 0.5,
                                    'count': p.usage_count or 1,
                                })
                    except Exception as e:
                        logger.debug(f"查询 StyleLearningPattern 表失败: {e}")

                    # 2. 从 style_learning_reviews 的 learned_patterns JSON 中提取
                    try:
                        stmt = select(StyleLearningReview.learned_patterns).where(
                            StyleLearningReview.learned_patterns.isnot(None)
                        ).order_by(
                            desc(StyleLearningReview.timestamp)
                        ).limit(20)
                        result = await session.execute(stmt)
                        rows = result.scalars().all()

                        for raw in rows:
                            if not raw:
                                continue
                            try:
                                parsed = json.loads(raw) if isinstance(raw, str) else raw
                            except (json.JSONDecodeError, TypeError):
                                continue

                            if isinstance(parsed, list):
                                for item in parsed:
                                    self._classify_pattern(item, patterns_data, pattern_type_map)
                            elif isinstance(parsed, dict):
                                for key, val in parsed.items():
                                    target = pattern_type_map.get(key.lower())
                                    if target and isinstance(val, list):
                                        for item in val:
                                            entry = self._to_pattern_entry(item)
                                            if entry:
                                                patterns_data[target].append(entry)
                                    elif not target:
                                        self._classify_pattern(parsed, patterns_data, pattern_type_map)
                                        break
                    except Exception as e:
                        logger.debug(f"查询 StyleLearningReview.learned_patterns 失败: {e}")

                # 3. 去重并限制数量
                for key in ['emotion_patterns', 'language_patterns', 'topic_patterns']:
                    seen = set()
                    unique = []
                    for item in patterns_data[key]:
                        name = item.get('name', '')
                        if name and name not in seen:
                            seen.add(name)
                            unique.append(item)
                    patterns_data[key] = unique[:20]

        except Exception as e:
            logger.warning(f"获取学习模式数据失败: {e}", exc_info=True)

        return patterns_data

    @staticmethod
    def _to_pattern_entry(item):
        """将各种格式的模式数据转为标准格式"""
        if isinstance(item, str):
            return {'name': item, 'confidence': 0.5, 'count': 1}
        elif isinstance(item, dict):
            name = item.get('name') or item.get('pattern') or item.get('text') or item.get('label', '')
            if not name:
                return None
            return {
                'name': name,
                'confidence': item.get('confidence') or item.get('score') or item.get('weight', 0.5),
                'count': item.get('count') or item.get('usage_count', 1),
            }
        return None

    @staticmethod
    def _classify_pattern(item, patterns_data, type_map):
        """根据模式的 type 字段分类到对应的列表"""
        entry = LearningService._to_pattern_entry(item)
        if not entry:
            return
        if isinstance(item, dict):
            pt = (item.get('type') or item.get('category') or item.get('pattern_type') or '').lower()
            target = type_map.get(pt)
            if target:
                patterns_data[target].append(entry)
                return
        # 默认放到 language_patterns
        patterns_data['language_patterns'].append(entry)
