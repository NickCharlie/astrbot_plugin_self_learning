"""
社交上下文注入器 - 将用户社交关系、好感度、Bot情绪信息注入到LLM prompt中
"""
from typing import Dict, Any, List, Optional

from astrbot.api import logger


class SocialContextInjector:
    """社交上下文注入器 - 格式化并注入用户社交关系、好感度、Bot情绪到prompt"""

    def __init__(self, database_manager, affection_manager=None, mood_manager=None, config=None):
        self.database_manager = database_manager
        self.affection_manager = affection_manager
        self.mood_manager = mood_manager
        self.config = config  # 添加config参数以读取配置

    async def format_complete_context(
        self,
        group_id: str,
        user_id: str,
        include_social_relations: bool = True,
        include_affection: bool = True,
        include_mood: bool = True,
        include_expression_patterns: bool = True
    ) -> Optional[str]:
        """
        格式化完整的上下文信息（社交关系、好感度、情绪、风格特征）

        Args:
            group_id: 群组ID
            user_id: 用户ID
            include_social_relations: 是否包含社交关系
            include_affection: 是否包含好感度信息
            include_mood: 是否包含情绪信息
            include_expression_patterns: 是否包含最近学到的表达模式

        Returns:
            格式化的完整上下文文本，如果没有任何信息则返回None
        """
        try:
            context_parts = []

            # 1. Bot当前情绪信息
            if include_mood and self.mood_manager:
                mood_text = await self._format_mood_context(group_id)
                if mood_text:
                    context_parts.append(mood_text)

            # 2. 对该用户的好感度信息
            if include_affection and self.affection_manager:
                affection_text = await self._format_affection_context(group_id, user_id)
                if affection_text:
                    context_parts.append(affection_text)

            # 3. 用户社交关系信息
            if include_social_relations:
                social_text = await self.format_social_context(group_id, user_id)
                if social_text:
                    context_parts.append(social_text)

            # 4. 最近学到的表达模式（风格特征）
            if include_expression_patterns:
                expression_text = await self._format_expression_patterns_context(group_id)
                if expression_text:
                    context_parts.append(expression_text)

            if not context_parts:
                return None

            # 组合所有上下文信息
            context_header = "=" * 50
            full_context = f"{context_header}\n"
            full_context += "【上下文参考信息】\n"
            full_context += "\n".join(context_parts)
            full_context += f"\n{context_header}"

            return full_context

        except Exception as e:
            logger.error(f"格式化完整上下文失败: {e}", exc_info=True)
            return None

    async def _format_mood_context(self, group_id: str) -> Optional[str]:
        """格式化Bot当前情绪信息"""
        try:
            if not self.mood_manager:
                return None

            mood_data = await self.mood_manager.get_current_mood(group_id)
            if not mood_data or 'current_mood' not in mood_data:
                return None

            current_mood = mood_data['current_mood']
            mood_description = mood_data.get('description', '')

            mood_text = f"【Bot当前情绪状态】\n"
            mood_text += f"情绪: {current_mood}"
            if mood_description:
                mood_text += f" - {mood_description}"

            return mood_text

        except Exception as e:
            logger.error(f"格式化情绪上下文失败: {e}", exc_info=True)
            return None

    async def _format_affection_context(self, group_id: str, user_id: str) -> Optional[str]:
        """格式化对该用户的好感度信息"""
        try:
            if not self.affection_manager:
                return None

            affection_data = await self.affection_manager.get_user_affection(group_id, user_id)
            if not affection_data:
                return None

            affection_level = affection_data.get('affection_level', 0)
            max_affection = affection_data.get('max_affection', 100)
            affection_rank = affection_data.get('rank', '未知')

            affection_text = f"【对该用户的好感度】\n"
            affection_text += f"好感度: {affection_level}/{max_affection}"

            # 添加好感度等级描述（范围: -100 到 100）
            if affection_level >= 80:
                level_desc = "非常喜欢"
            elif affection_level >= 60:
                level_desc = "比较喜欢"
            elif affection_level >= 40:
                level_desc = "一般好感"
            elif affection_level >= 20:
                level_desc = "略有好感"
            elif affection_level >= 0:
                level_desc = "初次见面"
            elif affection_level >= -20:
                level_desc = "略有反感"
            elif affection_level >= -40:
                level_desc = "比较反感"
            elif affection_level >= -60:
                level_desc = "相当讨厌"
            elif affection_level >= -80:
                level_desc = "非常讨厌"
            else:
                level_desc = "极度厌恶"

            affection_text += f" ({level_desc})"

            if affection_rank and affection_rank != '未知':
                affection_text += f"\n好感度排名: {affection_rank}"

            return affection_text

        except Exception as e:
            logger.error(f"格式化好感度上下文失败: {e}", exc_info=True)
            return None

    async def _format_expression_patterns_context(self, group_id: str) -> Optional[str]:
        """
        格式化最近学到的表达模式（风格特征）

        Args:
            group_id: 群组ID

        Returns:
            格式化的表达模式文本
        """
        try:
            # 从配置中读取时间范围，默认24小时
            hours = 24
            if self.config and hasattr(self.config, 'expression_patterns_hours'):
                hours = getattr(self.config, 'expression_patterns_hours', 24)

            # 获取指定时间范围内的表达模式
            patterns = await self.database_manager.get_recent_week_expression_patterns(
                group_id,
                limit=10,
                hours=hours
            )

            if not patterns:
                return None

            # 格式化表达模式文本
            time_desc = f"{hours}小时" if hours < 24 else f"{hours//24}天"
            pattern_text = f"【最近{time_desc}学到的表达风格特征】\n"
            pattern_text += f"以下是最近{time_desc}学习到的表达模式，参考这些风格进行回复：\n"

            for i, pattern in enumerate(patterns[:10], 1):  # 最多显示10个
                situation = pattern.get('situation', '未知场景')
                expression = pattern.get('expression', '未知表达')
                weight = pattern.get('weight', 1.0)

                # 简化显示
                pattern_text += f"{i}. 当{situation}时，使用类似「{expression}」的表达方式\n"

            pattern_text += "\n💡 提示：这些是从真实对话中学习到的表达模式，请在适当的场景下灵活运用，保持自然流畅。"

            return pattern_text

        except Exception as e:
            logger.error(f"格式化表达模式上下文失败: {e}", exc_info=True)
            return None

    async def format_social_context(self, group_id: str, user_id: str) -> Optional[str]:
        """
        格式化用户的社交关系上下文

        Args:
            group_id: 群组ID
            user_id: 用户ID

        Returns:
            格式化的社交关系文本，如果没有关系则返回None
        """
        try:
            # 获取用户社交关系
            relations_data = await self.database_manager.get_user_social_relations(group_id, user_id)

            if relations_data['total_relations'] == 0:
                return None

            # 格式化社交关系文本
            context_lines = []
            context_lines.append(f"【该用户的社交关系网络】")

            # 格式化发出的关系
            if relations_data['outgoing']:
                context_lines.append(f"该用户的互动对象（按频率排序）：")
                for i, relation in enumerate(relations_data['outgoing'][:5], 1):  # 只显示前5个
                    target = self._extract_user_id(relation['to_user'])
                    relation_type = self._format_relation_type(relation['relation_type'])
                    strength = relation['strength']
                    frequency = relation['frequency']

                    context_lines.append(
                        f"  {i}. 与 {target} - {relation_type}，强度: {strength:.1f}，互动{frequency}次"
                    )

            # 格式化接收的关系
            if relations_data['incoming']:
                context_lines.append(f"与该用户互动的成员（按频率排序）：")
                for i, relation in enumerate(relations_data['incoming'][:5], 1):  # 只显示前5个
                    source = self._extract_user_id(relation['from_user'])
                    relation_type = self._format_relation_type(relation['relation_type'])
                    strength = relation['strength']
                    frequency = relation['frequency']

                    context_lines.append(
                        f"  {i}. {source} - {relation_type}，强度: {strength:.1f}，互动{frequency}次"
                    )

            context_text = "\n".join(context_lines)
            return context_text

        except Exception as e:
            logger.error(f"格式化社交关系上下文失败: {e}", exc_info=True)
            return None

    def _extract_user_id(self, user_key: str) -> str:
        """从 user_key 中提取用户ID"""
        if ':' in user_key:
            return user_key.split(':')[-1]
        return user_key

    def _format_relation_type(self, relation_type: str) -> str:
        """格式化关系类型为中文"""
        type_map = {
            'mention': '@提及',
            'reply': '回复',
            'conversation': '对话',
            'frequent_interaction': '频繁互动',
            'topic_discussion': '话题讨论',
            'interaction': '互动'
        }
        return type_map.get(relation_type, relation_type)

    async def inject_context_to_prompt(
        self,
        original_prompt: str,
        group_id: str,
        user_id: str,
        injection_position: str = "end",
        include_social_relations: bool = True,
        include_affection: bool = True,
        include_mood: bool = True,
        include_expression_patterns: bool = True
    ) -> str:
        """
        将完整上下文（社交关系、好感度、情绪、表达模式）注入到prompt中

        Args:
            original_prompt: 原始prompt
            group_id: 群组ID
            user_id: 用户ID
            injection_position: 注入位置，'start' 或 'end'
            include_social_relations: 是否包含社交关系
            include_affection: 是否包含好感度
            include_mood: 是否包含情绪
            include_expression_patterns: 是否包含表达模式

        Returns:
            注入了上下文的prompt
        """
        try:
            context = await self.format_complete_context(
                group_id,
                user_id,
                include_social_relations=include_social_relations,
                include_affection=include_affection,
                include_mood=include_mood,
                include_expression_patterns=include_expression_patterns
            )

            if not context:
                # 没有任何上下文信息，返回原始prompt
                return original_prompt

            if injection_position == "start":
                return f"{context}\n\n{original_prompt}"
            else:  # end
                return f"{original_prompt}\n\n{context}"

        except Exception as e:
            logger.error(f"注入上下文失败: {e}", exc_info=True)
            return original_prompt
