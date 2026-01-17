"""
社交关系智能分析服务 - 基于LLM的群组成员关系分析
使用LLM一次性分析群组消息，识别成员之间的社交关系
"""
import asyncio
import time
import json
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict

from astrbot.api import logger

from ..config import PluginConfig
from ..core.framework_llm_adapter import FrameworkLLMAdapter
from ..exceptions import MessageAnalysisError
from ..utils.json_utils import safe_parse_llm_json


@dataclass
class SocialRelation:
    """社交关系数据结构"""
    from_user: str  # 发起方用户ID
    to_user: str  # 接收方用户ID
    relation_type: str  # 关系类型: 'frequent_interaction', 'mention', 'reply', 'topic_discussion'
    strength: float  # 关系强度 0.0-1.0
    frequency: int  # 互动频率（消息数量）
    last_interaction: str  # 最后互动时间
    relation_name: str  # 关系名称（中文描述）


class SocialRelationAnalyzer:
    """社交关系智能分析器"""

    def __init__(self, config: PluginConfig, llm_adapter: FrameworkLLMAdapter, db_manager):
        self.config = config
        self.llm_adapter = llm_adapter
        self.db_manager = db_manager
        self.logger = logger

        # 关系类型映射 - 扩展版本，包含15+种关系类型
        self.relation_type_map = {
            # 正常社交关系
            'frequent_interaction': '频繁互动',
            'mention': '提及(@)',
            'reply': '回复对话',
            'topic_discussion': '话题讨论',
            'question_answer': '问答互动',
            'agreement': '观点认同',
            'debate': '辩论讨论',
            'best_friend': '好友/闺蜜',
            'colleague': '同事/工作伙伴',
            'classmate': '同学',
            'teacher_student': '师生关系',

            # 亲属关系
            'parent_child': '父母子女',
            'siblings': '兄弟姐妹',
            'relatives': '亲戚',

            # 亲密关系
            'couple': '情侣/恋人',
            'spouse': '夫妻',
            'ambiguous': '暧昧关系',
            'affair': '不正当关系',

            # 其他特殊关系
            'enemy': '敌对/仇人',
            'rival': '竞争对手',
            'admiration': '崇拜/仰慕',
            'idol_fan': '偶像粉丝'
        }

        # 关系类型详细说明（供LLM理解）
        self.relation_type_descriptions = {
            'frequent_interaction': '经常对话、互相回复的普通互动关系',
            'mention': '直接提及或@对方，表示关注',
            'reply': '针对某人的消息进行回复',
            'topic_discussion': '围绕相同话题展开讨论',
            'question_answer': '一方提问，另一方回答，存在求助/帮助关系',
            'agreement': '表示赞同、支持对方观点',
            'debate': '存在不同观点的讨论或争论',
            'best_friend': '非常亲密的朋友关系，互相信任、分享私密话题、频繁互动',
            'colleague': '工作相关的同事关系，讨论工作话题',
            'classmate': '学习相关的同学关系，讨论学习话题',
            'teacher_student': '教学关系，一方传授知识/经验，另一方学习请教',
            'parent_child': '父母与子女的亲属关系，有明确的辈分、关怀、教导等特征',
            'siblings': '兄弟姐妹关系，平辈亲属关系',
            'relatives': '其他亲戚关系',
            'couple': '恋爱关系，表现出爱意、亲密称呼、情侣互动',
            'spouse': '夫妻关系，已婚配偶',
            'ambiguous': '暧昧关系，有超出普通朋友的亲密互动，但未明确恋爱关系',
            'affair': '不正当的亲密关系，可能涉及婚外情等',
            'enemy': '敌对关系，存在明显冲突、攻击性言论',
            'rival': '竞争对手关系，存在竞争但不一定敌对',
            'admiration': '崇拜或仰慕关系，一方对另一方表示崇拜、羡慕',
            'idol_fan': '偶像与粉丝的关系'
        }

        self.logger.info("社交关系智能分析器初始化完成")

    async def analyze_group_social_relations(
        self,
        group_id: str,
        message_limit: int = 200,
        force_refresh: bool = False
    ) -> List[SocialRelation]:
        """
        分析群组的社交关系网络

        Args:
            group_id: 群组ID
            message_limit: 分析的消息数量
            force_refresh: 是否强制重新分析

        Returns:
            社交关系列表
        """
        try:
            # 1. 获取群组最近的消息记录
            self.logger.info(f"开始分析群组 {group_id} 的社交关系，消息数量: {message_limit}")
            messages = await self._get_group_messages(group_id, message_limit)

            if len(messages) < 10:
                self.logger.warning(f"群组 {group_id} 消息数量不足 ({len(messages)} 条)，无法进行有效的社交关系分析")
                return []

            # 2. 提取用户列表
            users = self._extract_users_from_messages(messages)
            if len(users) < 2:
                self.logger.warning(f"群组 {group_id} 有效用户数量不足 ({len(users)} 人)")
                return []

            self.logger.info(f"群组 {group_id} 共有 {len(users)} 个活跃用户，{len(messages)} 条消息")

            # 3. 使用LLM分析社交关系
            relations = await self._analyze_relations_with_llm(group_id, messages, users)

            # 4. 保存到数据库
            if relations:
                await self._save_relations_to_database(group_id, relations)
                self.logger.info(f"成功分析并保存 {len(relations)} 条社交关系")
            else:
                self.logger.warning(f"未能分析出有效的社交关系")

            return relations

        except Exception as e:
            self.logger.error(f"分析群组社交关系失败: {e}", exc_info=True)
            return []

    async def _get_group_messages(self, group_id: str, limit: int) -> List[Dict[str, Any]]:
        """获取群组消息记录（使用 ORM 方法，支持跨线程调用）"""
        try:
            # ✅ 使用 ORM 方法获取消息（支持跨线程调用）
            raw_messages = await self.db_manager.get_recent_raw_messages(group_id, limit=limit)

            # 过滤掉 bot 消息并转换格式
            messages = []
            for msg in raw_messages:
                if msg.get('sender_id') != 'bot':
                    messages.append({
                        'id': msg.get('id'),
                        'sender_id': msg.get('sender_id'),
                        'sender_name': msg.get('sender_name') or msg.get('sender_id'),
                        'content': msg.get('message'),
                        'timestamp': msg.get('timestamp')
                    })

            # 按时间正序排列（最早的在前）
            messages.reverse()

            self.logger.debug(f"[SocialRelationAnalyzer] 获取群组消息: group_id={group_id}, 数量={len(messages)}")
            return messages

        except Exception as e:
            self.logger.error(f"获取群组消息失败: {e}", exc_info=True)
            return []

    def _extract_users_from_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """从消息中提取用户列表"""
        users_dict = {}
        for msg in messages:
            user_id = msg.get('sender_id')
            user_name = msg.get('sender_name', user_id)
            if user_id and user_id not in users_dict:
                users_dict[user_id] = user_name

        return [{'id': uid, 'name': name} for uid, name in users_dict.items()]

    async def _analyze_relations_with_llm(
        self,
        group_id: str,
        messages: List[Dict[str, Any]],
        users: List[Dict[str, str]]
    ) -> List[SocialRelation]:
        """使用LLM分析社交关系"""
        try:
            # 构建分析prompt
            prompt = self._build_analysis_prompt(messages, users)

            # 调用LLM - 使用generate_response方法
            self.logger.info(f"调用LLM分析社交关系 (消息数: {len(messages)}, 用户数: {len(users)})")
            response = await self.llm_adapter.generate_response(
                prompt=prompt,
                temperature=0.7,
                model_type="filter"  # 使用filter模型进行分析
            )

            if not response:
                self.logger.warning("LLM返回空响应")
                return []

            # 解析LLM响应
            relations = self._parse_llm_response(response, users)

            return relations

        except Exception as e:
            self.logger.error(f"LLM分析社交关系失败: {e}", exc_info=True)
            return []

    def _build_analysis_prompt(
        self,
        messages: List[Dict[str, Any]],
        users: List[Dict[str, str]]
    ) -> str:
        """构建社交关系分析prompt"""

        # 用户列表
        user_list = "\n".join([
            f"- {user['id']} (昵称: {user['name']})"
            for user in users
        ])

        # 消息上下文（选择有代表性的消息）
        # 如果消息太多，只选择部分有代表性的
        sample_messages = self._sample_representative_messages(messages, max_count=100)

        message_context = "\n".join([
            f"[{datetime.fromtimestamp(msg['timestamp']).strftime('%H:%M')}] {msg['sender_name']}: {msg['content'][:100]}"
            for msg in sample_messages
        ])

        # 构建关系类型说明
        relation_type_explanations = "\n".join([
            f"**{key}** ({value}): {self.relation_type_descriptions[key]}"
            for key, value in self.relation_type_map.items()
        ])

        prompt = f"""你是一个专业的社交关系分析专家。请仔细分析以下群聊消息记录，识别群成员之间的社交关系类型和强度。

【群组成员列表】
{user_list}

【消息记录样本】(共 {len(messages)} 条消息，以下为代表性样本)
{message_context}

【关系类型说明】
请识别以下社交关系类型（共{len(self.relation_type_map)}种）：

{relation_type_explanations}

【分析任务】
1. 根据消息内容中的互动模式、称呼、话题、语气等特征判断关系类型
2. 评估关系强度(0.0-1.0)，考虑因素包括：
   - 互动频率：越频繁，强度越高
   - 亲密程度：称呼、语气、话题私密性
   - 回复及时性：快速回复表示关系较强
   - 情感表达：表情、语气词的使用
   - 话题深度：是否涉及私密或重要话题
3. 估算互动频次（从消息记录中统计）

【输出格式】
请以JSON格式输出所有识别到的社交关系：
{{
    "relations": [
        {{
            "from_user": "用户ID",
            "to_user": "用户ID",
            "relation_type": "关系类型(英文key)",
            "relation_name": "关系名称(中文)",
            "strength": 0.85,  // 关系强度 0.0-1.0
            "frequency": 12,   // 互动次数
            "evidence": "识别依据：例如'频繁使用亲密称呼'、'讨论私密话题'、'快速回复'等"
        }}
    ]
}}

【重要提示】
- 关系是有方向的（from_user -> to_user），同一对用户的双向关系需要分别记录
- 只输出有明确证据的关系，证据不足的不要输出
- 同一对用户可能存在多种关系类型（例如既是同事又是好友）
- 特别注意识别亲密关系（couple, spouse, ambiguous, affair）的特征：
  * 特殊称呼（老婆、老公、宝贝、亲爱的等）
  * 情侣/夫妻间的互动模式
  * 暧昧的语言表达
- 亲属关系特征：
  * 明确的辈分称呼（爸妈、儿子女儿、哥姐弟妹等）
  * 家庭相关话题
- 敌对关系特征：
  * 明显的冲突性语言
  * 频繁的争吵或攻击
- strength评分标准：
  * 0.1-0.3: 偶尔互动，关系较弱
  * 0.4-0.6: 中等互动频率，普通关系
  * 0.7-0.8: 频繁互动，关系较好
  * 0.9-1.0: 非常亲密或特殊关系

请直接返回JSON，不要其他内容。"""

        return prompt

    def _sample_representative_messages(
        self,
        messages: List[Dict[str, Any]],
        max_count: int = 100
    ) -> List[Dict[str, Any]]:
        """采样有代表性的消息"""
        if len(messages) <= max_count:
            return messages

        # 均匀采样
        step = len(messages) / max_count
        sampled = []
        for i in range(max_count):
            index = int(i * step)
            sampled.append(messages[index])

        return sampled

    def _parse_llm_response(
        self,
        response: str,
        users: List[Dict[str, str]]
    ) -> List[SocialRelation]:
        """解析LLM返回的JSON响应"""
        try:
            # 使用safe_parse_llm_json解析
            data = safe_parse_llm_json(response)

            if not data or 'relations' not in data:
                self.logger.warning("LLM响应中没有找到relations字段")
                return []

            relations = []
            user_ids = {user['id'] for user in users}
            current_time = datetime.now().isoformat()

            for rel in data['relations']:
                try:
                    from_user = rel.get('from_user')
                    to_user = rel.get('to_user')

                    # 验证用户ID
                    if from_user not in user_ids or to_user not in user_ids:
                        self.logger.debug(f"跳过无效关系: {from_user} -> {to_user}")
                        continue

                    # 避免自己和自己的关系
                    if from_user == to_user:
                        continue

                    relation = SocialRelation(
                        from_user=from_user,
                        to_user=to_user,
                        relation_type=rel.get('relation_type', 'frequent_interaction'),
                        relation_name=rel.get('relation_name', self.relation_type_map.get(
                            rel.get('relation_type', 'frequent_interaction'), '互动'
                        )),
                        strength=float(rel.get('strength', 0.5)),
                        frequency=int(rel.get('frequency', 1)),
                        last_interaction=current_time
                    )

                    relations.append(relation)

                except Exception as e:
                    self.logger.warning(f"解析单条关系失败: {e}")
                    continue

            self.logger.info(f"成功解析 {len(relations)} 条社交关系")
            return relations

        except Exception as e:
            self.logger.error(f"解析LLM响应失败: {e}", exc_info=True)
            return []

    async def _save_relations_to_database(
        self,
        group_id: str,
        relations: List[SocialRelation]
    ):
        """保存社交关系到数据库"""
        try:
            for relation in relations:
                await self.db_manager.save_social_relation(
                    group_id=group_id,
                    relation_data={
                        'from_user': relation.from_user,
                        'to_user': relation.to_user,
                        'relation_type': relation.relation_type,
                        'strength': relation.strength,
                        'frequency': relation.frequency,
                        'last_interaction': relation.last_interaction
                    }
                )

            self.logger.info(f"成功保存 {len(relations)} 条社交关系到数据库")

        except Exception as e:
            self.logger.error(f"保存社交关系到数据库失败: {e}", exc_info=True)

    async def get_user_relations(
        self,
        group_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        获取指定用户的所有相关关系

        Args:
            group_id: 群组ID
            user_id: 用户ID

        Returns:
            包含该用户所有关系的字典
        """
        try:
            all_relations = await self.db_manager.get_social_relations_by_group(group_id)

            # 筛选与该用户相关的关系
            outgoing = []  # 该用户发起的关系
            incoming = []  # 指向该用户的关系

            for rel in all_relations:
                if rel['from_user'] == user_id:
                    outgoing.append(rel)
                if rel['to_user'] == user_id:
                    incoming.append(rel)

            return {
                'user_id': user_id,
                'outgoing_relations': outgoing,  # 我关注的人
                'incoming_relations': incoming,  # 关注我的人
                'total_relations': len(outgoing) + len(incoming)
            }

        except Exception as e:
            self.logger.error(f"获取用户关系失败: {e}")
            return {
                'user_id': user_id,
                'outgoing_relations': [],
                'incoming_relations': [],
                'total_relations': 0
            }
