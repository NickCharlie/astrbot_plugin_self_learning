"""
心理状态数据模型 - 包含情绪、认知、意志、社交等多维度心理状态
基于心理学理论的详细分类系统
"""
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import time


# 情绪情感类心理状态

class EmotionPositiveType(Enum):
    """积极情绪类型"""
    # 基础类
    JOYFUL = "愉悦"
    HAPPY = "快乐"
    EXCITED = "兴奋"
    SATISFIED = "满足"
    RELIEVED = "安心"
    STEADY = "踏实"

    # 复合类
    PROUD = "自豪"
    ACHIEVEMENT = "成就感"
    HONOR = "荣誉感"
    BLESSED = "幸福感"
    BELONGING = "归属感"
    SECURE = "安全感"
    LOVED = "被爱感"
    GRATEFUL = "感恩"
    MOVED = "感动"
    ADMIRING = "敬佩"

    # 状态类
    RELAXED = "轻松"
    COMFORTABLE = "惬意"
    CAREFREE = "悠然"
    PLEASANT = "舒畅"
    CHEERFUL = "兴高采烈"
    SPIRITED = "意气风发"
    MOTIVATED = "斗志昂扬"


class EmotionNegativeType(Enum):
    """消极情绪类型"""
    # 基础类
    SAD = "悲伤"
    UPSET = "难过"
    HEARTBROKEN = "伤心"
    PAINFUL = "痛苦"
    SORROWFUL = "悲哀"
    GRIEF = "悲痛"
    DEPRESSED = "沮丧"
    LOW = "低落"
    MELANCHOLY = "郁闷"
    STUFFY = "烦闷"
    IRRITABLE = "烦躁"
    RESTLESS = "焦躁"

    # 复合类
    ANGRY = "愤怒"
    FURIOUS = "暴怒"
    RESENTFUL = "怨恨"
    HATEFUL = "仇恨"
    JEALOUS = "嫉妒"
    ENVIOUS = "羡慕负面"
    GUILTY = "愧疚"
    SELF_BLAME = "自责"
    ASHAMED = "羞耻"
    INFERIOR = "自卑"
    ANXIOUS = "焦虑"
    WORRIED = "担忧"
    CONCERNED = "忧虑"
    FEARFUL = "恐惧"
    AFRAID = "害怕"
    TERRIFIED = "惊恐"
    PANICKED = "恐慌"
    UNEASY = "不安"
    APPREHENSIVE = "忐忑"
    DESPERATE = "绝望"
    HELPLESS = "无助"
    LONELY = "孤独"
    ISOLATED = "寂寞"
    BORED = "无聊"
    WEARY = "厌倦"
    DISGUSTED = "厌恶"
    REPULSED = "排斥"

    # 状态类
    SUPPRESSED = "压抑"
    AGGRIEVED = "憋屈"
    TORMENTED = "煎熬"
    CONFLICTED = "纠结"
    DISTURBED = "心烦意乱"
    RESTLESS_ANXIOUS = "坐立不安"
    TERRIFIED_FEARFUL = "胆战心惊"
    DEEPLY_WORRIED = "忧心忡忡"


class EmotionNeutralType(Enum):
    """中性情绪类型"""
    CALM = "平静"
    BLAND = "平淡"
    PEACEFUL = "平和"
    INDIFFERENT = "漠然"
    NUMB = "麻木"
    TRANQUIL = "淡定"
    COMPOSED = "从容"


class EmotionSpecialType(Enum):
    """特殊情绪状态"""
    STRESS = "应激紧张"
    ALERT = "警觉"
    FLUSTERED = "慌乱"
    STRESS_ACTIVATED = "应对性兴奋"

    # 心境状态
    PERSISTENT_JOY = "持久愉悦"
    PERSISTENT_LOW = "持久低落"

    # 激情状态
    ECSTASY = "狂喜"
    RAGE = "暴怒爆发"
    EXTREME_GRIEF = "极度悲伤"

    # 复合情绪
    LOVE_HATE = "爱恨交织"
    JOY_SORROW = "悲喜交加"
    CONFLICTED_LOVE = "又爱又恨"
    TRAGICOMIC = "哭笑不得"
    MIXED_FEELINGS = "百感交集"


