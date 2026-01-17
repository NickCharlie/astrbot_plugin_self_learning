"""
Guardrails AI 管理器
用于管理 LLM 的结构化输出,确保数据格式正确且符合约束
"""
from typing import Dict, List, Optional, Any, Type
from pydantic import BaseModel, Field, field_validator
from guardrails import Guard
from astrbot.api import logger


# ============================================================
# Pydantic 模型定义 - 用于心理状态分析
# ============================================================

class PsychologicalStateTransition(BaseModel):
    """
    心理状态转换结果模型
    """
    new_state: str = Field(
        description="新的心理状态名称(中文),例如: 愉悦、疲惫、专注等"
    )
    confidence: Optional[float] = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="置信度(0-1)",
    )
    reason: Optional[str] = Field(
        default="",
        description="状态转换的原因说明"
    )

    @field_validator('new_state')
    @classmethod
    def validate_state_name(cls, v: str) -> str:
        """验证状态名称"""
        if not v or len(v) > 20:
            raise ValueError("状态名称必须是1-20个字符")
        return v.strip()


# ============================================================
# Pydantic 模型定义 - 用于对话目标分析
# ============================================================

class GoalAnalysisResult(BaseModel):
    """
    对话目标分析结果模型
    """
    goal_type: str = Field(
        description="对话目标类型,例如: emotional_support, casual_chat等"
    )
    topic: str = Field(
        description="对话话题,简短描述(1-20字)"
    )
    confidence: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="置信度(0-1)"
    )
    reasoning: Optional[str] = Field(
        default="",
        description="分析理由"
    )

    @field_validator('goal_type')
    @classmethod
    def validate_goal_type(cls, v: str) -> str:
        """验证目标类型"""
        if not v or len(v) > 50:
            raise ValueError("目标类型必须是1-50个字符")
        return v.strip()

    @field_validator('topic')
    @classmethod
    def validate_topic(cls, v: str) -> str:
        """验证话题"""
        if not v or len(v) > 100:
            raise ValueError("话题必须是1-100个字符")
        return v.strip()


class ConversationIntentAnalysis(BaseModel):
    """
    对话意图分析结果模型
    """
    goal_switch_needed: bool = Field(
        default=False,
        description="是否需要切换目标类型"
    )
    new_goal_type: Optional[str] = Field(
        default=None,
        description="新的目标类型(如果需要切换)"
    )
    new_topic: Optional[str] = Field(
        default=None,
        description="新的话题(如果需要切换)"
    )
    topic_completed: bool = Field(
        default=False,
        description="当前话题是否已完成"
    )
    stage_completed: bool = Field(
        default=False,
        description="当前阶段是否已完成"
    )
    stage_adjustment_needed: bool = Field(
        default=False,
        description="是否需要调整当前阶段"
    )
    suggested_stage: Optional[str] = Field(
        default=None,
        description="建议的下一阶段任务"
    )
    completion_signals: int = Field(
        default=0,
        ge=0,
        description="检测到的完成信号数量"
    )
    user_engagement: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="用户参与度(0-1)"
    )
    reasoning: Optional[str] = Field(
        default="",
        description="分析理由"
    )


# ============================================================
# Pydantic 模型定义 - 用于社交关系分析
# ============================================================

class RelationChange(BaseModel):
    """
    单个关系类型的变化
    """
    relation_type: str = Field(
        description="关系类型名称,例如: 挚友、同事、陌生关系等"
    )
    value_delta: float = Field(
        ge=-1.0,
        le=1.0,
        description="关系强度变化量,范围[-1.0, 1.0]"
    )
    reason: Optional[str] = Field(
        default="",
        description="变化原因"
    )

    @field_validator('relation_type')
    @classmethod
    def validate_relation_type(cls, v: str) -> str:
        """验证关系类型名称"""
        if not v or len(v) > 30:
            raise ValueError("关系类型名称必须是1-30个字符")
        return v.strip()


