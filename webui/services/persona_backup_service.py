"""
人格备份 WebUI 服务 - 封装备份列表、详情、恢复与删除。
"""
from typing import Any, Dict, List, Optional, Tuple

from astrbot.api import logger

from .persona_service import _optional_container_attr


class PersonaBackupService:
    """人格备份管理服务。"""

    def __init__(self, container):
        self.container = container
        self.database_manager = _optional_container_attr(container, 'database_manager')
        self.persona_backup_manager = _optional_container_attr(container, 'persona_backup_manager')
        self.persona_manager = _optional_container_attr(container, 'persona_manager')
        self.persona_web_mgr = _optional_container_attr(container, 'persona_web_manager')

    @staticmethod
    def _normalize_limit(limit: Any, default: int = 20, maximum: int = 100) -> int:
        try:
            value = int(limit)
        except (TypeError, ValueError):
            value = default
        return max(1, min(value, maximum))

    @staticmethod
    def _backup_summary(backup: Dict[str, Any]) -> Dict[str, Any]:
        reason = backup.get('backup_reason') or backup.get('reason') or ''
        original_persona = backup.get('original_persona') or {}
        prompt = (
            original_persona.get('prompt')
            or original_persona.get('system_prompt')
            or backup.get('persona_content')
            or ''
        )
        return {
            'id': backup.get('id'),
            'group_id': backup.get('group_id'),
            'backup_name': backup.get('backup_name'),
            'timestamp': backup.get('timestamp') or backup.get('backup_time'),
            'created_at': backup.get('created_at'),
            'reason': reason,
            'reason_short': reason[:80],
            'persona_name': original_persona.get('name') or original_persona.get('persona_id') or '',
            'prompt_length': len(prompt),
        }

    @staticmethod
    def _persona_from_backup(backup: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        original = dict(backup.get('original_persona') or {})
        config = dict(backup.get('persona_config') or {})
        persona = {**config, **original}

        persona_content = backup.get('persona_content')
        if persona_content and not persona.get('prompt') and not persona.get('system_prompt'):
            persona['prompt'] = persona_content
        if 'system_prompt' not in persona and persona.get('prompt'):
            persona['system_prompt'] = persona['prompt']
        if 'prompt' not in persona and persona.get('system_prompt'):
            persona['prompt'] = persona['system_prompt']
        if not persona.get('persona_id'):
            persona['persona_id'] = persona.get('name') or backup.get('backup_name') or 'default'

        if not (persona.get('prompt') or persona.get('system_prompt')):
            return None
        persona.setdefault('name', persona.get('persona_id', '恢复的人格'))
        persona.setdefault('begin_dialogs', backup.get('imitation_dialogues') or [])
        persona.setdefault('tools', [])
        return persona

    def _ensure_database(self):
        if not self.database_manager:
            raise ValueError('数据库服务未初始化，无法管理人格备份')

    async def list_backups(self, group_id: str = 'default', limit: Any = 20) -> Dict[str, Any]:
        """获取人格备份列表。"""
        self._ensure_database()
        normalized_limit = self._normalize_limit(limit)

        if not hasattr(self.database_manager, 'get_persona_backups'):
            return {
                'group_id': group_id,
                'backups': [],
                'total': 0,
                'available': False,
                'message': '当前数据库实现不支持人格备份列表',
            }

        try:
            backups = await self.database_manager.get_persona_backups(
                group_id=group_id,
                limit=normalized_limit,
                include_content=True,
            )
        except TypeError:
            try:
                backups = await self.database_manager.get_persona_backups(group_id, normalized_limit)
            except TypeError:
                backups = await self.database_manager.get_persona_backups(normalized_limit)
        summaries = [self._backup_summary(backup) for backup in backups]
        return {
            'group_id': group_id,
            'backups': summaries,
            'total': len(summaries),
            'available': True,
        }

    async def get_backup(self, backup_id: int, group_id: str = 'default') -> Dict[str, Any]:
        """获取人格备份详情。"""
        self._ensure_database()
        if hasattr(self.database_manager, 'get_persona_backup'):
            backup = await self.database_manager.get_persona_backup(backup_id, group_id=group_id)
        elif hasattr(self.database_manager, 'restore_persona_backup'):
            backup = await self.database_manager.restore_persona_backup(group_id, backup_id)
        else:
            backup = None

        if not backup:
            raise ValueError('人格备份不存在')

        detail = dict(backup)
        detail['summary'] = self._backup_summary(detail)
        return detail

    async def restore_backup(self, backup_id: int, group_id: str = 'default') -> Tuple[bool, str]:
        """恢复人格备份。"""
        if self.persona_backup_manager and hasattr(self.persona_backup_manager, 'restore_backup'):
            try:
                success = await self.persona_backup_manager.restore_backup(group_id, backup_id)
                if success:
                    return True, '人格备份恢复成功'
            except Exception as e:
                logger.warning(f"正式备份管理器恢复失败，尝试 WebUI fallback: {e}")

        backup = await self.get_backup(backup_id, group_id=group_id)
        persona = self._persona_from_backup(backup)
        if not persona:
            return False, '备份中没有可恢复的人格内容'

        persona_id = persona['persona_id']
        if self.persona_web_mgr and hasattr(self.persona_web_mgr, 'update_persona_via_web'):
            result = await self.persona_web_mgr.update_persona_via_web(persona_id, persona)
            if result.get('success'):
                return True, '人格备份恢复成功'
            if hasattr(self.persona_web_mgr, 'create_persona_via_web'):
                result = await self.persona_web_mgr.create_persona_via_web(persona)
                if result.get('success'):
                    return True, '人格备份恢复成功'
            return False, result.get('error', '人格备份恢复失败')

        if self.persona_manager and hasattr(self.persona_manager, 'update_persona'):
            try:
                success = await self.persona_manager.update_persona(persona_id, persona)
            except TypeError:
                success = await self.persona_manager.update_persona(
                    persona_id=persona_id,
                    system_prompt=persona.get('system_prompt') or persona.get('prompt', ''),
                    begin_dialogs=persona.get('begin_dialogs', []),
                    tools=persona.get('tools'),
                )
            if success:
                return True, '人格备份恢复成功'

            if hasattr(self.persona_manager, 'create_persona'):
                success = await self.persona_manager.create_persona(persona)
                if success:
                    return True, '人格备份恢复成功'

        return False, 'PersonaManager 未初始化，无法恢复备份'

    async def delete_backup(self, backup_id: int, group_id: str = 'default') -> Tuple[bool, str]:
        """删除人格备份。"""
        self._ensure_database()
        if not hasattr(self.database_manager, 'delete_persona_backup'):
            return False, '当前数据库实现不支持删除人格备份'

        success = await self.database_manager.delete_persona_backup(backup_id, group_id=group_id)
        return (True, '人格备份已删除') if success else (False, '人格备份不存在或删除失败')
