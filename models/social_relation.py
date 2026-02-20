"""
社交关系类型数据模型 - 详细的人际关系分类系统
基于社会心理学理论的多维度关系分类
"""
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import time


# 核心联结基础类关系

class BloodRelationType(Enum):
    """血缘关系类型"""
    # 直系血缘
    PARENT_CHILD = "父母子女"
    GRANDPARENT_GRANDCHILD = "祖孙"
    GREAT_GRANDPARENT = "曾祖"

    # 旁系血缘
    SIBLINGS = "兄弟姐妹"
    COUSINS = "堂表兄弟姐妹"
    NIECE_NEPHEW = "侄子女外甥"
    UNCLE_AUNT = "叔伯姑舅姨"

    # 姻亲关联
    IN_LAWS = "姻亲"
    SPOUSE_PARENTS = "配偶父母"
    SPOUSE_SIBLINGS = "配偶兄弟姐妹"
    CHILD_SPOUSE = "子女配偶"
    SIBLING_SPOUSE = "兄弟姐妹配偶"

    # 特殊血缘
    ADOPTED = "领养关系"
    STEP_FAMILY = "继父母继子女"
    HALF_SIBLINGS = "同父异母同母异父"


class GeographicalRelationType(Enum):
    """地缘关系类型"""
    # 邻里关系
    NEIGHBOR = "邻居"
    SAME_BUILDING = "同楼居民"
    SAME_VILLAGE = "同村村民"
    SAME_STREET = "同街道住户"

    # 社区关系
    COMMUNITY_MEMBER = "同社区成员"
    COMMUNITY_STAFF = "居委会村委会"
    COMMUNITY_VOLUNTEER = "社区志愿者"

    # 地域关联
    HOMETOWN = "同乡"
    SCHOOLMATE = "同校"
    SAME_PARK = "同园区"

    # 临时地缘
    CO_PASSENGER = "同车乘客"
    CO_TRAVELER = "同航班旅客"
    TOURIST = "同景区游客"
    HOSPITAL_MATE = "同医院病友"


class CareerRelationType(Enum):
    """业缘关系类型"""
    # 职场关系
    SUPERVISOR_SUBORDINATE = "上下级"
    MENTOR_MENTEE = "导师学徒"
    COLLEAGUE = "同事"
    FORMER_COLLEAGUE = "前同事"
    PROJECT_PARTNER = "项目伙伴"

    # 合作方
    CLIENT_SUPPLIER = "甲方乙方"
    VENDOR_BUYER = "供应商采购"
    SERVICE_PROVIDER = "服务商客户"

    # 学业关系
    TEACHER_STUDENT = "师生"
    ADVISOR_GRADUATE = "导师研究生"
    COACH_TRAINEE = "教练学员"
    CLASSMATE = "同学"
    ALUMNI = "校友"
    DESKMATE = "同桌"
    ROOMMATE = "舍友"

    # 事业协作
    BUSINESS_PARTNER = "合伙人"
    INVESTOR_ENTREPRENEUR = "投资人创业者"
    INDUSTRY_PEER = "行业同行"
    COOPERATION_PARTNER = "合作伙伴"


class EmotionalRelationType(Enum):
    """情缘关系类型"""
    # 爱情关系
    LOVER = "恋人"
    FIANCE = "未婚夫妻"
    SPOUSE = "夫妻"
    EX_PARTNER = "前任"

    # 亲密友谊
    BEST_FRIEND = "挚友"
    CLOSE_FRIEND = "闺蜜兄弟"
    SOULMATE = "知己"

    # 暧昧关系
    AMBIGUOUS = "暧昧"
    CRUSH = "暗恋"

    # 特殊情缘
    CROSS_AGE_FRIEND = "忘年交"
    PLATONIC_FRIEND = "红颜蓝颜知己"


