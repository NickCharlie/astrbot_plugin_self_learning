"""
响应多样性管理器 - 解决LLM回复同质化问题
"""
import random
import time
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

from astrbot.api import logger


class ResponseDiversityManager:
    """
    响应多样性管理器

    核心功能：
    1. 动态Temperature调整
    2. 表达模式随机选择
    3. System Prompt多样化
    4. 语言风格轮换机制
    5. 提示词保护（防止多样性注入内容泄露）
    """

    def __init__(self, config, db_manager):
        self.config = config
        self.db_manager = db_manager

        # Temperature动态范围配置
        self.temperature_ranges = {
            'creative': (0.8, 1.2),      # 创意型回复
            'normal': (0.6, 0.9),         # 正常对话
            'precise': (0.3, 0.6),        # 精确分析
            'stable': (0.2, 0.4)          # 稳定输出
        }

        # 语言风格池（定期轮换）
        self.language_styles = [
            "简洁直接，不拐弯抹角",
            "温和友善，语气柔和",
            "活泼开朗，充满活力",
            "幽默风趣，善于调侃",
            "深思熟虑，逻辑清晰",
            "随性自然，口语化表达",
            "文艺范，用词讲究",
            "二次元风格，可爱俏皮"
        ]

        # 当前风格追踪（避免连续重复）
        self.recent_styles = []
        self.max_recent_styles = 3

        # 提示词保护服务（延迟加载）
        self._prompt_protection = None
        self._enable_protection = True  # 默认启用保护

        # 当前使用的风格和模式 (用于保存到数据库)
        self.current_language_style = None
        self.current_response_pattern = None

        # 回复模式池
        self.response_patterns = [
            "直接回答型：直接给出答案，不绕弯子",
            "引导思考型：通过提问引导对方思考",
            "幽默调侃型：用轻松幽默的方式回应",
            "详细解释型：给出详细的解释和背景",
            "简短点评型：用一两句话点评，言简意赅",
            "情感共鸣型：先理解情感，再给出回应"
        ]

        # 表达变化策略
        self.expression_variations = {
            'sentence_style': ['陈述句为主', '疑问句引导', '感叹句增强', '短句连用', '长短句结合'],
            'tone': ['肯定语气', '推测语气', '反问语气', '建议语气', '平铺直叙'],
            'emphasis': ['强调结论', '强调过程', '强调感受', '强调事实', '不作强调']
        }

        logger.info("响应多样性管理器初始化完成")

    def _get_prompt_protection(self):
        """延迟加载提示词保护服务"""
        if self._prompt_protection is None and self._enable_protection:
            try:
                from .prompt_sanitizer import PromptProtectionService
                self._prompt_protection = PromptProtectionService(wrapper_template_index=1)
                logger.info("多样性管理器: 提示词保护服务已加载")
            except Exception as e:
                logger.warning(f"加载提示词保护服务失败: {e}")
                self._enable_protection = False
        return self._prompt_protection

    def _wrap_diversity_content(self, content: str) -> str:
        """
        使用元指令包装多样性注入内容

        Args:
            content: 原始多样性注入内容

        Returns:
            包装后的内容
        """
        protection = self._get_prompt_protection()
        if protection:
            return protection.wrap_prompt(content, register_for_filter=True)
        return content

    def sanitize_llm_response(self, response: str) -> Tuple[str, Dict[str, Any]]:
        """
        消毒LLM回复，移除泄露的多样性提示词

        Args:
            response: LLM原始回复

        Returns:
            (消毒后的回复, 处理报告)
        """
        protection = self._get_prompt_protection()
        if protection:
            return protection.sanitize_response(response)
        return response, {'sanitized': False}

    def get_dynamic_temperature(self, context_type: str = 'normal', randomize: bool = True) -> float:
        """
        获取动态调整的temperature值

        Args:
            context_type: 上下文类型 ('creative', 'normal', 'precise', 'stable')
            randomize: 是否在范围内随机化

        Returns:
            float: temperature值
        """
        try:
            temp_range = self.temperature_ranges.get(context_type, self.temperature_ranges['normal'])

            if randomize:
                # 在范围内随机选择，增加多样性
                temperature = random.uniform(temp_range[0], temp_range[1])
            else:
                # 使用范围中点
                temperature = (temp_range[0] + temp_range[1]) / 2

            logger.debug(f"动态Temperature: {temperature:.2f} (类型: {context_type}, 随机化: {randomize})")
            return round(temperature, 2)

        except Exception as e:
            logger.error(f"获取动态Temperature失败: {e}")
            return 0.7  # 默认值

    def get_random_language_style(self, avoid_recent: bool = True) -> str:
        """
        获取随机语言风格，避免连续重复

        Args:
            avoid_recent: 是否避免最近使用的风格

        Returns:
            str: 语言风格描述
        """
        try:
            available_styles = self.language_styles.copy()

            if avoid_recent and self.recent_styles:
                # 排除最近使用的风格
                available_styles = [s for s in available_styles if s not in self.recent_styles]

            if not available_styles:
                # 如果所有风格都被排除了，重置
                available_styles = self.language_styles.copy()
                self.recent_styles.clear()

            # 随机选择
            selected_style = random.choice(available_styles)

            # 记录使用
            self.recent_styles.append(selected_style)
            if len(self.recent_styles) > self.max_recent_styles:
                self.recent_styles.pop(0)

            logger.debug(f"选择语言风格: {selected_style}")
            return selected_style

        except Exception as e:
            logger.error(f"获取随机语言风格失败: {e}")
            return "自然随性，正常对话"

    def get_random_response_pattern(self) -> str:
        """获取随机回复模式"""
        try:
            pattern = random.choice(self.response_patterns)
            logger.debug(f"选择回复模式: {pattern}")
            return pattern
        except Exception as e:
            logger.error(f"获取随机回复模式失败: {e}")
            return "直接回答型：直接给出答案，不绕弯子"

    def get_expression_variation(self) -> Dict[str, str]:
        """获取表达变化策略"""
        try:
            variation = {
                'sentence_style': random.choice(self.expression_variations['sentence_style']),
                'tone': random.choice(self.expression_variations['tone']),
                'emphasis': random.choice(self.expression_variations['emphasis'])
            }

            logger.debug(f"表达变化策略: {variation}")
            return variation

        except Exception as e:
            logger.error(f"获取表达变化策略失败: {e}")
            return {
                'sentence_style': '长短句结合',
                'tone': '平铺直叙',
                'emphasis': '不作强调'
            }

    async def build_diversity_prompt_injection(self, base_prompt: str,
                                        group_id: str = None,
                                        inject_style: bool = True,
                                        inject_pattern: bool = True,
                                        inject_variation: bool = True,
                                        inject_history: bool = True,
                                        enable_protection: bool = True) -> str:
        """
        构建多样性增强的Prompt注入（带提示词保护）

        Args:
            base_prompt: 原始系统提示词
            group_id: 群组ID (用于获取历史消息)
            inject_style: 是否注入语言风格
            inject_pattern: 是否注入回复模式
            inject_variation: 是否注入表达变化
            inject_history: 是否注入历史Bot消息
            enable_protection: 是否启用提示词保护

        Returns:
            str: 增强后的系统提示词
        """
        try:
            # 收集所有要注入的原始提示词
            raw_prompts = []

            if inject_style:
                style = self.get_random_language_style()
                self.current_language_style = style  # ✅ 保存当前风格
                raw_prompts.append(f"当前语言风格：{style}")

            if inject_pattern:
                pattern = self.get_random_response_pattern()
                self.current_response_pattern = pattern  # ✅ 保存当前模式
                raw_prompts.append(f"推荐回复模式：{pattern}")

            if inject_variation:
                variation = self.get_expression_variation()
                variation_text = (
                    f"表达多样性指引：\n"
                    f"- 句式风格：{variation['sentence_style']}\n"
                    f"- 语气选择：{variation['tone']}\n"
                    f"- 强调重点：{variation['emphasis']}"
                )
                raw_prompts.append(variation_text)

            # 历史消息避重提示
            if inject_history and group_id:
                try:
                    recent_responses = await self.db_manager.get_recent_bot_responses(group_id, limit=5)
                    if recent_responses:
                        history_text = "【你最近的回复历史】\n参考这些回复，避免使用相同的开场白、结尾、句式和表达方式：\n"
                        for i, response in enumerate(recent_responses, 1):
                            # 截取前100字符避免prompt过长
                            truncated = response[:100] + "..." if len(response) > 100 else response
                            history_text += f"{i}. {truncated}\n"

                        history_text += "\n特别注意：\n"
                        history_text += "- 避免重复使用上述回复中的开场白（如\"好的\"、\"明白了\"等）\n"
                        history_text += "- 避免重复使用上述回复中的结尾语\n"
                        history_text += "- 尝试使用与上述回复不同的句式结构\n"
                        history_text += "- 尝试使用不同的表达逻辑结构，允许语言中出现口语化、非标准表达\n"
                        history_text += "- 如果观点相似，也要用不同的表达方式，建议用一定的合理的倒装句、省略句等"

                        raw_prompts.append(history_text)
                        logger.info(f"✅ 已注入 {len(recent_responses)} 条历史Bot消息到多样性提示")
                    else:
                        logger.debug(f"群组 {group_id} 暂无历史Bot消息")
                except Exception as e:
                    logger.warning(f"获取历史Bot消息失败，跳过历史注入: {e}")

            # 添加通用多样性提醒
            diversity_reminder = (
                "多样性提醒：\n"
                "1. 避免使用固定的开场白和结尾语\n"
                "2. 尝试不同的表达方式和句式结构\n"
                "3. 根据对话内容灵活调整语气和风格\n"
                "4. 不要总是遵循相同的逻辑结构\n"
                "5. 允许语言中出现口语化、非标准表达"
            )
            raw_prompts.append(diversity_reminder)

            # 应用提示词保护
            if enable_protection and self._enable_protection:
                protection = self._get_prompt_protection()
                if protection:
                    # 使用元指令包装器包装所有多样性提示词
                    wrapped = protection.wrap_prompts(raw_prompts)
                    enhanced_prompt = base_prompt + "\n\n" + wrapped
                    logger.info(f"✅ 多样性Prompt已保护包装 - 原长度: {len(base_prompt)}, 新长度: {len(enhanced_prompt)}")
                else:
                    # 保护服务不可用，使用原始拼接
                    enhanced_prompt = base_prompt + "\n\n" + "\n\n".join([f"【{i+1}】\n{p}" for i, p in enumerate(raw_prompts)])
                    logger.warning("提示词保护服务不可用，使用原始注入方式")
            else:
                # 未启用保护，直接拼接
                enhanced_prompt = base_prompt + "\n\n" + "\n\n".join([f"【{i+1}】\n{p}" for i, p in enumerate(raw_prompts)])
                logger.debug("未启用提示词保护")

            logger.debug(f"注入的完整内容:\n{enhanced_prompt[len(base_prompt):]}")
            return enhanced_prompt

        except Exception as e:
            logger.error(f"构建多样性Prompt注入失败: {e}")
            return base_prompt

    async def select_diverse_few_shots(self, group_id: str, count: int = 5) -> List[Dict[str, str]]:
        """
        从表达模式库中选择多样化的Few Shots示例

        Args:
            group_id: 群组ID
            count: 选择数量

        Returns:
            List[Dict]: Few Shots示例列表
        """
        try:
            # 从数据库获取所有可用的表达模式
            all_patterns = await self.db_manager.get_all_expression_patterns(group_id)

            if not all_patterns or len(all_patterns) < count:
                logger.warning(f"表达模式数量不足: {len(all_patterns) if all_patterns else 0} < {count}")
                return []

            # 随机打乱顺序
            random.shuffle(all_patterns)

            # 选择前N个（确保多样性）
            selected = all_patterns[:count]

            # 转换为Few Shots格式
            few_shots = []
            for pattern in selected:
                few_shots.append({
                    'context': pattern.get('context', ''),
                    'expression': pattern.get('expression', ''),
                    'quality_score': pattern.get('quality_score', 0.5)
                })

            logger.info(f"为群组 {group_id} 选择了 {len(few_shots)} 个多样化Few Shots")
            return few_shots

        except Exception as e:
            logger.error(f"选择多样化Few Shots失败: {e}")
            return []

    def get_sampling_parameters(self, diversity_level: str = 'medium') -> Dict[str, Any]:
        """
        获取LLM采样参数（temperature, top_p, top_k等）

        Args:
            diversity_level: 多样性级别 ('low', 'medium', 'high')

        Returns:
            Dict: 采样参数
        """
        try:
            if diversity_level == 'low':
                params = {
                    'temperature': 0.5,
                    'top_p': 0.8,
                    'top_k': 40,
                    'frequency_penalty': 0.0,
                    'presence_penalty': 0.0
                }
            elif diversity_level == 'high':
                params = {
                    'temperature': 1.0,
                    'top_p': 0.95,
                    'top_k': 100,
                    'frequency_penalty': 0.8,
                    'presence_penalty': 0.6
                }
            else:  # medium
                params = {
                    'temperature': 0.7,
                    'top_p': 0.9,
                    'top_k': 60,
                    'frequency_penalty': 0.5,
                    'presence_penalty': 0.3
                }

            logger.debug(f"采样参数 (多样性: {diversity_level}): {params}")
            return params

        except Exception as e:
            logger.error(f"获取采样参数失败: {e}")
            return {
                'temperature': 0.7,
                'top_p': 0.9,
                'top_k': 60,
                'frequency_penalty': 0.0,
                'presence_penalty': 0.0
            }

    async def analyze_recent_responses(self, group_id: str, limit: int = 10) -> Dict[str, Any]:
        """
        分析最近的回复，检测同质化程度

        Args:
            group_id: 群组ID
            limit: 分析最近N条回复

        Returns:
            Dict: 同质化分析结果
        """
        try:
            # 从数据库获取最近的回复记录
            recent_responses = await self.db_manager.get_recent_bot_responses(group_id, limit)

            if not recent_responses:
                return {
                    'homogeneity_score': 0.0,
                    'warning': 'insufficient_data',
                    'suggestion': '数据不足，无法分析'
                }

            # 简单的同质化检测：检查开头和结尾的重复
            openings = [resp[:10] for resp in recent_responses]
            endings = [resp[-10:] for resp in recent_responses]

            # 计算重复率
            opening_unique_ratio = len(set(openings)) / len(openings)
            ending_unique_ratio = len(set(endings)) / len(endings)

            # 同质化得分 (0=完全多样, 1=完全同质)
            homogeneity_score = 1.0 - (opening_unique_ratio + ending_unique_ratio) / 2

            analysis = {
                'homogeneity_score': round(homogeneity_score, 2),
                'opening_diversity': round(opening_unique_ratio, 2),
                'ending_diversity': round(ending_unique_ratio, 2),
                'sample_size': len(recent_responses)
            }

            # 生成建议
            if homogeneity_score > 0.7:
                analysis['warning'] = 'high_homogeneity'
                analysis['suggestion'] = '检测到高度同质化，建议增加Temperature和启用多样性增强'
            elif homogeneity_score > 0.4:
                analysis['warning'] = 'medium_homogeneity'
                analysis['suggestion'] = '存在一定同质化，建议启用语言风格轮换'
            else:
                analysis['warning'] = 'low_homogeneity'
                analysis['suggestion'] = '多样性良好，保持当前设置'

            logger.info(f"群组 {group_id} 同质化分析: {analysis}")
            return analysis

        except Exception as e:
            logger.error(f"分析回复同质化失败: {e}")
            return {
                'homogeneity_score': 0.0,
                'warning': 'analysis_error',
                'suggestion': '分析失败'
            }

    def create_anti_repetition_instruction(self) -> str:
        """创建反重复指令（添加到System Prompt中）"""
        instruction = """
【防止回复重复的重要指示】
- 每次回复都要有新鲜感，避免使用固定模板
- 开场白和结尾要多样化，不要总是"好的"、"明白了"、"那么"等
- 同样的意思，尝试用不同的表达方式
- 避免重复使用相同的句式结构和逻辑顺序
- 允许语言中的不完美和口语化，更像真人
        """
        return instruction.strip()

    def get_current_style(self) -> Optional[str]:
        """
        获取当前使用的语言风格

        Returns:
            str: 当前语言风格，如果未设置则返回None
        """
        return self.current_language_style

    def get_current_pattern(self) -> Optional[str]:
        """
        获取当前使用的回复模式

        Returns:
            str: 当前回复模式，如果未设置则返回None
        """
        return self.current_response_pattern
