"""
好感度管理服务 - 管理用户好感度系统和bot情绪状态
"""
import asyncio
import random
import time
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

from astrbot.api import logger

from ..config import PluginConfig

from ..core.patterns import AsyncServiceBase

from ..core.interfaces import IDataStorage

from ..core.framework_llm_adapter import FrameworkLLMAdapter  # 导入框架适配器


class MoodType(Enum):
    """情绪类型枚举"""
    HAPPY = "happy"
    SAD = "sad"
    EXCITED = "excited"
    CALM = "calm"
    ANGRY = "angry"
    ANXIOUS = "anxious"
    PLAYFUL = "playful"
    SERIOUS = "serious"
    NOSTALGIC = "nostalgic"
    CURIOUS = "curious"


class InteractionType(Enum):
    """交互类型枚举"""
    CHAT = "chat"              # 普通聊天
    COMPLIMENT = "compliment"  # 称赞
    FLIRT = "flirt"           # 撩拨
    COMFORT = "comfort"       # 安慰
    HELP = "help"             # 求助
    THANKS = "thanks"         # 感谢
    APOLOGY = "apology"       # 道歉
    TEASE = "tease"           # 调侃
    CARE = "care"             # 关心
    GIFT = "gift"             # 送礼物
    # 新增负面交互类型
    INSULT = "insult"         # 侮辱
    HARASSMENT = "harassment" # 骚扰
    ABUSE = "abuse"           # 谩骂
    THREAT = "threat"         # 威胁
    # 新增积极交互类型
    PRAISE = "praise"         # 夸赞
    ENCOURAGE = "encourage"   # 鼓励
    SUPPORT = "support"       # 支持


@dataclass
class BotMood:
    """Bot情绪状态"""
    mood_type: MoodType
    intensity: float  # 0.0 - 1.0
    description: str
    start_time: float
    duration_hours: int
    
    def is_active(self) -> bool:
        """检查情绪是否仍然活跃"""
        current_time = time.time()
        return current_time < (self.start_time + self.duration_hours * 3600)
    
    def get_mood_modifier(self) -> float:
        """获取情绪对好感度的修正系数"""
        mood_modifiers = {
            MoodType.HAPPY: 1.2,
            MoodType.EXCITED: 1.3,
            MoodType.PLAYFUL: 1.1,
            MoodType.CALM: 1.0,
            MoodType.CURIOUS: 1.05,
            MoodType.NOSTALGIC: 0.9,
            MoodType.SERIOUS: 0.8,
            MoodType.SAD: 0.6,
            MoodType.ANXIOUS: 0.7,
            MoodType.ANGRY: 0.4
        }
        base_modifier = mood_modifiers.get(self.mood_type, 1.0)
        return base_modifier * (0.5 + self.intensity * 0.5)


@dataclass
class UserAffection:
    """用户好感度"""
    user_id: str
    group_id: str
    affection_level: int
    last_interaction: float
    interaction_count: int
    
    def can_increase(self, max_level: int) -> bool:
        """检查是否可以增加好感度"""
        return self.affection_level < max_level


