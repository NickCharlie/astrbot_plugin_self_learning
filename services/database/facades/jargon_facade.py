"""
黑话 Facade — 黑话（Jargon）域的业务入口

封装所有黑话相关的数据库操作，对外仅暴露 Dict / List[Dict] 等纯数据结构。
"""
import time
import json
from typing import Dict, List, Optional, Any

from sqlalchemy import select, and_, func, desc, or_, case
from sqlalchemy.exc import IntegrityError
from astrbot.api import logger

from ._base import BaseFacade
from ....models.orm.jargon import Jargon


class JargonFacade(BaseFacade):
    """黑话管理 Facade"""

    # 1. get_jargon
    async def get_jargon(self, chat_id: str, content: str) -> Optional[Dict[str, Any]]:
        """查询指定黑话（按 chat_id + content 唯一定位）

        Args:
            chat_id: 群组ID
            content: 黑话内容

        Returns:
            黑话字典或 None
        """
        try:
            async with self.get_session() as session:

                stmt = select(Jargon).where(and_(
                    Jargon.chat_id == chat_id,
                    Jargon.content == content
                ))
                result = await session.execute(stmt)
                record = result.scalars().first()

                if not record:
                    return None

                return record.to_dict()

        except Exception as e:
            self._logger.error(f"[JargonFacade] 查询黑话失败: {e}", exc_info=True)
            return None

    # 2. insert_jargon
    async def insert_jargon(self, jargon_data: Dict[str, Any]) -> Optional[int]:
        """插入新的黑话记录

        当唯一约束冲突（chat_id + content 重复）时，回退到查询并返回
        已有记录的 ID，避免并发插入导致的 IntegrityError。

        Args:
            jargon_data: 黑话数据字典

        Returns:
            新记录 ID 或 None
        """
        try:
            async with self.get_session() as session:

                now_ts = int(time.time())

                # 处理 created_at / updated_at — 统一转为 int 时间戳
                created_at = jargon_data.get('created_at')
                updated_at = jargon_data.get('updated_at')
                if created_at and not isinstance(created_at, (int, float)):
                    created_at = now_ts
                elif created_at:
                    created_at = int(created_at)
                else:
                    created_at = now_ts

                if updated_at and not isinstance(updated_at, (int, float)):
                    updated_at = now_ts
                elif updated_at:
                    updated_at = int(updated_at)
                else:
                    updated_at = now_ts

                record = Jargon(
                    content=jargon_data.get('content', ''),
                    raw_content=jargon_data.get('raw_content', '[]'),
                    meaning=jargon_data.get('meaning'),
                    is_jargon=jargon_data.get('is_jargon'),
                    count=jargon_data.get('count', 1),
                    last_inference_count=jargon_data.get('last_inference_count', 0),
                    is_complete=jargon_data.get('is_complete', False),
                    is_global=jargon_data.get('is_global', False),
                    chat_id=jargon_data.get('chat_id', ''),
                    created_at=created_at,
                    updated_at=updated_at
                )

                session.add(record)
                await session.commit()
                await session.refresh(record)

                self._logger.info(
                    f"[JargonFacade] 插入黑话成功: id={record.id}, content={record.content}"
                )
                return record.id

        except IntegrityError:
            # 并发插入导致的唯一约束冲突，回退到查询已有记录
            chat_id = jargon_data.get('chat_id', '')
            content = jargon_data.get('content', '')
            self._logger.debug(
                f"[JargonFacade] 黑话已存在，跳过插入: "
                f"chat_id={chat_id}, content='{content}'"
            )
            existing = await self.get_jargon(chat_id, content)
            return existing.get('id') if existing else None
        except Exception as e:
            self._logger.error(f"[JargonFacade] 插入黑话失败: {e}", exc_info=True)
            return None

    # 3. update_jargon
    async def update_jargon(self, jargon_data: Dict[str, Any]) -> bool:
        """更新现有黑话记录

        Args:
            jargon_data: 包含 id 和待更新字段的字典

        Returns:
            是否更新成功
        """
        jargon_id = jargon_data.get('id')
        if not jargon_id:
            self._logger.error("[JargonFacade] 更新黑话失败: 缺少 id")
            return False

        try:
            async with self.get_session() as session:

                stmt = select(Jargon).where(Jargon.id == jargon_id)
                result = await session.execute(stmt)
                record = result.scalars().first()

                if not record:
                    self._logger.warning(f"[JargonFacade] 更新黑话失败: 未找到 id={jargon_id}")
                    return False

                # 更新字段
                if 'content' in jargon_data:
                    record.content = jargon_data['content']
                if 'raw_content' in jargon_data:
                    record.raw_content = jargon_data['raw_content']
                if 'meaning' in jargon_data:
                    record.meaning = jargon_data['meaning']
                if 'is_jargon' in jargon_data:
                    record.is_jargon = jargon_data['is_jargon']
                if 'count' in jargon_data:
                    record.count = jargon_data['count']
                if 'last_inference_count' in jargon_data:
                    record.last_inference_count = jargon_data['last_inference_count']
                if 'is_complete' in jargon_data:
                    record.is_complete = jargon_data['is_complete']
                if 'is_global' in jargon_data:
                    record.is_global = jargon_data['is_global']

                # updated_at 统一为 int 时间戳
                updated_at = jargon_data.get('updated_at')
                if updated_at and not isinstance(updated_at, (int, float)):
                    record.updated_at = int(time.time())
                elif updated_at:
                    record.updated_at = int(updated_at)
                else:
                    record.updated_at = int(time.time())

                await session.commit()
                self._logger.debug(f"[JargonFacade] 更新黑话成功: id={jargon_id}")
                return True

        except Exception as e:
            self._logger.error(f"[JargonFacade] 更新黑话失败: {e}", exc_info=True)
            return False

    # 4. get_jargon_statistics
    async def get_jargon_statistics(self, group_id: str = None) -> Dict[str, Any]:
        """获取黑话学习统计信息

        Args:
            group_id: 群组ID（可选，None 表示全局统计）

        Returns:
            统计数据字典，包含 total_candidates, confirmed_jargon,
            completed_inference, total_occurrences, average_count, active_groups
        """
        default_stats = {
            'total_candidates': 0,
            'confirmed_jargon': 0,
            'completed_inference': 0,
            'total_occurrences': 0,
            'average_count': 0.0,
            'active_groups': 0,
        }
        try:
            async with self.get_session() as session:

                columns = [
                    func.count().label('total'),
                    func.count(case((Jargon.is_jargon == True, 1))).label('confirmed'),
                    func.count(case((Jargon.is_complete == True, 1))).label('completed'),
                    func.coalesce(func.sum(Jargon.count), 0).label('total_occurrences'),
                    func.coalesce(func.avg(Jargon.count), 0).label('avg_count'),
                ]

                if not group_id:
                    columns.append(
                        func.count(func.distinct(Jargon.chat_id)).label('active_groups')
                    )

                stmt = select(*columns)
                if group_id:
                    stmt = stmt.where(Jargon.chat_id == group_id)

                result = await session.execute(stmt)
                row = result.fetchone()

                if not row:
                    return default_stats

                stats = {
                    'total_candidates': int(row.total) if row.total else 0,
                    'confirmed_jargon': int(row.confirmed) if row.confirmed else 0,
                    'completed_inference': int(row.completed) if row.completed else 0,
                    'total_occurrences': int(row.total_occurrences) if row.total_occurrences else 0,
                    'average_count': round(float(row.avg_count), 1) if row.avg_count else 0.0,
                }

                if not group_id:
                    stats['active_groups'] = int(row.active_groups) if row.active_groups else 0
                else:
                    stats['active_groups'] = 1 if stats['total_candidates'] > 0 else 0

                return stats

        except Exception as e:
            self._logger.error(f"[JargonFacade] 获取黑话统计失败: {e}", exc_info=True)
            return default_stats

    # 5. get_recent_jargon_list
    async def get_recent_jargon_list(
        self,
        group_id: str = None,
        chat_id: str = None,
        limit: int = 10,
        offset: int = 0,
        only_confirmed: bool = None
    ) -> List[Dict]:
        """获取最近的黑话列表

        Args:
            group_id: 群组ID（可选，None 表示获取所有群组）
            chat_id: 聊天ID（可选，兼容参数）
            limit: 返回数量限制
            offset: 偏移量（用于分页）
            only_confirmed: 是否只返回已确认的黑话

        Returns:
            黑话列表
        """
        # chat_id 是 group_id 的别名（向后兼容）
        if group_id is None and chat_id is not None:
            group_id = chat_id

        try:
            async with self.get_session() as session:

                # 构建查询
                stmt = select(Jargon)

                # 如果指定了 group_id，则只查询该群组
                if group_id is not None:
                    stmt = stmt.where(Jargon.chat_id == group_id)

                # 按确认状态过滤（None=全部, True=已确认, False=未确认）
                if only_confirmed is True:
                    stmt = stmt.where(Jargon.is_jargon == True)
                elif only_confirmed is False:
                    stmt = stmt.where(
                        (Jargon.is_jargon == False) | (Jargon.is_jargon == None)
                    )

                # 按更新时间倒序排列，分页
                stmt = stmt.order_by(Jargon.updated_at.desc())
                if offset > 0:
                    stmt = stmt.offset(offset)
                stmt = stmt.limit(limit)

                result = await session.execute(stmt)
                jargon_records = result.scalars().all()

                self._logger.debug(
                    f"[JargonFacade] 查询最近黑话列表: group_id={group_id}, "
                    f"数量={len(jargon_records)}"
                )

                jargon_list = []
                for record in jargon_records:
                    try:
                        jargon_list.append({
                            'id': record.id,
                            'content': record.content,
                            'raw_content': record.raw_content,
                            'meaning': record.meaning,
                            'is_jargon': record.is_jargon,
                            'count': record.count or 0,
                            'last_inference_count': record.last_inference_count or 0,
                            'is_complete': record.is_complete,
                            'chat_id': record.chat_id,
                            'updated_at': record.updated_at,
                            'is_global': record.is_global or False
                        })
                    except Exception as row_error:
                        self._logger.warning(f"处理黑话记录行时出错，跳过: {row_error}")
                        continue

                return jargon_list

        except Exception as e:
            self._logger.error(f"[JargonFacade] 获取最近黑话列表失败: {e}", exc_info=True)
            return []

    # 6. get_jargon_count
    async def get_jargon_count(
        self,
        chat_id: Optional[str] = None,
        only_confirmed: Optional[bool] = None,
    ) -> int:
        """获取黑话记录总数（用于分页）

        Args:
            chat_id: 群组ID（可选，None 表示所有群组）
            only_confirmed: None=全部, True=已确认, False=未确认

        Returns:
            记录总数
        """
        try:
            async with self.get_session() as session:

                stmt = select(func.count(Jargon.id))

                if chat_id is not None:
                    stmt = stmt.where(Jargon.chat_id == chat_id)

                if only_confirmed is True:
                    stmt = stmt.where(Jargon.is_jargon == True)
                elif only_confirmed is False:
                    stmt = stmt.where(
                        (Jargon.is_jargon == False) | (Jargon.is_jargon == None)
                    )

                result = await session.execute(stmt)
                return result.scalar() or 0
        except Exception as e:
            self._logger.error(f"[JargonFacade] 获取黑话总数失败: {e}", exc_info=True)
            return 0

    # 7. search_jargon
    async def search_jargon(
        self,
        keyword: str,
        chat_id: Optional[str] = None,
        confirmed_only: bool = True,
        limit: int = 10
    ) -> List[Dict]:
        """搜索黑话（LIKE 匹配）

        Args:
            keyword: 搜索关键词
            chat_id: 群组ID（有值搜本群，无值搜全局已确认黑话）
            confirmed_only: 是否仅返回已确认的黑话（默认 True）
            limit: 返回数量限制

        Returns:
            匹配的黑话列表
        """
        try:
            async with self.get_session() as session:

                conditions = [
                    Jargon.content.ilike(f'%{keyword}%'),
                ]
                if confirmed_only:
                    conditions.append(Jargon.is_jargon == True)
                if chat_id:
                    conditions.append(Jargon.chat_id == chat_id)
                elif confirmed_only:
                    # 无群组限制 + 仅已确认 → 限定全局黑话
                    conditions.append(Jargon.is_global == True)

                stmt = (
                    select(Jargon)
                    .where(and_(*conditions))
                    .order_by(Jargon.count.desc(), Jargon.updated_at.desc())
                    .limit(limit)
                )
                result = await session.execute(stmt)
                records = result.scalars().all()

                return [
                    {
                        'id': r.id,
                        'content': r.content,
                        'raw_content': r.raw_content,
                        'meaning': r.meaning,
                        'is_jargon': r.is_jargon,
                        'count': r.count or 0,
                        'is_complete': r.is_complete,
                        'is_global': r.is_global or False,
                        'chat_id': r.chat_id,
                        'updated_at': r.updated_at,
                    }
                    for r in records
                ]
        except Exception as e:
            self._logger.error(f"[JargonFacade] 搜索黑话失败: {e}", exc_info=True)
            return []

    # 8. get_jargon_by_id
    async def get_jargon_by_id(self, jargon_id: int) -> Optional[Dict]:
        """根据 ID 获取黑话记录

        Args:
            jargon_id: 黑话记录 ID

        Returns:
            黑话字典或 None
        """
        try:
            async with self.get_session() as session:

                stmt = select(Jargon).where(Jargon.id == jargon_id)
                result = await session.execute(stmt)
                record = result.scalars().first()

                if not record:
                    return None

                return record.to_dict()

        except Exception as e:
            self._logger.error(
                f"[JargonFacade] 获取黑话记录失败 (id={jargon_id}): {e}", exc_info=True
            )
            return None

    # 9. delete_jargon_by_id
    async def delete_jargon_by_id(self, jargon_id: int) -> bool:
        """根据 ID 删除黑话记录

        Args:
            jargon_id: 黑话记录 ID

        Returns:
            是否删除成功
        """
        try:
            async with self.get_session() as session:

                stmt = select(Jargon).where(Jargon.id == jargon_id)
                result = await session.execute(stmt)
                record = result.scalars().first()

                if not record:
                    return False

                await session.delete(record)
                await session.commit()
                self._logger.debug(f"[JargonFacade] 删除黑话记录成功, ID: {jargon_id}")
                return True
        except Exception as e:
            self._logger.error(
                f"[JargonFacade] 删除黑话失败 (id={jargon_id}): {e}", exc_info=True
            )
            return False

    # 10. set_jargon_global
    async def set_jargon_global(self, jargon_id: int, is_global: bool) -> bool:
        """设置黑话的全局共享状态

        Args:
            jargon_id: 黑话记录 ID
            is_global: 是否全局共享

        Returns:
            是否更新成功
        """
        try:
            async with self.get_session() as session:

                stmt = select(Jargon).where(Jargon.id == jargon_id)
                result = await session.execute(stmt)
                record = result.scalars().first()

                if not record:
                    return False

                record.is_global = is_global
                record.updated_at = int(time.time())
                await session.commit()
                self._logger.info(
                    f"[JargonFacade] 黑话全局状态已更新: ID={jargon_id}, is_global={is_global}"
                )
                return True
        except Exception as e:
            self._logger.error(
                f"[JargonFacade] 更新黑话全局状态失败 (id={jargon_id}): {e}", exc_info=True
            )
            return False

    # 11. sync_global_jargon_to_group
    async def sync_global_jargon_to_group(self, target_chat_id: str) -> int:
        """将全局黑话同步到指定群组

        对全局黑话逐条检查目标群组是否已存在相同内容，不存在则插入。

        Args:
            target_chat_id: 目标群组 ID

        Returns:
            成功同步的数量
        """
        try:
            async with self.get_session() as session:

                # 获取非目标群组的全局黑话
                stmt = select(Jargon).where(and_(
                    Jargon.is_jargon == True,
                    Jargon.is_global == True,
                    Jargon.chat_id != target_chat_id
                ))
                result = await session.execute(stmt)
                global_jargons = result.scalars().all()

                synced_count = 0
                now_ts = int(time.time())

                for gj in global_jargons:
                    # 检查目标群组是否已存在
                    check_stmt = select(Jargon).where(and_(
                        Jargon.chat_id == target_chat_id,
                        Jargon.content == gj.content
                    ))
                    check_result = await session.execute(check_stmt)
                    if check_result.scalars().first():
                        continue

                    new_jargon = Jargon(
                        content=gj.content,
                        raw_content='[]',
                        meaning=gj.meaning,
                        is_jargon=True,
                        count=1,
                        last_inference_count=0,
                        is_complete=False,
                        is_global=False,
                        chat_id=target_chat_id,
                        created_at=now_ts,
                        updated_at=now_ts,
                    )
                    session.add(new_jargon)
                    synced_count += 1

                await session.commit()
                self._logger.info(
                    f"[JargonFacade] 同步全局黑话到群组 {target_chat_id}: 同步 {synced_count} 条"
                )
                return synced_count
        except Exception as e:
            self._logger.error(f"[JargonFacade] 同步全局黑话失败: {e}", exc_info=True)
            return 0

    # 12. save_or_update_jargon
    async def save_or_update_jargon(
        self,
        chat_id: str,
        content: str,
        jargon_data: Dict[str, Any]
    ) -> Optional[int]:
        """保存或更新黑话记录（Upsert）

        按 chat_id + content 检查是否已存在：
        - 存在 → 用 jargon_data 中的字段更新
        - 不存在 → 插入新记录

        Args:
            chat_id: 群组 ID
            content: 黑话内容
            jargon_data: 黑话数据字典

        Returns:
            记录 ID 或 None
        """
        try:
            async with self.get_session() as session:

                stmt = select(Jargon).where(and_(
                    Jargon.chat_id == chat_id,
                    Jargon.content == content,
                ))
                result = await session.execute(stmt)
                record = result.scalars().first()

                now_ts = int(time.time())

                if record:
                    # 更新已有记录
                    if 'meaning' in jargon_data:
                        record.meaning = jargon_data['meaning']
                    if 'raw_content' in jargon_data:
                        record.raw_content = jargon_data['raw_content']
                    if 'is_jargon' in jargon_data:
                        record.is_jargon = jargon_data['is_jargon']
                    if 'count' in jargon_data:
                        record.count = jargon_data['count']
                    if 'last_inference_count' in jargon_data:
                        record.last_inference_count = jargon_data['last_inference_count']
                    if 'is_complete' in jargon_data:
                        record.is_complete = jargon_data['is_complete']
                    if 'is_global' in jargon_data:
                        record.is_global = jargon_data['is_global']
                    record.updated_at = now_ts

                    await session.commit()
                    self._logger.debug(
                        f"[JargonFacade] 更新黑话: content='{content}', chat_id={chat_id}, "
                        f"id={record.id}"
                    )
                    return record.id
                else:
                    # 插入新记录
                    new_record = Jargon(
                        content=content,
                        raw_content=jargon_data.get('raw_content', '[]'),
                        meaning=jargon_data.get('meaning'),
                        is_jargon=jargon_data.get('is_jargon', True),
                        count=jargon_data.get('count', 1),
                        last_inference_count=jargon_data.get('last_inference_count', 0),
                        is_complete=jargon_data.get('is_complete', False),
                        is_global=jargon_data.get('is_global', False),
                        chat_id=chat_id,
                        created_at=now_ts,
                        updated_at=now_ts,
                    )
                    session.add(new_record)
                    await session.commit()
                    await session.refresh(new_record)
                    self._logger.debug(
                        f"[JargonFacade] 插入黑话: content='{content}', chat_id={chat_id}, "
                        f"id={new_record.id}"
                    )
                    return new_record.id

        except Exception as e:
            self._logger.error(
                f"[JargonFacade] 保存/更新黑话失败 (content='{content}'): {e}",
                exc_info=True,
            )
            return None

    # 13. get_global_jargon_list
    async def get_global_jargon_list(self, limit: int = 50) -> List[Dict]:
        """获取全局共享的黑话列表

        Args:
            limit: 返回数量限制

        Returns:
            全局黑话列表
        """
        try:
            async with self.get_session() as session:

                stmt = select(Jargon).where(
                    Jargon.is_jargon == True,
                    Jargon.is_global == True
                ).order_by(
                    Jargon.count.desc(),
                    Jargon.updated_at.desc()
                ).limit(limit)

                result = await session.execute(stmt)
                jargon_list = result.scalars().all()

                self._logger.debug(
                    f"[JargonFacade] 查询全局黑话列表: 数量={len(jargon_list)}"
                )

                return [
                    {
                        'id': jargon.id,
                        'content': jargon.content,
                        'raw_content': jargon.raw_content,
                        'meaning': jargon.meaning,
                        'is_jargon': jargon.is_jargon,
                        'count': jargon.count,
                        'last_inference_count': jargon.last_inference_count,
                        'is_complete': jargon.is_complete,
                        'is_global': jargon.is_global,
                        'chat_id': jargon.chat_id,
                        'updated_at': jargon.updated_at
                    }
                    for jargon in jargon_list
                ]

        except Exception as e:
            self._logger.error(f"[JargonFacade] 获取全局黑话列表失败: {e}", exc_info=True)
            return []

    # 14. get_jargon_groups
    async def get_jargon_groups(self) -> List[Dict]:
        """获取包含黑话的群组列表

        Returns:
            群组列表 [{chat_id, count}, ...]
        """
        try:
            async with self.get_session() as session:

                stmt = select(
                    Jargon.chat_id,
                    func.count(Jargon.id).label('count')
                ).group_by(
                    Jargon.chat_id
                ).order_by(
                    func.count(Jargon.id).desc()
                )

                result = await session.execute(stmt)
                rows = result.all()

                self._logger.debug(f"[JargonFacade] 查询黑话群组列表: 数量={len(rows)}")

                groups = []
                for row in rows:
                    try:
                        chat_id = row.chat_id or ''
                        groups.append({
                            'group_id': chat_id,
                            'group_name': chat_id,
                            'id': chat_id,
                            'chat_id': chat_id,
                            'count': row.count or 0
                        })
                    except Exception as row_error:
                        self._logger.warning(
                            f"处理黑话群组数据行失败: {row_error}, 行数据: {row}"
                        )
                        continue

                return groups

        except Exception as e:
            self._logger.error(f"[JargonFacade] 获取黑话群组列表失败: {e}", exc_info=True)
            return []
