"""
人格优化服务 - 应用MaiBot的极简人格和反完美主义技术

关键技术:
1. 极简人格核心 - 将人格描述简化为1句话核心
2. 动态表达规则 - 每次随机选择8条学习到的表达习惯
3. 反完美主义提示 - 添加让回复更自然的指令
4. 情绪随机切换 - 20%概率切换情绪状态
"""
import random
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from astrbot.api import logger


class PersonaPromptOptimizer:
    """
    人格Prompt优化器 - 应用MaiBot的五层人格架构

    五层架构:
    1. 极简核心 (1句话)
    2. 动态表达规则 (8条随机选择)
    3. 实时情绪状态
    4. 行为规划思考 (可选)
    5. 反完美主义指令 (关键!)
    """

    # 反完美主义提示模板
    ANTI_PERFECTIONISM_PROMPTS = [
        "回复时请注意: 平淡一些,不要太有条理,可以有个性。像真人一样自然对话,不必每次都很完美。",
        "说话自然一点,不需要面面俱到,有时候简短随意的回复更真实。",
        "回复时可以有自己的小情绪和个性,不必总是很专业很完美。",
        "不用每次都回复得很周全,有时候随口说说也挺好的。",
    ]

    # 默认情绪状态列表
    DEFAULT_MOODS = [
        '平静', '开心', '好奇', '慵懒', '兴奋',
        '困倦', '活泼', '沉思', '放松', '调皮'
    ]

    def __init__(self, db_manager=None):
        """
        初始化人格优化器

        Args:
            db_manager: 数据库管理器 (用于获取学习到的表达规则)
        """
        self.db = db_manager
        self.current_mood = random.choice(self.DEFAULT_MOODS)
        self.last_mood_change = datetime.now()

    async def build_optimized_persona_prompt(
        self,
        base_persona_core: str,
        group_id: Optional[str] = None,
        include_mood: bool = True,
        include_anti_perfectionism: bool = True,
        expression_rules_count: int = 8
    ) -> str:
        """
        构建优化后的人格Prompt

        Args:
            base_persona_core: 基础人格核心描述 (应该是1句话的简短描述)
            group_id: 群组ID (用于获取群组特定的表达规则)
            include_mood: 是否包含情绪状态
            include_anti_perfectionism: 是否包含反完美主义提示
            expression_rules_count: 要包含的表达规则数量

        Returns:
            优化后的完整人格Prompt
        """
        prompt_parts = []

        # 第1层: 极简人格核心
        core = self._simplify_persona_core(base_persona_core)
        prompt_parts.append(f"你是{core}")

        # 第2层: 动态表达规则
        if self.db and group_id:
            expressions = await self._get_random_expression_rules(
                group_id, expression_rules_count
            )
            if expressions:
                prompt_parts.append("\n你学到的表达习惯:")
                for expr in expressions:
                    prompt_parts.append(f"- {expr}")

        # 第3层: 实时情绪状态
        if include_mood:
            # 20%概率切换情绪
            self._maybe_switch_mood()
            prompt_parts.append(f"\n当前情绪状态: {self.current_mood}")

        # 第4层: 行为规划 (可选,根据需要添加)
        # 这一层通常在具体对话时动态生成

        # 第5层: 反完美主义指令 (关键!)
        if include_anti_perfectionism:
            anti_perfect = random.choice(self.ANTI_PERFECTIONISM_PROMPTS)
            prompt_parts.append(f"\n{anti_perfect}")

        return "\n".join(prompt_parts)

    def _simplify_persona_core(self, persona_description: str) -> str:
        """
        简化人格描述为1句话核心

        MaiBot的关键洞察: 过度详细的人格描述会约束太多,缺乏灵活性
        极简核心反而能让LLM发挥更自然

        Args:
            persona_description: 原始人格描述

        Returns:
            简化后的1句话核心
        """
        if not persona_description:
            return "友好的AI助手"

        # 如果已经很短,直接返回
        if len(persona_description) <= 50:
            return persona_description

        # 尝试提取第一句话作为核心
        sentences = persona_description.replace('\n', '。').split('。')
        if sentences:
            first_sentence = sentences[0].strip()
            if first_sentence and len(first_sentence) >= 5:
                return first_sentence

        # 如果无法提取,截取前50个字符
        return persona_description[:50] + "..."

    async def _get_random_expression_rules(
        self,
        group_id: str,
        count: int = 8
    ) -> List[str]:
        """
        获取随机的表达规则

        MaiBot的关键洞察: 每次随机选择不同的表达规则,保持新鲜感

        Args:
            group_id: 群组ID
            count: 要获取的规则数量

        Returns:
            表达规则列表
        """
        try:
            if not self.db:
                return self._get_default_expression_rules(count)

            # 从数据库获取学习到的表达规则
            # 这里需要调用表达学习服务的方法
            # 暂时使用默认规则
            all_rules = await self._fetch_learned_expressions(group_id)

            if not all_rules:
                return self._get_default_expression_rules(count)

            # 随机选择指定数量的规则
            if len(all_rules) <= count:
                return all_rules

            return random.sample(all_rules, count)

        except Exception as e:
            logger.error(f"获取表达规则失败: {e}")
            return self._get_default_expression_rules(count)

    async def _fetch_learned_expressions(self, group_id: str) -> List[str]:
        """
        从数据库获取学习到的表达规则

        Args:
            group_id: 群组ID

        Returns:
            表达规则列表
        """
        # TODO: 集成表达学习模块后,从数据库读取
        # 暂时返回空列表,使用默认规则
        return []

    def _get_default_expression_rules(self, count: int = 8) -> List[str]:
        """
        获取默认的表达规则

        Args:
            count: 规则数量

        Returns:
            默认表达规则列表
        """
        default_rules = [
            "可以使用口语化的表达方式",
            "适当使用语气词让对话更自然",
            "回复不必太长,简洁有力也很好",
            "可以表达自己的看法和小情绪",
            "不必每次都正式严肃",
            "有时候可以用问句来互动",
            "可以适当使用网络用语",
            "回复时可以有自己的风格",
            "不用总是解释得很详细",
            "偶尔可以调皮一下",
        ]
        return random.sample(default_rules, min(count, len(default_rules)))

    def _maybe_switch_mood(self, probability: float = 0.2):
        """
        概率性切换情绪状态

        MaiBot的关键洞察: 20%概率随机切换情绪,保持对话的自然变化

        Args:
            probability: 切换概率 (默认20%)
        """
        if random.random() < probability:
            old_mood = self.current_mood
            self.current_mood = random.choice(self.DEFAULT_MOODS)
            if self.current_mood != old_mood:
                self.last_mood_change = datetime.now()
                logger.debug(f"情绪切换: {old_mood} -> {self.current_mood}")

    def get_current_mood(self) -> str:
        """获取当前情绪状态"""
        return self.current_mood

    def set_mood(self, mood: str):
        """手动设置情绪状态"""
        self.current_mood = mood
        self.last_mood_change = datetime.now()

    @staticmethod
    def enhance_reply_with_naturalness(reply: str) -> str:
        """
        增强回复的自然感

        应用反完美主义原则,让回复更像真人

        Args:
            reply: 原始回复

        Returns:
            增强后的回复
        """
        # 如果回复太长太完美,适当简化
        if len(reply) > 300:
            # 考虑只保留前几句话
            sentences = reply.split('。')
            if len(sentences) > 5:
                # 保留前3-4句,然后随机决定是否保留更多
                keep_count = random.randint(3, 5)
                reply = '。'.join(sentences[:keep_count]) + '。'

        # 随机决定是否去掉结尾的客套话
        politeness_endings = [
            '如果你还有什么问题',
            '希望这能帮到你',
            '如果需要更多帮助',
            '欢迎随时问我',
        ]
        for ending in politeness_endings:
            if ending in reply and random.random() < 0.5:
                reply = reply.split(ending)[0].strip()

        return reply