# 认知类心理状态

class AttentionState(Enum):
    """注意力状态"""
    # 高效类
    FOCUSED = "专注"
    CONCENTRATED = "集中"
    ATTENTIVE = "专心"
    ABSORBED = "全神贯注"
    ENGROSSED = "聚精会神"
    SINGLE_MINDED = "心无旁骛"
    HIGHLY_ALERT = "高度警觉"

    # 低效类
    SCATTERED = "涣散"
    DISTRACTED = "分心"
    WANDERING = "走神"
    INATTENTIVE = "注意力不集中"
    ABSENT_MINDED = "心不在焉"
    DAZED = "恍惚"
    DETACHED = "游离"


class ThinkingState(Enum):
    """思维状态"""
    # 清晰类
    CLEAR_LOGIC = "逻辑清晰"
    ORGANIZED = "条理分明"
    AGILE_THINKING = "思维敏捷"
    BROAD_MINDED = "思路开阔"
    INSIGHTFUL = "举一反三"
    ANALOGICAL = "触类旁通"
    DELIBERATE = "深思熟虑"
    METICULOUS = "周密严谨"

    # 混乱类
    CONFUSED_THINKING = "思维混乱"
    ILLOGICAL = "逻辑混乱"
    FUZZY_THINKING = "思路模糊"
    DISORGANIZED = "条理不清"
    OVERTHINKING = "胡思乱想"
    FIXATED = "钻牛角尖"
    STUCK = "冥思苦想无果"

    # 特殊类
    INTUITIVE = "直觉思维"
    ANALYTICAL = "分析思维"
    CREATIVE = "创造性思维"
    CRITICAL = "批判性思维"
    CONCRETE = "具象思维"
    ABSTRACT = "抽象思维"


class MemoryState(Enum):
    """记忆状态"""
    # 高效类
    CLEAR_MEMORY = "记忆清晰"
    PHOTOGRAPHIC = "过目不忘"
    SMOOTH_RECALL = "回忆顺畅"
    VIVID = "印象深刻"

    # 低效类
    FUZZY_MEMORY = "记忆模糊"
    FORGOTTEN = "遗忘"
    RECALL_DIFFICULTY = "回忆困难"
    CONFUSED_MEMORY = "记混"
    FALSE_MEMORY = "记错"
    FLEETING = "转瞬即忘"

    # 特殊类
    NOSTALGIC = "怀旧"
    FLASHBACK = "闪回"
    AMNESIA = "遗忘症"


class PerceptionState(Enum):
    """感知状态"""
    # 正常类
    KEEN_PERCEPTION = "感知敏锐"
    OBSERVANT = "观察细致"
    CLEAR_SENSES = "感知清晰"
    COORDINATED = "感知协调"

    # 异常类
    DULL_PERCEPTION = "感知迟钝"
    INSENSITIVE = "麻木不仁"
    ILLUSION = "错觉"
    HALLUCINATION = "幻觉"
    DISTORTED_PERCEPTION = "感知扭曲"


class DecisionState(Enum):
    """决策与判断状态"""
    # 理性类
    CALM_JUDGMENT = "冷静判断"
    OBJECTIVE_ANALYSIS = "客观分析"
    WEIGHING_OPTIONS = "权衡利弊"
    DECISIVE = "果断决策"
    WELL_CONSIDERED = "深思熟虑"

    # 非理性类
    IMPULSIVE = "冲动判断"
    SUBJECTIVE = "主观臆断"
    ONE_SIDED = "片面化"
    EXTREME = "极端化"
    HESITANT = "犹豫不决"
    INDECISIVE = "优柔寡断"
    FOLLOWING_CROWD = "随波逐流"


# 意志与行为倾向类心理状态

class WillStrengthState(Enum):
    """意志强度状态"""
    # 积极类
    DETERMINED = "坚定"
    RESOLUTE = "坚决"
    PERSISTENT = "坚持"
    TENACIOUS = "坚韧"
    UNYIELDING = "顽强"
    PERSEVERING = "持之以恒"
    INDOMITABLE = "百折不挠"

    # 消极类
    WEAK = "软弱"
    RETREATING = "退缩"
    GIVING_UP = "放弃"
    HALF_HEARTED = "半途而废"
    ANTICLIMACTIC = "虎头蛇尾"
    WAVERING = "优柔寡断"

    # 特殊类
    DECISIVE_ACTION = "果断"
    STUBBORN = "固执"
    COMPROMISING = "妥协"


