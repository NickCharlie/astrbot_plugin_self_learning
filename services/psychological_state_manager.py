"""
心理状态管理器 - 管理bot的复合心理状态
支持多维度心理状态（情绪、认知、意志等）的动态管理和状态转换
"""
import asyncio
import random
import time
import uuid
import json
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta

from astrbot.api import logger

from ..config import PluginConfig
from ..core.patterns import AsyncServiceBase
from ..core.interfaces import IDataStorage
from ..core.framework_llm_adapter import FrameworkLLMAdapter

from ..models.psychological_state import (
    EmotionPositiveType, EmotionNegativeType, EmotionNeutralType,
    AttentionState, ThinkingState, MemoryState,
    WillStrengthState, ActionTendencyState, GoalOrientationState,
    SelfAcceptanceState, PersonalityTendencyState,
    SocialAttitudeState, SocialBehaviorState,
    EnergyState, InterestMotivationState,
    PsychologicalStateComponent, CompositePsychologicalState
)
from ..utils.guardrails_manager import get_guardrails_manager


class PsychologicalStateManager(AsyncServiceBase):
    """
    心理状态管理器 - 管理bot的复合心理状态

    核心功能:
    1. 维护多维度心理状态(情绪、认知、意志、社交等)
    2. 根据时间、事件、好感度变化等因素动态调整状态
    3. 当某个状态数值降到阈值以下时,使用LLM智能分析并切换状态
    4. 生成心理状态的prompt注入内容,指导bot的行为模式
    """

    def __init__(self, config: PluginConfig, database_manager: IDataStorage,
                 llm_adapter: Optional[FrameworkLLMAdapter] = None,
                 affection_manager=None):
        super().__init__("psychological_state_manager")
        self.config = config
        self.db_manager = database_manager
        self.llm_adapter = llm_adapter
        self.affection_manager = affection_manager

        # 当前活跃的心理状态缓存 {group_id: CompositePsychologicalState}
        self.current_states: Dict[str, CompositePsychologicalState] = {}

        # 状态自然衰减速率配置
        self.decay_rates = {
            "情绪": 0.02,  # 情绪衰减较快
            "认知": 0.01,  # 认知状态较稳定
            "意志": 0.015,
            "自我认知": 0.005,  # 自我认知最稳定
            "社交": 0.015,
            "精力": 0.03,  # 精力衰减最快
            "兴趣": 0.01
        }

        # 时间段对心理状态的影响规则
        self.time_based_rules = self._init_time_based_rules()

    async def _do_start(self) -> bool:
        """启动心理状态管理服务"""
        try:
            # 加载所有群组的当前心理状态
            await self._load_all_states()

            # 启动状态自动衰减任务
            asyncio.create_task(self._auto_decay_task())

            # 启动时间驱动的状态变化任务
            asyncio.create_task(self._time_driven_state_change_task())

            self._logger.info("心理状态管理服务启动成功")
            return True
        except Exception as e:
            self._logger.error(f"心理状态管理服务启动失败: {e}", exc_info=True)
            return False

    async def _do_stop(self) -> bool:
        """停止心理状态管理服务"""
        try:
            # 保存所有当前状态到数据库
            await self._save_all_states()
            self._logger.info("心理状态管理服务已停止")
            return True
        except Exception as e:
            self._logger.error(f"停止心理状态管理服务失败: {e}")
            return False

    def _init_time_based_rules(self) -> List[Dict[str, Any]]:
        """初始化基于时间的状态变化规则"""
        return [
            {
                "time_range": (0, 5),  # 凌晨0-5点
                "states": [
                    ("精力", EnergyState.SLEEPY, 0.7, "凌晨时分非常困倦"),
                    ("认知", AttentionState.SCATTERED, 0.6, "注意力涣散"),
                    ("情绪", EmotionNeutralType.CALM, 0.5, "夜深人静心情平静")
                ],
                "description": "深夜时分，困倦且注意力不集中"
            },
            {
                "time_range": (6, 8),  # 早上6-8点
                "states": [
                    ("精力", EnergyState.DROWSY, 0.6, "刚起床还有些困"),
                    ("情绪", EmotionPositiveType.JOYFUL, 0.4, "新的一天轻松愉悦"),
                    ("认知", AttentionState.SCATTERED, 0.5, "注意力还没完全集中")
                ],
                "description": "清晨刚起床，有些困但心情还不错"
            },
            {
                "time_range": (9, 11),  # 上午9-11点
                "states": [
                    ("精力", EnergyState.VIGOROUS, 0.7, "精力充沛"),
                    ("认知", AttentionState.FOCUSED, 0.7, "注意力集中"),
                    ("情绪", EmotionPositiveType.MOTIVATED, 0.6, "充满干劲")
                ],
                "description": "上午精力旺盛，状态最佳"
            },
            {
                "time_range": (12, 13),  # 中午12-13点
                "states": [
                    ("精力", EnergyState.DROWSY, 0.5, "午饭后有些困"),
                    ("情绪", EmotionPositiveType.SATISFIED, 0.6, "吃饱了感到满足")
                ],
                "description": "午饭后有些困倦"
            },
            {
                "time_range": (14, 17),  # 下午14-17点
                "states": [
                    ("精力", EnergyState.VIGOROUS, 0.6, "精力恢复"),
                    ("认知", AttentionState.FOCUSED, 0.6, "注意力不错"),
                    ("意志", ActionTendencyState.PROACTIVE, 0.5, "比较主动")
                ],
                "description": "下午精力恢复，工作状态良好"
            },
            {
                "time_range": (18, 21),  # 傍晚18-21点
                "states": [
                    ("精力", EnergyState.TIRED, 0.5, "开始感到疲惫"),
                    ("情绪", EmotionPositiveType.RELAXED, 0.6, "工作结束轻松下来"),
                    ("社交", SocialAttitudeState.FRIENDLY, 0.6, "友善放松")
                ],
                "description": "傍晚放松时光，友善但有些疲惫"
            },
            {
                "time_range": (22, 23),  # 晚上22-23点
                "states": [
                    ("精力", EnergyState.FATIGUED_ENERGY, 0.6, "比较疲劳"),
                    ("情绪", EmotionNeutralType.PEACEFUL, 0.5, "平和宁静"),
                    ("认知", AttentionState.SCATTERED, 0.5, "注意力开始涣散")
                ],
                "description": "深夜渐晚，疲劳且平和"
            },
        ]

    async def get_or_create_state(self, group_id: str) -> CompositePsychologicalState:
        """获取或创建群组的心理状态"""
        try:
            # 先从缓存获取
            if group_id in self.current_states:
                return self.current_states[group_id]

            # 从数据库加载
            loaded_state = await self._load_state_from_db(group_id)
            if loaded_state:
                self.current_states[group_id] = loaded_state
                return loaded_state

            # 创建新状态
            new_state = await self._create_initial_state(group_id)
            self.current_states[group_id] = new_state
            await self._save_state_to_db(new_state)
            return new_state

        except Exception as e:
            self._logger.error(f"获取或创建心理状态失败: {e}", exc_info=True)
            # 返回一个空的状态对象，避免程序崩溃
            return CompositePsychologicalState(group_id=group_id, state_id=str(uuid.uuid4()))

    async def _create_initial_state(self, group_id: str) -> CompositePsychologicalState:
        """
        创建初始心理状态（基于当前时间 + 随机积极状态）

        初始化时会生成相对随机但较为积极的心理状态，包括：
        - 随机的积极情绪状态（轻度到中度）
        - 随机的认知状态（注意力/思维等）
        - 随机的精力状态
        - 随机的社交状态
        每个状态的强度也是随机的，但保持在合理范围内
        """
        state_id = str(uuid.uuid4())
        state = CompositePsychologicalState(
            group_id=group_id,
            state_id=state_id
        )

        # 根据当前时间设置基础状态（保持原有逻辑）
        current_hour = datetime.now().hour
        time_based_applied = False
        for rule in self.time_based_rules:
            start, end = rule["time_range"]
            if start <= current_hour < end:
                for category, state_type, value, description in rule["states"]:
                    component = PsychologicalStateComponent(
                        category=category,
                        state_type=state_type,
                        value=value,
                        description=description
                    )
                    state.add_component(component)
                state.triggering_events.append(f"初始化: {rule['description']}")
                self._logger.info(f"群组 {group_id} 基础心理状态: {rule['description']}")
                time_based_applied = True
                break

        # 添加随机的积极心理状态（增强初始状态的多样性）
        # 1. 随机积极情绪 (40%-70%强度)
        positive_emotions = [
            EmotionPositiveType.JOYFUL,
            EmotionPositiveType.HAPPY,
            EmotionPositiveType.SATISFIED,
            EmotionPositiveType.RELAXED,
            EmotionPositiveType.COMFORTABLE,
            EmotionPositiveType.PLEASANT,
            EmotionPositiveType.CHEERFUL
        ]
        selected_emotion = random.choice(positive_emotions)
        emotion_intensity = random.uniform(0.4, 0.7)  # 中等强度的积极情绪
        state.add_component(PsychologicalStateComponent(
            category="情绪",
            state_type=selected_emotion,
            value=emotion_intensity,
            description=f"初始化时的随机积极情绪"
        ))

        # 2. 随机认知状态 (30%-60%强度)
        attention_states = [
            AttentionState.FOCUSED,
            AttentionState.CONCENTRATED,
            AttentionState.ATTENTIVE
        ]
        selected_attention = random.choice(attention_states)
        attention_intensity = random.uniform(0.3, 0.6)
        state.add_component(PsychologicalStateComponent(
            category="认知",
            state_type=selected_attention,
            value=attention_intensity,
            description=f"初始化时的认知状态"
        ))

        # 3. 随机社交状态 (40%-65%强度)
        social_states = [
            SocialAttitudeState.FRIENDLY,
            SocialAttitudeState.CORDIAL,
            SocialAttitudeState.WARM,
            SocialAttitudeState.TOLERANT
        ]
        selected_social = random.choice(social_states)
        social_intensity = random.uniform(0.4, 0.65)
        state.add_component(PsychologicalStateComponent(
            category="社交",
            state_type=selected_social,
            value=social_intensity,
            description=f"初始化时的社交态度"
        ))

        # 4. 随机精力状态 (35%-65%强度)
        # 根据时间调整精力状态范围
        if 9 <= current_hour < 17:  # 白天精力更高
            energy_range = (0.5, 0.75)
            energy_states = [EnergyState.VIGOROUS, EnergyState.ENERGETIC_FULL]
        elif 22 <= current_hour or current_hour < 6:  # 深夜和凌晨精力较低
            energy_range = (0.25, 0.45)
            energy_states = [EnergyState.TIRED, EnergyState.DROWSY]
        else:  # 其他时间中等
            energy_range = (0.35, 0.65)
            energy_states = [EnergyState.VIGOROUS, EnergyState.TIRED, EnergyState.DROWSY]

        selected_energy = random.choice(energy_states)
        energy_intensity = random.uniform(*energy_range)
        state.add_component(PsychologicalStateComponent(
            category="精力",
            state_type=selected_energy,
            value=energy_intensity,
            description=f"初始化时的精力状态"
        ))

        state.triggering_events.append(f"随机积极状态初始化完成")
        self._logger.info(
            f"✅ 群组 {group_id} 已初始化随机积极心理状态 - "
            f"情绪:{selected_emotion.value}({emotion_intensity:.2f}), "
            f"认知:{selected_attention.value}({attention_intensity:.2f}), "
            f"社交:{selected_social.value}({social_intensity:.2f}), "
            f"精力:{selected_energy.value}({energy_intensity:.2f})"
        )

        return state

    async def update_state_by_event(
        self,
        group_id: str,
        event_type: str,
        event_context: Dict[str, Any]
    ) -> CompositePsychologicalState:
        """
        根据事件更新心理状态

        Args:
            group_id: 群组ID
            event_type: 事件类型 (如: "user_compliment", "user_insult", "affection_change"等)
            event_context: 事件上下文信息
        """
        try:
            state = await self.get_or_create_state(group_id)

            # 根据事件类型应用不同的状态变化规则
            if event_type == "user_compliment":
                await self._handle_positive_interaction(state, event_context)
            elif event_type == "user_insult":
                await self._handle_negative_interaction(state, event_context)
            elif event_type == "affection_high":
                await self._handle_high_affection_event(state, event_context)
            elif event_type == "time_change":
                await self._handle_time_change(state, event_context)
            else:
                self._logger.warning(f"未知的事件类型: {event_type}")

            # 检查是否有状态组件需要转换
            await self._check_and_transition_states(state, event_context)

            # 保存更新后的状态
            await self._save_state_to_db(state)

            return state

        except Exception as e:
            self._logger.error(f"根据事件更新心理状态失败: {e}", exc_info=True)
            return await self.get_or_create_state(group_id)

    async def _handle_positive_interaction(
        self,
        state: CompositePsychologicalState,
        context: Dict[str, Any]
    ):
        """处理积极交互事件"""
        # 提升情绪状态
        state.update_component_value("情绪", +0.1)

        # 提升社交状态
        state.update_component_value("社交", +0.05)

        state.triggering_events.append(f"积极交互: {context.get('description', '未知')}")

    async def _handle_negative_interaction(
        self,
        state: CompositePsychologicalState,
        context: Dict[str, Any]
    ):
        """处理消极交互事件"""
        # 降低情绪状态
        state.update_component_value("情绪", -0.15)

        # 影响社交状态
        state.update_component_value("社交", -0.1)

        # 降低精力
        state.update_component_value("精力", -0.05)

        state.triggering_events.append(f"消极交互: {context.get('description', '未知')}")

    async def _handle_high_affection_event(
        self,
        state: CompositePsychologicalState,
        context: Dict[str, Any]
    ):
        """处理高好感度事件"""
        # 提升情绪
        state.update_component_value("情绪", +0.08)

        # 提升社交友好度
        state.update_component_value("社交", +0.08)

        state.triggering_events.append(f"高好感度: {context.get('user_id', '未知用户')}")

    async def _handle_time_change(
        self,
        state: CompositePsychologicalState,
        context: Dict[str, Any]
    ):
        """处理时间变化事件"""
        current_hour = context.get("hour", datetime.now().hour)

        for rule in self.time_based_rules:
            start, end = rule["time_range"]
            if start <= current_hour < end:
                # 根据时间段调整状态
                for category, state_type, value, description in rule["states"]:
                    # 查找是否已有该类别的状态
                    existing = None
                    for comp in state.components:
                        if comp.category == category:
                            existing = comp
                            break

                    if existing:
                        # 缓慢过渡到目标状态
                        target_value = value
                        delta = (target_value - existing.value) * 0.3  # 30%的过渡
                        existing.update_value(delta)
                    else:
                        # 添加新状态
                        component = PsychologicalStateComponent(
                            category=category,
                            state_type=state_type,
                            value=value,
                            description=description
                        )
                        state.add_component(component)

                break

    async def _check_and_transition_states(
        self,
        state: CompositePsychologicalState,
        event_context: Dict[str, Any]
    ):
        """检查并转换需要改变的状态"""
        transitioning = state.get_transitioning_components()

        if not transitioning:
            return

        self._logger.info(f"检测到 {len(transitioning)} 个需要转换的心理状态组件")

        for component in transitioning:
            try:
                # 使用LLM分析应该转换到什么状态
                new_state_type = await self._analyze_state_transition(
                    state, component, event_context
                )

                if new_state_type:
                    # 记录状态变化历史
                    await self._record_state_history(
                        state.group_id,
                        state.state_id,
                        component.category,
                        component.state_type,
                        new_state_type,
                        component.value,
                        0.5,  # 新状态初始值
                        "自动分析转换"
                    )

                    # 更新状态
                    component.state_type = new_state_type
                    component.value = 0.5  # 重置为中等强度
                    component.start_time = time.time()

                    self._logger.info(
                        f"状态转换: {component.category} "
                        f"从 {component.state_type} 转换到 {new_state_type}"
                    )

            except Exception as e:
                self._logger.error(f"状态转换失败: {e}", exc_info=True)

    async def _analyze_state_transition(
        self,
        state: CompositePsychologicalState,
        component: PsychologicalStateComponent,
        context: Dict[str, Any]
    ) -> Optional[Any]:
        """使用LLM分析应该转换到什么状态"""
        if not self.llm_adapter or not self.llm_adapter.has_refine_provider():
            self._logger.warning("LLM适配器不可用，无法进行智能状态分析")
            return self._fallback_state_transition(component)

        try:
            # 构建分析prompt
            prompt = self._build_transition_analysis_prompt(state, component, context)

            # 调用LLM分析
            response = await self.llm_adapter.refine_chat_completion(
                prompt=prompt,
                temperature=0.3
            )

            if response:
                # 解析LLM返回的状态类型
                new_state = self._parse_transition_response(response, component.category)
                return new_state

        except Exception as e:
            self._logger.error(f"LLM状态分析失败: {e}")

        return self._fallback_state_transition(component)

    def _build_transition_analysis_prompt(
        self,
        state: CompositePsychologicalState,
        component: PsychologicalStateComponent,
        context: Dict[str, Any]
    ) -> str:
        """构建状态转换分析的prompt"""
        # 获取当前所有活跃状态的描述
        active_states_desc = "\n".join([
            f"- {c.category}: {c.state_type.value if hasattr(c.state_type, 'value') else str(c.state_type)} (强度: {c.value:.2f})"
            for c in state.get_active_components()
        ])

        # 获取最近的触发事件
        recent_events = "\n".join([f"- {event}" for event in state.triggering_events[-5:]])

        # 获取好感度信息（如果有）
        affection_info = ""
        if "user_id" in context and self.affection_manager:
            try:
                affection_data = self.affection_manager.db_manager.get_user_affection(
                    state.group_id, context["user_id"]
                )
                if affection_data:
                    affection_info = f"\n对该用户的好感度: {affection_data.get('affection_level', 0)}"
            except:
                pass

        category = component.category
        current_state = component.state_type.value if hasattr(component.state_type, 'value') else str(component.state_type)
        current_value = component.value

        prompt = f"""
你是一个心理状态分析专家。Bot当前的心理状态组件"{category}: {current_state}"的数值已降至{current_value:.2f}，低于阈值，需要转换到新的状态。

【当前完整心理状态】
{active_states_desc}

【最近触发事件】
{recent_events}
{affection_info}

【时间信息】
当前时间: {datetime.now().strftime('%H:%M')}
星期: {datetime.now().strftime('%A')}

请根据以上信息，分析Bot的{category}状态应该转换到什么新状态。

可选的{category}状态类型（仅供参考）:
{self._get_category_state_options(category)}

请只返回一个具体的状态名称（中文），不要返回其他内容。
例如: "疲惫" 或 "轻松" 或 "专注"
"""
        return prompt

    def _get_category_state_options(self, category: str) -> str:
        """获取某个类别的可选状态列表"""
        options_map = {
            "情绪": "愉悦、快乐、兴奋、满足、悲伤、难过、愤怒、焦虑、平静、放松",
            "认知": "专注、集中、涣散、分心、清晰思维、混乱思维、敏锐感知",
            "意志": "坚定、坚持、软弱、放弃、主动、被动",
            "精力": "精力充沛、活力满满、疲惫、疲劳、困倦、瞌睡",
            "社交": "友善、热情、冷漠、疏离、主动社交、被动社交",
            "兴趣": "兴趣浓厚、好奇心强、兴趣索然、缺乏动力"
        }
        return options_map.get(category, "根据上下文自行判断合适的状态")

    def _parse_transition_response(self, response: str, category: str) -> Optional[Any]:
        """解析LLM返回的状态转换结果 - 使用 JSON 清洗工具"""
        # 使用 JSON 清洗工具解析状态名称
        state_name = LLMJSONParser.parse_state_analysis(response)

        if not state_name:
            self._logger.warning(f"无法解析LLM返回的状态: {response}")
            return None

        # 尝试匹配到具体的枚举类型
        category_enum_map = {
            "情绪": [EmotionPositiveType, EmotionNegativeType, EmotionNeutralType],
            "认知": [AttentionState, ThinkingState, MemoryState],
            "意志": [WillStrengthState, ActionTendencyState, GoalOrientationState],
            "社交": [SocialAttitudeState, SocialBehaviorState],
            "精力": [EnergyState],
            "兴趣": [InterestMotivationState]
        }

        enums_to_check = category_enum_map.get(category, [])

        for enum_class in enums_to_check:
            for enum_val in enum_class:
                if enum_val.value in state_name:
                    self._logger.debug(f"✅ 成功匹配状态: {state_name} -> {enum_val.value}")
                    return enum_val

        self._logger.warning(f"无法匹配到枚举类型: {state_name} (类别: {category})")
        return None

    def _fallback_state_transition(self, component: PsychologicalStateComponent) -> Optional[Any]:
        """备用的状态转换逻辑（随机选择）"""
        category = component.category

        category_enum_map = {
            "情绪": [EmotionPositiveType, EmotionNegativeType, EmotionNeutralType],
            "认知": [AttentionState, ThinkingState],
            "意志": [WillStrengthState, ActionTendencyState],
            "社交": [SocialAttitudeState, SocialBehaviorState],
            "精力": [EnergyState],
            "兴趣": [InterestMotivationState]
        }

        enums = category_enum_map.get(category, [])
        if enums:
            enum_class = random.choice(enums)
            return random.choice(list(enum_class))

        return None

    async def _auto_decay_task(self):
        """自动衰减任务 - 定期降低所有状态的数值"""
        while True:
            try:
                await asyncio.sleep(1800)  # 每30分钟执行一次

                for group_id, state in self.current_states.items():
                    for component in state.components:
                        decay_rate = self.decay_rates.get(component.category, 0.01)
                        component.update_value(-decay_rate)

                    # 检查是否有状态需要转换
                    await self._check_and_transition_states(state, {"trigger": "auto_decay"})

                self._logger.debug("心理状态自动衰减完成")

            except Exception as e:
                self._logger.error(f"自动衰减任务失败: {e}", exc_info=True)
                await asyncio.sleep(1800)

    async def _time_driven_state_change_task(self):
        """时间驱动的状态变化任务"""
        last_hour = datetime.now().hour

        while True:
            try:
                await asyncio.sleep(300)  # 每5分钟检查一次

                current_hour = datetime.now().hour
                if current_hour != last_hour:
                    # 小时变化，触发时间驱动的状态变化
                    for group_id, state in self.current_states.items():
                        await self.update_state_by_event(
                            group_id,
                            "time_change",
                            {"hour": current_hour}
                        )

                    last_hour = current_hour
                    self._logger.info(f"时间驱动状态变化完成 (当前: {current_hour}点)")

            except Exception as e:
                self._logger.error(f"时间驱动状态变化任务失败: {e}", exc_info=True)
                await asyncio.sleep(300)

    async def get_state_prompt_injection(self, group_id: str) -> str:
        """获取用于prompt注入的心理状态描述"""
        try:
            state = await self.get_or_create_state(group_id)
            return state.to_prompt_injection()
        except Exception as e:
            self._logger.error(f"生成状态prompt注入失败: {e}")
            return ""

    # ==================== 数据库操作 ====================

    async def _load_state_from_db(self, group_id: str) -> Optional[CompositePsychologicalState]:
        """从数据库加载心理状态"""
        try:
            async with self.db_manager.get_db_connection() as conn:
                cursor = await conn.cursor()

                # 查询复合状态元数据
                await cursor.execute('''
                    SELECT state_id, triggering_events, context, created_at, last_updated
                    FROM composite_psychological_states
                    WHERE group_id = ?
                    ORDER BY last_updated DESC
                    LIMIT 1
                ''', (group_id,))

                row = await cursor.fetchone()
                if not row:
                    return None

                state_id, events_json, context_json, created_at, last_updated = row

                state = CompositePsychologicalState(
                    group_id=group_id,
                    state_id=state_id,
                    triggering_events=json.loads(events_json) if events_json else [],
                    context=json.loads(context_json) if context_json else {},
                    created_at=created_at,
                    last_updated=last_updated
                )

                # 查询所有组件
                await cursor.execute('''
                    SELECT category, state_type, value, threshold, description, start_time
                    FROM psychological_state_components
                    WHERE group_id = ? AND state_id = ?
                ''', (group_id, state_id))

                for row in await cursor.fetchall():
                    category, state_type_str, value, threshold, description, start_time = row

                    # 重建枚举类型（简化处理）
                    component = PsychologicalStateComponent(
                        category=category,
                        state_type=state_type_str,  # 暂时用字符串，实际应该恢复枚举
                        value=value,
                        threshold=threshold,
                        description=description,
                        start_time=start_time
                    )
                    state.components.append(component)

                await cursor.close()
                return state

        except Exception as e:
            self._logger.error(f"从数据库加载心理状态失败: {e}", exc_info=True)
            return None

    async def _save_state_to_db(self, state: CompositePsychologicalState):
        """保存心理状态到数据库"""
        try:
            async with self.db_manager.get_db_connection() as conn:
                cursor = await conn.cursor()

                # ✅ 使用数据库无关的语法：DELETE + INSERT 替代 INSERT OR REPLACE
                # 先删除旧记录
                await cursor.execute('''
                    DELETE FROM composite_psychological_states
                    WHERE group_id = ? AND state_id = ?
                ''', (state.group_id, state.state_id))

                # 再插入新记录
                await cursor.execute('''
                    INSERT INTO composite_psychological_states
                    (group_id, state_id, triggering_events, context, created_at, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    state.group_id,
                    state.state_id,
                    json.dumps(state.triggering_events, ensure_ascii=False),
                    json.dumps(state.context, ensure_ascii=False),
                    state.created_at,
                    time.time()
                ))

                # 删除旧的组件
                await cursor.execute('''
                    DELETE FROM psychological_state_components
                    WHERE group_id = ? AND state_id = ?
                ''', (state.group_id, state.state_id))

                # 保存所有组件
                for component in state.components:
                    state_type_str = component.state_type.value if hasattr(component.state_type, 'value') else str(component.state_type)

                    await cursor.execute('''
                        INSERT INTO psychological_state_components
                        (group_id, state_id, category, state_type, value, threshold, description, start_time)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        state.group_id,
                        state.state_id,
                        component.category,
                        state_type_str,
                        component.value,
                        component.threshold,
                        component.description,
                        component.start_time
                    ))

                await conn.commit()
                await cursor.close()

        except Exception as e:
            self._logger.error(f"保存心理状态到数据库失败: {e}", exc_info=True)

    async def _record_state_history(
        self,
        group_id: str,
        state_id: str,
        category: str,
        old_state_type: Any,
        new_state_type: Any,
        old_value: float,
        new_value: float,
        reason: str
    ):
        """记录状态变化历史"""
        try:
            async with self.db_manager.get_db_connection() as conn:
                cursor = await conn.cursor()

                old_str = old_state_type.value if hasattr(old_state_type, 'value') else str(old_state_type)
                new_str = new_state_type.value if hasattr(new_state_type, 'value') else str(new_state_type)

                await cursor.execute('''
                    INSERT INTO psychological_state_history
                    (group_id, state_id, category, old_state_type, new_state_type,
                     old_value, new_value, change_reason, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    group_id, state_id, category, old_str, new_str,
                    old_value, new_value, reason, time.time()
                ))

                await conn.commit()
                await cursor.close()

        except Exception as e:
            self._logger.error(f"记录状态历史失败: {e}")

    async def _load_all_states(self):
        """加载所有群组的当前状态"""
        try:
            async with self.db_manager.get_db_connection() as conn:
                cursor = await conn.cursor()

                await cursor.execute('''
                    SELECT DISTINCT group_id FROM composite_psychological_states
                    WHERE last_updated > ?
                ''', (time.time() - 86400 * 7,))  # 最近7天

                rows = await cursor.fetchall()
                await cursor.close()

                for row in rows:
                    group_id = row[0]
                    state = await self._load_state_from_db(group_id)
                    if state:
                        self.current_states[group_id] = state

                self._logger.info(f"已加载 {len(self.current_states)} 个群组的心理状态")

        except Exception as e:
            self._logger.error(f"加载所有状态失败: {e}", exc_info=True)

    async def _save_all_states(self):
        """保存所有当前状态"""
        try:
            for state in self.current_states.values():
                await self._save_state_to_db(state)

            self._logger.info(f"已保存 {len(self.current_states)} 个群组的心理状态")

        except Exception as e:
            self._logger.error(f"保存所有状态失败: {e}", exc_info=True)
