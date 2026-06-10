"""
黑话管理服务 - 处理黑话学习相关业务逻辑
"""
import json
from typing import Dict, Any, List, Tuple, Optional
from astrbot.api import logger


class JargonService:
    """黑话管理服务"""

    def __init__(self, container):
        """
        初始化黑话管理服务

        Args:
            container: ServiceContainer 依赖注入容器
        """
        self.container = container
        self.database_manager = container.database_manager

    @staticmethod
    def _format_jargon_for_frontend(j: Dict[str, Any]) -> Dict[str, Any]:
        """
        将数据库字段映射为前端期望的字段名

        DB → Frontend:
            content → term
            is_jargon → is_confirmed
            count → occurrences
            raw_content (JSON str) → context_examples (list)
            chat_id → group_id
        """
        # 解析 raw_content JSON 为 context_examples 列表
        raw = j.get('raw_content', '[]')
        try:
            context_examples = json.loads(raw) if raw else []
        except (json.JSONDecodeError, TypeError):
            context_examples = []

        content = j.get('content', '')
        meaning = j.get('meaning', '')
        is_jargon = j.get('is_jargon', False)
        count = j.get('count', 0)
        chat_id = j.get('chat_id')

        return {
            'id': j.get('id'),
            'term': content,
            'content': content,
            'meaning': meaning,
            'definition': meaning,
            'review_detail': meaning or '暂无释义',
            'is_confirmed': bool(is_jargon),
            'is_jargon': is_jargon,
            'is_global': bool(j.get('is_global', False)),
            'occurrences': count,
            'count': count,
            'group_id': chat_id,
            'chat_id': chat_id,
            'context_examples': context_examples,
            'raw_content': j.get('raw_content', '[]'),
            'last_inference_count': j.get('last_inference_count', 0),
            'is_complete': bool(j.get('is_complete', False)),
            'created_at': j.get('created_at'),
            'updated_at': j.get('updated_at'),
        }

    @staticmethod
    def _format_group_for_frontend(group: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize jargon group payload for both old and new frontends."""
        count = group.get('confirmed_jargon')
        if count is None:
            count = group.get('count', 0)

        group_id = group.get('group_id') or group.get('chat_id') or group.get('id')
        return {
            'group_id': group_id,
            'group_name': group.get('group_name') or group_id,
            'id': group.get('id') or group_id,
            'chat_id': group.get('chat_id') or group_id,
            'count': count,
            'confirmed_jargon': count,
            'total_candidates': group.get('total_candidates', count),
        }

    async def get_jargon_stats(self, group_id: Optional[str] = None) -> Dict[str, Any]:
        """
        获取黑话统计信息

        Args:
            group_id: 群组ID（可选，None 表示全局统计）

        Returns:
            Dict: 统计信息（字段已与前端对齐）
        """
        empty = {
            'total_candidates': 0,
            'confirmed_jargon': 0,
            'completed_inference': 0,
            'total_occurrences': 0,
            'average_count': 0,
            'active_groups': 0,
        }
        if not self.database_manager:
            return empty

        try:
            stats = await self.database_manager.get_jargon_statistics(
                group_id=group_id
            )
            return {
                'total_candidates': stats.get('total_candidates', 0),
                'confirmed_jargon': stats.get('confirmed_jargon', 0),
                'completed_inference': stats.get('completed_inference', 0),
                'total_occurrences': stats.get('total_occurrences', 0),
                'average_count': stats.get('average_count', 0),
                'active_groups': stats.get('active_groups', 0),
            }
        except Exception as e:
            logger.error(f"获取黑话统计失败: {e}", exc_info=True)
            return empty

    async def get_jargon_list(
        self,
        group_id: Optional[str] = None,
        confirmed: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20,
        pending_only: bool = False,
        global_only: bool = False,
        local_only: bool = False,
    ) -> Dict[str, Any]:
        """
        获取黑话列表

        Args:
            group_id: 群组ID (可选,默认获取全局黑话)
            confirmed: 过滤已确认/未确认（None=全部）
            page: 页码
            page_size: 每页数量
            pending_only: 是否只返回待确认的
            global_only: 是否只返回全局共享的黑话
            local_only: 是否只返回本地（非全局）的黑话

        Returns:
            Dict: 黑话列表和分页信息，key 为 'jargon_list'
        """
        if not self.database_manager:
            raise ValueError('数据库管理器未初始化')

        try:
            # 获取真实总数
            total = await self.database_manager.get_jargon_count(
                chat_id=group_id,
                only_confirmed=confirmed,
                pending_only=pending_only,
                global_only=global_only,
                local_only=local_only,
            )

            # DB 层分页
            offset = (page - 1) * page_size
            jargons = await self.database_manager.get_recent_jargon_list(
                chat_id=group_id,
                limit=page_size,
                offset=offset,
                only_confirmed=confirmed,
                pending_only=pending_only,
                global_only=global_only,
                local_only=local_only,
            )

            formatted = [self._format_jargon_for_frontend(j) for j in jargons]
            if pending_only:
                unfiltered_count = len(formatted)
                formatted = [
                    item for item in formatted
                    if not item.get('is_confirmed') and not item.get('is_complete')
                ]
                if unfiltered_count != len(formatted):
                    total = len(formatted)

            return {
                'jargon_list': formatted,
                'total': total,
                'page': page,
                'page_size': page_size,
                'total_pages': (total + page_size - 1) // page_size
            }
        except Exception as e:
            logger.error(f"获取黑话列表失败: {e}", exc_info=True)
            raise

    async def search_jargon(
        self,
        keyword: str,
        chat_id: Optional[str] = None,
        confirmed_only: bool = False,
        unconfirmed_only: bool = False,
        pending_only: bool = False,
        global_only: bool = False,
        local_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        搜索黑话

        Args:
            keyword: 搜索关键词
            chat_id: 群组ID（可选）
            confirmed_only: 是否仅返回已确认的黑话
            unconfirmed_only: 是否仅返回未确认的黑话
            pending_only: 是否仅返回待审查的黑话
            global_only: 是否只返回全局共享的黑话
            local_only: 是否只返回本地（非全局）的黑话

        Returns:
            List[Dict]: 匹配的黑话列表（字段已映射为前端格式）
        """
        if not self.database_manager:
            raise ValueError('数据库管理器未初始化')

        try:
            results = await self.database_manager.search_jargon(
                keyword,
                chat_id=chat_id,
                confirmed_only=confirmed_only,
                pending_only=pending_only,
                global_only=global_only,
                local_only=local_only,
            )
            formatted = [self._format_jargon_for_frontend(r) for r in results]
            if pending_only:
                return [
                    item for item in formatted
                    if not item.get('is_confirmed') and not item.get('is_complete')
                ]
            if unconfirmed_only:
                return [
                    item for item in formatted
                    if not item.get('is_confirmed')
                ]
            return formatted
        except Exception as e:
            logger.error(f"搜索黑话失败: {e}", exc_info=True)
            raise

    async def get_global_jargon_list(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        获取全局共享的黑话列表

        Args:
            limit: 返回数量限制

        Returns:
            List[Dict]: 全局黑话列表（字段已映射为前端格式）
        """
        if not self.database_manager:
            raise ValueError('数据库管理器未初始化')

        try:
            jargons = await self.database_manager.get_global_jargon_list(limit=limit)
            return [self._format_jargon_for_frontend(j) for j in jargons]
        except Exception as e:
            logger.error(f"获取全局黑话列表失败: {e}", exc_info=True)
            raise

    async def delete_jargon(self, jargon_id: int) -> Tuple[bool, str]:
        """
        删除黑话

        Args:
            jargon_id: 黑话ID

        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        if not self.database_manager:
            raise ValueError('数据库管理器未初始化')

        try:
            success = await self.database_manager.delete_jargon_by_id(jargon_id)
            if success:
                logger.info(f"黑话 {jargon_id} 已删除")
                return True, f"黑话 {jargon_id} 已删除"
            else:
                return False, "删除失败"
        except Exception as e:
            logger.error(f"删除黑话失败: {e}", exc_info=True)
            raise

    async def review_jargon(
        self,
        jargon_id: int,
        action: str,
        meaning: Optional[str] = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """确认或驳回黑话候选。"""
        if not self.database_manager:
            raise ValueError('数据库管理器未初始化')

        if action not in {"approve", "reject"}:
            return False, "action 必须是 approve 或 reject", {}

        try:
            current = await self.database_manager.get_jargon_by_id(jargon_id)
            if not current:
                return False, "黑话不存在", {}

            payload = {
                "id": jargon_id,
                "is_jargon": action == "approve",
                "is_complete": True,
            }
            if meaning is not None:
                payload["meaning"] = meaning

            success = await self.database_manager.update_jargon(payload)
            if not success:
                return False, "审查失败", current

            updated = await self.database_manager.get_jargon_by_id(jargon_id) or {
                **current,
                **payload,
            }
            formatted = self._format_jargon_for_frontend(updated)
            if action == "approve":
                return True, f"已确认黑话「{formatted.get('term') or jargon_id}」", formatted
            return True, f"已驳回候选「{formatted.get('term') or jargon_id}」", formatted

        except Exception as e:
            logger.error(f"审查黑话失败: {e}", exc_info=True)
            raise

    async def batch_review_jargon(
        self,
        jargon_ids: List[int],
        action: str,
        meaning: Optional[str] = None,
    ) -> Dict[str, Any]:
        """批量确认或驳回黑话候选。"""
        if action not in {"approve", "reject"}:
            return {
                "success": False,
                "error": "action must be 'approve' or 'reject'",
            }

        success_count = 0
        failed_count = 0
        errors = []

        for jargon_id in jargon_ids:
            try:
                normalized_id = int(jargon_id)
                success, message, _ = await self.review_jargon(
                    normalized_id,
                    action,
                    meaning=meaning,
                )
                if success:
                    success_count += 1
                else:
                    failed_count += 1
                    errors.append({"id": normalized_id, "message": message})
            except Exception as e:
                logger.error(f"批量审查黑话 {jargon_id} 失败: {e}", exc_info=True)
                failed_count += 1
                errors.append({"id": jargon_id, "message": str(e)})

        action_text = "确认" if action == "approve" else "驳回"
        return {
            "success": True,
            "message": f"批量{action_text}黑话完成：成功 {success_count} 条，失败 {failed_count} 条",
            "details": {
                "success_count": success_count,
                "failed_count": failed_count,
                "total_count": len(jargon_ids),
                "errors": errors,
            },
        }

    async def update_jargon(
        self,
        jargon_id: int,
        content: Optional[str] = None,
        meaning: Optional[str] = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """编辑已确认黑话的词条或释义。"""
        if not self.database_manager:
            raise ValueError('数据库管理器未初始化')

        try:
            current = await self.database_manager.get_jargon_by_id(jargon_id)
            if not current:
                return False, "黑话不存在", {}

            payload: Dict[str, Any] = {"id": jargon_id}
            if content is not None:
                payload["content"] = content
            if meaning is not None:
                payload["meaning"] = meaning

            if len(payload) <= 1:
                return False, "没有需要更新的字段", self._format_jargon_for_frontend(current)

            success = await self.database_manager.update_jargon(payload)
            if not success:
                return False, "更新失败", self._format_jargon_for_frontend(current)

            updated = await self.database_manager.get_jargon_by_id(jargon_id) or {**current, **payload}
            formatted = self._format_jargon_for_frontend(updated)
            return True, f"已更新黑话「{formatted.get('term') or jargon_id}」", formatted

        except Exception as e:
            logger.error(f"编辑黑话失败: {e}", exc_info=True)
            raise

    async def toggle_jargon_global(self, jargon_id: int) -> Tuple[bool, str, bool]:
        """
        切换黑话的全局状态

        Args:
            jargon_id: 黑话ID

        Returns:
            Tuple[bool, str, bool]: (是否成功, 消息, 新的全局状态)
        """
        if not self.database_manager:
            raise ValueError('数据库管理器未初始化')

        try:
            jargon = await self.database_manager.get_jargon_by_id(jargon_id)
            if not jargon:
                return False, "黑话不存在", False

            new_status = not jargon.get('is_global', False)
            success = await self.database_manager.set_jargon_global(jargon_id, new_status)

            if success:
                status_text = "全局" if new_status else "非全局"
                logger.info(f"黑话 {jargon_id} 已设置为{status_text}")
                return True, f"黑话已设置为{status_text}", new_status
            else:
                return False, "设置失败", jargon.get('is_global', False)
        except Exception as e:
            logger.error(f"切换黑话全局状态失败: {e}", exc_info=True)
            raise

    async def get_jargon_groups(self) -> List[Dict[str, Any]]:
        """
        获取包含黑话的群组列表

        Returns:
            List[str]: 群组ID列表
        """
        if not self.database_manager:
            raise ValueError('数据库管理器未初始化')

        try:
            groups = await self.database_manager.get_jargon_groups()
            return [self._format_group_for_frontend(group) for group in groups]
        except Exception as e:
            logger.error(f"获取黑话群组列表失败: {e}", exc_info=True)
            raise

    async def sync_global_to_group(self, target_group_id: str) -> Tuple[bool, str, int]:
        """
        同步全局黑话到指定群组

        Args:
            target_group_id: 目标群组ID

        Returns:
            Tuple[bool, str, int]: (是否成功, 消息, 同步数量)
        """
        if not self.database_manager:
            raise ValueError('数据库管理器未初始化')

        try:
            count = await self.database_manager.sync_global_jargon_to_group(target_group_id)
            logger.info(f"已同步 {count} 个全局黑话到群组 {target_group_id}")
            return True, f"已同步 {count} 个全局黑话", count
        except Exception as e:
            logger.error(f"同步全局黑话失败: {e}", exc_info=True)
            raise