class AffectionManager(AsyncServiceBase):
    """好感度管理服务"""
    
    def __init__(self, config: PluginConfig, database_manager: IDataStorage, 
                 llm_adapter: Optional[FrameworkLLMAdapter] = None):
        super().__init__("affection_manager")
        self.config = config
        self.db_manager = database_manager
        
        # 使用框架适配器
        self.llm_adapter = llm_adapter
        
        # 情绪和好感度状态缓存
        self.current_moods: Dict[str, BotMood] = {}  # group_id -> BotMood
        self.user_affections: Dict[str, Dict[str, UserAffection]] = {}  # group_id -> {user_id -> UserAffection}
        
        # 预定义的情绪描述模板
        self.mood_descriptions = self._init_mood_descriptions()
        
        # 好感度变化规则
        self.affection_rules = self._init_affection_rules()
    
    async def _do_start(self) -> bool:
        """启动好感度管理服务"""
        try:
            # 为所有活跃群组设置初始随机情绪（如果启用）
            if self.config.enable_startup_random_mood:
                await self._initialize_random_moods_for_active_groups()
            
            # 启动每日情绪更新任务
            if self.config.enable_daily_mood:
                asyncio.create_task(self._daily_mood_updater())
            
            self._logger.info("好感度管理服务启动成功")
            return True
        except Exception as e:
            self._logger.error(f"好感度管理服务启动失败: {e}")
            return False
    
    async def _do_stop(self) -> bool:
        """停止好感度管理服务"""
        # 保存当前状态
        await self._save_current_state()
        return True
    
    def _init_mood_descriptions(self) -> Dict[MoodType, List[str]]:
        """初始化情绪描述模板"""
        return {
            MoodType.HAPPY: [
                "今天心情特别好，看什么都觉得很有趣呢~",
                "感觉整个世界都充满了阳光，好开心啊！",
                "今天是个美好的一天，想和大家多聊聊天~"
            ],
            MoodType.EXCITED: [
                "哇！感觉有好多有趣的事情要发生，好兴奋！",
                "今天充满了活力，什么都想尝试一下！",
                "感觉像是喝了好多咖啡，特别有精神~"
            ],
            MoodType.CALM: [
                "今天的心情很平静，适合安静地聊天。",
                "感觉内心很宁静，想听听大家的故事。",
                "今天想要慢节奏地度过，不着急。"
            ],
            MoodType.PLAYFUL: [
                "今天想要开点小玩笑，大家别介意哦~",
                "感觉特别想玩，有什么有趣的游戏吗？",
                "今天的心情很调皮，想逗大家开心！"
            ],
            MoodType.SAD: [
                "今天有点忧郁，需要大家的安慰呢...",
                "心情有些低落，希望能得到一些温暖的话语。",
                "感觉有点孤单，想要更多的陪伴。"
            ],
            MoodType.ANXIOUS: [
                "今天有些紧张不安，需要大家多包容一下。",
                "感觉心里有点忐忑，不太确定该怎么办。",
                "今天的状态不是很稳定，可能反应会有点慢。"
            ],
            MoodType.ANGRY: [
                "今天心情不太好，可能说话会比较直接。",
                "感觉有些烦躁，需要一些时间平静下来。",
                "今天不太想被打扰，希望大家理解。"
            ],
            MoodType.SERIOUS: [
                "今天想要认真讨论一些问题，专注一点。",
                "感觉需要集中精力，暂时不太想开玩笑。",
                "今天的心境比较严肃，想深入思考。"
            ],
            MoodType.NOSTALGIC: [
                "今天想起了很多过往的事情，有点怀念。",
                "感觉很想回忆以前的美好时光。",
                "今天的心情有些感性，容易触景生情。"
            ],
            MoodType.CURIOUS: [
                "今天对什么都很好奇，想了解更多！",
                "感觉有好多问题想问，希望大家不要嫌烦。",
                "今天的求知欲特别强，想学习新的东西。"
            ]
        }
    
    def _init_affection_rules(self) -> Dict[InteractionType, Dict]:
        """初始化好感度变化规则"""
        return {
            # 积极交互
            InteractionType.CHAT: {
                "base_change": 1,
                "mood_sensitive": True,
                "mood_effect": 0.1,  # 对情绪的影响程度
                "description": "普通聊天"
            },
            InteractionType.COMPLIMENT: {
                "base_change": 3,
                "mood_sensitive": True,
                "mood_effect": 0.2,
                "description": "称赞鼓励"
            },
            InteractionType.PRAISE: {
                "base_change": 5,
                "mood_sensitive": True,
                "mood_effect": 0.3,
                "positive_mood_boost": True,  # 提升积极情绪
                "description": "夸赞表扬"
            },
            InteractionType.ENCOURAGE: {
                "base_change": 4,
                "mood_sensitive": True,
                "mood_effect": 0.25,
                "positive_mood_boost": True,
                "description": "鼓励支持"
            },
            InteractionType.SUPPORT: {
                "base_change": 4,
                "mood_sensitive": True,
                "mood_effect": 0.2,
                "description": "支持认同"
            },
            InteractionType.FLIRT: {
                "base_change": 5,
                "mood_sensitive": True,
                "mood_effect": 0.15,
                "mood_requirements": [MoodType.HAPPY, MoodType.PLAYFUL, MoodType.EXCITED],
                "description": "撩拨调情"
            },
            InteractionType.COMFORT: {
                "base_change": 4,
                "mood_sensitive": True,
                "mood_effect": 0.3,
                "mood_requirements": [MoodType.SAD, MoodType.ANXIOUS],
                "description": "安慰关怀"
            },
            InteractionType.HELP: {
                "base_change": 2,
                "mood_sensitive": False,
                "mood_effect": 0.1,
                "description": "寻求帮助"
            },
            InteractionType.THANKS: {
                "base_change": 2,
                "mood_sensitive": True,
                "mood_effect": 0.15,
                "description": "表达感谢"
            },
            InteractionType.APOLOGY: {
                "base_change": 1,
                "mood_sensitive": True,
                "mood_effect": 0.1,
                "mood_requirements": [MoodType.ANGRY, MoodType.SAD],
                "description": "道歉认错"
            },
            InteractionType.TEASE: {
                "base_change": 2,
                "mood_sensitive": True,
                "mood_effect": 0.1,
                "mood_requirements": [MoodType.PLAYFUL, MoodType.HAPPY],
                "description": "善意调侃"
            },
            InteractionType.CARE: {
                "base_change": 3,
                "mood_sensitive": True,
                "mood_effect": 0.2,
                "description": "关心问候"
            },
            InteractionType.GIFT: {
                "base_change": 8,
                "mood_sensitive": True,
                "mood_effect": 0.4,
                "positive_mood_boost": True,
                "description": "赠送礼物"
            },
            
            # 负面交互
            InteractionType.INSULT: {
                "base_change": -8,
                "mood_sensitive": True,
                "mood_effect": -0.5,  # 负面影响情绪
                "negative_mood_trigger": True,  # 触发负面情绪
                "description": "侮辱攻击"
            },
            InteractionType.HARASSMENT: {
                "base_change": -6,
                "mood_sensitive": True,
                "mood_effect": -0.4,
                "negative_mood_trigger": True,
                "description": "骚扰行为"
            },
            InteractionType.ABUSE: {
                "base_change": -10,
                "mood_sensitive": True,
                "mood_effect": -0.6,
                "negative_mood_trigger": True,
                "description": "恶意谩骂"
            },
            InteractionType.THREAT: {
                "base_change": -12,
                "mood_sensitive": True,
                "mood_effect": -0.7,
                "negative_mood_trigger": True,
                "trigger_fear": True,  # 触发恐惧情绪
                "description": "威胁恐吓"
            }
        }
    
    async def get_current_mood(self, group_id: str) -> Optional[BotMood]:
        """获取当前bot情绪"""
        # 先检查内存缓存
        if group_id in self.current_moods:
            mood = self.current_moods[group_id]
            if mood.is_active():
                return mood
            else:
                # 情绪过期，移除缓存
                del self.current_moods[group_id]
        
        # 从数据库加载
        mood_data = await self.db_manager.get_current_bot_mood(group_id)
        if mood_data:
            try:
                mood = BotMood(
                    mood_type=MoodType(mood_data['mood_type']),
                    intensity=mood_data['mood_intensity'],
                    description=mood_data['mood_description'],
                    start_time=mood_data['start_time'],
                    duration_hours=int((mood_data['end_time'] - mood_data['start_time']) / 3600)
                )
                if mood.is_active():
                    self.current_moods[group_id] = mood
                    return mood
            except Exception as e:
                self._logger.error(f"解析情绪数据失败: {e}")
        
        return None
    
    async def set_random_daily_mood(self, group_id: str) -> BotMood:
        """设置随机的每日情绪"""
        # 随机选择情绪类型
        mood_type = random.choice(list(MoodType))
        intensity = random.uniform(0.3, 0.9)
        
        # 随机选择描述
        descriptions = self.mood_descriptions.get(mood_type, ["今天的心情很特别。"])
        description = random.choice(descriptions)
        
        # 创建情绪对象
        mood = BotMood(
            mood_type=mood_type,
            intensity=intensity,
            description=description,
            start_time=time.time(),
            duration_hours=self.config.mood_persistence_hours
        )
        
        # 保存到数据库和缓存
        await self.db_manager.save_bot_mood(
            group_id, mood_type.value, intensity, description, mood.duration_hours
        )
        self.current_moods[group_id] = mood
        
        self._logger.info(f"为群 {group_id} 设置新的每日情绪: {mood_type.value} ({intensity:.2f})")
        return mood
    
    async def ensure_mood_for_group(self, group_id: str) -> Optional[BotMood]:
        """确保指定群组有情绪状态，如果没有则创建随机情绪"""
        try:
            # 先检查是否已有活跃情绪
            current_mood = await self.get_current_mood(group_id)
            if current_mood and current_mood.is_active():
                return current_mood
            
            # 如果没有活跃情绪，设置随机情绪
            self._logger.info(f"群组 {group_id} 没有活跃情绪，正在设置随机情绪...")
            return await self.set_random_daily_mood(group_id)
            
        except Exception as e:
            self._logger.error(f"为群组 {group_id} 确保情绪状态失败: {e}")
            return None
    
    async def _initialize_random_moods_for_active_groups(self):
        """为所有活跃群组初始化随机情绪"""
        try:
            # 获取所有活跃群组列表
            active_groups = await self._get_active_groups()
            
            if not active_groups:
                self._logger.info("没有发现活跃群组，跳过情绪初始化")
                return
            
            initialized_count = 0
            for group_id in active_groups:
                try:
                    # 检查该群组是否已经有活跃情绪
                    current_mood = await self.get_current_mood(group_id)
                    if current_mood and current_mood.is_active():
                        self._logger.debug(f"群组 {group_id} 已有活跃情绪，跳过初始化")
                        continue
                    
                    # 设置随机初始情绪
                    await self.set_random_daily_mood(group_id)
                    initialized_count += 1
                    
                    # 避免同时初始化过多群组
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    self._logger.error(f"为群组 {group_id} 初始化随机情绪失败: {e}")
            
            self._logger.info(f"成功为 {initialized_count} 个群组初始化了随机情绪")
            
        except Exception as e:
            self._logger.error(f"初始化群组随机情绪失败: {e}")
    
    async def _get_active_groups(self) -> List[str]:
        """获取活跃群组列表（从数据库中获取最近有消息的群组）"""
        try:
            # 从数据库获取最近24小时内有消息的群组
            async with self.db_manager.get_db_connection() as conn:
                cursor = await conn.cursor()
                
                # 先尝试获取最近24小时内有消息的群组
                cutoff_time = time.time() - 86400  # 24小时前
                await cursor.execute('''
                    SELECT DISTINCT group_id, COUNT(*) as msg_count
                    FROM raw_messages 
                    WHERE timestamp > ? AND group_id IS NOT NULL AND group_id != ''
                    GROUP BY group_id
                    HAVING msg_count >= 3
                    ORDER BY msg_count DESC
                    LIMIT 20
                ''', (cutoff_time,))
                
                active_groups = []
                for row in await cursor.fetchall():
                    if row[0]:  # 确保group_id不为空
                        active_groups.append(row[0])
                
                # 如果24小时内没有活跃群组，扩大时间范围到7天，降低消息数要求
                if not active_groups:
                    cutoff_time = time.time() - 604800  # 7天前
                    await cursor.execute('''
                        SELECT DISTINCT group_id, COUNT(*) as msg_count
                        FROM raw_messages 
                        WHERE timestamp > ? AND group_id IS NOT NULL AND group_id != ''
                        GROUP BY group_id
                        HAVING msg_count >= 1
                        ORDER BY msg_count DESC
                        LIMIT 10
                    ''', (cutoff_time,))
                    
                    for row in await cursor.fetchall():
                        if row[0]:  # 确保group_id不为空
                            active_groups.append(row[0])
                
                # 如果还是没有，获取所有有消息记录的群组
                if not active_groups:
                    await cursor.execute('''
                        SELECT DISTINCT group_id
                        FROM raw_messages 
                        WHERE group_id IS NOT NULL AND group_id != ''
                        LIMIT 5
                    ''')
                    
                    for row in await cursor.fetchall():
                        if row[0]:  # 确保group_id不为空
                            active_groups.append(row[0])
                
                await cursor.close()
            
            self._logger.info(f"找到 {len(active_groups)} 个活跃群组用于情绪初始化")
            return active_groups
            
        except Exception as e:
            self._logger.error(f"获取活跃群组列表失败: {e}")
            # 返回空列表，让调用者决定如何处理
            return []
    
    
    async def analyze_interaction_type(self, group_id: str, user_id: str, message: str) -> InteractionType:
        """使用LLM主分析，规则作为备选"""
        try:
            # 首先使用LLM进行智能分析
            current_mood = await self.get_current_mood(group_id)
            mood_context = f"当前心情：{current_mood.description}" if current_mood else "心情未知"
            
            analysis_prompt = f"""
            请分析以下用户消息属于什么类型的交互行为：
            
            用户消息：{message}
            机器人{mood_context}
            
            可能的交互类型：
            积极类型：
            - chat: 普通聊天
            - compliment: 称赞鼓励 (例如：你好美、你真棒、好厉害等)
            - praise: 夸赞表扬 (例如：做得好、很优秀等)
            - encourage: 鼓励支持
            - support: 支持认同
            - flirt: 撩拨调情 (例如：好看、漂亮、可爱等)
            - comfort: 安慰关怀
            - help: 寻求帮助
            - thanks: 表达感谢
            - apology: 道歉认错
            - tease: 善意调侃
            - care: 关心问候 (例如：你好吗、怎么样等)
            - gift: 赠送礼物
            
            负面类型：
            - insult: 明确的侮辱攻击 (例如：蠢货、白痴、垃圾等恶毒词汇)
            - harassment: 骚扰行为 (例如：持续骚扰、不当言论等)
            - abuse: 恶意谩骂 (例如：脏话、恶毒攻击等)
            - threat: 威胁恐吓 (例如：威胁、恐吓等)
            
            请仔细分析消息的情感色彩和意图，特别注意：
            1. "你好美"、"很漂亮"、"真可爱"等是赞美，应归类为compliment或flirt
            2. 只有明确包含侮辱、攻击性词汇时才是insult
            3. 只有真正的骚扰、威胁性表达才是负面类型
            4. 当不确定时，优先选择积极类型或chat
            
            请只返回一个类型名称，不要其他内容。
            """
            
            # 使用框架适配器进行分析
            if self.llm_adapter and self.llm_adapter.has_filter_provider():
                try:
                    response = await self.llm_adapter.filter_chat_completion(
                        prompt=analysis_prompt,
                        temperature=0.1
                    )
                    
                    if response:
                        result = response.strip().lower()
                        try:
                            return InteractionType(result)
                        except ValueError:
                            # LLM返回无效结果，使用规则作为备选
                            self._logger.warning(f"LLM返回无效的交互类型: {result}，使用规则分析作为备选")
                            rule_based_type = self._rule_based_interaction_analysis(message)
                            return rule_based_type if rule_based_type else InteractionType.CHAT
                except Exception as e:
                    self._logger.error(f"框架适配器分析交互类型失败: {e}，使用规则分析作为备选")
            
        except Exception as e:
            self._logger.error(f"LLM分析交互类型失败: {e}，使用规则分析作为备选")
        
        # 如果LLM分析失败，使用基于规则的备选方案
        rule_based_type = self._rule_based_interaction_analysis(message)
        return rule_based_type if rule_based_type else InteractionType.CHAT
    
    def _rule_based_interaction_analysis(self, message: str) -> Optional[InteractionType]:
        """基于规则的交互类型分析（备选方案，当LLM分析失败时使用）"""
        message_lower = message.lower().strip()
        
        # 明确的赞美词汇
        compliment_keywords = [
            '好美', '漂亮', '可爱', '帅', '美丽', '好看', '美', '棒', '厉害', 
            '优秀', '聪明', '温柔', '体贴', '贴心', '善良', '完美', '很棒',
            '真好', '不错', '赞', '给力', '牛', '强', '6', '666', '牛逼',
            '好', '好的', '好啊', '好呀', '棒棒', '太棒了', '真棒', '真厉害',
            '哇', '哇塞', '厉害了', '太好了', '好厉害', '好强', '好棒', '赞赞',
            '牛牛', '牛b', 'nb', '牛批', '牛皮', '好牛', '超棒', '超好',
            '很好', '很棒', '很厉害', '太厉害了', '好喜欢', '喜欢你', '爱了',
            '太可爱了', '好可爱', '可爱爆了', '萌', '萌萌', '好萌'
        ]
        
        # 感谢词汇
        thanks_keywords = ['谢谢', '感谢', '多谢', 'thank', '谢', 'thx', '谢啦', '谢了']
        
        # 问候词汇  
        care_keywords = [
            '你好', '早上好', '晚上好', '怎么样', '最近好吗', 'hello', 'hi',
            '嗨', '哈喽', '哈罗', '安', '早', '晚安', '午安', '下午好',
            '你在吗', '在吗', '你在不在', '在不在', '你好呀', '你好啊'
        ]
        
        # 明确的负面词汇
        negative_keywords = [
            '傻逼', '蠢货', '白痴', '垃圾', '废物', '滚', '死', '去死',
            '操', '草', '妈的', '他妈', '狗', '畜生', '贱', '婊'
        ]
        
        # 威胁词汇
        threat_keywords = ['威胁', '杀', '打死', '弄死', '干掉', '揍', '打你']
        
        # 检查赞美
        for keyword in compliment_keywords:
            if keyword in message_lower:
                self._logger.info(f"规则匹配到赞美关键词 '{keyword}' 在消息 '{message}' 中")
                return InteractionType.COMPLIMENT
        
        # 检查感谢
        for keyword in thanks_keywords:
            if keyword in message_lower:
                return InteractionType.THANKS
        
        # 检查问候
        for keyword in care_keywords:
            if keyword in message_lower:
                return InteractionType.CARE
                
        # 检查威胁
        for keyword in threat_keywords:
            if keyword in message_lower:
                return InteractionType.THREAT
        
        # 检查侮辱
        for keyword in negative_keywords:
            if keyword in message_lower:
                return InteractionType.INSULT
        
        # 如果都没匹配到，返回None让LLM分析
        return None

    async def update_affection(self, group_id: str, user_id: str, 
                             interaction_type: InteractionType) -> Dict[str, Any]:
        """更新用户好感度"""
        try:
            # 获取当前好感度
            current_affection = await self.db_manager.get_user_affection(group_id, user_id)
            if not current_affection:
                current_level = 0
            else:
                current_level = current_affection['affection_level']
            
            # 获取当前情绪
            current_mood = await self.get_current_mood(group_id)
            
            # 计算好感度变化
            change_result = self._calculate_affection_change(
                interaction_type, current_level, current_mood
            )
            
            # 处理情绪动态响应
            await self._handle_mood_response(group_id, interaction_type, current_mood)
            
            if not change_result['can_change']:
                return {
                    'success': False,
                    'reason': change_result['reason'],
                    'current_level': current_level,
                    'change': 0
                }
            
            new_level = current_level + change_result['change']
            new_level = max(0, min(new_level, self.config.max_user_affection))
            
            # 检查总好感度限制
            if new_level > current_level:
                total_affection = await self.db_manager.get_total_affection(group_id)
                if total_affection >= self.config.max_total_affection:
                    # 需要降低其他用户的好感度
                    await self._redistribute_affection(group_id, user_id, new_level - current_level)
            
            # 更新数据库
            mood_str = f"{current_mood.mood_type.value}({current_mood.intensity:.2f})" if current_mood else "unknown"
            success = await self.db_manager.update_user_affection(
                group_id, user_id, new_level,
                change_result['reason'], mood_str
            )
            
            if success:
                return {
                    'success': True,
                    'previous_level': current_level,
                    'new_level': new_level,
                    'change': new_level - current_level,
                    'reason': change_result['reason'],
                    'mood': mood_str
                }
            else:
                return {
                    'success': False,
                    'reason': "数据库更新失败",
                    'current_level': current_level,
                    'change': 0
                }
                
        except Exception as e:
            self._logger.error(f"更新好感度失败: {e}")
            return {
                'success': False,
                'reason': f"系统错误: {str(e)}",
                'current_level': 0,
                'change': 0
            }
    
    def _calculate_affection_change(self, interaction_type: InteractionType, 
                                   current_level: int, current_mood: Optional[BotMood]) -> Dict[str, Any]:
        """计算好感度变化"""
        rule = self.affection_rules.get(interaction_type, self.affection_rules[InteractionType.CHAT])
        
        # 检查情绪要求
        if 'mood_requirements' in rule and current_mood:
            if current_mood.mood_type not in rule['mood_requirements']:
                return {
                    'can_change': False,
                    'change': 0,
                    'reason': f"当前心情({current_mood.mood_type.value})不适合{rule['description']}"
                }
        
        # 计算基础变化
        base_change = rule['base_change']
        
        # 应用情绪修正
        if rule['mood_sensitive'] and current_mood:
            mood_modifier = current_mood.get_mood_modifier()
            actual_change = int(base_change * mood_modifier)
        else:
            actual_change = base_change
        
        # 检查是否已达到上限
        if current_level >= self.config.max_user_affection and actual_change > 0:
            return {
                'can_change': False,
                'change': 0,
                'reason': "好感度已达到上限"
            }
        
        return {
            'can_change': True,
            'change': actual_change,
            'reason': rule['description']
        }
    
    async def _handle_mood_response(self, group_id: str, interaction_type: InteractionType, 
                                   current_mood: Optional[BotMood]):
        """处理情绪动态响应"""
        try:
            rule = self.affection_rules.get(interaction_type)
            if not rule:
                return
            
            mood_effect = rule.get('mood_effect', 0)
            
            # 如果情绪影响为0或很小，不进行处理
            if abs(mood_effect) < 0.1:
                return
            
            # 处理负面交互触发的情绪变化
            if rule.get('negative_mood_trigger', False):
                await self._trigger_negative_mood_response(group_id, interaction_type, mood_effect)
            
            # 处理积极交互触发的情绪提升
            elif rule.get('positive_mood_boost', False):
                await self._trigger_positive_mood_response(group_id, interaction_type, mood_effect)
            
            # 处理一般情绪调整
            else:
                await self._adjust_current_mood(group_id, current_mood, mood_effect)
                
        except Exception as e:
            self._logger.error(f"处理情绪响应失败: {e}")
    
    async def _trigger_negative_mood_response(self, group_id: str, interaction_type: InteractionType, 
                                            mood_effect: float):
        """触发负面情绪响应"""
        try:
            # 根据交互类型确定情绪类型
            if interaction_type == InteractionType.THREAT:
                new_mood_type = MoodType.ANXIOUS
                descriptions = [
                    "感到被威胁，心情变得紧张不安...",
                    "受到恐吓，现在有些害怕和担心。",
                    "被威胁让我感到很不安全。"
                ]
            elif interaction_type == InteractionType.ABUSE:
                new_mood_type = MoodType.ANGRY
                descriptions = [
                    "被恶意谩骂，现在心情很愤怒！",
                    "受到恶毒攻击，感到非常生气。",
                    "恶语相向让我感到愤怒和受伤。"
                ]
            elif interaction_type == InteractionType.INSULT:
                new_mood_type = MoodType.SAD
                descriptions = [
                    "被侮辱攻击，心情变得很低落...",
                    "受到攻击，感到伤心和失望。",
                    "被人侮辱让我感到很难过。"
                ]
            else:  # HARASSMENT
                new_mood_type = MoodType.ANXIOUS
                descriptions = [
                    "被骚扰困扰，现在感到很不安。",
                    "持续的骚扰让我感到紧张。",
                    "这种行为让我感到不舒服。"
                ]
            
            # 计算情绪强度（负面情绪通常比较强烈）
            intensity = min(0.9, abs(mood_effect))
            description = random.choice(descriptions)
            
            # 设置新的负面情绪
            await self._set_immediate_mood(group_id, new_mood_type, intensity, description, 2)  # 持续2小时
            
            self._logger.info(f"群 {group_id} 触发负面情绪响应: {new_mood_type.value} ({intensity:.2f})")
            
        except Exception as e:
            self._logger.error(f"触发负面情绪响应失败: {e}")
    
    async def _trigger_positive_mood_response(self, group_id: str, interaction_type: InteractionType, 
                                            mood_effect: float):
        """触发积极情绪响应"""
        try:
            # 根据交互类型确定积极情绪
            if interaction_type in [InteractionType.PRAISE, InteractionType.ENCOURAGE]:
                new_mood_type = MoodType.HAPPY
                descriptions = [
                    "被夸赞鼓励，心情变得很开心！",
                    "收到赞美，感到特别高兴。",
                    "这些鼓励的话让我心情大好！"
                ]
            elif interaction_type == InteractionType.GIFT:
                new_mood_type = MoodType.EXCITED
                descriptions = [
                    "收到礼物，太兴奋了！",
                    "有人送礼物给我，好开心好激动！",
                    "这个礼物让我感到非常兴奋！"
                ]
            else:
                new_mood_type = MoodType.HAPPY
                descriptions = [
                    "感受到善意，心情变好了。",
                    "这种关怀让我感到温暖。",
                    "谢谢你的友好，我心情好多了。"
                ]
            
            # 积极情绪强度适中
            intensity = min(0.8, mood_effect)
            description = random.choice(descriptions)
            
            # 设置新的积极情绪，持续时间较长
            await self._set_immediate_mood(group_id, new_mood_type, intensity, description, 4)  # 持续4小时
            
            self._logger.info(f"群 {group_id} 触发积极情绪响应: {new_mood_type.value} ({intensity:.2f})")
            
        except Exception as e:
            self._logger.error(f"触发积极情绪响应失败: {e}")
    
    async def _adjust_current_mood(self, group_id: str, current_mood: Optional[BotMood], 
                                  mood_effect: float):
        """调整当前情绪强度"""
        try:
            if not current_mood:
                return
            
            # 调整当前情绪的强度
            new_intensity = current_mood.intensity + mood_effect
            new_intensity = max(0.1, min(0.9, new_intensity))
            
            # 如果强度变化较大，更新情绪
            if abs(new_intensity - current_mood.intensity) > 0.1:
                await self._set_immediate_mood(
                    group_id, current_mood.mood_type, new_intensity, 
                    current_mood.description, 1  # 短时间调整
                )
                
        except Exception as e:
            self._logger.error(f"调整当前情绪失败: {e}")
    
    async def _set_immediate_mood(self, group_id: str, mood_type: MoodType, 
                                 intensity: float, description: str, duration_hours: int):
        """立即设置新情绪（用于动态响应）"""
        try:
            mood = BotMood(
                mood_type=mood_type,
                intensity=intensity,
                description=description,
                start_time=time.time(),
                duration_hours=duration_hours
            )
            
            # 保存到数据库并更新缓存
            await self.db_manager.save_bot_mood(
                group_id, mood_type.value, intensity, description, duration_hours
            )
            self.current_moods[group_id] = mood
            
        except Exception as e:
            self._logger.error(f"设置即时情绪失败: {e}")
    
    async def _redistribute_affection(self, group_id: str, target_user_id: str, increase_amount: int):
        """重新分配好感度以保持总量限制"""
        try:
            # 获取所有用户的好感度
            all_affections = await self.db_manager.get_all_user_affections(group_id)
            
            # 计算需要减少的总量
            total_to_decrease = increase_amount
            
            # 按好感度从高到低排序，优先减少高好感度用户
            other_users = [a for a in all_affections if a['user_id'] != target_user_id]
            other_users.sort(key=lambda x: x['affection_level'], reverse=True)
            
            # 按比例减少其他用户的好感度
            for user_affection in other_users:
                if total_to_decrease <= 0:
                    break
                
                current_level = user_affection['affection_level']
                if current_level <= 0:
                    continue
                
                # 计算这个用户应该减少的量（按当前好感度比例）
                decrease_ratio = min(1.0, total_to_decrease / sum(u['affection_level'] for u in other_users))
                decrease_amount = max(1, int(current_level * decrease_ratio * self.config.affection_decay_rate))
                decrease_amount = min(decrease_amount, current_level, total_to_decrease)
                
                new_level = current_level - decrease_amount
                await self.db_manager.update_user_affection(
                    group_id, user_affection['user_id'], new_level,
                    f"好感度重新分配，为其他用户让出空间", ""
                )
                
                total_to_decrease -= decrease_amount
                
        except Exception as e:
            self._logger.error(f"重新分配好感度失败: {e}")
    
    async def get_mood_influenced_system_prompt(self, group_id: str, base_prompt: str) -> str:
        """获取受情绪影响的系统提示词"""
        current_mood = await self.get_current_mood(group_id)
        if not current_mood:
            return base_prompt
        
        # 如果base_prompt为空，使用默认提示词
        if not base_prompt:
            base_prompt = "你是一个智能助手。"
        
        mood_prompts = {
            MoodType.HAPPY: "你现在心情很好，说话比较活泼开朗，容易表达正面情感。",
            MoodType.SAD: "你现在心情有些低落，说话比较温和，需要更多的理解和安慰。",
            MoodType.EXCITED: "你现在很兴奋，说话比较有活力，对很多事情都很感兴趣。",
            MoodType.CALM: "你现在心情平静，说话比较稳重，给人安全感。",
            MoodType.ANGRY: "你现在心情不太好，说话可能比较直接，不太有耐心。",
            MoodType.ANXIOUS: "你现在有些紧张不安，说话可能比较谨慎，需要更多确认。",
            MoodType.PLAYFUL: "你现在心情很调皮，喜欢开玩笑，说话比较幽默风趣。",
            MoodType.SERIOUS: "你现在比较严肃认真，说话简洁直接，专注于重要的事情。",
            MoodType.NOSTALGIC: "你现在有些怀旧情绪，说话带有回忆色彩，比较感性。",
            MoodType.CURIOUS: "你现在对很多事情都很好奇，喜欢提问和探索新事物。"
        }
        
        mood_prompt = mood_prompts.get(current_mood.mood_type, "")
        intensity_modifier = "非常" if current_mood.intensity > 0.7 else "有些" if current_mood.intensity > 0.4 else "轻微"
        
        final_mood_prompt = f"{mood_prompt.replace('现在', f'现在{intensity_modifier}')}"
        
        # 检查base_prompt中是否已经包含情绪状态信息，避免重复添加
        mood_keywords = ["当前情绪状态", "心情", "情绪", "【当前情绪状态", "【增量更新"]
        has_existing_mood = any(keyword in base_prompt for keyword in mood_keywords)
        
        if has_existing_mood:
            # 如果已经包含情绪信息，直接返回base_prompt
            self._logger.info("Base prompt已包含情绪状态信息，跳过重复添加")
            return base_prompt
        
        return f"{base_prompt}\n\n当前情绪状态：{current_mood.description} {final_mood_prompt}\n\n请根据以上情绪状态调整你的回复风格和语气。"
    
    async def _daily_mood_updater(self):
        """每日情绪更新任务"""
        while True:
            try:
                current_hour = datetime.now().hour
                if current_hour == self.config.mood_change_hour:
                    # 为所有活跃群组更新情绪
                    # 这里需要获取活跃群组列表，简化实现暂时跳过
                    # await self._update_all_group_moods()
                    pass
                
                # 每小时检查一次
                await asyncio.sleep(3600)
                
            except Exception as e:
                self._logger.error(f"每日情绪更新失败: {e}")
                await asyncio.sleep(3600)
    
    async def _save_current_state(self):
        """保存当前状态到数据库"""
        try:
            # 当前的情绪状态已经在设置时保存到数据库了
            # 这里可以添加其他需要持久化的状态
            self._logger.info("好感度管理服务状态已保存")
        except Exception as e:
            self._logger.error(f"保存状态失败: {e}")
    
    async def get_affection_status(self, group_id: str) -> Dict[str, Any]:
        """获取群组好感度状态"""
        try:
            all_affections = await self.db_manager.get_all_user_affections(group_id)
            total_affection = sum(a['affection_level'] for a in all_affections)
            current_mood = await self.get_current_mood(group_id)
            
            return {
                'total_affection': total_affection,
                'max_total_affection': self.config.max_total_affection,
                'user_count': len(all_affections),
                'top_users': all_affections[:5],  # 前5名
                'current_mood': {
                    'type': current_mood.mood_type.value if current_mood else None,
                    'intensity': current_mood.intensity if current_mood else None,
                    'description': current_mood.description if current_mood else None
                } if current_mood else None
            }
            
        except Exception as e:
            self._logger.error(f"获取好感度状态失败: {e}")
            return {
                'total_affection': 0,
                'max_total_affection': self.config.max_total_affection,
                'user_count': 0,
                'top_users': [],
                'current_mood': None
            }
    
    async def process_message_interaction(self, group_id: str, user_id: str, message: str) -> Dict[str, Any]:
        """处理用户消息交互的主要入口方法"""
        try:
            # 记录交互开始（用于调试）
            self._logger.info(f"开始处理消息交互: group_id={group_id}, user_id={user_id[:8]}..., message_len={len(message)}")
            
            # 1. 分析交互类型
            interaction_type = await self.analyze_interaction_type(group_id, user_id, message)
            self._logger.info(f"交互类型分析结果: {interaction_type.value} (group: {group_id})")
            
            # 2. 更新好感度
            affection_result = await self.update_affection(group_id, user_id, interaction_type)
            if affection_result.get('success'):
                self._logger.info(f"好感度更新成功: 用户{user_id[:8]}... 在群{group_id} 的好感度从 {affection_result.get('previous_level', 0)} 变为 {affection_result.get('new_level', 0)} (变化: {affection_result.get('change', 0)})")
            else:
                self._logger.warning(f"好感度更新失败: {affection_result.get('reason', '未知原因')}")
            
            # 3. 获取更新后的情绪状态
            current_mood = await self.get_current_mood(group_id)
            
            # 4. 返回完整的处理结果
            return {
                'success': True,
                'interaction_type': interaction_type.value,
                'affection_result': affection_result,
                'current_mood': {
                    'type': current_mood.mood_type.value if current_mood else None,
                    'intensity': current_mood.intensity if current_mood else None,
                    'description': current_mood.description if current_mood else None
                } if current_mood else None,
                'message': f"处理{interaction_type.value}交互成功"
            }
            
        except Exception as e:
            self._logger.error(f"处理消息交互失败: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'interaction_type': 'unknown',
                'affection_result': {'success': False, 'reason': '系统错误'},
                'current_mood': None
            }