class ActionTendencyState(Enum):
    """行动倾向状态"""
    # 主动类
    PROACTIVE = "积极主动"
    INITIATIVE = "主动出击"
    SELF_DRIVEN = "自觉行动"
    SPONTANEOUS = "自发行动"
    ADVENTUROUS = "勇于尝试"
    DARING = "敢于突破"

    # 被动类
    PASSIVE = "被动应付"
    SLUGGISH = "消极怠工"
    PROCRASTINATING = "拖延"
    PERFUNCTORY = "敷衍了事"
    SHIRKING = "推诿责任"
    EVADING = "逃避"
    AVOIDING = "回避"

    # 特殊类
    IMPULSIVE_ACTION = "冲动行为"
    RESTRAINED_ACTION = "克制行为"
    HABITUAL_ACTION = "习惯性行为"


class GoalOrientationState(Enum):
    """目标导向状态"""
    # 明确类
    CLEAR_GOAL = "目标清晰"
    CLEAR_DIRECTION = "方向明确"
    STRONG_MISSION = "使命感强"
    STRONG_MOTIVATION = "动机强烈"
    AMBITIOUS = "野心勃勃"
    PURSUING_EXCELLENCE = "追求卓越"

    # 模糊类
    LOST = "迷茫"
    WANDERING = "彷徨"
    BEWILDERED = "不知所措"
    AIMLESS = "漫无目的"
    GOING_WITH_FLOW = "随遇而安"
    LACKING_DRIVE = "缺乏动力"
    GETTING_BY = "得过且过"

    # 特殊类
    HIGH_AMBITION = "野心"
    BUDDHIST_MODE = "佛系"
    UTILITARIAN = "功利性"


# 自我认知与人格倾向类心理状态

class SelfAcceptanceState(Enum):
    """自我接纳状态"""
    # 积极类
    SELF_ACCEPTING = "自我接纳"
    CONFIDENT = "自信"
    SELF_RESPECTING = "自尊"
    SELF_LOVING = "自爱"
    SELF_VALUING = "自重"
    SELF_AFFIRMING = "自我肯定"
    SELF_IDENTIFYING = "自我认同"
    ACCOMPLISHED = "成就感"

    # 消极类
    INFERIOR = "自卑"
    SELF_DENYING = "自我否定"
    SELF_DOUBTING = "自我怀疑"
    SELF_LOATHING = "自我厌恶"
    SELF_ABANDONING = "自暴自弃"
    SELF_BLAMING = "自责"
    SHAMEFUL = "羞耻"
    GUILTY = "愧疚"

    # 特殊类
    ARROGANT = "自负"
    NARCISSISTIC = "自恋"
    SELF_DEPRECATING = "自嘲"


class SelfStateType(Enum):
    """自我状态（心理学理论）"""
    # 父母自我状态
    CRITICAL_PARENT = "挑剔"
    ACCUSING_PARENT = "指责"
    PROTECTIVE_PARENT = "保护"
    CARING_PARENT = "照顾"
    TEACHING_PARENT = "说教"
    AUTHORITATIVE_PARENT = "权威"

    # 成人自我状态
    RATIONAL_ADULT = "理性"
    OBJECTIVE_ADULT = "客观"
    CALM_ADULT = "冷静"
    LOGICAL_ADULT = "逻辑"
    PROBLEM_SOLVING_ADULT = "解决问题"

    # 儿童自我状态
    NAIVE_CHILD = "天真"
    IMMATURE_CHILD = "幼稚"
    DEPENDENT_CHILD = "依赖"
    IMPULSIVE_CHILD = "冲动"
    EMOTIONAL_CHILD = "情绪化"
    CURIOUS_CHILD = "好奇"
    REBELLIOUS_CHILD = "叛逆"