class PersonaOptimizationService:
    """
    人格优化服务 - 整合所有人格优化功能

    提供:
    1. 优化人格Prompt构建
    2. 回复自然感增强
    3. 情绪状态管理
    4. 提示词保护 (元指令包装 + 后处理过滤 + 双重检查)
    """

    def __init__(self, db_manager=None, enable_prompt_protection: bool = True):
        """
        初始化人格优化服务

        Args:
            db_manager: 数据库管理器
            enable_prompt_protection: 是否启用提示词保护
        """
        self.optimizer = PersonaPromptOptimizer(db_manager)
        self.enable_prompt_protection = enable_prompt_protection
        self._protection_service = None

    def _get_protection_service(self):
        """延迟加载提示词保护服务"""
        if self._protection_service is None and self.enable_prompt_protection:
            from .prompt_sanitizer import PromptProtectionService
            self._protection_service = PromptProtectionService()
        return self._protection_service

    async def get_optimized_persona(
        self,
        base_persona: str,
        group_id: str = None
    ) -> str:
        """
        获取优化后的人格Prompt

        Args:
            base_persona: 基础人格描述
            group_id: 群组ID

        Returns:
            优化后的人格Prompt
        """
        return await self.optimizer.build_optimized_persona_prompt(
            base_persona_core=base_persona,
            group_id=group_id,
            include_mood=True,
            include_anti_perfectionism=True
        )

    def enhance_reply(self, reply: str) -> str:
        """
        增强回复的自然感

        Args:
            reply: 原始回复

        Returns:
            增强后的回复
        """
        return PersonaPromptOptimizer.enhance_reply_with_naturalness(reply)

    def get_current_mood(self) -> str:
        """获取当前情绪"""
        return self.optimizer.get_current_mood()

    def wrap_diversity_prompts(self, prompts: List[str]) -> str:
        """
        使用元指令包装多样性提示词

        Args:
            prompts: 多样性提示词列表

        Returns:
            包装后的提示词
        """
        protection = self._get_protection_service()
        if protection:
            return protection.wrap_prompts(prompts)
        return "\n".join(prompts)

    def sanitize_response(self, response: str) -> Tuple[str, Dict[str, Any]]:
        """
        消毒LLM回复 - 移除泄露的提示词

        Args:
            response: LLM原始回复

        Returns:
            (消毒后的回复, 处理报告)
        """
        protection = self._get_protection_service()
        if protection:
            return protection.sanitize_response(response)
        return response, {'sanitized': False}

    def process_with_protection(
        self,
        diversity_prompts: List[str],
        llm_response: str
    ) -> Tuple[str, str, Dict[str, Any]]:
        """
        完整的保护流程处理

        Args:
            diversity_prompts: 多样性注入提示词
            llm_response: LLM回复

        Returns:
            (包装后的提示词, 消毒后的回复, 处理报告)
        """
        protection = self._get_protection_service()
        if protection:
            return protection.process_llm_interaction(diversity_prompts, llm_response)
        return "\n".join(diversity_prompts), llm_response, {'protected': False}

    def get_protection_stats(self) -> Optional[Dict[str, Any]]:
        """获取提示词保护统计信息"""
        protection = self._get_protection_service()
        if protection:
            return protection.get_stats()
        return None
