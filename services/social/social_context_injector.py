"""
社交上下文注入器 - 将用户社交关系、好感度、Bot情绪信息注入到LLM prompt中
支持缓存机制以避免频繁查询数据库

整合了原 PsychologicalSocialContextInjector 的行为指导生成功能:
- 深度心理状态分析
- LLM驱动的行为模式指导(非阻塞后台生成)
- 好感度/社交关系联动分析
"""
import asyncio
import time
from typing import Dict, Any, List, Optional, Tuple
from cachetools import TTLCache

from astrbot.api import logger


class SocialContextInjector:
    """社交上下文注入器 - 格式化并注入用户社交关系、好感度、Bot情绪到prompt"""

    def __init__(
        self,
        database_manager,
        affection_manager=None,
        mood_manager=None,
        config=None,
        psychological_state_manager=None,
        social_relation_manager=None,
        llm_adapter=None,
        goal_manager=None
    ):
        self.database_manager = database_manager
        self.affection_manager = affection_manager
        self.mood_manager = mood_manager
        self.config = config # 添加config参数以读取配置

        # 新增：心理状态和社交关系管理器（整合自 PsychologicalSocialContextInjector）
        self.psych_manager = psychological_state_manager
        self.social_manager = social_relation_manager
        self.llm_adapter = llm_adapter

        # 新增：对话目标管理器
        self.goal_manager = goal_manager

        # 提示词保护服务（延迟加载）
        self._prompt_protection = None
        self._enable_protection = True

        # 缓存机制 - 使用cachetools的TTLCache
        # maxsize=1000: 最多缓存1000个条目
        # ttl=60: 缓存有效期60秒（1分钟）
        self._cache = TTLCache(maxsize=1000, ttl=60)

        # 行为指导后台生成 (整合自 PsychologicalSocialContextInjector)
        self._background_tasks: set = set()
        self._llm_generation_lock: Dict[str, asyncio.Lock] = {}

    def _get_prompt_protection(self):
        """延迟加载提示词保护服务"""
        if self._prompt_protection is None and self._enable_protection:
            try:
                from ..response import PromptProtectionService
                self._prompt_protection = PromptProtectionService(wrapper_template_index=0)
                logger.info("社交上下文注入器: 提示词保护服务已加载")
            except Exception as e:
                logger.warning(f"加载提示词保护服务失败: {e}")
                self._enable_protection = False
        return self._prompt_protection

    def _get_from_cache(self, key: str) -> Optional[Any]:
        """从缓存获取数据 (使用TTLCache自动过期机制)"""
        return self._cache.get(key)

    def _set_to_cache(self, key: str, data: Any):
        """设置缓存 (使用TTLCache自动管理过期)"""
        self._cache[key] = data

    async def format_complete_context(
        self,
        group_id: str,
        user_id: str,
        include_social_relations: bool = True,
        include_affection: bool = True,
        include_mood: bool = True,
        include_expression_patterns: bool = True,
        include_psychological: bool = True,
        include_behavior_guidance: bool = True,
        include_conversation_goal: bool = False,
        enable_protection: bool = True
    ) -> Optional[str]:
        """
        格式化完整的上下文信息（社交关系、好感度、情绪、风格特征、心理状态、行为指导、对话目标）
        并统一应用提示词保护

        Args:
            group_id: 群组ID
            user_id: 用户ID
            include_social_relations: 是否包含社交关系
            include_affection: 是否包含好感度信息
            include_mood: 是否包含情绪信息
            include_expression_patterns: 是否包含最近学到的表达模式
            include_psychological: 是否包含深度心理状态分析（整合自 PsychologicalSocialContextInjector）
            include_behavior_guidance: 是否包含行为模式指导（整合自 PsychologicalSocialContextInjector）
            include_conversation_goal: 是否包含对话目标上下文
            enable_protection: 是否启用提示词保护

        Returns:
            格式化的完整上下文文本（已保护），如果没有任何信息则返回None
        """
        try:
            context_parts = []

            # 1. 深度心理状态分析（整合自 PsychologicalSocialContextInjector）
            if include_psychological and self.psych_manager:
                psych_context = await self._build_psychological_context(group_id)
                if psych_context:
                    context_parts.append(psych_context)
                    logger.info(f" [社交上下文] 已准备深度心理状态 (群组: {group_id}, 长度: {len(psych_context)})")
                else:
                    logger.info(f" [社交上下文] 群组 {group_id} 暂无活跃的心理状态")

            # 2. Bot当前情绪信息（基础版，可与心理状态共存）
            if include_mood and self.mood_manager:
                mood_text = await self._format_mood_context(group_id)
                if mood_text:
                    context_parts.append(mood_text)
                    logger.debug(f" [社交上下文] 已准备情绪信息 (群组: {group_id})")

            # 3. 对该用户的好感度信息
            if include_affection and self.affection_manager:
                affection_text = await self._format_affection_context(group_id, user_id)
                if affection_text:
                    context_parts.append(affection_text)
                    logger.debug(f" [社交上下文] 已准备好感度信息 (群组: {group_id}, 用户: {user_id[:8]}...)")

            # 4. 用户社交关系信息（使用 SocialContextInjector 原有实现）
            if include_social_relations:
                social_text = await self.format_social_context(group_id, user_id)
                if social_text:
                    context_parts.append(social_text)
                    logger.debug(f" [社交上下文] 已准备社交关系 (群组: {group_id}, 用户: {user_id[:8]}...)")

            # 5. 最近学到的表达模式（风格特征）- SocialContextInjector 独有
            # 注意：表达模式内部已经应用了保护，这里获取的是保护后的文本
            if include_expression_patterns:
                expression_text = await self._format_expression_patterns_context(
                    group_id,
                    enable_protection=enable_protection # 传递保护参数
                )
                if expression_text:
                    context_parts.append(expression_text)
                    logger.info(f" [社交上下文] 已准备表达模式 (群组: {group_id}, 长度: {len(expression_text)})")
                else:
                    logger.info(f" [社交上下文] 群组 {group_id} 暂无表达模式学习记录")

            # 6. 行为模式指导（整合自 PsychologicalSocialContextInjector）
            if include_behavior_guidance and (include_psychological or include_social_relations):
                behavior_guidance = await self._build_behavior_guidance(group_id, user_id)
                if behavior_guidance:
                    context_parts.append(behavior_guidance)
                    logger.info(f" [社交上下文] 已准备行为模式指导 (长度: {len(behavior_guidance)})")
                else:
                    logger.debug(f" [社交上下文] 未生成行为模式指导")

            # 7. 对话目标上下文（新增）
            if include_conversation_goal and self.goal_manager:
                logger.info(f" [社交上下文] 尝试获取对话目标上下文 (user={user_id[:8]}..., group={group_id})")
                goal_context = await self._format_conversation_goal_context(group_id, user_id)
                if goal_context:
                    context_parts.append(goal_context)
                    logger.info(f" [社交上下文] 已准备对话目标 (长度: {len(goal_context)})")
                else:
                    logger.info(f" [社交上下文] 未找到活跃对话目标 (user={user_id[:8]}..., group={group_id})")
            elif include_conversation_goal and not self.goal_manager:
                logger.warning(f" [社交上下文] 对话目标功能已启用但goal_manager未初始化")

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
                        logger.info(f" [社交上下文] 已对情绪/好感度/社交关系应用提示词保护")
                    else:
                        protected_other = raw_other_context
                        logger.warning(f" [社交上下文] 提示词保护服务不可用，使用原始文本")
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

            # 输出最终上下文的组成部分用于调试
            logger.info(f" [社交上下文] 最终上下文包含 {len(final_parts)} 个部分")
            if "对话目标" in full_context or "【当前对话目标状态】" in full_context:
                logger.info(f" [社交上下文] 对话目标上下文已成功包含在最终输出中")
            else:
                logger.info(f" [社交上下文] 对话目标上下文未包含在最终输出中")

            return full_context

        except Exception as e:
            logger.error(f"格式化完整上下文失败: {e}", exc_info=True)
            return None

    async def _format_mood_context(self, group_id: str) -> Optional[str]:
        """格式化Bot当前情绪信息（带缓存）"""
        try:
            if not self.mood_manager:
                return None

            # 尝试从缓存获取
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

            # 缓存结果
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

            # 尝试从缓存获取
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

            # 缓存结果
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
            # 尝试从缓存获取
            cache_key = f"expression_patterns_{group_id}"
            cached = self._get_from_cache(cache_key)
            if cached is not None:
                return cached

            # 从配置中读取时间范围，默认24小时
            hours = 24
            if self.config and hasattr(self.config, 'expression_patterns_hours'):
                hours = getattr(self.config, 'expression_patterns_hours', 24)

            # 优先获取当前群组的表达模式
            patterns = await self.database_manager.get_recent_week_expression_patterns(
                group_id,
                limit=10,
                hours=hours
            )

            source_desc = f"群组 {group_id}"

            # 如果当前群组没有表达模式，且启用了全局回退，则获取全局表达模式
            if not patterns and enable_global_fallback:
                logger.info(f" [表达模式] 群组 {group_id} 无表达模式，尝试使用全局表达模式")
                patterns = await self.database_manager.get_recent_week_expression_patterns(
                    group_id=None, # None = 全局查询
                    limit=10,
                    hours=hours
                )
                source_desc = "全局所有群组"

            if not patterns:
                # 缓存空结果（避免频繁查询空数据）
                self._set_to_cache(cache_key, None)
                logger.info(f" [表达模式] {source_desc} 均无表达模式学习记录")
                return None

            # 构建原始表达模式文本
            time_desc = f"{hours}小时" if hours < 24 else f"{hours//24}天"
            raw_pattern_text = f"最近{time_desc}学到的表达风格特征（来源: {source_desc}）：\n"
            raw_pattern_text += f"以下是最近{time_desc}学习到的表达模式，参考这些风格进行回复：\n"

            for i, pattern in enumerate(patterns[:10], 1): # 最多显示10个
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
                    logger.info(f" [表达模式] 已应用提示词保护 (来源: {source_desc}, 模式数: {len(patterns)})")
                    # 缓存保护后的结果
                    self._set_to_cache(cache_key, protected_text)
                    return protected_text
                else:
                    logger.warning(f" [表达模式] 提示词保护服务不可用，使用原始文本")

            # 缓存原始结果
            logger.info(f" [表达模式] 已准备表达模式（未保护）(来源: {source_desc}, 模式数: {len(patterns)})")
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
            # 先从缓存获取
            cache_key = f"social_relations_{group_id}_{user_id}"
            cached = self._get_from_cache(cache_key)
            if cached is not None:
                return cached

            # 获取用户社交关系
            relations_data = await self.database_manager.get_user_social_relations(group_id, user_id)

            # 兼容两种返回格式：旧版 {total_relations, outgoing, incoming} 和新版 {relations}
            relations = relations_data.get('relations', [])
            if not relations and relations_data.get('total_relations', 0) == 0:
                # 缓存空结果
                self._set_to_cache(cache_key, None)
                return None
            if not relations:
                self._set_to_cache(cache_key, None)
                return None

            # 将 flat relations 分为 outgoing / incoming
            outgoing = [r for r in relations if r.get('from_user_id', r.get('from_user', '')) == user_id]
            incoming = [r for r in relations if r.get('to_user_id', r.get('to_user', '')) == user_id]

            # 格式化社交关系文本
            context_lines = []
            context_lines.append(f"【该用户的社交关系网络】")

            # 格式化发出的关系
            if outgoing:
                context_lines.append(f"该用户的互动对象（按频率排序）：")
                for i, relation in enumerate(sorted(outgoing, key=lambda r: r.get('frequency', 0), reverse=True)[:5], 1):
                    target = self._extract_user_id(relation.get('to_user_id', relation.get('to_user', '')))
                    relation_type = self._format_relation_type(relation.get('relation_type', 'interaction'))
                    strength = relation.get('value', relation.get('strength', 0))
                    frequency = relation.get('frequency', 0)

                    context_lines.append(
                        f" {i}. 与 {target} - {relation_type}，强度: {strength:.1f}，互动{frequency}次"
                    )

            # 格式化接收的关系
            if incoming:
                context_lines.append(f"与该用户互动的成员（按频率排序）：")
                for i, relation in enumerate(sorted(incoming, key=lambda r: r.get('frequency', 0), reverse=True)[:5], 1):
                    source = self._extract_user_id(relation.get('from_user_id', relation.get('from_user', '')))
                    relation_type = self._format_relation_type(relation.get('relation_type', 'interaction'))
                    strength = relation.get('value', relation.get('strength', 0))
                    frequency = relation.get('frequency', 0)

                    context_lines.append(
                        f" {i}. {source} - {relation_type}，强度: {strength:.1f}，互动{frequency}次"
                    )

            context_text = "\n".join(context_lines)

            # 缓存结果
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
            else: # end
                return f"{original_prompt}\n\n{context}"

        except Exception as e:
            logger.error(f"注入上下文失败: {e}", exc_info=True)
            return original_prompt
    # 行为指导生成 (整合自 PsychologicalSocialContextInjector)

    async def _build_behavior_guidance(self, group_id: str, user_id: str) -> str:
        """
        构建行为模式指导（基于心理状态和社交关系的联动分析）

        使用LLM提炼模型生成对bot行为有强烈指导性但不死板的提示词。

        非阻塞设计：
        - 优先返回缓存数据(TTLCache自动管理过期)
        - 如果缓存不存在,返回空字符串,并在后台异步生成
        - 后台生成完成后更新缓存,下次调用时可用
        """
        try:
            cache_key = f"behavior_guidance_{group_id}_{user_id}"

            # 1. 优先返回缓存
            cached = self._get_from_cache(cache_key)
            if cached:
                logger.debug(f"[behavior_guidance] cache hit (group: {group_id[:8]}...)")
                return cached

            # 2. 缓存未命中 - 检查是否已有后台生成任务在运行
            if cache_key not in self._llm_generation_lock:
                self._llm_generation_lock[cache_key] = asyncio.Lock()

            if self._llm_generation_lock[cache_key].locked():
                logger.debug(f"[behavior_guidance] generation in progress, skip (group: {group_id[:8]}...)")
                return ""

            # 3. 获取锁后,启动后台生成任务(不等待)
            async with self._llm_generation_lock[cache_key]:
                # 双重检查
                cached = self._get_from_cache(cache_key)
                if cached:
                    return cached

                task = asyncio.create_task(self._background_generate_guidance(
                    cache_key, group_id, user_id
                ))
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)

                logger.debug(f"[behavior_guidance] bg task started (group: {group_id[:8]}...)")
                return ""

        except Exception as e:
            logger.error(f"[behavior_guidance] build failed: {e}", exc_info=True)
            return ""

    async def _background_generate_guidance(
        self,
        cache_key: str,
        group_id: str,
        user_id: str
    ):
        """后台生成行为指导(异步任务,不阻塞主流程)"""
        try:
            # 获取心理状态
            psych_state = None
            if self.psych_manager and hasattr(self.psych_manager, 'get_or_create_state'):
                psych_state = await self.psych_manager.get_or_create_state(group_id)

            # 获取社交关系
            social_profile = None
            if self.social_manager and hasattr(self.social_manager, 'get_or_create_profile'):
                social_profile = await self.social_manager.get_or_create_profile(
                    user_id, group_id
                )

            # 获取好感度
            affection_level = 0
            if self.affection_manager:
                try:
                    affection_data = await self.database_manager.get_user_affection(group_id, user_id)
                    if affection_data:
                        affection_level = affection_data.get('affection_level', 0)
                except Exception:
                    pass

            # 使用LLM提炼模型生成行为指导
            guidance = await self._generate_guidance_by_llm(
                psych_state, social_profile, affection_level, group_id, user_id
            )

            if guidance:
                self._set_to_cache(cache_key, guidance)
                logger.info(f"[behavior_guidance] bg generation done and cached (group: {group_id[:8]}...)")
            else:
                logger.debug(f"[behavior_guidance] LLM returned empty (group: {group_id[:8]}...)")

        except Exception as e:
            logger.error(f"[behavior_guidance] bg generation failed: {e}", exc_info=True)

    async def _generate_guidance_by_llm(
        self,
        psych_state,
        social_profile,
        affection_level: int,
        group_id: str,
        user_id: str
    ) -> str:
        """使用LLM提炼模型生成行为指导prompt"""
        try:
            if not self.llm_adapter:
                return ""
            if not hasattr(self.llm_adapter, 'has_refine_provider') or not self.llm_adapter.has_refine_provider():
                return ""

            # 构建心理状态描述
            psych_desc = ""
            if psych_state and hasattr(psych_state, 'get_active_components'):
                active_components = psych_state.get_active_components()
                if active_components:
                    psych_parts = []
                    for component in active_components[:5]:
                        category = component.category
                        state_name = (
                            component.state_type.value
                            if hasattr(component.state_type, 'value')
                            else str(component.state_type)
                        )
                        intensity = component.value
                        psych_parts.append(f"- {category}: {state_name} (intensity: {intensity:.2f})")
                    psych_desc = "\n".join(psych_parts)

            # 构建社交关系描述
            social_desc = ""
            if social_profile and hasattr(social_profile, 'get_significant_relations'):
                significant_relations = social_profile.get_significant_relations()
                if significant_relations:
                    social_parts = []
                    for rel in significant_relations[:3]:
                        rel_name = (
                            rel.relation_type.value
                            if hasattr(rel.relation_type, 'value')
                            else str(rel.relation_type)
                        )
                        social_parts.append(f"- {rel_name} (strength: {rel.value:.2f})")
                    social_desc = "\n".join(social_parts)

            # 构建好感度描述
            if affection_level >= 80:
                affection_desc = f"very fond ({affection_level}/100)"
            elif affection_level >= 60:
                affection_desc = f"fairly fond ({affection_level}/100)"
            elif affection_level >= 40:
                affection_desc = f"some affection ({affection_level}/100)"
            elif affection_level >= 20:
                affection_desc = f"slight affection ({affection_level}/100)"
            elif affection_level >= 0:
                affection_desc = f"first meeting ({affection_level}/100)"
            elif affection_level >= -20:
                affection_desc = f"slight dislike ({affection_level}/100)"
            elif affection_level >= -40:
                affection_desc = f"fairly disliked ({affection_level}/100)"
            else:
                affection_desc = f"strongly disliked ({affection_level}/100)"

            # 构建LLM prompt
            prompt = self._build_llm_guidance_prompt(psych_desc, social_desc, affection_desc)

            response = await self.llm_adapter.refine_chat_completion(
                prompt=prompt,
                temperature=0.7
            )

            if response:
                return response.strip()

            return ""

        except Exception as e:
            logger.error(f"[behavior_guidance] LLM generation failed: {e}", exc_info=True)
            return ""

    @staticmethod
    def _build_llm_guidance_prompt(
        psych_desc: str,
        social_desc: str,
        affection_desc: str
    ) -> str:
        """构建发送给LLM提炼模型的行为指导生成prompt"""
        return (
            "You are an AI conversation behavior analyst. "
            "Based on the following Bot's current psychological state, social relations, "
            "and affection level, generate a concise but effective behavior guidance prompt.\n\n"
            f"[Bot Current Psychological State]\n"
            f"{psych_desc if psych_desc else 'No notable psychological state'}\n\n"
            f"[Social Relationship with User]\n"
            f"{social_desc if social_desc else 'First contact, stranger relationship'}\n\n"
            f"[Affection Level for User]\n"
            f"{affection_desc}\n\n"
            "---\n\n"
            "Please generate behavior guidance with 2-4 bullet points:\n"
            "1. Tone & style: describe the tone (e.g. relaxed, calm, direct)\n"
            "2. Attitude: describe attitude towards the user (e.g. friendly, slightly cold)\n"
            "3. Reply style: describe reply characteristics (e.g. brief, detailed, patient)\n"
            "4. Special note: any other relevant suggestion (optional)\n\n"
            "Output the guidance directly, no extra explanation or title."
        )

    # 心理状态上下文

    async def _build_psychological_context(self, group_id: str) -> str:
        """构建深度心理状态上下文"""
        try:
            if not self.psych_manager:
                return ""

            cache_key = f"psych_context_{group_id}"
            cached = self._get_from_cache(cache_key)
            if cached:
                return cached

            state_prompt = await self.psych_manager.get_state_prompt_injection(group_id)

            if state_prompt:
                self._set_to_cache(cache_key, state_prompt)
                return state_prompt

            return ""

        except Exception as e:
            logger.error(f"[psych_context] build failed: {e}", exc_info=True)
            return ""

    # 对话目标上下文

    async def _format_conversation_goal_context(self, group_id: str, user_id: str) -> Optional[str]:
        """格式化对话目标上下文（带缓存）"""
        try:
            if not self.goal_manager:
                return None

            # 尝试从缓存获取
            cache_key = f"conv_goal_{group_id}_{user_id}"
            cached = self._get_from_cache(cache_key)
            if cached is not None:
                return cached

            # 获取当前对话目标
            goal = await self.goal_manager.get_conversation_goal(user_id, group_id)
            if not goal:
                # 缓存空结果
                self._set_to_cache(cache_key, None)
                logger.debug(f" [对话目标上下文] 群组 {group_id} 用户 {user_id[:8]}... 暂无活跃对话目标")
                return None

            # 提取关键信息
            final_goal = goal.get('final_goal', {})
            current_stage = goal.get('current_stage', {})
            planned_stages = goal.get('planned_stages', [])
            metrics = goal.get('metrics', {})

            goal_type = final_goal.get('type', 'unknown')
            goal_name = final_goal.get('name', '未知目标')
            topic = final_goal.get('topic', '未知话题')
            topic_status = final_goal.get('topic_status', 'active')

            current_task = current_stage.get('task', '无')
            task_index = current_stage.get('index', 0)

            rounds = metrics.get('rounds', 0)
            user_engagement = metrics.get('user_engagement', 0.5)
            progress = metrics.get('goal_progress', 0.0)

            logger.info(f" [对话目标上下文] 检测到活跃目标 - 类型: {goal_type}, 名称: {goal_name}, 进度: {progress:.0%}, 阶段: {current_task}")

            # 格式化上下文文本
            context_lines = []
            context_lines.append("【当前对话目标状态】")
            context_lines.append(f"对话目标: {goal_name} (类型: {goal_type})")
            context_lines.append(f"当前话题: {topic} (状态: {'进行中' if topic_status == 'active' else '已完结'})")
            context_lines.append(f"当前阶段: {current_task} ({task_index + 1}/{len(planned_stages)})")

            # 显示规划的阶段
            if planned_stages:
                context_lines.append(f"规划阶段: {' → '.join(planned_stages)}")

            context_lines.append(f"对话进度: {progress:.0%}, 已进行{rounds}轮")
            context_lines.append(f"用户参与度: {user_engagement:.0%}")

            # 添加明确的行为指令
            context_lines.append("")
            context_lines.append("【回复指令】")
            if task_index < len(planned_stages):
                context_lines.append(f" 请根据以上对话目标信息，结合用户的最新消息，围绕当前阶段性目标「{current_task}」组织你的回复内容。")
                context_lines.append(f" 你的回复应该自然地推进对话朝着「{goal_name}」的方向发展，同时保持对话的连贯性和真实性。")
                context_lines.append(f" 注意：不要机械地提及'目标'或'阶段'等元信息，而是通过对话内容本身体现当前阶段的意图。")

                # 根据进度和参与度调整提示
                if progress < 0.3:
                    context_lines.append(f" 对话刚开始，重点是{current_task}，建立良好的互动基础。")
                elif progress < 0.7:
                    context_lines.append(f" 对话进行中，继续围绕{current_task}深入交流，适时引导话题发展。")
                else:
                    context_lines.append(f" 对话接近完成，注意把握{current_task}的收尾，为下一阶段做准备。")

                if user_engagement < 0.4:
                    context_lines.append(f" 用户参与度较低({user_engagement:.0%})，尝试提出开放性问题或话题，激发用户兴趣。")
                elif user_engagement > 0.7:
                    context_lines.append(f" 用户参与度很高({user_engagement:.0%})，保持当前互动风格，深化对话内容。")
            else:
                context_lines.append(f" 对话目标「{goal_name}」的所有规划阶段已完成，请自然地结束本话题或引导新话题。")
                context_lines.append(f" 注意：避免生硬地结束对话，保持自然流畅的互动。")

            context_text = "\n".join(context_lines)

            # 缓存结果
            self._set_to_cache(cache_key, context_text)
            return context_text

        except Exception as e:
            logger.error(f"格式化对话目标上下文失败: {e}", exc_info=True)
            return None