class InterestRelationType(Enum):
    """趣缘关系类型"""
    # 兴趣社群
    CHESS_MATE = "棋友"
    SPORTS_MATE = "球友"
    TRAVEL_MATE = "驴友"
    BOOK_MATE = "书友"
    MOVIE_MATE = "影友"
    MUSIC_MATE = "乐友"
    GAME_TEAMMATE = "游戏队友"
    PHOTO_PARTNER = "摄影伙伴"

    # 理念认同
    LIKE_MINDED = "志同道合"
    CHARITY_PARTNER = "公益伙伴"
    FAITH_COMPANION = "信仰同伴"

    # 兴趣组织
    CLUB_MEMBER = "社团成员"
    FAN_CIRCLE = "粉丝圈同好"
    CLUB_MATE = "俱乐部成员"


class InterestRelationType(Enum):
    """利益关系类型"""
    # 经济利益
    CREDITOR_DEBTOR = "借贷关系"
    BUSINESS_ASSOCIATE = "合伙人"
    BUSINESS_CONTACT = "生意伙伴"
    EMPLOYER_EMPLOYEE = "雇主雇员"

    # 资源交换
    NETWORK_EXCHANGE = "人脉互换"
    SKILL_COMPLEMENT = "技能互补"
    POWER_RELATION = "权力关联"

    # 临时利益
    AGENT_CLIENT = "中介委托"
    SERVICE_CONSUMER = "服务消费"
    COMPANION = "搭子关系"


# 按亲密度与情感深度分类

class IntimacyLevel(Enum):
    """亲密度等级"""
    # 亲密关系
    CORE_INTIMATE = "核心亲密"  # 配偶、父母、子女、兄弟姐妹
    DEEP_INTIMATE = "深度亲密"  # 挚友、知己、长期恋人
    EXCLUSIVE_INTIMATE = "专属亲密"  # 灵魂伴侣、患难之交

    # 普通关系
    DAILY_ORDINARY = "日常普通"  # 同事、同学、邻居
    SOCIAL_ORDINARY = "社交普通"  # 普通朋友、行业同行
    PROFESSIONAL_ORDINARY = "专业普通"  # 医生患者、律师委托人

    # 疏远关系
    STRANGER = "陌生关系"  # 路人
    SHALLOW = "浅层认识"  # 一面之缘
    AVOIDANT = "回避型疏远"  # 有矛盾、刻意保持距离


# 按社会功能与互动场景分类

class FamilyRelationType(Enum):
    """家庭关系类型"""
    CORE_FAMILY = "核心家庭"  # 夫妻、父母与未成年子女
    EXTENDED_FAMILY = "扩展家庭"  # 祖孙、叔伯姑舅姨
    SINGLE_PARENT = "单亲家庭"
    BLENDED_FAMILY = "重组家庭"
    DINK_FAMILY = "丁克家庭"
    EMPTY_NEST = "空巢老人与子女"


class WorkplaceRelationType(Enum):
    """职场关系类型"""
    MANAGEMENT = "管理关系"  # 上下级
    COLLABORATION = "协作关系"  # 同事
    SERVICE = "服务关系"  # 供应商客户
    MENTORSHIP = "传承关系"  # 导师学徒


class SocialRelationType(Enum):
    """社交关系类型"""
    CLOSE_FRIEND = "朋友关系"  # 挚友、普通朋友、酒肉朋友
    COMMUNITY = "社群关系"  # 兴趣社群、公益组织
    TEMPORARY = "临时社交"  # 活动参与者


class NetworkRelationType(Enum):
    """网络关系类型"""
    VIRTUAL_FRIEND = "虚拟好友"  # 微信QQ好友
    INTERACTIVE_ONLINE = "互动型网络"  # 游戏队友、直播
    TRANSACTIONAL_ONLINE = "交易型网络"  # 电商、线上服务
    STRANGER_ONLINE = "陌生网络"  # 评论区互动


