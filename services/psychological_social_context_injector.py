"""
心理状态与社交关系上下文注入器
将bot的心理状态和用户的社交关系信息整合注入到LLM prompt中
支持提示词保护,避免注入内容泄露
"""
import asyncio
from typing import Dict, Any, List, Optional, Tuple

from astrbot.api import logger


class PsychologicalSocialContextInjector:
    """
    心理状态与社交关系上下文注入器

    核心功能:
    1. 整合心理状态管理器和社交关系管理器的数据
    2. 生成结构化的上下文注入内容
    3. 应用提示词保护机制
    4. 使用统一缓存管理器优化性能
    5. 生成指导bot行为模式的详细提示词
    """

    def __init__(
        self,
        database_manager,
        psychological_state_manager=None,
        social_relation_manager=None,
        affection_manager=None,
        diversity_manager=None,
        llm_adapter=None,
        config=None
    ):
        self.db_manager = database_manager
        self.psych_manager = psychological_state_manager
        self.social_manager = social_relation_manager
        self.affection_manager = affection_manager
        self.diversity_manager = diversity_manager
        self.llm_adapter = llm_adapter
        self.config = config

        # 提示词保护服务（延迟加载）
        self._prompt_protection = None
        self._enable_protection = True

        # 使用统一缓存管理器
        from ..utils.cache_manager import get_cache_manager
        self._cache_manager = get_cache_manager()

        # 为心理社交上下文创建专用缓存(如果不存在)
        if not hasattr(self._cache_manager, 'psych_social_cache'):
            from cachetools import TTLCache
            self._cache_manager.psych_social_cache = TTLCache(maxsize=1000, ttl=300)  # 5分钟TTL
            # 注册到缓存管理器的映射表
            if hasattr(self._cache_manager, '_get_cache'):
                # 动态添加到cache_map
                logger.info("✅ [心理社交上下文] 已创建专用缓存 (maxsize=1000, ttl=300s)")

        # 后台任务管理 - 用于异步更新缓存
        self._background_tasks: set = set()
        self._llm_generation_lock: Dict[str, asyncio.Lock] = {}  # 防止重复LLM调用

    def _get_prompt_protection(self):
        """延迟加载提示词保护服务"""
        if self._prompt_protection is None and self._enable_protection:
            try:
                from .prompt_sanitizer import PromptProtectionService
                self._prompt_protection = PromptProtectionService(wrapper_template_index=2)
                logger.info("心理社交上下文注入器: 提示词保护服务已加载")
            except Exception as e:
                logger.warning(f"加载提示词保护服务失败: {e}")
                self._enable_protection = False
        return self._prompt_protection

    def _get_from_cache(self, key: str) -> Optional[Any]:
        """
        从统一缓存管理器获取数据

        Args:
            key: 缓存键

        Returns:
            缓存值或None
        """
        return self._cache_manager.psych_social_cache.get(key)

    def _set_to_cache(self, key: str, data: Any):
        """设置缓存到统一缓存管理器"""
        self._cache_manager.psych_social_cache[key] = data

    async def build_complete_context(
        self,
        group_id: str,
        user_id: str,
        include_psychological: bool = True,
        include_social_relation: bool = True,
        include_affection: bool = True,
        include_diversity: bool = True,
        enable_protection: bool = True
    ) -> str:
        """
        构建完整的上下文注入内容

        Args:
            group_id: 群组ID
            user_id: 用户ID
            include_psychological: 是否包含心理状态
            include_social_relation: 是否包含社交关系
            include_affection: 是否包含好感度
            include_diversity: 是否包含多样性指导
            enable_protection: 是否启用提示词保护

        Returns:
            完整的上下文注入字符串
        """
        try:
            context_parts = []

            # 1. Bot的心理状态
            if include_psychological and self.psych_manager:
                psych_context = await self._build_psychological_context(group_id)
                if psych_context:
                    context_parts.append(psych_context)
                    logger.debug(f"✅ [心理社交上下文] 已准备心理状态 (群组: {group_id})")

            # 2. 用户的社交关系
            if include_social_relation and self.social_manager:
                social_context = await self._build_social_relation_context(
                    user_id, group_id
                )
                if social_context:
                    context_parts.append(social_context)
                    logger.debug(f"✅ [心理社交上下文] 已准备社交关系 (用户: {user_id[:8]}...)")

            # 3. 好感度信息
            if include_affection and self.affection_manager:
                affection_context = await self._build_affection_context(
                    user_id, group_id
                )
                if affection_context:
                    context_parts.append(affection_context)
                    logger.debug(f"✅ [心理社交上下文] 已准备好感度信息")

            # 4. 行为模式指导（基于心理状态和社交关系联动）
            if include_psychological or include_social_relation:
                behavior_guidance = await self._build_behavior_guidance(
                    group_id, user_id
                )
                if behavior_guidance:
                    context_parts.append(behavior_guidance)
                    logger.debug(f"✅ [心理社交上下文] 已准备行为模式指导")

            # 5. 多样性指导（可选）
            if include_diversity and self.diversity_manager:
                diversity_context = await self._build_diversity_context(group_id)
                if diversity_context:
                    context_parts.append(diversity_context)
                    logger.debug(f"✅ [心理社交上下文] 已准备多样性指导")

            if not context_parts:
                return ""

            # 组合所有上下文
            raw_context = "\n\n".join(context_parts)

            # 应用提示词保护
            if enable_protection and self._enable_protection:
                protection = self._get_prompt_protection()
                if protection:
                    protected_context = protection.wrap_prompt(raw_context, register_for_filter=True)
                    logger.info(
                        f"✅ [心理社交上下文] 已保护包装 - "
                        f"原长度: {len(raw_context)}, 新长度: {len(protected_context)}"
                    )
                    return protected_context
                else:
                    logger.warning("⚠️ [心理社交上下文] 提示词保护服务不可用，使用原始文本")

            return raw_context

        except Exception as e:
            logger.error(f"构建完整上下文失败: {e}", exc_info=True)
            return ""

    async def _build_psychological_context(self, group_id: str) -> str:
        """构建心理状态上下文"""
        try:
            cache_key = f"psych_context_{group_id}"
            cached = self._get_from_cache(cache_key)
            if cached:
                return cached

            # 从心理状态管理器获取当前状态
            state_prompt = await self.psych_manager.get_state_prompt_injection(group_id)

            if state_prompt:
                self._set_to_cache(cache_key, state_prompt)
                return state_prompt

            return ""

        except Exception as e:
            logger.error(f"构建心理状态上下文失败: {e}", exc_info=True)
            return ""

    async def _build_social_relation_context(
        self,
        user_id: str,
        group_id: str
    ) -> str:
        """构建社交关系上下文"""
        try:
            cache_key = f"social_context_{user_id}_{group_id}"
            cached = self._get_from_cache(cache_key)
            if cached:
                return cached

            # 从社交关系管理器获取关系描述
            relation_prompt = await self.social_manager.get_relation_prompt_injection(
                user_id, "bot", group_id
            )

            if relation_prompt:
                self._set_to_cache(cache_key, relation_prompt)
                return relation_prompt

            return ""

        except Exception as e:
            logger.error(f"构建社交关系上下文失败: {e}", exc_info=True)
            return ""

    async def _build_affection_context(
        self,
        user_id: str,
        group_id: str
    ) -> str:
        """构建好感度上下文"""
        try:
            cache_key = f"affection_context_{user_id}_{group_id}"
            cached = self._get_from_cache(cache_key)
            if cached:
                return cached

            # 从好感度管理器获取信息
            affection_data = await self.db_manager.get_user_affection(group_id, user_id)

            if not affection_data:
                return ""

            level = affection_data.get('affection_level', 0)
            max_level = affection_data.get('max_affection', 100)

            # 生成描述
            if level >= 80:
                desc = "非常喜欢这个用户，关系非常亲密"
            elif level >= 60:
                desc = "比较喜欢这个用户，关系较好"
            elif level >= 40:
                desc = "对这个用户有一定好感"
            elif level >= 20:
                desc = "对这个用户略有好感"
            elif level >= 0:
                desc = "与这个用户初次见面，关系一般"
            elif level >= -20:
                desc = "对这个用户略有反感"
            elif level >= -40:
                desc = "比较不喜欢这个用户"
            else:
                desc = "非常讨厌这个用户"

            context = f"【对该用户的好感度】\n好感度: {level}/{max_level} ({desc})"

            self._set_to_cache(cache_key, context)
            return context

        except Exception as e:
            logger.error(f"构建好感度上下文失败: {e}", exc_info=True)
            return ""

    async def _build_behavior_guidance(
        self,
        group_id: str,
        user_id: str
    ) -> str:
        """
        构建行为模式指导（基于心理状态和社交关系的联动分析）

        这是核心功能：根据当前的心理状态和社交关系，
        使用LLM提炼模型生成对bot行为有强烈指导性但不死板的提示词

        ⚡ 非阻塞设计：
        - 优先返回缓存数据(5分钟TTL)
        - 如果缓存不存在,返回空字符串,并在后台异步生成
        - 后台生成完成后更新缓存,下次调用时可用
        """
        try:
            cache_key = f"behavior_guidance_{group_id}_{user_id}"

            # 1. 优先返回缓存(TTLCache自动管理过期,5分钟TTL)
            cached = self._get_from_cache(cache_key)
            if cached:
                logger.debug(f"💾 [行为指导] 使用缓存 (group: {group_id[:8]}...)")
                return cached

            # 2. 缓存未命中 - 检查是否已有后台生成任务在运行
            if cache_key not in self._llm_generation_lock:
                self._llm_generation_lock[cache_key] = asyncio.Lock()

            # 尝试获取锁(非阻塞)
            if self._llm_generation_lock[cache_key].locked():
                # 已有任务在生成,直接返回空字符串,不阻塞
                logger.debug(f"⏳ [行为指导] 生成任务进行中,返回空字符串 (group: {group_id[:8]}...)")
                return ""

            # 3. 获取锁后,启动后台生成任务(不等待)
            async with self._llm_generation_lock[cache_key]:
                # 双重检查:再次查询缓存(可能其他协程已经生成了)
                cached = self._get_from_cache(cache_key)
                if cached:
                    return cached

                # 启动后台生成任务
                task = asyncio.create_task(self._background_generate_guidance(
                    cache_key, group_id, user_id
                ))
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)

                # 立即返回空字符串,不阻塞主流程
                logger.debug(f"🚀 [行为指导] 已启动后台生成任务 (group: {group_id[:8]}...)")
                return ""

        except Exception as e:
            logger.error(f"构建行为模式指导失败: {e}", exc_info=True)
            return ""

    async def _background_generate_guidance(
        self,
        cache_key: str,
        group_id: str,
        user_id: str
    ):
        """
        后台生成行为指导(异步任务,不阻塞主流程)

        Args:
            cache_key: 缓存键
            group_id: 群组ID
            user_id: 用户ID
        """
        try:
            logger.debug(f"🔄 [后台任务] 开始生成行为指导 (group: {group_id[:8]}...)")

            # 获取心理状态
            psych_state = None
            if self.psych_manager:
                psych_state = await self.psych_manager.get_or_create_state(group_id)

            # 获取社交关系
            social_profile = None
            if self.social_manager:
                social_profile = await self.social_manager.get_or_create_profile(
                    user_id, group_id
                )

            # 获取好感度
            affection_level = 0
            if self.affection_manager:
                try:
                    affection_data = await self.db_manager.get_user_affection(group_id, user_id)
                    if affection_data:
                        affection_level = affection_data.get('affection_level', 0)
                except:
                    pass

            # 使用LLM提炼模型生成行为指导
            guidance = await self._generate_guidance_by_llm(
                psych_state, social_profile, affection_level, group_id, user_id
            )

            if guidance:
                # 缓存生成的指导(5分钟TTL)
                self._set_to_cache(cache_key, guidance)
                logger.info(f"✅ [后台任务] 行为指导生成完成并已缓存 (group: {group_id[:8]}...)")
            else:
                logger.warning(f"⚠️ [后台任务] LLM生成失败,未缓存 (group: {group_id[:8]}...)")

        except Exception as e:
            logger.error(f"❌ [后台任务] 生成行为指导失败: {e}", exc_info=True)

    async def _generate_guidance_by_llm(
        self,
        psych_state,
        social_profile,
        affection_level: int,
        group_id: str,
        user_id: str
    ) -> str:
        """
        使用LLM提炼模型生成行为指导prompt

        Args:
            psych_state: 复合心理状态对象
            social_profile: 社交关系profile对象
            affection_level: 好感度等级
            group_id: 群组ID
            user_id: 用户ID

        Returns:
            LLM生成的行为指导prompt字符串
        """
        try:
            # 检查LLM适配器是否可用
            if not self.llm_adapter or not hasattr(self.llm_adapter, 'has_refine_provider') or not self.llm_adapter.has_refine_provider():
                logger.warning("⚠️ [行为指导生成] LLM提炼模型不可用，无法生成指导")
                return ""

            # 构建心理状态描述
            psych_desc = ""
            active_components = []
            if psych_state:
                active_components = psych_state.get_active_components()
                if active_components:
                    psych_parts = []
                    for component in active_components[:5]:  # 取前5个最显著的状态
                        category = component.category
                        state_name = component.state_type.value if hasattr(
                            component.state_type, 'value') else str(component.state_type)
                        intensity = component.value
                        psych_parts.append(f"- {category}: {state_name} (强度: {intensity:.2f})")
                    psych_desc = "\n".join(psych_parts)

            # 构建社交关系描述
            social_desc = ""
            if social_profile:
                significant_relations = social_profile.get_significant_relations()
                if significant_relations:
                    social_parts = []
                    for rel in significant_relations[:3]:  # 取前3个最显著的关系
                        rel_name = rel.relation_type.value if hasattr(
                            rel.relation_type, 'value') else str(rel.relation_type)
                        social_parts.append(f"- {rel_name} (强度: {rel.value:.2f})")
                    social_desc = "\n".join(social_parts)

            # 构建好感度描述
            if affection_level >= 80:
                affection_desc = f"非常喜欢 ({affection_level}/100)"
            elif affection_level >= 60:
                affection_desc = f"比较喜欢 ({affection_level}/100)"
            elif affection_level >= 40:
                affection_desc = f"有一定好感 ({affection_level}/100)"
            elif affection_level >= 20:
                affection_desc = f"略有好感 ({affection_level}/100)"
            elif affection_level >= 0:
                affection_desc = f"初次见面 ({affection_level}/100)"
            elif affection_level >= -20:
                affection_desc = f"略有反感 ({affection_level}/100)"
            elif affection_level >= -40:
                affection_desc = f"比较不喜欢 ({affection_level}/100)"
            else:
                affection_desc = f"非常讨厌 ({affection_level}/100)"

            # 构建LLM prompt
            prompt = self._build_llm_guidance_prompt(
                psych_desc, social_desc, affection_desc
            )

            # 调用LLM生成
            logger.debug(f"📤 [行为指导] 调用LLM提炼模型生成指导 (group: {group_id[:8]}...)")

            response = await self.llm_adapter.refine_chat_completion(
                prompt=prompt,
                temperature=0.7  # 适度的创造性
            )

            if response:
                # 包装为标准格式
                guidance = f"【行为模式指导】\n{response.strip()}"
                logger.info(f"✅ [行为指导] LLM生成成功 (长度: {len(guidance)})")
                return guidance
            else:
                logger.warning("⚠️ [行为指导] LLM返回空响应")
                return ""

        except Exception as e:
            logger.error(f"❌ [行为指导] LLM生成失败: {e}", exc_info=True)
            return ""

    def _build_llm_guidance_prompt(
        self,
        psych_desc: str,
        social_desc: str,
        affection_desc: str
    ) -> str:
        """
        构建发送给LLM提炼模型的prompt

        Args:
            psych_desc: 心理状态描述
            social_desc: 社交关系描述
            affection_desc: 好感度描述

        Returns:
            完整的prompt字符串
        """
        prompt = f"""你是一个AI对话行为分析专家。根据以下Bot当前的心理状态、社交关系和好感度信息，生成一段简洁但有效的行为指导prompt。

【Bot当前心理状态】
{psych_desc if psych_desc else "无明显心理状态"}

【与该用户的社交关系】
{social_desc if social_desc else "初次接触，关系陌生"}

【对该用户的好感度】
{affection_desc}

---

请生成一段行为指导，用于指导Bot在对话中的语气、态度和行为模式。要求：

1. **简洁明确**：用2-4个要点说明，每个要点1-2句话
2. **自然灵活**：避免死板的规则，给Bot留有发挥空间
3. **情感真实**：根据心理状态和好感度，体现真实的情感倾向
4. **关系适配**：根据社交关系强度调整亲密度和距离感

输出格式示例：
- 语气风格：[描述语气特点，如"轻松活泼"、"平和沉稳"等]
- 态度倾向：[描述对用户的态度，如"友好热情"、"略显冷淡"等]
- 回复特点：[描述回复风格，如"简短直接"、"详细耐心"等]
- 特别提示：[可选的其他建议]

请直接输出行为指导内容，不要包含额外的解释或标题。"""

        return prompt

    def _generate_emotion_guidance(self, emotion: str, intensity: float) -> str:
        """根据情绪生成行为指导"""
        intensity_desc = "强烈" if intensity > 0.7 else "明显" if intensity > 0.4 else "轻微"

        # 根据不同情绪生成不同指导
        if "愉悦" in emotion or "快乐" in emotion or "兴奋" in emotion:
            return (
                f"- 当前情绪: {intensity_desc}{emotion}\n"
                f"  建议: 语气活泼开朗，可以多用积极的表达，适度使用感叹号和表情符号\n"
                f"  语言风格: 轻松愉快，对话中可以展现出喜悦的情感"
            )
        elif "悲伤" in emotion or "难过" in emotion or "低落" in emotion:
            return (
                f"- 当前情绪: {intensity_desc}{emotion}\n"
                f"  建议: 语气相对平和或低沉，回复可以简短一些，避免过于活泼\n"
                f"  语言风格: 略显沉默，可能需要他人的理解和安慰"
            )
        elif "愤怒" in emotion or "烦躁" in emotion:
            return (
                f"- 当前情绪: {intensity_desc}{emotion}\n"
                f"  建议: 语气可能比较直接或强硬，回复简洁，不太有耐心\n"
                f"  语言风格: 直接了当，可能略显不耐烦"
            )
        elif "平静" in emotion or "平和" in emotion:
            return (
                f"- 当前情绪: {intensity_desc}{emotion}\n"
                f"  建议: 语气平稳温和，回复理性客观\n"
                f"  语言风格: 平和稳重，给人安全感"
            )
        else:
            return f"- 当前情绪: {intensity_desc}{emotion}"

    def _generate_cognitive_guidance(self, cognitive: str, intensity: float) -> str:
        """根据认知状态生成行为指导"""
        if "专注" in cognitive or "集中" in cognitive:
            return (
                f"- 当前认知状态: {cognitive}\n"
                f"  建议: 回复详细深入，逻辑清晰，可以展开讨论\n"
                f"  思维模式: 思路清晰，能够深入分析问题"
            )
        elif "涣散" in cognitive or "分心" in cognitive:
            return (
                f"- 当前认知状态: {cognitive}\n"
                f"  建议: 回复可能相对简短，思路可能跳跃\n"
                f"  思维模式: 注意力不太集中，可能需要对方提醒"
            )
        else:
            return f"- 当前认知状态: {cognitive}"

    def _generate_social_guidance(self, social: str, intensity: float) -> str:
        """根据社交状态生成行为指导"""
        if "友善" in social or "热情" in social:
            return (
                f"- 当前社交状态: {social}\n"
                f"  建议: 主动积极回应，语气友好热情，可以主动提问或关心对方\n"
                f"  社交模式: 开放友好，乐于交流"
            )
        elif "冷漠" in social or "疏离" in social:
            return (
                f"- 当前社交状态: {social}\n"
                f"  建议: 回复相对冷淡，不太主动，保持一定距离感\n"
                f"  社交模式: 不太愿意深入交流，保持距离"
            )
        else:
            return f"- 当前社交状态: {social}"

    def _generate_energy_guidance(self, energy: str, intensity: float) -> str:
        """根据精力状态生成行为指导"""
        if "充沛" in energy or "活力" in energy:
            return (
                f"- 当前精力状态: {energy}\n"
                f"  建议: 回复可以更长更详细，充满活力\n"
                f"  精神状态: 精力旺盛，可以处理复杂话题"
            )
        elif "疲惫" in energy or "困倦" in energy or "瞌睡" in energy:
            return (
                f"- 当前精力状态: {energy}\n"
                f"  建议: 回复简短一些，可能反应稍慢，语气略显疲惫\n"
                f"  精神状态: 比较累，需要休息"
            )
        else:
            return f"- 当前精力状态: {energy}"

    def _generate_relation_guidance(
        self,
        relation_type: str,
        relation_value: float,
        affection_level: int
    ) -> str:
        """根据社交关系生成行为指导"""
        strength = "非常强" if relation_value > 0.7 else "较强" if relation_value > 0.4 else "一般"

        guidance = f"- 与该用户的关系: {relation_type} (强度: {strength})\n"

        # 根据关系类型调整语气和态度
        if "挚友" in relation_type or "知己" in relation_type or "闺蜜" in relation_type:
            guidance += (
                "  建议: 语气亲密自然，可以开玩笑，展现真实性格\n"
                "  态度: 放松随意，无需过分客套，像对待老朋友一样"
            )
        elif "恋人" in relation_type or "情侣" in relation_type:
            guidance += (
                "  建议: 语气温柔体贴，关心对方，可以适度撒娇或甜蜜\n"
                "  态度: 亲密关爱，重视对方的感受"
            )
        elif "同事" in relation_type or "同学" in relation_type:
            guidance += (
                "  建议: 语气友好但保持适当专业性\n"
                "  态度: 友善合作，但不过分亲密"
            )
        elif "陌生" in relation_type or relation_value < 0.2:
            guidance += (
                "  建议: 语气礼貌客气，保持一定距离\n"
                "  态度: 谨慎友好，慢慢建立信任"
            )
        else:
            guidance += (
                "  建议: 根据具体情况自然应对\n"
                "  态度: 友好适度"
            )

        # 结合好感度调整
        if affection_level >= 70:
            guidance += "\n  特别提示: 好感度很高，可以更加亲近和真实"
        elif affection_level <= -20:
            guidance += "\n  特别提示: 好感度较低，需要谨慎应对，避免冲突"

        return guidance

    async def _build_diversity_context(self, group_id: str) -> str:
        """构建多样性指导上下文"""
        try:
            if not self.diversity_manager:
                return ""

            # 获取多样性管理器的当前设置
            current_style = self.diversity_manager.get_current_style()
            current_pattern = self.diversity_manager.get_current_pattern()

            if not current_style and not current_pattern:
                return ""

            context_parts = ["【回复多样性指导】"]

            if current_style:
                context_parts.append(f"当前语言风格: {current_style}")

            if current_pattern:
                context_parts.append(f"推荐回复模式: {current_pattern}")

            context_parts.append(
                "注意: 这些是参考建议，请自然运用，不必严格遵守"
            )

            return "\n".join(context_parts)

        except Exception as e:
            logger.error(f"构建多样性上下文失败: {e}")
            return ""

    async def inject_to_system_prompt(
        self,
        original_system_prompt: str,
        group_id: str,
        user_id: str,
        position: str = "end"
    ) -> str:
        """
        将完整上下文注入到system prompt

        Args:
            original_system_prompt: 原始system prompt
            group_id: 群组ID
            user_id: 用户ID
            position: 注入位置 ('start' 或 'end')

        Returns:
            注入后的system prompt
        """
        try:
            context = await self.build_complete_context(
                group_id, user_id,
                include_psychological=True,
                include_social_relation=True,
                include_affection=True,
                include_diversity=False,  # 多样性指导通常单独处理
                enable_protection=True
            )

            if not context:
                return original_system_prompt

            if position == "start":
                return f"{context}\n\n{original_system_prompt}"
            else:
                return f"{original_system_prompt}\n\n{context}"

        except Exception as e:
            logger.error(f"注入上下文到system prompt失败: {e}", exc_info=True)
            return original_system_prompt
