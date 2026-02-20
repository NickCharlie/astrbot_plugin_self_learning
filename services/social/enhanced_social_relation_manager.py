"""
增强的社交关系管理器 - 管理用户之间的多维度社交关系
支持多种关系类型的数值化管理,每种关系都有独立的数值[0,1]和变化难度系数
"""
import asyncio
import random
import time
import json
from typing import Dict, List, Optional, Any, Tuple

from astrbot.api import logger

from ...config import PluginConfig
from ...core.patterns import AsyncServiceBase
from ...core.interfaces import IDataStorage
from ...core.framework_llm_adapter import FrameworkLLMAdapter

from ...models.social_relation import (
    BloodRelationType, GeographicalRelationType, CareerRelationType,
    EmotionalRelationType, InterestRelationType,
    IntimacyLevel, RelationDuration, PowerStructure,
    SocialRelationComponent, UserSocialProfile,
    RelationChangeRule, RelationInfluenceOnPsychology
)


class EnhancedSocialRelationManager(AsyncServiceBase):
    """
    增强的社交关系管理器

    核心功能:
    1. 管理用户之间的多维度社交关系
    2. 每种关系类型都有独立的数值[0,1]
    3. 不同关系类型有不同的变化难度(如血缘关系极难变化)
    4. 社交关系变化会影响心理状态
    5. 使用LLM智能分析关系类型和强度
    """

    def __init__(self, config: PluginConfig, database_manager: IDataStorage,
                 llm_adapter: Optional[FrameworkLLMAdapter] = None,
                 psychological_state_manager=None):
        super().__init__("enhanced_social_relation_manager")
        self.config = config
        self.db_manager = database_manager
        self.llm_adapter = llm_adapter
        self.psych_manager = psychological_state_manager

        # 用户社交档案缓存 {(user_id, group_id): UserSocialProfile}
        self.user_profiles: Dict[Tuple[str, str], UserSocialProfile] = {}

        # 关系类型的变化难度系数 (0=极易变化, 1=几乎不变)
        self.relation_change_difficulty = self._init_relation_difficulty()

        # 关系变化规则
        self.relation_change_rules = self._init_relation_change_rules()

        # 关系对心理状态的影响规则
        self.relation_psych_influence = self._init_relation_psych_influence()

    def _init_relation_difficulty(self) -> Dict[str, float]:
        """
        初始化关系类型的变化难度系数

        Returns:
            Dict[关系类型名称, 难度系数(0-1)]
            - 0: 极易变化 (如临时地缘、搭子关系)
            - 0.3: 较易变化 (如普通朋友、同事)
            - 0.6: 较难变化 (如挚友、长期恋人)
            - 0.9: 极难变化 (如血缘关系、法定关系)
        """
        return {
            # 血缘关系 - 几乎不变
            "父母子女": 0.98,
            "祖孙": 0.98,
            "兄弟姐妹": 0.95,
            "堂表兄弟姐妹": 0.92,
            "姻亲": 0.90,
            "领养关系": 0.88,

            # 地缘关系 - 中等难度
            "邻居": 0.40,
            "同村村民": 0.45,
            "同乡": 0.50,
            "同校": 0.55,
            "同车乘客": 0.05, # 临时关系,易变

            # 业缘关系 - 中等到较高难度
            "上下级": 0.65,
            "导师学徒": 0.70,
            "同事": 0.35,
            "前同事": 0.45,
            "师生": 0.75,
            "同学": 0.60,
            "校友": 0.55,
            "同桌": 0.50,
            "舍友": 0.50,
            "合伙人": 0.70,

            # 情缘关系 - 较高难度
            "恋人": 0.75,
            "夫妻": 0.90,
            "前任": 0.60,
            "挚友": 0.80,
            "闺蜜兄弟": 0.75,
            "知己": 0.85,
            "暧昧": 0.30,
            "暗恋": 0.40,
            "忘年交": 0.70,

            # 趣缘关系 - 较易变化
            "棋友": 0.25,
            "球友": 0.25,
            "驴友": 0.30,
            "书友": 0.30,
            "游戏队友": 0.20,
            "志同道合": 0.55,
            "公益伙伴": 0.50,
            "社团成员": 0.35,
            "粉丝圈同好": 0.30,

            # 利益关系 - 中等难度
            "借贷关系": 0.60,
            "生意伙伴": 0.55,
            "雇主雇员": 0.50,
            "搭子关系": 0.15, # 临时功能关系,易变

            # 亲密度等级相关
            "核心亲密": 0.90,
            "深度亲密": 0.80,
            "专属亲密": 0.85,
            "日常普通": 0.30,
            "社交普通": 0.25,
            "陌生关系": 0.05,

            # 法定关系 - 极难变化
            "法定亲属": 0.95,
            "雇佣合同": 0.70,

            # 默认
            "default": 0.40
        }

    def _init_relation_change_rules(self) -> List[RelationChangeRule]:
        """初始化关系变化规则"""
        rules = []

        # 积极交互规则
        rules.append(RelationChangeRule(
            trigger_event="user_chat",
            relation_type="日常普通",
            value_change=0.02,
            frequency_change=1
        ))

        rules.append(RelationChangeRule(
            trigger_event="user_compliment",
            relation_type="深度亲密",
            value_change=0.05,
            frequency_change=1
        ))

        rules.append(RelationChangeRule(
            trigger_event="user_help",
            relation_type="深度亲密",
            value_change=0.08,
            frequency_change=1
        ))

        # 消极交互规则
        rules.append(RelationChangeRule(
            trigger_event="user_insult",
            relation_type="日常普通",
            value_change=-0.10,
            frequency_change=1
        ))

        rules.append(RelationChangeRule(
            trigger_event="user_threat",
            relation_type="深度亲密",
            value_change=-0.15,
            frequency_change=1
        ))

        return rules

    def _init_relation_psych_influence(self) -> List[RelationInfluenceOnPsychology]:
        """初始化关系对心理状态的影响规则"""
        influences = []

        # 亲密关系的影响
        influences.append(RelationInfluenceOnPsychology(
            relation_type="挚友",
            relation_value_threshold=0.6,
            interaction_type="compliment",
            psychological_impact={
                "情绪": 0.15, # 挚友的称赞让情绪大幅提升
                "社交": 0.10,
                "精力": 0.05
            },
            trigger_probability=0.9
        ))

        influences.append(RelationInfluenceOnPsychology(
            relation_type="挚友",
            relation_value_threshold=0.6,
            interaction_type="insult",
            psychological_impact={
                "情绪": -0.25, # 挚友的侮辱伤害更深
                "社交": -0.15,
                "意志": -0.10
            },
            trigger_probability=0.95
        ))

        # 普通关系的影响
        influences.append(RelationInfluenceOnPsychology(
            relation_type="日常普通",
            relation_value_threshold=0.3,
            interaction_type="compliment",
            psychological_impact={
                "情绪": 0.05,
                "社交": 0.03
            },
            trigger_probability=0.5
        ))

        influences.append(RelationInfluenceOnPsychology(
            relation_type="日常普通",
            relation_value_threshold=0.3,
            interaction_type="insult",
            psychological_impact={
                "情绪": -0.08,
                "社交": -0.05
            },
            trigger_probability=0.6
        ))

        # 恋人关系的影响
        influences.append(RelationInfluenceOnPsychology(
            relation_type="恋人",
            relation_value_threshold=0.7,
            interaction_type="compliment",
            psychological_impact={
                "情绪": 0.20, # 恋人的赞美影响最大
                "社交": 0.12,
                "精力": 0.08,
                "兴趣": 0.05
            },
            trigger_probability=1.0
        ))

        influences.append(RelationInfluenceOnPsychology(
            relation_type="恋人",
            relation_value_threshold=0.7,
            interaction_type="insult",
            psychological_impact={
                "情绪": -0.30, # 恋人的伤害最深
                "社交": -0.20,
                "意志": -0.15,
                "精力": -0.10
            },
            trigger_probability=1.0
        ))

        return influences

    async def _do_start(self) -> bool:
        """启动社交关系管理服务"""
        try:
            # 加载活跃用户的社交档案
            await self._load_active_profiles()

            self._logger.info("增强社交关系管理服务启动成功")
            return True
        except Exception as e:
            self._logger.error(f"增强社交关系管理服务启动失败: {e}", exc_info=True)
            return False

    async def _do_stop(self) -> bool:
        """停止社交关系管理服务"""
        try:
            # 保存所有缓存的社交档案
            await self._save_all_profiles()
            self._logger.info("增强社交关系管理服务已停止")
            return True
        except Exception as e:
            self._logger.error(f"停止社交关系管理服务失败: {e}")
            return False

    async def get_or_create_profile(
        self,
        user_id: str,
        group_id: str
    ) -> UserSocialProfile:
        """获取或创建用户的社交档案"""
        try:
            key = (user_id, group_id)

            # 先从缓存获取
            if key in self.user_profiles:
                return self.user_profiles[key]

            # 从数据库加载
            profile = await self._load_profile_from_db(user_id, group_id)
            if profile:
                self.user_profiles[key] = profile
                return profile

            # 创建新档案
            profile = UserSocialProfile(user_id=user_id, group_id=group_id)
            self.user_profiles[key] = profile
            await self._save_profile_to_db(profile)

            return profile

        except Exception as e:
            self._logger.error(f"获取或创建社交档案失败: {e}", exc_info=True)
            return UserSocialProfile(user_id=user_id, group_id=group_id)

    async def update_relation(
        self,
        from_user_id: str,
        to_user_id: str,
        group_id: str,
        interaction_type: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        更新用户之间的社交关系

        Args:
            from_user_id: 发起方用户ID
            to_user_id: 接收方用户ID (通常是bot)
            group_id: 群组ID
            interaction_type: 交互类型
            context: 上下文信息

        Returns:
            更新结果
        """
        try:
            # 获取发起方的社交档案
            profile = await self.get_or_create_profile(from_user_id, group_id)

            # 使用LLM分析当前交互应该影响哪些关系类型
            affected_relations = await self._analyze_affected_relations(
                from_user_id, to_user_id, group_id, interaction_type, context
            )

            changes = []

            for relation_type_str, value_delta in affected_relations.items():
                # 获取该关系的变化难度
                difficulty = self.relation_change_difficulty.get(
                    relation_type_str,
                    self.relation_change_difficulty["default"]
                )

                # 应用难度系数：难度越高，变化越小
                adjusted_delta = value_delta * (1 - difficulty)

                # 查找或创建关系组件
                relation = profile.get_relation_by_type(relation_type_str)
                if not relation:
                    relation = SocialRelationComponent(
                        relation_type=relation_type_str,
                        value=0.5, # 初始中等强度
                        description=f"与 {to_user_id} 的{relation_type_str}关系"
                    )
                    profile.add_relation(relation)

                old_value = relation.value
                relation.update_value(adjusted_delta)
                relation.update_interaction()

                changes.append({
                    "relation_type": relation_type_str,
                    "old_value": old_value,
                    "new_value": relation.value,
                    "delta": adjusted_delta,
                    "difficulty": difficulty
                })

                # 记录关系变化历史
                await self._record_relation_history(
                    from_user_id, to_user_id, group_id,
                    relation_type_str, old_value, relation.value,
                    f"{interaction_type}: {context.get('message', '')[:50]}"
                )

            # 保存档案
            await self._save_profile_to_db(profile)

            # 触发心理状态影响
            if self.psych_manager:
                await self._trigger_psychological_influence(
                    group_id, from_user_id, interaction_type, affected_relations
                )

            return {
                "success": True,
                "changes": changes,
                "total_relations": profile.total_relations,
                "significant_relations": profile.significant_relations
            }

        except Exception as e:
            self._logger.error(f"更新社交关系失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _analyze_affected_relations(
        self,
        from_user_id: str,
        to_user_id: str,
        group_id: str,
        interaction_type: str,
        context: Dict[str, Any]
    ) -> Dict[str, float]:
        """
        使用LLM分析当前交互应该影响哪些关系类型及其变化量

        Returns:
            Dict[关系类型名称, 数值变化量]
        """
        if not self.llm_adapter or not self.llm_adapter.has_refine_provider():
            return self._fallback_relation_analysis(interaction_type)

        try:
            # 获取现有关系
            profile = await self.get_or_create_profile(from_user_id, group_id)
            existing_relations = profile.get_significant_relations()
            existing_desc = "\n".join([
                f"- {r.relation_type}: {r.value:.2f} (互动{r.frequency}次)"
                for r in existing_relations[:5]
            ])

            message = context.get("message", "")

            prompt = f"""
你是社交关系分析专家。请分析以下交互对用户与bot之间的社交关系有什么影响。

【用户信息】
用户ID: {from_user_id[:8]}...
群组ID: {group_id[:8]}...

【当前交互】
交互类型: {interaction_type}
消息内容: {message[:200]}

【现有关系】
{existing_desc if existing_desc else "暂无已建立的显著关系"}

【可能的关系类型】
- 血缘关系类: 父母子女、兄弟姐妹、亲戚等 (极难变化)
- 业缘关系类: 同事、师生、同学、校友等
- 情缘关系类: 恋人、挚友、闺蜜兄弟、知己、普通朋友等
- 趣缘关系类: 游戏队友、兴趣伙伴、社团成员等
- 利益关系类: 合作伙伴、搭子关系等
- 亲密度类: 核心亲密、深度亲密、日常普通、陌生关系等

请分析这次交互会影响哪1-3种关系类型,以及每种关系的数值变化量（-1到+1之间）。

注意:
1. 积极交互(称赞、帮助等)应增加关系数值
2. 消极交互(侮辱、威胁等)应减少关系数值
3. 普通聊天略微增加关系数值
4. 考虑现有关系的基础上进行调整
5. 血缘关系几乎不受影响，不要选择血缘关系

请只返回JSON格式:
{{"关系类型1": 数值变化, "关系类型2": 数值变化}}

例如: {{"日常普通": 0.02, "游戏队友": 0.05}}
"""

            response = await self.llm_adapter.refine_chat_completion(
                prompt=prompt,
                temperature=0.3
            )

            if response:
                # 解析JSON
                result = json.loads(response.strip())
                self._logger.info(f"LLM分析社交关系影响: {result}")
                return result

        except Exception as e:
            self._logger.error(f"LLM分析社交关系失败: {e}", exc_info=True)

        return self._fallback_relation_analysis(interaction_type)

    def _fallback_relation_analysis(self, interaction_type: str) -> Dict[str, float]:
        """备用的关系分析逻辑"""
        relation_effects = {
            "chat": {"日常普通": 0.01},
            "compliment": {"日常普通": 0.03, "深度亲密": 0.05},
            "praise": {"深度亲密": 0.08, "日常普通": 0.04},
            "help": {"深度亲密": 0.10, "日常普通": 0.05},
            "insult": {"日常普通": -0.10, "深度亲密": -0.15},
            "threat": {"日常普通": -0.15, "深度亲密": -0.20},
        }

        return relation_effects.get(interaction_type, {"日常普通": 0.01})

    async def _trigger_psychological_influence(
        self,
        group_id: str,
        from_user_id: str,
        interaction_type: str,
        affected_relations: Dict[str, float]
    ):
        """触发社交关系对心理状态的影响"""
        try:
            if not self.psych_manager:
                return

            # 根据关系影响规则,计算对心理状态的影响
            for influence_rule in self.relation_psych_influence:
                relation_type_str = influence_rule.relation_type
                if isinstance(relation_type_str, type):
                    relation_type_str = relation_type_str.__name__

                # 检查是否匹配受影响的关系类型
                if relation_type_str not in affected_relations:
                    continue

                # 检查关系类型和交互类型是否匹配
                if influence_rule.interaction_type != interaction_type:
                    continue

                # 获取关系强度
                profile = await self.get_or_create_profile(from_user_id, group_id)
                relation = profile.get_relation_by_type(relation_type_str)

                if not relation or relation.value < influence_rule.relation_value_threshold:
                    continue

                # 根据概率决定是否触发
                if random.random() > influence_rule.trigger_probability:
                    continue

                # 计算实际影响
                impacts = influence_rule.calculate_impact(relation.value)

                # 应用到心理状态（需要实现）
                self._logger.info(
                    f"社交关系影响心理状态: 群组{group_id}, "
                    f"关系{relation_type_str}, 影响{impacts}"
                )

                # 这里需要调用心理状态管理器的接口
                # 暂时省略具体实现

        except Exception as e:
            self._logger.error(f"触发心理状态影响失败: {e}", exc_info=True)

    async def get_relation_description(
        self,
        from_user_id: str,
        to_user_id: str,
        group_id: str
    ) -> str:
        """获取关系描述（用于prompt注入）"""
        try:
            profile = await self.get_or_create_profile(from_user_id, group_id)
            return profile.to_description()
        except Exception as e:
            self._logger.error(f"获取关系描述失败: {e}")
            return ""

    async def get_relation_prompt_injection(
        self,
        from_user_id: str,
        to_user_id: str,
        group_id: str
    ) -> str:
        """获取关系的prompt注入内容"""
        try:
            profile = await self.get_or_create_profile(from_user_id, group_id)
            return profile.to_prompt_injection()
        except Exception as e:
            self._logger.error(f"生成关系prompt注入失败: {e}")
            return ""

    # 数据库操作

    async def _load_profile_from_db(
        self,
        user_id: str,
        group_id: str
    ) -> Optional[UserSocialProfile]:
        """从数据库加载用户社交档案"""
        try:
            async with self.db_manager.get_db_connection() as conn:
                cursor = await conn.cursor()

                # 加载档案统计
                await cursor.execute('''
                    SELECT total_relations, significant_relations, dominant_relation_type,
                           created_at, last_updated
                    FROM user_social_profiles
                    WHERE user_id = ? AND group_id = ?
                ''', (user_id, group_id))

                row = await cursor.fetchone()
                if not row:
                    return None

                total, significant, dominant, created, updated = row

                profile = UserSocialProfile(
                    user_id=user_id,
                    group_id=group_id,
                    total_relations=total,
                    significant_relations=significant,
                    dominant_relation_type=dominant,
                    created_at=created,
                    last_updated=updated
                )

                # 加载所有关系组件
                await cursor.execute('''
                    SELECT relation_type, value, frequency, last_interaction,
                           description, tags, created_at
                    FROM user_social_relation_components
                    WHERE from_user_id = ? AND group_id = ?
                ''', (user_id, group_id))

                for row in await cursor.fetchall():
                    rel_type, value, freq, last_int, desc, tags_json, created = row

                    component = SocialRelationComponent(
                        relation_type=rel_type,
                        value=value,
                        frequency=freq,
                        last_interaction=last_int,
                        description=desc,
                        tags=json.loads(tags_json) if tags_json else [],
                        created_at=created
                    )
                    profile.relations.append(component)

                await cursor.close()
                return profile

        except Exception as e:
            self._logger.error(f"从数据库加载社交档案失败: {e}", exc_info=True)
            return None

    async def _save_profile_to_db(self, profile: UserSocialProfile):
        """保存用户社交档案到数据库"""
        try:
            async with self.db_manager.get_db_connection() as conn:
                cursor = await conn.cursor()

                # 使用数据库无关的语法：DELETE + INSERT 替代 INSERT OR REPLACE
                # 先删除旧记录
                await cursor.execute('''
                    DELETE FROM user_social_profiles
                    WHERE user_id = ? AND group_id = ?
                ''', (profile.user_id, profile.group_id))

                # 再插入新记录
                await cursor.execute('''
                    INSERT INTO user_social_profiles
                    (user_id, group_id, total_relations, significant_relations,
                     dominant_relation_type, created_at, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    profile.user_id, profile.group_id, profile.total_relations,
                    profile.significant_relations, profile.dominant_relation_type,
                    profile.created_at, time.time()
                ))

                # 保存所有关系组件
                for relation in profile.relations:
                    rel_type_str = relation.relation_type.value if hasattr(
                        relation.relation_type, 'value') else str(relation.relation_type)

                    # 先删除旧关系记录
                    await cursor.execute('''
                        DELETE FROM user_social_relation_components
                        WHERE from_user_id = ? AND to_user_id = ? AND group_id = ? AND relation_type = ?
                    ''', (profile.user_id, "bot", profile.group_id, rel_type_str))

                    # 再插入新关系记录
                    await cursor.execute('''
                        INSERT INTO user_social_relation_components
                        (from_user_id, to_user_id, group_id, relation_type, value,
                         frequency, last_interaction, description, tags, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        profile.user_id, "bot", profile.group_id, rel_type_str,
                        relation.value, relation.frequency, relation.last_interaction,
                        relation.description, json.dumps(relation.tags, ensure_ascii=False),
                        relation.created_at
                    ))

                await conn.commit()
                await cursor.close()

        except Exception as e:
            self._logger.error(f"保存社交档案到数据库失败: {e}", exc_info=True)

    async def _record_relation_history(
        self,
        from_user_id: str,
        to_user_id: str,
        group_id: str,
        relation_type: str,
        old_value: float,
        new_value: float,
        reason: str
    ):
        """记录关系变化历史"""
        try:
            async with self.db_manager.get_db_connection() as conn:
                cursor = await conn.cursor()

                await cursor.execute('''
                    INSERT INTO social_relation_history
                    (from_user_id, to_user_id, group_id, relation_type,
                     old_value, new_value, change_reason, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    from_user_id, to_user_id, group_id, relation_type,
                    old_value, new_value, reason, time.time()
                ))

                await conn.commit()
                await cursor.close()

        except Exception as e:
            self._logger.error(f"记录关系历史失败: {e}")

    async def _load_active_profiles(self):
        """加载活跃用户的社交档案"""
        try:
            async with self.db_manager.get_db_connection() as conn:
                cursor = await conn.cursor()

                # 获取最近7天有互动的用户
                await cursor.execute('''
                    SELECT DISTINCT user_id, group_id
                    FROM user_social_profiles
                    WHERE last_updated > ?
                    LIMIT 100
                ''', (time.time() - 86400 * 7,))

                rows = await cursor.fetchall()
                await cursor.close()

                for user_id, group_id in rows:
                    profile = await self._load_profile_from_db(user_id, group_id)
                    if profile:
                        self.user_profiles[(user_id, group_id)] = profile

                self._logger.info(f"已加载 {len(self.user_profiles)} 个用户的社交档案")

        except Exception as e:
            self._logger.error(f"加载活跃档案失败: {e}", exc_info=True)

    async def _save_all_profiles(self):
        """保存所有缓存的社交档案"""
        try:
            for profile in self.user_profiles.values():
                await self._save_profile_to_db(profile)

            self._logger.info(f"已保存 {len(self.user_profiles)} 个用户的社交档案")

        except Exception as e:
            self._logger.error(f"保存所有档案失败: {e}", exc_info=True)
