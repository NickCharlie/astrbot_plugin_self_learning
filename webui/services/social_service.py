"""
社交关系服务 - 处理社交关系分析相关业务逻辑
直接使用 db_manager 方法获取数据（与旧 webui 保持一致）
"""
from typing import Dict, Any, List, Tuple, Optional
from astrbot.api import logger


class SocialService:
    """社交关系服务"""

    def __init__(self, container):
        """
        初始化社交关系服务

        Args:
            container: ServiceContainer 依赖注入容器
        """
        self.container = container
        self.database_manager = container.database_manager

    async def get_social_relations(self, group_id: str) -> Dict[str, Any]:
        """
        获取指定群组的社交关系分析数据

        Args:
            group_id: 群组ID

        Returns:
            Dict: 社交关系数据
        """
        try:
            if not self.database_manager:
                return {
                    "success": False,
                    "group_id": group_id,
                    "relations": [],
                    "members": [],
                    "error": "数据库管理器未初始化"
                }

            # 从数据库加载已保存的社交关系
            logger.info(f"从数据库加载群组 {group_id} 的社交关系...")
            saved_relations = await self.database_manager.get_social_relations_by_group(group_id)
            logger.info(f"从数据库加载到 {len(saved_relations)} 条社交关系记录")

            # 构建用户列表和统计消息数 - 使用 ORM 方法获取用户统计
            user_message_counts = {}
            user_names = {}

            user_stats = await self.database_manager.get_group_user_statistics(group_id)

            for sender_id, stats in user_stats.items():
                user_key = f"{group_id}:{sender_id}"
                user_message_counts[user_key] = stats['message_count']
                user_names[user_key] = stats['sender_name']
                user_names[sender_id] = stats['sender_name']

            logger.info(f"群组 {group_id} 从数据库统计到 {len(user_message_counts)} 个用户")

            raw_messages = []

            # 如果没有统计到用户,尝试从最近消息获取
            if not user_message_counts:
                raw_messages = await self.database_manager.get_recent_raw_messages(group_id, limit=200)
                if not raw_messages:
                    return {
                        "success": False,
                        "error": f"群组 {group_id} 没有消息记录",
                        "relations": [],
                        "members": []
                    }

                for msg in raw_messages:
                    sender_id = msg.get('sender_id', '')
                    sender_name = msg.get('sender_name', '')
                    if sender_id and sender_id != 'bot':
                        user_key = f"{group_id}:{sender_id}"
                        if user_key not in user_message_counts:
                            user_message_counts[user_key] = 0
                            user_names[user_key] = sender_name
                            user_names[sender_id] = sender_name
                        user_message_counts[user_key] += 1

            # 构建成员列表
            group_nodes = []
            for user_key, message_count in user_message_counts.items():
                user_id = user_key.split(':')[-1] if ':' in user_key else user_key
                group_nodes.append({
                    'user_id': user_id,
                    'nickname': user_names.get(user_key, user_id),
                    'message_count': message_count,
                    'nicknames': [user_names.get(user_key, user_id)],
                    'id': user_key
                })

            # 构建关系列表
            group_edges = []
            relation_type_map = {
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
                'parent_child': '父母子女',
                'siblings': '兄弟姐妹',
                'relatives': '亲戚',
                'couple': '情侣/恋人',
                'spouse': '夫妻',
                'ambiguous': '暧昧关系',
                'affair': '不正当关系',
                'enemy': '敌对/仇人',
                'rival': '竞争对手',
                'admiration': '崇拜/仰慕',
                'idol_fan': '偶像粉丝',
                'conversation': '对话',
            }

            for relation in saved_relations:
                from_key = relation['from_user']
                to_key = relation['to_user']

                from_id = from_key.split(':')[-1] if ':' in from_key else from_key
                to_id = to_key.split(':')[-1] if ':' in to_key else to_key

                from_name = user_names.get(from_key, user_names.get(from_id, from_id))
                to_name = user_names.get(to_key, user_names.get(to_id, to_id))

                relation_type_text = relation_type_map.get(
                    relation.get('relation_type', 'interaction'), '互动'
                )

                group_edges.append({
                    'source': from_id,
                    'target': to_id,
                    'source_name': from_name,
                    'target_name': to_name,
                    'strength': relation.get('strength', 0.5),
                    'type': relation.get('relation_type', 'interaction'),
                    'type_text': relation_type_text,
                    'frequency': relation.get('frequency', 1),
                    'last_interaction': relation.get('last_interaction', '')
                })

            logger.info(f"群组 {group_id} 构建了 {len(group_edges)} 条社交关系")

            total_message_count = sum(user_message_counts.values()) if user_message_counts else len(raw_messages)

            return {
                "success": True,
                "group_id": group_id,
                "members": group_nodes,
                "relations": group_edges,
                "message_count": total_message_count,
                "member_count": len(group_nodes),
                "relation_count": len(group_edges)
            }

        except Exception as e:
            logger.error(f"获取社交关系失败: {e}", exc_info=True)
            return {
                "success": False,
                "group_id": group_id,
                "relations": [],
                "members": [],
                "error": str(e)
            }

    async def get_available_groups(self) -> List[Dict[str, Any]]:
        """
        获取可用于社交关系分析的群组列表

        Returns:
            List[Dict]: 群组数据列表
        """
        try:
            if not self.database_manager:
                return []

            groups_data = await self.database_manager.get_groups_for_social_analysis()

            groups = []
            for group_data in groups_data:
                try:
                    group_id = group_data['group_id']
                    message_count = group_data['message_count']
                    member_count = group_data['member_count']
                    relation_count = group_data['relation_count']

                    groups.append({
                        'group_id': group_id,
                        'message_count': message_count,
                        'member_count': member_count,
                        'user_count': member_count,
                        'relation_count': relation_count
                    })
                except Exception as row_error:
                    logger.warning(f"处理群组数据行时出错，跳过: {row_error}, data: {group_data}")
                    continue

            return groups

        except Exception as e:
            logger.error(f"获取可用群组列表失败: {e}", exc_info=True)
            return []

    async def trigger_analysis(self, group_id: str) -> Tuple[bool, str]:
        """
        触发群组社交关系分析

        Args:
            group_id: 群组ID

        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        try:
            if not self.database_manager:
                return False, "数据库管理器未初始化"

            # 尝试获取社交关系分析器
            factory_manager = self.container.factory_manager
            if not factory_manager:
                return False, "工厂管理器未初始化"

            from ...services.social import SocialRelationAnalyzer

            service_factory = factory_manager.get_service_factory()
            db_manager = service_factory.create_database_manager()
            llm_adapter = service_factory.create_framework_llm_adapter()
            plugin_config = getattr(self.container, 'plugin_config', None)

            analyzer = SocialRelationAnalyzer(plugin_config, llm_adapter, db_manager)

            result = await analyzer.analyze_group_social_relations(group_id)

            logger.info(f"群组 {group_id} 的社交关系分析已完成")
            return True, f"群组 {group_id} 的社交关系分析已完成"

        except ImportError:
            return False, "社交关系分析器模块未找到"
        except Exception as e:
            logger.error(f"触发社交关系分析失败: {e}", exc_info=True)
            return False, f"触发分析失败: {str(e)}"

    async def clear_relations(self, group_id: str) -> Tuple[bool, str]:
        """
        清空群组社交关系数据

        Args:
            group_id: 群组ID

        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        try:
            if not self.database_manager:
                return False, "数据库管理器未初始化"

            success = await self.database_manager.clear_social_relations(group_id)

            if success:
                logger.info(f"群组 {group_id} 的社交关系数据已清空")
                return True, f"群组 {group_id} 的社交关系数据已清空"
            else:
                return False, "清空数据失败"

        except Exception as e:
            logger.error(f"清空社交关系数据失败: {e}", exc_info=True)
            return False, f"清空数据失败: {str(e)}"

    async def get_user_relations(self, group_id: str, user_id: str) -> Dict[str, Any]:
        """
        获取指定用户的社交关系

        Args:
            group_id: 群组ID
            user_id: 用户ID

        Returns:
            Dict: 用户社交关系数据
        """
        try:
            if not self.database_manager:
                return {
                    "user_id": user_id,
                    "relations": [],
                    "error": "数据库管理器未初始化"
                }

            # 获取该群组的所有社交关系,然后筛选该用户相关的
            saved_relations = await self.database_manager.get_social_relations_by_group(group_id)

            user_relations = []
            for relation in saved_relations:
                from_id = relation['from_user'].split(':')[-1] if ':' in relation['from_user'] else relation['from_user']
                to_id = relation['to_user'].split(':')[-1] if ':' in relation['to_user'] else relation['to_user']

                if from_id == user_id or to_id == user_id:
                    user_relations.append(relation)

            return {
                "user_id": user_id,
                "group_id": group_id,
                "relations": user_relations,
                "profile": {}
            }

        except Exception as e:
            logger.error(f"获取用户社交关系失败: {e}", exc_info=True)
            return {
                "user_id": user_id,
                "relations": [],
                "error": str(e)
            }