class PersonalityTendencyState(Enum):
    """人格倾向状态"""
    # 外向倾向
    OUTGOING = "开朗"
    LIVELY = "活泼"
    TALKATIVE = "健谈"
    ENTHUSIASTIC = "热情"
    SOCIABLE = "善于交际"
    GREGARIOUS = "合群"
    EXTROVERTED = "外向"

    # 内向倾向
    INTROVERTED = "内向"
    QUIET = "安静"
    SILENT = "沉默"
    ALOOF = "孤僻"
    SOLITARY = "独处倾向"
    UNSOCIABLE = "不善交际"
    RESERVED = "内敛"

    # 中间类
    BALANCED = "内外向均衡"
    EASYGOING = "随和"
    NEUTRAL = "中性"
    ADAPTABLE = "灵活应变"


# 社交互动类心理状态

class SocialAttitudeState(Enum):
    """社交态度状态"""
    # 积极类
    FRIENDLY = "友善"
    CORDIAL = "友好"
    WARM = "热情"
    SINCERE = "真诚"
    TOLERANT = "包容"
    UNDERSTANDING = "体谅"
    HELPFUL = "乐于助人"
    COOPERATIVE = "合作"
    COLLABORATIVE = "协作"
    EMPATHETIC = "共情"
    SYMPATHETIC = "同理心强"

    # 消极类
    HOSTILE = "敌对"
    ANTAGONISTIC = "敌意"
    COLD = "冷漠"
    DISTANT = "疏离"
    REJECTING = "排斥"
    DISCRIMINATING = "歧视"
    BIASED = "偏见"
    SUSPICIOUS = "怀疑"
    GUARDED = "戒备"
    DEFENSIVE = "防备"
    SELFISH = "自私"
    MEAN = "刻薄"

    # 特殊类
    PLEASING = "讨好"
    ARROGANT_SOCIAL = "傲慢"
    HUMBLE = "谦逊"


class SocialBehaviorState(Enum):
    """社交行为状态"""
    # 主动类
    PROACTIVE_SOCIAL = "主动社交"
    PROACTIVE_COMMUNICATION = "主动沟通"
    PROACTIVE_APPROACH = "主动亲近"
    EXPRESSIVE = "善于表达"
    SHARING = "乐于分享"
    LEADING_INTERACTION = "主导互动"

    # 被动类
    PASSIVE_SOCIAL = "被动社交"
    TACITURN = "沉默寡言"
    AVOIDING_COMMUNICATION = "回避沟通"
    FEARING_SOCIAL = "害怕社交"
    SOCIAL_ANXIETY = "社交焦虑"
    WITHDRAWING = "退缩"
    ISOLATED_BEHAVIOR = "孤立"

    # 特殊类
    SOCIAL_PHOBIA = "社交恐惧"
    SOCIALLY_SKILLED = "八面玲珑"
    LONE_WOLF = "独来独往"


class InterpersonalRoleState(Enum):
    """人际角色状态"""
    # 领导型
    LEADING = "主导"
    COMMANDING = "指挥"
    DECISION_MAKING = "决策"
    COORDINATING = "统筹"
    AUTHORITATIVE_ROLE = "权威"
    CONTROLLING = "掌控"

    # 跟随型
    OBEDIENT = "服从"
    COOPERATIVE_FOLLOWER = "配合"
    ASSISTING = "辅助"
    SUPPORTING = "支持"
    DEPENDENT_ROLE = "依赖"
    COMPLIANT = "顺从"

    # 平等型
    EQUAL_COOPERATION = "合作"
    NEGOTIATING = "协商"
    MUTUAL_HELP = "互助"
    MUTUAL_BENEFIT = "互利"
    EQUAL_DIALOGUE = "平等对话"


# 适应与应激类心理状态

class EnvironmentalAdaptationState(Enum):
    """环境适应状态"""
    # 良好类
    WELL_ADAPTED = "适应良好"
    INTEGRATED = "融入环境"
    FLEXIBLE = "灵活应变"
    ACCEPTING_SITUATION = "随遇而安"
    COMPOSED_ADAPTATION = "从容不迫"

    # 不良类
    MALADAPTED = "适应不良"
    OUT_OF_PLACE = "格格不入"
    DIFFICULT_INTEGRATION = "难以融入"
    RESISTING_ENVIRONMENT = "抵触环境"
    ANXIOUS_ADAPTATION = "焦虑不安"
    BEWILDERED_ADAPTATION = "无所适从"

    # 特殊类
    STRESS_ADAPTATION = "应激适应"
    LONG_TERM_ADAPTATION = "长期适应"


