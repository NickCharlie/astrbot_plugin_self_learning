import logging
from typing import Dict, Any, Optional, List

from astrbot.api.star import Context
from ..config import PluginConfig

from ..core.interfaces import IPersonaManager, IPersonaUpdater, IPersonaBackupManager, ServiceLifecycle, MessageData

from ..exceptions import SelfLearningError # 导入 SelfLearningError

class PersonaManagerService(IPersonaManager):
    """
    人格管理器服务，负责协调人格的更新、备份和恢复。
    实现 IPersonaManager 接口。
    """
    def __init__(self, config: PluginConfig, context: Context,
                 persona_updater: IPersonaUpdater, persona_backup_manager: IPersonaBackupManager):
        self.config = config
        self.context = context
        self._logger = logging.getLogger(self.__class__.__name__)
        self._persona_updater = persona_updater
        self._persona_backup_manager = persona_backup_manager
        self._status = ServiceLifecycle.CREATED
        # group_id到unified_msg_origin映射（多配置文件支持）
        self.group_id_to_unified_origin: Dict[str, str] = {}

    def _resolve_umo(self, group_id: str = None) -> Optional[str]:
        """将group_id解析为unified_msg_origin以支持多配置文件"""
        if not group_id:
            return None
        return self.group_id_to_unified_origin.get(group_id, group_id)

    @property
    def status(self) -> ServiceLifecycle:
        return self._status

    async def start(self) -> bool:
        self._status = ServiceLifecycle.RUNNING
        self._logger.info("PersonaManagerService started.")
        return True

    async def stop(self) -> bool:
        self._status = ServiceLifecycle.STOPPED
        self._logger.info("PersonaManagerService stopped.")
        return True

    async def restart(self) -> bool:
        await self.stop()
        return await self.start()

    async def health_check(self) -> bool:
        return self._status == ServiceLifecycle.RUNNING

    async def update_persona(self, group_id: str, style_data: Dict[str, Any], messages: List[MessageData]) -> bool:
        """
        更新人格。
        此方法将委托给 PersonaUpdater。
        """
        try:
            self._logger.info(f"PersonaManagerService: Updating persona for group {group_id}...")
            # 在更新前创建备份
            backup_id = await self._persona_backup_manager.create_backup_before_update(
                group_id,
                f"Style update initiated by PersonaManagerService for group {group_id}"
            )
            self._logger.info(f"PersonaManagerService: Created persona backup: {backup_id} for group {group_id}")

            # 调用 PersonaUpdater 的方法进行实际更新
            update_success = await self._persona_updater.update_persona_with_style(group_id, style_data, messages)
            
            if update_success:
                self._logger.info(f"PersonaManagerService: Persona updated successfully for group {group_id}.")
            else:
                self._logger.warning(f"PersonaManagerService: Persona update failed via PersonaUpdater for group {group_id}.")
            
            return update_success
            
        except Exception as e:
            self._logger.error(f"PersonaManagerService: Failed to update persona for group {group_id}: {e}")
            raise SelfLearningError(f"人格更新失败: {str(e)}") from e

    async def backup_persona(self, group_id: str, reason: str) -> int:
        """
        备份人格。
        此方法将委托给 PersonaBackupManager。
        """
        try:
            self._logger.info(f"PersonaManagerService: Backing up persona for group {group_id} with reason: {reason}")
            backup_id = await self._persona_backup_manager.create_backup_before_update(group_id, reason)
            self._logger.info(f"PersonaManagerService: Persona backup created with ID: {backup_id} for group {group_id}")
            return backup_id
        except Exception as e:
            self._logger.error(f"PersonaManagerService: Failed to backup persona for group {group_id}: {e}")
            raise SelfLearningError(f"人格备份失败: {str(e)}") from e

    async def restore_persona(self, group_id: str, backup_id: int) -> bool:
        """
        恢复人格。
        此方法将委托给 PersonaBackupManager。
        """
        try:
            self._logger.info(f"PersonaManagerService: Restoring persona for group {group_id} from backup ID: {backup_id}")
            restore_success = await self._persona_backup_manager.restore_persona(group_id, backup_id)
            if restore_success:
                self._logger.info(f"PersonaManagerService: Persona restored successfully for group {group_id} from backup ID: {backup_id}")
            else:
                self._logger.warning(f"PersonaManagerService: Failed to restore persona for group {group_id} from backup ID: {backup_id}")
            return restore_success
        except Exception as e:
            self._logger.error(f"PersonaManagerService: Failed to restore persona for group {group_id}: {e}")
            raise SelfLearningError(f"人格恢复失败: {str(e)}") from e

    async def get_current_persona_description(self, group_id: str = None) -> Optional[str]:
        """获取当前人格的描述"""
        try:
            umo = self._resolve_umo(group_id)
            persona = await self.context.persona_manager.get_default_persona_v3(umo)
            if persona:
                return persona.get('prompt', '') if isinstance(persona, dict) else getattr(persona, 'prompt', '')
            return None
        except Exception as e:
            self._logger.error(f"获取当前人格描述失败: {e}")
            return None

    async def get_current_persona(self, group_id: str = None) -> Optional[Dict[str, Any]]:
        """获取当前人格信息"""
        try:
            umo = self._resolve_umo(group_id)
            persona = await self.context.persona_manager.get_default_persona_v3(umo)
            if persona:
                return dict(persona) if isinstance(persona, dict) else {'prompt': getattr(persona, 'prompt', '')}
            return None
        except Exception as e:
            self._logger.error(f"获取当前人格失败 for group {group_id}: {e}")
            return None