class PublicRelationType(Enum):
    """公共关系类型"""
    SERVICE_PUBLIC = "服务者与公众"  # 医生患者、警察市民
    STRANGER_INTERACTION = "陌生人互动"  # 超市收银员、公交司机


# 按法律与契约属性分类

class LegalRelationType(Enum):
    """法定关系类型"""
    FAMILY_LEGAL = "亲属法定"  # 夫妻、父母子女
    SOCIAL_LEGAL = "社会法定"  # 公民与国家机关
    CONTRACT_LEGAL = "契约法定"  # 买卖、借贷、租赁


class ContractualRelationType(Enum):
    """契约关系类型"""
    EMPLOYMENT = "职场契约"  # 雇佣合同
    CIVIL_CONTRACT = "民事契约"  # 委托代理、担保
    VERBAL_AGREEMENT = "口头契约"  # 朋友借款、临时合作


class NonContractualRelationType(Enum):
    """无契约关系类型"""
    EMOTIONAL_RELATION = "情感类"  # 朋友、恋人
    SOCIAL_RELATION = "社交类"  # 陌生人、兴趣社群
    TEMPORARY_RELATION = "临时类"  # 同车乘客、活动参与者


# 按其他关键维度分类

class RelationDuration(Enum):
    """关系存续时间"""
    LONG_TERM = "长期关系"  # 数年以上
    MEDIUM_TERM = "中期关系"  # 项目周期内
    SHORT_TERM = "短期关系"  # 短期兼职
    TEMPORARY = "临时关系"  # 瞬间/单次互动


class PowerStructure(Enum):
    """权力结构与地位"""
    EQUAL = "平等关系"  # 朋友、同事
    SUBORDINATE = "从属关系"  # 上下级、师生
    DOMINANT = "支配关系"  # 霸凌、控制型


class InterestRelevance(Enum):
    """利益相关性"""
    PURE_EMOTIONAL = "纯情感关系"  # 挚友、灵魂伴侣
    PURE_INTEREST = "纯利益关系"  # 生意伙伴、借贷
    MIXED = "混合关系"  # 夫妻、同事


class CrossDimensional(Enum):
    """跨维度特征"""
    CROSS_GENERATION = "跨代关系"  # 祖孙、忘年交
    CROSS_CULTURE = "跨文化关系"  # 不同国籍/民族
    SPECIAL_INTERACTION = "特殊互动"  # 医患、律师委托人
    CONFLICT = "冲突型关系"  # 仇人


# 社交关系数值化数据模型

@dataclass
class SocialRelationComponent:
    """社交关系组件 - 单个关系类型及其数值"""
    relation_type: Any  # 关系类型枚举
    value: float  # 关系强度 [0, 1]
    frequency: int = 0  # 互动频率
    last_interaction: float = field(default_factory=time.time)
    created_at: float = field(default_factory=time.time)
    description: str = ""  # 关系描述
    tags: List[str] = field(default_factory=list)  # 关系标签

    def is_significant(self, threshold: float = 0.3) -> bool:
        """判断关系是否显著"""
        return self.value >= threshold

    def update_value(self, delta: float):
        """更新关系数值"""
        self.value = max(0.0, min(1.0, self.value + delta))

    def update_interaction(self):
        """更新互动记录"""
        self.frequency += 1
        self.last_interaction = time.time()


