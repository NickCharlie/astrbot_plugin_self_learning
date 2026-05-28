"""
学习功能服务 - 处理风格学习相关业务逻辑
"""
import json
import re
from typing import Dict, Any, List, Tuple
from astrbot.api import logger

from .persona_review_service import PersonaReviewService


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
                # 优先使用 Facade 方法获取统计数据
                if hasattr(self.db_manager, 'get_style_learning_statistics'):
                    real_stats = await self.db_manager.get_style_learning_statistics()
                    if real_stats:
                        results_data['statistics'].update(real_stats)
                elif hasattr(self.db_manager, 'get_session'):
                    # 降级到 Repository 方式
                    from ...repositories.learning_repository import StyleLearningReviewRepository

                    async with self.db_manager.get_session() as session:
                        style_repo = StyleLearningReviewRepository(session)
                        real_stats = await style_repo.get_statistics()
                        if real_stats:
                            results_data['statistics'].update(real_stats)

                    logger.debug(f"使用ORM获取风格学习统计: {real_stats}")

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
        persona_review_service = PersonaReviewService(self.container)

        # 格式化审查数据
        formatted_reviews = []
        for review in pending_reviews:
            pattern_details = self._normalize_pattern_details(
                review.get('learned_patterns')
            )
            few_shot_pairs = self._parse_few_shot_pairs(
                review.get('few_shots_content')
            )
            formatted_review = {
                'id': review['id'],
                'review_source': 'style_learning',
                'type': '对话风格学习',
                'group_id': review['group_id'],
                'description': review['description'],
                'timestamp': review['timestamp'],
                'created_at': review['created_at'],
                'status': review['status'],
                'learned_patterns': review['learned_patterns'],
                'few_shots_content': review['few_shots_content'],
                'pattern_details': pattern_details,
                'few_shot_pairs': few_shot_pairs,
                'persona_change_preview': await persona_review_service._style_preview(
                    review.get('group_id', 'default'),
                    review,
                ),
                'persona_change_snapshot': await persona_review_service._load_change_snapshot(
                    'style_learning',
                    str(review['id']),
                ),
            }
            formatted_reviews.append(formatted_review)

        return {
            'reviews': formatted_reviews,
            'total': len(formatted_reviews)
        }

    @staticmethod
    def _parse_jsonish(value: Any) -> Any:
        if value is None or value == "":
            return None
        if isinstance(value, (list, dict)):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
        return value

    @classmethod
    def _normalize_pattern_details(cls, value: Any) -> List[Dict[str, Any]]:
        parsed = cls._parse_jsonish(value)
        if isinstance(parsed, dict):
            parsed = parsed.get("patterns") or parsed.get("items") or [
                {"situation": key, "expression": val}
                for key, val in parsed.items()
            ]
        if not isinstance(parsed, list):
            parsed = [parsed] if parsed else []

        details = []
        for item in parsed:
            if isinstance(item, str):
                situation = ""
                expression = item
                weight = None
                confidence = None
            elif isinstance(item, dict):
                situation = (
                    item.get("situation")
                    or item.get("context")
                    or item.get("scene")
                    or item.get("trigger")
                    or ""
                )
                expression = (
                    item.get("expression")
                    or item.get("pattern")
                    or item.get("text")
                    or item.get("example")
                    or item.get("name")
                    or ""
                )
                weight = item.get("weight")
                confidence = item.get("confidence") or item.get("score")
            else:
                continue

            if not situation and not expression:
                continue
            details.append(
                {
                    "situation": str(situation),
                    "expression": str(expression),
                    "weight": weight,
                    "confidence": confidence,
                }
            )
        return details

    @staticmethod
    def _parse_few_shot_pairs(content: Any) -> List[Dict[str, str]]:
        if not content:
            return []
        text = str(content)
        pairs = []
        for match in re.finditer(
            r"(?:^|\n)A:\s*(?P<user>.*?)(?:\n+)B:\s*(?P<bot>.*?)(?=\n+A:|\Z)",
            text,
            flags=re.DOTALL,
        ):
            user = match.group("user").strip()
            bot = match.group("bot").strip()
            if user and bot:
                pairs.append({"user": user, "bot": bot})
        return pairs

    async def approve_style_learning_review(self, review_id: int) -> Tuple[bool, str]:
        """
        批准对话风格学习审查

        Args:
            review_id: 审查ID

        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        review_service = PersonaReviewService(self.container)
        return await review_service.review_persona_update(
            f"style_{review_id}",
            "approve",
        )

    async def reject_style_learning_review(self, review_id: int) -> Tuple[bool, str]:
        """
        拒绝对话风格学习审查

        Args:
            review_id: 审查ID

        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        review_service = PersonaReviewService(self.container)
        return await review_service.review_persona_update(
            f"style_{review_id}",
            "reject",
        )

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
