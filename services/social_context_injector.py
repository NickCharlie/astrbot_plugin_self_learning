"""
社交上下文注入器 - 将用户社交关系、好感度、Bot情绪信息注入到LLM prompt中
支持缓存机制以避免频繁查询数据库
"""
import time
from typing import Dict, Any, List, Optional, Tuple

from astrbot.api import logger


class SocialContextInjector:
    """社交上下文注入器 - 格式化并注入用户社交关系、好感度、Bot情绪到prompt"""

    def __init__(self, database_manager, affection_manager=None, mood_manager=None, config=None):
        self.database_manager = database_manager
        self.affection_manager = affection_manager
        self.mood_manager = mood_manager
        self.config = config  # 添加config参数以读取配置

        # 提示词保护服务（延迟加载）
        self._prompt_protection = None
        self._enable_protection = True

        # ⚡ 缓存机制 - 避免频繁查询数据库
        self._cache: Dict[str, Tuple[float, Any]] = {}  # key -> (timestamp, data)
        self._cache_ttl = 60  # 缓存有效期：60秒（1分钟）

    def _get_prompt_protection(self):
        """延迟加载提示词保护服务"""
        if self._prompt_protection is None and self._enable_protection:
            try:
                from .prompt_sanitizer import PromptProtectionService
                self._prompt_protection = PromptProtectionService(wrapper_template_index=0)
                logger.info("社交上下文注入器: 提示词保护服务已加载")
            except Exception as e:
                logger.warning(f"加载提示词保护服务失败: {e}")
                self._enable_protection = False
        return self._prompt_protection

    def _get_from_cache(self, key: str) -> Optional[Any]:
        """从缓存获取数据"""
        if key in self._cache:
            timestamp, data = self._cache[key]
            if time.time() - timestamp < self._cache_ttl:
                return data
            else:
                # 缓存过期，删除
                del self._cache[key]
        return None

    def _set_to_cache(self, key: str, data: Any):
        """设置缓存"""
        self._cache[key] = (time.time(), data)

    async def format_complete_context(
        self,
        group_id: str,
        user_id: str,
        include_social_relations: bool = True,
        include_affection: bool = True,
        include_mood: bool = True,
        include_expression_patterns: bool = True,
        enable_protection: bool = True
    ) -> Optional[str]:
        """
        格式化完整的上下文信息（社交关系、好感度、情绪、风格特征）
        并统一应用提示词保护

        Args:
            group_id: 群组ID
            user_id: 用户ID
            include_social_relations: 是否包含社交关系
            include_affection: 是否包含好感度信息
            include_mood: 是否包含情绪信息
            include_expression_patterns: 是否包含最近学到的表达模式
            enable_protection: 是否启用提示词保护

        Returns:
            格式化的完整上下文文本（已保护），如果没有任何信息则返回None
        """
        try:
            context_parts = []

            # 1. Bot当前情绪信息
            if include_mood and self.mood_manager:
                mood_text = await self._format_mood_context(group_id)
                if mood_text:
                    context_parts.append(mood_text)
                    logger.debug(f"✅ [社交上下文] 已准备情绪信息 (群组: {group_id})")

            # 2. 对该用户的好感度信息
            if include_affection and self.affection_manager:
                affection_text = await self._format_affection_context(group_id, user_id)
                if affection_text:
                    context_parts.append(affection_text)
                    logger.debug(f"✅ [社交上下文] 已准备好感度信息 (群组: {group_id}, 用户: {user_id[:8]}...)")

            # 3. 用户社交关系信息
            if include_social_relations:
                social_text = await self.format_social_context(group_id, user_id)
                if social_text:
                    context_parts.append(social_text)
                    logger.debug(f"✅ [社交上下文] 已准备社交关系 (群组: {group_id}, 用户: {user_id[:8]}...)")

            # 4. 最近学到的表达模式（风格特征）
            # 注意：表达模式内部已经应用了保护，这里获取的是保护后的文本
            if include_expression_patterns:
                expression_text = await self._format_expression_patterns_context(
                    group_id,
                    enable_protection=enable_protection  # 传递保护参数
                )
                if expression_text:
                    context_parts.append(expression_text)
                    logger.info(f"✅ [社交上下文] 已准备表达模式 (群组: {group_id}, 长度: {len(expression_text)})")
                else:
                    logger.info(f"⚠️ [社交上下文] 群组 {group_id} 暂无表达模式学习记录")

            if not context_parts:
                return None

            # 组合所有上下文信息（不包含表达模式，因为它已经被保护）
            # 将表达模式分离出来
            expression_part = None
            other_parts = []
            for part in context_parts:
                if "表达风格特征" in part or "HIDDEN_INSTRUCTION" in part:
                    expression_part = part
                else:
                    other_parts.append(part)

            # 对其他部分（情绪、好感度、社交关系）应用统一的提示词保护
            if other_parts:
                context_header = "=" * 50
                raw_other_context = f"{context_header}\n"
                raw_other_context += "【上下文参考信息】\n"
                raw_other_context += "\n".join(other_parts)
                raw_other_context += f"\n{context_header}"

                # 应用提示词保护
                if enable_protection and self._enable_protection:
                    protection = self._get_prompt_protection()
                    if protection:
                        protected_other = protection.wrap_prompt(raw_other_context, register_for_filter=True)
                        logger.info(f"✅ [社交上下文] 已对情绪/好感度/社交关系应用提示词保护")
                    else:
                        protected_other = raw_other_context
                        logger.warning(f"⚠️ [社交上下文] 提示词保护服务不可用，使用原始文本")
                else:
                    protected_other = raw_other_context
            else:
                protected_other = ""

            # 组合保护后的内容（表达模式已经被保护，其他内容刚刚被保护）
            final_parts = []
            if protected_other:
                final_parts.append(protected_other)
            if expression_part:
                final_parts.append(expression_part)

            if not final_parts:
                return None

            full_context = "\n\n".join(final_parts)
            return full_context

        except Exception as e:
            logger.error(f"格式化完整上下文失败: {e}", exc_info=True)
            return None

    async def _format_mood_context(self, group_id: str) -> Optional[str]:
        """格式化Bot当前情绪信息（带缓存）"""
        try:
            if not self.mood_manager:
                return None

            # ⚡ 尝试从缓存获取
            cache_key = f"mood_{group_id}"
            cached = self._get_from_cache(cache_key)
            if cached is not None:
                return cached

            mood_raw = await self.mood_manager.get_current_mood(group_id)
            if not mood_raw:
                return None

            # 兼容 BotMood 对象或字典格式的数据
            def _normalize_mood(record: Any) -> Tuple[Optional[str], Optional[float], str]:
                if record is None:
                    return None, None, ""

                # BotMood dataclass（具备属性）
                if hasattr(record, "mood_type") or hasattr(record, "description"):
                    mood_type = getattr(record, "mood_type", None)
                    mood_label = None
                    if mood_type is not None:
                        mood_label = getattr(mood_type, "value", None) or str(mood_type)
                    else:
                        mood_label = getattr(record, "name", None)

                    intensity = getattr(record, "intensity", None)
                    description = getattr(record, "description", "") or ""
                    return mood_label, intensity, description

                # 字典格式
                if isinstance(record, dict):
                    mood_label = (
                        record.get("type")
                        or record.get("mood_type")
                        or record.get("name")
                        or record.get("current_mood")
                    )
                    intensity = record.get("intensity")
                    description = record.get("description") or record.get("desc") or ""
                    return mood_label, intensity, description

                # 其他类型（字符串等）
                return str(record), None, ""

            # 如果返回的是包含 current_mood 的字典，则取内部值
            if isinstance(mood_raw, dict) and "current_mood" in mood_raw:
                current_record = mood_raw.get("current_mood")
                # 兼容可能嵌套 description 在外层的结构
                if isinstance(current_record, dict) and not current_record.get("description"):
                    current_record = {**current_record, "description": mood_raw.get("description", "")}
            else:
                current_record = mood_raw

            mood_label, mood_intensity, mood_description = _normalize_mood(current_record)
            if not mood_label and not mood_description:
                return None

            mood_text = "【Bot当前情绪状态】\n"
            if mood_label:
                mood_text += f"情绪: {mood_label}"
                if isinstance(mood_intensity, (int, float)):
                    mood_text += f" (强度 {mood_intensity:.2f})"
            if mood_description:
                connector = " - " if mood_label else ""
                mood_text += f"{connector}{mood_description}"

            # ⚡ 缓存结果
            self._set_to_cache(cache_key, mood_text)
            return mood_text

        except Exception as e:
            logger.error(f"格式化情绪上下文失败: {e}", exc_info=True)
            return None

    async def _format_affection_context(self, group_id: str, user_id: str) -> Optional[str]:
        """格式化对该用户的好感度信息（带缓存）"""
        try:
            if not self.affection_manager:
                return None

            # ⚡ 尝试从缓存获取
            cache_key = f"affection_{group_id}_{user_id}"
            cached = self._get_from_cache(cache_key)
            if cached is not None:
                return cached

            affection_data = await self.database_manager.get_user_affection(group_id, user_id)
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

            # ⚡ 缓存结果
            self._set_to_cache(cache_key, affection_text)
            return affection_text

        except Exception as e:
            logger.error(f"格式化好感度上下文失败: {e}", exc_info=True)
            return None

    async def _format_expression_patterns_context(
        self,
        group_id: str,
        enable_protection: bool = True,
        enable_global_fallback: bool = True
    ) -> Optional[str]:
        """
        格式化最近学到的表达模式（风格特征）- 带提示词保护和缓存
        支持全局回退：如果当前群组没有表达模式，则使用全局表达模式

        Args:
            group_id: 群组ID
            enable_protection: 是否启用提示词保护
            enable_global_fallback: 是否启用全局回退（当群组无数据时使用全局数据）

        Returns:
            格式化的表达模式文本（已保护包装）
        """
        try:
            # ⚡ 尝试从缓存获取
            cache_key = f"expression_patterns_{group_id}"
            cached = self._get_from_cache(cache_key)
            if cached is not None:
                return cached

            # 从配置中读取时间范围，默认24小时
            hours = 24
            if self.config and hasattr(self.config, 'expression_patterns_hours'):
                hours = getattr(self.config, 'expression_patterns_hours', 24)

            # 1️⃣ 优先获取当前群组的表达模式
            patterns = await self.database_manager.get_recent_week_expression_patterns(
                group_id,
                limit=10,
                hours=hours
            )

            source_desc = f"群组 {group_id}"

            # 2️⃣ 如果当前群组没有表达模式，且启用了全局回退，则获取全局表达模式
            if not patterns and enable_global_fallback:
                logger.info(f"⚠️ [表达模式] 群组 {group_id} 无表达模式，尝试使用全局表达模式")
                patterns = await self.database_manager.get_recent_week_expression_patterns(
                    group_id=None,  # None = 全局查询
                    limit=10,
                    hours=hours
                )
                source_desc = "全局所有群组"

            if not patterns:
                # ⚡ 缓存空结果（避免频繁查询空数据）
                self._set_to_cache(cache_key, None)
                logger.info(f"⚠️ [表达模式] {source_desc} 均无表达模式学习记录")
                return None

            # 构建原始表达模式文本
            time_desc = f"{hours}小时" if hours < 24 else f"{hours//24}天"
            raw_pattern_text = f"最近{time_desc}学到的表达风格特征（来源: {source_desc}）：\n"
            raw_pattern_text += f"以下是最近{time_desc}学习到的表达模式，参考这些风格进行回复：\n"

            for i, pattern in enumerate(patterns[:10], 1):  # 最多显示10个
                situation = pattern.get('situation', '未知场景')
                expression = pattern.get('expression', '未知表达')

                # 简化显示
                raw_pattern_text += f"{i}. 当{situation}时，使用类似「{expression}」的表达方式\n"

            raw_pattern_text += "\n提示：这些是从真实对话中学习到的表达模式，请在适当的场景下灵活运用，保持自然流畅。"

            # 应用提示词保护
            if enable_protection and self._enable_protection:
                protection = self._get_prompt_protection()
                if protection:
                    protected_text = protection.wrap_prompt(raw_pattern_text, register_for_filter=True)
                    logger.info(f"✅ [表达模式] 已应用提示词保护 (来源: {source_desc}, 模式数: {len(patterns)})")
                    # ⚡ 缓存保护后的结果
                    self._set_to_cache(cache_key, protected_text)
                    return protected_text
                else:
                    logger.warning(f"⚠️ [表达模式] 提示词保护服务不可用，使用原始文本")

            # ⚡ 缓存原始结果
            logger.info(f"✅ [表达模式] 已准备表达模式（未保护）(来源: {source_desc}, 模式数: {len(patterns)})")
            self._set_to_cache(cache_key, raw_pattern_text)
            return raw_pattern_text

        except Exception as e:
            logger.error(f"格式化表达模式上下文失败: {e}", exc_info=True)
            return None

    async def format_social_context(self, group_id: str, user_id: str) -> Optional[str]:
        """
        格式化用户的社交关系上下文（带缓存）

        Args:
            group_id: 群组ID
            user_id: 用户ID

        Returns:
            格式化的社交关系文本，如果没有关系则返回None
        """
        try:
            # ⚡ 先从缓存获取
            cache_key = f"social_relations_{group_id}_{user_id}"
            cached = self._get_from_cache(cache_key)
            if cached is not None:
                return cached

            # 获取用户社交关系
            relations_data = await self.database_manager.get_user_social_relations(group_id, user_id)

            if relations_data['total_relations'] == 0:
                # ⚡ 缓存空结果
                self._set_to_cache(cache_key, None)
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

            # ⚡ 缓存结果
            self._set_to_cache(cache_key, context_text)
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