class SocialRelationAnalysis(BaseModel):
    """
    社交关系分析结果模型
    """
    relations: List[RelationChange] = Field(
        description="受影响的关系类型及变化量列表",
        min_length=0,
        max_length=5
    )
    overall_sentiment: Optional[str] = Field(
        default="neutral",
        description="整体情感倾向: positive/neutral/negative"
    )

    @field_validator('relations')
    @classmethod
    def validate_relations_count(cls, v: List[RelationChange]) -> List[RelationChange]:
        """限制关系数量"""
        if len(v) > 5:
            logger.warning(f"关系数量过多({len(v)}),截取前5个")
            return v[:5]
        return v


# ============================================================
# Guardrails 管理器
# ============================================================

class GuardrailsManager:
    """
    Guardrails AI 管理器

    功能:
    1. 管理不同数据模型的 Guard 实例
    2. 提供高性能的 LLM 调用接口
    3. 自动验证和修复 LLM 输出
    4. 支持重试和错误处理
    """

    def __init__(self, max_reasks: int = 1):
        """
        初始化 Guardrails 管理器

        Args:
            max_reasks: 最大重试次数(默认1次,保持高性能)
        """
        self.max_reasks = max_reasks

        # 创建不同用途的 Guard 实例
        self._state_guard: Optional[Guard] = None
        self._relation_guard: Optional[Guard] = None
        self._goal_analysis_guard: Optional[Guard] = None
        self._intent_analysis_guard: Optional[Guard] = None

        logger.info(f"[Guardrails] 管理器初始化完成 (max_reasks={max_reasks})")

    def get_state_transition_guard(self) -> Guard:
        """
        获取心理状态转换的 Guard 实例

        Returns:
            Guard 实例
        """
        if self._state_guard is None:
            self._state_guard = Guard.for_pydantic(
                output_class=PsychologicalStateTransition,
                # 不使用额外的验证器,保持高性能
            )
            logger.debug("[Guardrails] 心理状态转换 Guard 已创建")

        return self._state_guard

    def get_relation_analysis_guard(self) -> Guard:
        """
        获取社交关系分析的 Guard 实例

        Returns:
            Guard 实例
        """
        if self._relation_guard is None:
            self._relation_guard = Guard.for_pydantic(
                output_class=SocialRelationAnalysis,
            )
            logger.debug("[Guardrails] 社交关系分析 Guard 已创建")

        return self._relation_guard

    async def parse_state_transition(
        self,
        llm_callable,
        prompt: str,
        model: str = "gpt-4o",
        **kwargs
    ) -> Optional[PsychologicalStateTransition]:
        """
        解析心理状态转换结果

        Args:
            llm_callable: LLM 调用函数(应该返回文本)
            prompt: 提示词
            model: 模型名称
            **kwargs: 其他参数

        Returns:
            PsychologicalStateTransition 对象,失败返回 None
        """
        try:
            guard = self.get_state_transition_guard()

            # 使用 JSON 模式获取结构化输出
            # 为提示词添加 JSON 输出要求
            enhanced_prompt = f"""{prompt}

请以 JSON 格式返回结果,格式如下:
{{
    "new_state": "新状态名称",
    "confidence": 0.8,
    "reason": "转换原因"
}}
"""

            # 调用 LLM(通过用户提供的 callable)
            response_text = await llm_callable(enhanced_prompt, model=model, **kwargs)

            # 使用 Guard 验证
            result = guard.parse(response_text)

            if result.validation_passed:
                logger.debug(f"✅ [Guardrails] 心理状态解析成功: {result.validated_output.new_state}")
                return result.validated_output
            else:
                logger.warning(f"⚠️ [Guardrails] 心理状态验证失败: {result.validation_summaries}")
                return None

        except Exception as e:
            logger.error(f"❌ [Guardrails] 心理状态解析失败: {e}", exc_info=True)
            return None

    async def parse_relation_analysis(
        self,
        llm_callable,
        prompt: str,
        model: str = "gpt-4o",
        **kwargs
    ) -> Optional[SocialRelationAnalysis]:
        """
        解析社交关系分析结果

        Args:
            llm_callable: LLM 调用函数
            prompt: 提示词
            model: 模型名称
            **kwargs: 其他参数

        Returns:
            SocialRelationAnalysis 对象,失败返回 None
        """
        try:
            guard = self.get_relation_analysis_guard()

            # 增强提示词
            enhanced_prompt = f"""{prompt}

请以 JSON 格式返回结果,格式如下:
{{
    "relations": [
        {{"relation_type": "关系类型1", "value_delta": 0.05, "reason": "原因"}},
        {{"relation_type": "关系类型2", "value_delta": 0.03, "reason": "原因"}}
    ],
    "overall_sentiment": "positive"
}}

注意:
- relations 最多返回5个
- value_delta 范围 [-1.0, 1.0]
- overall_sentiment 可选值: positive/neutral/negative
"""

            # 调用 LLM
            response_text = await llm_callable(enhanced_prompt, model=model, **kwargs)

            # 使用 Guard 验证
            result = guard.parse(response_text)

            if result.validation_passed:
                relation_count = len(result.validated_output.relations)
                logger.debug(f"✅ [Guardrails] 社交关系解析成功: {relation_count}个关系")
                return result.validated_output
            else:
                logger.warning(f"⚠️ [Guardrails] 社交关系验证失败: {result.validation_summaries}")
                return None

        except Exception as e:
            logger.error(f"❌ [Guardrails] 社交关系解析失败: {e}", exc_info=True)
            return None

    def get_goal_analysis_guard(self) -> Guard:
        """
        获取对话目标分析的 Guard 实例

        Returns:
            Guard 实例
        """
        if self._goal_analysis_guard is None:
            self._goal_analysis_guard = Guard.for_pydantic(
                output_class=GoalAnalysisResult,
            )
            logger.debug("[Guardrails] 对话目标分析 Guard 已创建")

        return self._goal_analysis_guard

    def get_intent_analysis_guard(self) -> Guard:
        """
        获取对话意图分析的 Guard 实例

        Returns:
            Guard 实例
        """
        if self._intent_analysis_guard is None:
            self._intent_analysis_guard = Guard.for_pydantic(
                output_class=ConversationIntentAnalysis,
            )
            logger.debug("[Guardrails] 对话意图分析 Guard 已创建")

        return self._intent_analysis_guard

    async def parse_goal_analysis(
        self,
        llm_callable,
        prompt: str,
        model: str = "gpt-4o",
        **kwargs
    ) -> Optional[GoalAnalysisResult]:
        """
        解析对话目标分析结果

        Args:
            llm_callable: LLM 调用函数
            prompt: 提示词
            model: 模型名称
            **kwargs: 其他参数

        Returns:
            GoalAnalysisResult 对象,失败返回 None
        """
        try:
            guard = self.get_goal_analysis_guard()

            # 增强提示词
            enhanced_prompt = f"""{prompt}

请以 JSON 格式返回结果,格式如下:
{{
    "goal_type": "emotional_support",
    "topic": "工作压力",
    "confidence": 0.85,
    "reasoning": "简短理由"
}}

注意:
- goal_type 必须是英文蛇形命名(如 emotional_support, casual_chat)
- topic 简短描述(1-20字)
- confidence 范围 [0.0, 1.0]
"""

            # 调用 LLM
            response_text = await llm_callable(enhanced_prompt, model=model, **kwargs)

            # 使用 Guard 验证
            result = guard.parse(response_text)

            if result.validation_passed:
                logger.debug(f"✅ [Guardrails] 对话目标解析成功: {result.validated_output.goal_type}")
                return result.validated_output
            else:
                logger.warning(f"⚠️ [Guardrails] 对话目标验证失败: {result.validation_summaries}")
                return None

        except Exception as e:
            logger.error(f"❌ [Guardrails] 对话目标解析失败: {e}", exc_info=True)
            return None

    async def parse_intent_analysis(
        self,
        llm_callable,
        prompt: str,
        model: str = "gpt-4o",
        **kwargs
    ) -> Optional[ConversationIntentAnalysis]:
        """
        解析对话意图分析结果

        Args:
            llm_callable: LLM 调用函数
            prompt: 提示词
            model: 模型名称
            **kwargs: 其他参数

        Returns:
            ConversationIntentAnalysis 对象,失败返回 None
        """
        try:
            guard = self.get_intent_analysis_guard()

            # 增强提示词
            enhanced_prompt = f"""{prompt}

请以 JSON 格式返回结果,格式如下:
{{
    "goal_switch_needed": false,
    "new_goal_type": null,
    "new_topic": null,
    "topic_completed": false,
    "stage_completed": true,
    "stage_adjustment_needed": false,
    "suggested_stage": "下一阶段任务",
    "completion_signals": 1,
    "user_engagement": 0.8,
    "reasoning": "简短理由(20字内)"
}}

注意:
- goal_switch_needed/topic_completed/stage_completed/stage_adjustment_needed 为 boolean 类型
- new_goal_type/new_topic/suggested_stage 为字符串或 null
- completion_signals 为非负整数
- user_engagement 范围 [0.0, 1.0]
"""

            # 调用 LLM
            response_text = await llm_callable(enhanced_prompt, model=model, **kwargs)

            # 使用 Guard 验证
            result = guard.parse(response_text)

            if result.validation_passed:
                logger.debug(f"✅ [Guardrails] 对话意图解析成功")
                return result.validated_output
            else:
                logger.warning(f"⚠️ [Guardrails] 对话意图验证失败: {result.validation_summaries}")
                return None

        except Exception as e:
            logger.error(f"❌ [Guardrails] 对话意图解析失败: {e}", exc_info=True)
            return None

    def parse_json_direct(
        self,
        response_text: str,
        model_class: Type[BaseModel]
    ) -> Optional[BaseModel]:
        """
        直接解析 JSON 文本(不调用 LLM)

        Args:
            response_text: JSON 文本
            model_class: Pydantic 模型类

        Returns:
            模型实例,失败返回 None
        """
        try:
            guard = Guard.for_pydantic(output_class=model_class)
            result = guard.parse(response_text)

            if result.validation_passed:
                return result.validated_output
            else:
                logger.warning(f"⚠️ [Guardrails] JSON 验证失败: {result.validation_summaries}")
                return None

        except Exception as e:
            logger.error(f"❌ [Guardrails] JSON 解析失败: {e}")
            return None

    def validate_and_clean_json(
        self,
        response_text: str,
        expected_type: str = "auto"
    ) -> Optional[Any]:
        """
        通用 JSON 验证和清洗 - 适用于所有 LLM 返回

        Args:
            response_text: LLM 返回的文本（可能包含 Markdown、代码块等）
            expected_type: 期望的类型 ("object", "array", "auto")

        Returns:
            清洗后的 JSON 对象/数组，失败返回 None
        """
        import json
        import re

        try:
            # 检查输入是否为空
            if not response_text:
                logger.error(f"❌ [Guardrails] 输入为空，无法解析 JSON")
                return None

            # 1. 移除 Markdown 代码块标记
            cleaned_text = response_text.strip()

            # 记录原始响应长度用于调试
            logger.debug(f"🔍 [Guardrails] 原始响应长度: {len(response_text)}, 清理后长度: {len(cleaned_text)}")

            # 移除 ```json 和 ``` 标记
            if cleaned_text.startswith("```json"):
                cleaned_text = cleaned_text[7:]
            elif cleaned_text.startswith("```"):
                cleaned_text = cleaned_text[3:]

            if cleaned_text.endswith("```"):
                cleaned_text = cleaned_text[:-3]

            cleaned_text = cleaned_text.strip()

            # 2. 尝试提取 JSON 部分（处理 LLM 可能在 JSON 前后加说明的情况）
            # 匹配最外层的 { } 或 [ ]
            json_pattern = r'(\{(?:[^{}]|(?:\{(?:[^{}]|(?:\{[^{}]*\}))*\}))*\})'
            array_pattern = r'(\[(?:[^\[\]]|(?:\[(?:[^\[\]]|(?:\[[^\[\]]*\]))*\]))*\])'

            json_match = re.search(json_pattern, cleaned_text, re.DOTALL)
            array_match = re.search(array_pattern, cleaned_text, re.DOTALL)

            if expected_type == "object" or (expected_type == "auto" and json_match):
                if json_match:
                    cleaned_text = json_match.group(1)
            elif expected_type == "array" or (expected_type == "auto" and array_match):
                if array_match:
                    cleaned_text = array_match.group(1)

            # 3. 尝试解析 JSON
            parsed = json.loads(cleaned_text)

            logger.debug(f"✅ [Guardrails] JSON 验证成功，类型: {type(parsed).__name__}")
            return parsed

        except json.JSONDecodeError as e:
            # 显示响应预览用于调试
            preview = cleaned_text[:200] if len(cleaned_text) > 200 else cleaned_text
            logger.warning(f"⚠️ [Guardrails] JSON 解析失败: {e}，尝试修复...")
            logger.debug(f"🔍 [Guardrails] 响应预览: {preview}")

            # 尝试修复常见的 JSON 错误
            try:
                # 替换单引号为双引号（Python dict 风格）
                fixed_text = cleaned_text.replace("'", '"')

                # 移除尾随逗号
                fixed_text = re.sub(r',\s*}', '}', fixed_text)
                fixed_text = re.sub(r',\s*]', ']', fixed_text)

                parsed = json.loads(fixed_text)
                logger.info(f"✅ [Guardrails] JSON 修复成功")
                return parsed

            except Exception as fix_error:
                logger.error(f"❌ [Guardrails] JSON 修复失败: {fix_error}")
                return None

        except Exception as e:
            logger.error(f"❌ [Guardrails] JSON 验证异常: {e}")
            return None

    async def validate_llm_response(
        self,
        llm_callable,
        prompt: str,
        expected_format: str = "json",
        model: str = "gpt-4o",
        **kwargs
    ) -> Optional[Any]:
        """
        通用 LLM 响应验证器 - 包装所有 LLM 调用

        Args:
            llm_callable: LLM 调用函数
            prompt: 提示词
            expected_format: 期望的格式 ("json", "text", "list", "object")
            model: 模型名称
            **kwargs: 其他参数

        Returns:
            验证后的响应内容，失败返回 None
        """
        try:
            # 增强提示词 - 明确要求输出格式
            if expected_format == "json":
                enhanced_prompt = f"""{prompt}

请以 JSON 格式返回结果，不要包含任何额外说明。"""
            elif expected_format in ["list", "array"]:
                enhanced_prompt = f"""{prompt}

请以 JSON 数组格式返回结果，例如: ["item1", "item2"]"""
            elif expected_format == "object":
                enhanced_prompt = f"""{prompt}

请以 JSON 对象格式返回结果，例如: {{"key": "value"}}"""
            else:
                enhanced_prompt = prompt

            # 调用 LLM
            response_text = await llm_callable(enhanced_prompt, model=model, **kwargs)

            if not response_text:
                logger.warning("⚠️ [Guardrails] LLM 返回为空")
                return None

            # 根据期望格式验证
            if expected_format in ["json", "list", "array", "object"]:
                result = self.validate_and_clean_json(
                    response_text,
                    expected_type="array" if expected_format in ["list", "array"] else "object"
                )
                return result
            else:
                # 纯文本，直接返回
                return response_text.strip()

        except Exception as e:
            logger.error(f"❌ [Guardrails] LLM 响应验证失败: {e}", exc_info=True)
            return None


# ============================================================
# 全局单例
# ============================================================

# 使用 max_reasks=1 保持高性能
_guardrails_manager: Optional[GuardrailsManager] = None


def get_guardrails_manager(max_reasks: int = 1) -> GuardrailsManager:
    """
    获取全局 Guardrails 管理器单例

    Args:
        max_reasks: 最大重试次数

    Returns:
        GuardrailsManager 实例
    """
    global _guardrails_manager

    if _guardrails_manager is None:
        _guardrails_manager = GuardrailsManager(max_reasks=max_reasks)

    return _guardrails_manager