@dataclass
class UserSocialProfile:
    """用户社交关系档案 - 存储一个用户与他人的所有关系"""
    user_id: str
    group_id: str
    relations: List[SocialRelationComponent] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)

    # 社交特征统计
    total_relations: int = 0
    significant_relations: int = 0
    dominant_relation_type: Optional[str] = None

    def add_relation(self, relation: SocialRelationComponent):
        """添加关系组件"""
        self.relations.append(relation)
        self._update_statistics()

    def get_relation_by_type(self, relation_type: Any) -> Optional[SocialRelationComponent]:
        """根据类型获取关系"""
        for relation in self.relations:
            if relation.relation_type == relation_type:
                return relation
        return None

    def get_significant_relations(self, threshold: float = 0.3) -> List[SocialRelationComponent]:
        """获取显著的关系（数值高于阈值）"""
        return [r for r in self.relations if r.is_significant(threshold)]

    def _update_statistics(self):
        """更新统计信息"""
        self.total_relations = len(self.relations)
        self.significant_relations = len(self.get_significant_relations())
        self.last_updated = time.time()

        # 找出最强的关系类型
        if self.relations:
            dominant = max(self.relations, key=lambda r: r.value)
            self.dominant_relation_type = dominant.relation_type.value if hasattr(dominant.relation_type, 'value') else str(dominant.relation_type)

    def to_description(self) -> str:
        """生成人类可读的社交关系描述"""
        significant = self.get_significant_relations()
        if not significant:
            return "尚未建立显著的社交关系"

        descriptions = []
        for relation in significant[:5]:  # 只取前5个最重要的关系
            rel_name = relation.relation_type.value if hasattr(relation.relation_type, 'value') else str(relation.relation_type)
            strength = "非常强" if relation.value > 0.7 else "较强" if relation.value > 0.4 else "一般"
            descriptions.append(f"{rel_name}(强度:{strength})")

        return "、".join(descriptions)

    def to_prompt_injection(self) -> str:
        """生成用于注入到LLM prompt中的社交关系描述"""
        significant = self.get_significant_relations()
        if not significant:
            return ""

        prompt_parts = ["【该用户的社交关系】"]

        # 按强度排序
        sorted_relations = sorted(significant, key=lambda r: r.value, reverse=True)

        for i, relation in enumerate(sorted_relations[:10], 1):  # 最多显示10个
            rel_name = relation.relation_type.value if hasattr(relation.relation_type, 'value') else str(relation.relation_type)
            strength_desc = f"强度 {relation.value:.2f}"
            freq_desc = f"互动 {relation.frequency} 次"

            if relation.description:
                prompt_parts.append(f"{i}. {rel_name} ({strength_desc}, {freq_desc}): {relation.description}")
            else:
                prompt_parts.append(f"{i}. {rel_name} ({strength_desc}, {freq_desc})")

        prompt_parts.append("\n请根据以上社交关系调整对该用户的态度、语气和回复方式。")
        return "\n".join(prompt_parts)


# 社交关系变化规则

@dataclass
class RelationChangeRule:
    """社交关系变化规则"""
    trigger_event: str  # 触发事件
    relation_type: Any  # 关系类型
    value_change: float  # 数值变化
    frequency_change: int = 1  # 频率变化
    conditions: Dict[str, Any] = field(default_factory=dict)  # 触发条件

    def apply(self, relation: SocialRelationComponent, event_context: Dict[str, Any]) -> bool:
        """应用规则到关系组件"""
        # 检查条件
        for key, expected in self.conditions.items():
            if key not in event_context or event_context[key] != expected:
                return False

        # 应用变化
        relation.update_value(self.value_change)
        relation.frequency += self.frequency_change
        relation.update_interaction()
        return True


@dataclass
class RelationInfluenceOnPsychology:
    """社交关系对心理状态的影响规则"""
    relation_type: Any  # 社交关系类型
    relation_value_threshold: float  # 关系数值阈值
    interaction_type: str  # 交互类型（如：compliment, insult）
    psychological_impact: Dict[str, float]  # 对各心理状态的影响 {状态类别: 数值变化}
    trigger_probability: float = 1.0  # 触发概率

    def calculate_impact(self, relation_value: float) -> Dict[str, float]:
        """计算实际影响（考虑关系强度）"""
        if relation_value < self.relation_value_threshold:
            return {}

        # 关系越强，影响越大
        strength_multiplier = min(relation_value / self.relation_value_threshold, 2.0)

        return {
            category: change * strength_multiplier
            for category, change in self.psychological_impact.items()
        }
