"""
人格备份 Facade — 人格配置备份与恢复的业务入口
"""
import time
import json
from typing import Dict, List, Optional, Any

from astrbot.api import logger

from ._base import BaseFacade
from ....repositories.persona_backup_repository import PersonaBackupRepository


class PersonaFacade(BaseFacade):
    """人格备份管理 Facade"""

    async def backup_persona(self, backup_data: Dict[str, Any]) -> bool:
        """创建人格备份"""
        try:
            async with self.get_session() as session:
                from ....models.orm.psychological import PersonaBackup

                backup = PersonaBackup(
                    group_id=backup_data.get('group_id', 'default'),
                    backup_name=backup_data.get('backup_name', f'backup_{int(time.time())}'),
                    timestamp=time.time(),
                    reason=backup_data.get('reason', ''),
                    persona_config=json.dumps(backup_data.get('persona_config', {}), ensure_ascii=False),
                    original_persona=json.dumps(backup_data.get('original_persona', {}), ensure_ascii=False),
                    imitation_dialogues=json.dumps(backup_data.get('imitation_dialogues', []), ensure_ascii=False),
                    backup_reason=backup_data.get('backup_reason', ''),
                )
                session.add(backup)
                await session.commit()
                return True
        except Exception as e:
            self._logger.error(f"[PersonaFacade] 备份人格失败: {e}")
            return False

    async def get_persona_backups(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取人格备份列表"""
        try:
            async with self.get_session() as session:
                repo = PersonaBackupRepository(session)
                backups = await repo.list_backups(limit=limit)
                return [
                    {
                        'id': b.id,
                        'backup_name': b.backup_name,
                        'timestamp': b.timestamp,
                        'reason': b.reason,
                        'persona_config': json.loads(b.persona_config) if b.persona_config else {},
                        'original_persona': json.loads(b.original_persona) if b.original_persona else {},
                        'imitation_dialogues': json.loads(b.imitation_dialogues) if b.imitation_dialogues else [],
                        'backup_reason': b.backup_reason,
                    }
                    for b in backups
                ]
        except Exception as e:
            self._logger.error(f"[PersonaFacade] 获取备份列表失败: {e}")
            return []

    async def restore_persona_backup(self, backup_id: int) -> Optional[Dict[str, Any]]:
        """恢复指定备份"""
        try:
            async with self.get_session() as session:
                repo = PersonaBackupRepository(session)
                backup = await repo.get_backup(backup_id)
                if not backup:
                    return None
                return {
                    'id': backup.id,
                    'backup_name': backup.backup_name,
                    'timestamp': backup.timestamp,
                    'persona_config': json.loads(backup.persona_config) if backup.persona_config else {},
                    'original_persona': json.loads(backup.original_persona) if backup.original_persona else {},
                    'imitation_dialogues': json.loads(backup.imitation_dialogues) if backup.imitation_dialogues else [],
                }
        except Exception as e:
            self._logger.error(f"[PersonaFacade] 恢复备份失败: {e}")
            return None

    async def get_persona_update_history(
        self, group_id: str = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """获取人格更新历史"""
        try:
            async with self.get_session() as session:
                from sqlalchemy import select, desc
                from ....models.orm.learning import PersonaLearningReview

                stmt = select(PersonaLearningReview).order_by(
                    desc(PersonaLearningReview.timestamp)
                ).limit(limit)
                if group_id:
                    stmt = stmt.where(PersonaLearningReview.group_id == group_id)

                result = await session.execute(stmt)
                rows = result.scalars().all()
                return [
                    {
                        'id': r.id,
                        'timestamp': r.timestamp,
                        'group_id': r.group_id,
                        'update_type': r.update_type,
                        'status': r.status,
                        'confidence_score': r.confidence_score,
                    }
                    for r in rows
                ]
        except Exception as e:
            self._logger.error(f"[PersonaFacade] 获取更新历史失败: {e}")
            return []
