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

        # 关系类型映射
        self.relation_type_map = {
            'frequent_interaction': '频繁互动',
            'mention': '提及(@)',
            'reply': '回复对话',
            'topic_discussion': '话题讨论',
            'question_answer': '问答互动',
            'agreement': '观点认同',
            'debate': '辩论讨论'
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
        """获取群组消息记录"""
        try:
            async with self.db_manager.get_db_connection() as conn:
                cursor = await conn.cursor()

                # 获取最近的消息，排除bot消息
                await cursor.execute('''
                    SELECT id, sender_id, sender_name, message, timestamp
                    FROM raw_messages
                    WHERE group_id = ? AND sender_id != 'bot'
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (group_id, limit))

                messages = []
                for row in await cursor.fetchall():
                    messages.append({
                        'id': row[0],
                        'sender_id': row[1],
                        'sender_name': row[2] or row[1],
                        'content': row[3],
                        'timestamp': row[4]
                    })

                await cursor.close()

                # 按时间正序排列（最早的在前）
                messages.reverse()
                return messages

        except Exception as e:
            self.logger.error(f"获取群组消息失败: {e}")
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

        prompt = f"""你是一个专业的社交关系分析专家。请分析以下群聊消息记录，识别群成员之间的社交关系。

【群组成员列表】
{user_list}

【消息记录样本】(共 {len(messages)} 条消息，以下为代表性样本)
{message_context}

【分析任务】
请根据消息内容分析群成员之间的社交关系，识别以下几种关系类型：
1. **frequent_interaction** (频繁互动): 经常对话、互相回复
2. **mention** (提及@): 直接提及或@某人
3. **reply** (回复对话): 针对某人的消息进行回复
4. **topic_discussion** (话题讨论): 围绕相同话题展开讨论
5. **question_answer** (问答互动): 一方提问，另一方回答
6. **agreement** (观点认同): 表示赞同、支持对方观点
7. **debate** (辩论讨论): 存在不同观点的讨论

【输出格式】
请以JSON格式输出所有识别到的社交关系，格式如下：
{{
    "relations": [
        {{
            "from_user": "用户ID",
            "to_user": "用户ID",
            "relation_type": "关系类型(英文)",
            "relation_name": "关系名称(中文)",
            "strength": 0.8,  // 关系强度 0.0-1.0，基于互动频率和质量
            "frequency": 5,   // 互动次数（估算）
            "evidence": "分析依据的简要说明"
        }}
    ]
}}

【分析要点】
- 关系是有方向的（from_user -> to_user）
- strength 应该基于互动频率、回复及时性、话题深度等综合评估
- frequency 可以根据消息中的互动次数估算
- 只输出有明确证据的关系，不要猜测
- 同一对用户可能有多种关系类型

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
