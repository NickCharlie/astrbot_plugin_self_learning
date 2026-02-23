"""
表达风格 Facade — 表达模式、风格画像、语言模式的业务入口
"""
import time
import json
from typing import Dict, List, Optional, Any

from astrbot.api import logger

from ._base import BaseFacade
from ....repositories.style_profile_repository import StyleProfileRepository


class ExpressionFacade(BaseFacade):
    """表达风格管理 Facade"""

    async def get_all_expression_patterns(self) -> Dict[str, List[Dict[str, Any]]]:
        """获取所有群组的表达模式"""
        try:
            async with self.get_session() as session:
                from ....repositories.expression_repository import ExpressionPatternRepository

                repo = ExpressionPatternRepository(session)
                all_patterns = await repo.get_all(limit=1000)

                grouped: Dict[str, List[Dict[str, Any]]] = {}
                for p in all_patterns:
                    gid = p.group_id or 'global'
                    if gid not in grouped:
                        grouped[gid] = []
                    grouped[gid].append(self._row_to_dict(p))
                return grouped
        except Exception as e:
            self._logger.error(f"[ExpressionFacade] 获取所有表达模式失败: {e}")
            return {}

    async def get_expression_patterns_statistics(self) -> Dict[str, Any]:
        """获取表达模式统计"""
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, func
                from ....models.orm.expression import ExpressionPattern

                total_stmt = select(func.count()).select_from(ExpressionPattern)
                total_result = await session.execute(total_stmt)
                total = total_result.scalar() or 0

                groups_stmt = select(func.count(func.distinct(ExpressionPattern.group_id)))
                groups_result = await session.execute(groups_stmt)
                groups = groups_result.scalar() or 0

                return {'total_patterns': total, 'groups_with_patterns': groups}
        except Exception as e:
            self._logger.error(f"[ExpressionFacade] 获取统计失败: {e}")
            return {'total_patterns': 0, 'groups_with_patterns': 0}

    async def get_group_expression_patterns(
        self, group_id: str, limit: int = None
    ) -> List[Dict[str, Any]]:
        """获取指定群组的表达模式"""
        try:
            async with self.get_session() as session:
                from ....repositories.expression_repository import ExpressionPatternRepository

                repo = ExpressionPatternRepository(session)
                patterns = await repo.find_many(
                    group_id=group_id, limit=limit or 100
                )
                return [self._row_to_dict(p) for p in patterns]
        except Exception as e:
            self._logger.error(f"[ExpressionFacade] 获取群组表达模式失败: {e}")
            return []

    async def get_recent_week_expression_patterns(
        self, group_id: str = None, limit: int = 50, hours: int = 168
    ) -> List[Dict[str, Any]]:
        """获取最近指定时间范围的表达模式"""
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, desc
                from ....models.orm.expression import ExpressionPattern

                cutoff = time.time() - (hours * 3600)
                stmt = select(ExpressionPattern).where(
                    ExpressionPattern.last_active_time >= cutoff
                )
                if group_id:
                    stmt = stmt.where(ExpressionPattern.group_id == group_id)
                stmt = stmt.order_by(desc(ExpressionPattern.weight)).limit(limit)

                result = await session.execute(stmt)
                return [self._row_to_dict(p) for p in result.scalars().all()]
        except Exception as e:
            self._logger.error(f"[ExpressionFacade] 获取近期表达模式失败: {e}")
            return []

    # ---- 风格画像 ----

    async def load_style_profile(self, profile_name: str) -> Optional[Dict[str, Any]]:
        """加载风格画像"""
        try:
            async with self.get_session() as session:
                repo = StyleProfileRepository(session)
                sp = await repo.load(profile_name)
                if not sp:
                    return None
                return {
                    'profile_name': sp.profile_name,
                    'vocabulary_richness': sp.vocabulary_richness,
                    'sentence_complexity': sp.sentence_complexity,
                    'emotional_expression': sp.emotional_expression,
                    'interaction_tendency': sp.interaction_tendency,
                    'topic_diversity': sp.topic_diversity,
                    'formality_level': sp.formality_level,
                    'creativity_score': sp.creativity_score,
                }
        except Exception as e:
            self._logger.error(f"[ExpressionFacade] 加载风格画像失败: {e}")
            return None

    async def save_style_profile(
        self, profile_name: str, profile_data: Dict[str, Any]
    ) -> bool:
        """保存风格画像（upsert）"""
        try:
            async with self.get_session() as session:
                from sqlalchemy import select
                from ....models.orm.expression import StyleProfile

                stmt = select(StyleProfile).where(StyleProfile.profile_name == profile_name)
                result = await session.execute(stmt)
                sp = result.scalar_one_or_none()
                if sp:
                    for key in ('vocabulary_richness', 'sentence_complexity', 'emotional_expression',
                                'interaction_tendency', 'topic_diversity', 'formality_level', 'creativity_score'):
                        if key in profile_data:
                            setattr(sp, key, profile_data[key])
                else:
                    sp = StyleProfile(profile_name=profile_name, **{
                        k: profile_data.get(k)
                        for k in ('vocabulary_richness', 'sentence_complexity', 'emotional_expression',
                                  'interaction_tendency', 'topic_diversity', 'formality_level', 'creativity_score')
                    })
                    session.add(sp)
                await session.commit()
                return True
        except Exception as e:
            self._logger.error(f"[ExpressionFacade] 保存风格画像失败: {e}")
            return False

    # ---- 风格学习记录 ----

    async def save_style_learning_record(self, record_data: Dict[str, Any]) -> bool:
        """保存风格学习记录"""
        try:
            async with self.get_session() as session:
                from ....models.orm.expression import StyleLearningRecord

                rec = StyleLearningRecord(
                    style_type=record_data.get('style_type', 'unknown'),
                    learned_patterns=json.dumps(record_data.get('learned_patterns', []), ensure_ascii=False),
                    confidence_score=record_data.get('confidence_score', 0.0),
                    sample_count=record_data.get('sample_count', 0),
                    last_updated=time.time(),
                )
                session.add(rec)
                await session.commit()
                return True
        except Exception as e:
            self._logger.error(f"[ExpressionFacade] 保存风格学习记录失败: {e}")
            return False

    async def save_language_style_pattern(
        self, language_style: str, pattern_data: Dict[str, Any]
    ) -> bool:
        """保存语言风格模式（upsert）"""
        try:
            async with self.get_session() as session:
                from sqlalchemy import select
                from ....models.orm.expression import LanguageStylePattern

                stmt = select(LanguageStylePattern).where(
                    LanguageStylePattern.language_style == language_style
                )
                result = await session.execute(stmt)
                pat = result.scalar_one_or_none()
                now = time.time()
                if pat:
                    pat.example_phrases = json.dumps(pattern_data.get('example_phrases', []), ensure_ascii=False)
                    pat.usage_frequency = (pat.usage_frequency or 0) + 1
                    pat.context_type = pattern_data.get('context_type', 'general')
                    pat.confidence_score = pattern_data.get('confidence_score')
                    pat.last_updated = now
                else:
                    pat = LanguageStylePattern(
                        language_style=language_style,
                        example_phrases=json.dumps(pattern_data.get('example_phrases', []), ensure_ascii=False),
                        usage_frequency=1,
                        context_type=pattern_data.get('context_type', 'general'),
                        confidence_score=pattern_data.get('confidence_score'),
                        last_updated=now,
                    )
                    session.add(pat)
                await session.commit()
                return True
        except Exception as e:
            self._logger.error(f"[ExpressionFacade] 保存语言风格模式失败: {e}")
            return False