class StressCopingState(Enum):
    """压力应对状态"""
    # 积极应对
    RESILIENT = "坚韧"
    STRESS_RESISTANT = "抗压"
    OPTIMISTIC = "乐观"
    PROACTIVE_SOLVING = "主动解决"
    SEEKING_SUPPORT = "寻求支持"
    EMOTION_REGULATION = "情绪调节能力强"

    # 消极应对
    AVOIDING_STRESS = "逃避"
    WITHDRAWING_STRESS = "退缩"
    ANXIOUS_COPING = "焦虑"
    DEPRESSIVE_COPING = "抑郁"
    BREAKING_DOWN = "崩溃"
    LOSING_CONTROL = "情绪失控"
    SUBSTANCE_DEPENDENT = "依赖酒精药物"

    # 特殊类
    PTSD = "创伤后应激"
    ACUTE_STRESS = "急性应激"


class BodyMindCoordinationState(Enum):
    """身心协调状态"""
    # 健康类
    BALANCED_BODY_MIND = "身心平衡"
    EMOTIONALLY_STABLE = "情绪稳定"
    ENERGETIC = "精力充沛"
    GOOD_SLEEP = "睡眠良好"
    NORMAL_APPETITE = "食欲正常"

    # 失调类
    IMBALANCED_BODY_MIND = "身心失衡"
    EMOTIONAL_DISORDER = "情绪紊乱"
    FATIGUED = "疲劳乏力"
    INSOMNIA = "失眠"
    POOR_APPETITE = "食欲不振"
    OVEREATING = "暴饮暴食"
    PSYCHOSOMATIC = "心因性躯体症状"


# 其他维度心理状态

class EnergyState(Enum):
    """精力状态"""
    # 充沛类
    VIGOROUS = "精力充沛"
    SPIRITED_ENERGY = "神采奕奕"
    ENERGETIC_FULL = "活力满满"
    RADIANT = "精神焕发"

    # 匮乏类
    TIRED = "疲惫"
    FATIGUED_ENERGY = "疲劳"
    DROWSY = "困倦"
    SLEEPY = "瞌睡"
    LISTLESS = "无精打采"
    LETHARGIC = "萎靡不振"
    EXHAUSTED = "心力交瘁"


class InterestMotivationState(Enum):
    """兴趣/动机状态"""
    # 浓厚类
    HIGH_INTEREST = "兴趣浓厚"
    CURIOUS_INTEREST = "好奇心强"
    EAGER_TO_LEARN = "求知欲强"
    STRONG_MOTIVATION = "动机强烈"
    HIGH_ENTHUSIASM = "热情高涨"

    # 淡薄类
    INDIFFERENT = "兴趣索然"
    NO_INTEREST = "毫无兴趣"
    APATHETIC = "麻木不仁"
    UNMOTIVATED = "缺乏动力"
    GETTING_BY_INTEREST = "得过且过"


class TimePerceptionState(Enum):
    """时间感知状态"""
    # 快速类
    TIME_FLIES = "光阴似箭"
    SWIFT_TIME = "时间飞逝"

    # 缓慢类
    TIME_DRAGS = "度日如年"
    DRAGGING_TIME = "时间难熬"

    # 正常类
    BALANCED_TIME = "时间感知均衡"
    STEADY_PACE = "按部就班"


# 复合心理状态

@dataclass
class PsychologicalStateComponent:
    """单个心理状态组件（用于复合状态）"""
    category: str  # 类别名称：情绪、认知、意志等
    state_type: Any  # 具体状态枚举值
    value: float  # 状态数值 [0, 1]
    threshold: float = 0.3  # 阈值，低于此值时需要更换状态
    description: str = ""  # 自定义描述
    start_time: float = field(default_factory=time.time)  # 状态开始时间

    def is_active(self) -> bool:
        """判断状态是否仍然活跃（数值大于阈值）"""
        return self.value > self.threshold

    def should_transition(self) -> bool:
        """判断是否需要状态转换"""
        return self.value <= self.threshold

    def update_value(self, delta: float):
        """更新状态数值"""
        self.value = max(0.0, min(1.0, self.value + delta))


@dataclass
class CompositePsychologicalState:
    """复合心理状态 - 由多个心理状态组件组合而成"""
    group_id: str  # 群组ID
    state_id: str  # 状态唯一标识
    components: List[PsychologicalStateComponent] = field(default_factory=list)
    overall_state: str = "neutral"  # 总体状态
    state_intensity: float = 0.5  # 状态强度
    last_transition_time: Optional[float] = None  # 上次转换时间
    created_at: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)

    # 状态元数据
    triggering_events: List[str] = field(default_factory=list)  # 触发事件列表
    context: Dict[str, Any] = field(default_factory=dict)  # 上下文信息

    def get_active_components(self) -> List[PsychologicalStateComponent]:
        """获取所有活跃的状态组件"""
        return [c for c in self.components if c.is_active()]

    def get_transitioning_components(self) -> List[PsychologicalStateComponent]:
        """获取需要转换的状态组件"""
        return [c for c in self.components if c.should_transition()]

    def add_component(self, component: PsychologicalStateComponent):
        """添加一个状态组件"""
        self.components.append(component)
        self.last_updated = time.time()

    def remove_component(self, component: PsychologicalStateComponent):
        """移除一个状态组件"""
        if component in self.components:
            self.components.remove(component)
            self.last_updated = time.time()

    def update_component_value(self, category: str, delta: float):
        """更新指定类别的状态数值"""
        for component in self.components:
            if component.category == category:
                component.update_value(delta)
                self.last_updated = time.time()
                break

    def to_description(self) -> str:
        """生成人类可读的心理状态描述"""
        active = self.get_active_components()
        if not active:
            return "当前没有明显的心理状态特征"

        descriptions = []
        for component in active:
            state_name = component.state_type.value if hasattr(component.state_type, 'value') else str(component.state_type)
            intensity = "非常" if component.value > 0.7 else "比较" if component.value > 0.4 else "略微"
            descriptions.append(f"{intensity}{state_name}")

        return "、".join(descriptions)

    def to_prompt_injection(self) -> str:
        """生成用于注入到LLM prompt中的心理状态描述"""
        active = self.get_active_components()
        if not active:
            return ""

        prompt_parts = ["【当前心理状态】"]

        # 按类别分组
        category_groups: Dict[str, List[PsychologicalStateComponent]] = {}
        for component in active:
            if component.category not in category_groups:
                category_groups[component.category] = []
            category_groups[component.category].append(component)

        # 生成每个类别的描述
        for category, components in category_groups.items():
            prompt_parts.append(f"\n{category}状态:")
            for component in components:
                state_name = component.state_type.value if hasattr(component.state_type, 'value') else str(component.state_type)
                intensity_desc = f"(强度: {component.value:.2f})"
                if component.description:
                    prompt_parts.append(f"  - {state_name} {intensity_desc}: {component.description}")
                else:
                    prompt_parts.append(f"  - {state_name} {intensity_desc}")

        prompt_parts.append("\n请根据以上心理状态调整回复的语气、情感表达和行为模式。")
        return "\n".join(prompt_parts)


# 状态转换规则

@dataclass
class StateTransitionRule:
    """心理状态转换规则"""
    trigger_event: str  # 触发事件类型
    current_state_pattern: Dict[str, Any]  # 当前状态匹配模式
    target_state_type: Any  # 目标状态类型
    transition_probability: float  # 转换概率
    value_change: float  # 状态数值变化量
    conditions: Dict[str, Any] = field(default_factory=dict)  # 附加条件

    def matches(self, current_state: CompositePsychologicalState, event_context: Dict[str, Any]) -> bool:
        """判断是否匹配当前状态和事件"""
        # 简单实现：检查是否包含特定类别的状态
        if "required_categories" in self.current_state_pattern:
            required = self.current_state_pattern["required_categories"]
            active_categories = {c.category for c in current_state.get_active_components()}
            if not all(cat in active_categories for cat in required):
                return False

        # 检查附加条件
        for key, expected_value in self.conditions.items():
            if key not in event_context or event_context[key] != expected_value:
                return False

        return True
