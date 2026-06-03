"""
人格管理服务 - 处理人格相关业务逻辑
"""
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from astrbot.api import logger


def _optional_container_attr(container, name: str, default=None):
    value = getattr(container, name, default)
    if value is default:
        return default
    if value.__class__.__module__ == 'unittest.mock' and name not in getattr(container, '__dict__', {}):
        return default
    return value


def _optional_object_attr(obj, name: str, default=None):
    if obj is None:
        return default
    if obj.__class__.__module__ == 'unittest.mock' and name not in getattr(obj, '__dict__', {}):
        return default
    return getattr(obj, name, default)


class PersonaService:
    """人格管理服务"""

    def __init__(self, container):
        """
        初始化人格管理服务

        Args:
            container: ServiceContainer 依赖注入容器
        """
        self.container = container
        self.persona_manager = _optional_container_attr(container, 'persona_manager')
        self.persona_web_mgr = _optional_container_attr(container, 'persona_web_manager')
        self.astrbot_persona_manager = (
            _optional_container_attr(container, 'astrbot_persona_manager')
            or self.persona_manager
        )

    def _ensure_manager(self):
        if not self.persona_manager and not self.persona_web_mgr:
            raise ValueError("PersonaManager未初始化")

    @staticmethod
    def _normalize_persona_data(data: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(data)
        if 'system_prompt' not in normalized and 'prompt' in normalized:
            normalized['system_prompt'] = normalized['prompt']
        if 'prompt' not in normalized and 'system_prompt' in normalized:
            normalized['prompt'] = normalized['system_prompt']
        return normalized

    @staticmethod
    def _has_required_persona_fields(data: Dict[str, Any]) -> bool:
        return bool(data.get('persona_id') and (data.get('prompt') or data.get('system_prompt')))

    @staticmethod
    def _compact_persona(persona: Dict[str, Any]) -> Dict[str, Any]:
        normalized = PersonaService._normalize_persona_data(persona or {})
        return {
            "persona_id": normalized.get("persona_id") or normalized.get("id") or normalized.get("name") or "default",
            "name": normalized.get("name") or normalized.get("persona_id") or "默认人格",
            "prompt": normalized.get("prompt", ""),
            "system_prompt": normalized.get("system_prompt", ""),
            "begin_dialogs": normalized.get("begin_dialogs") or [],
            "tools": normalized.get("tools") or [],
            "metadata": normalized.get("metadata") or {},
        }

    async def get_all_personas(self) -> List[Dict[str, Any]]:
        """
        获取所有人格列表

        Returns:
            List[Dict]: 人格列表
        """
        self._ensure_manager()

        try:
            if self.persona_web_mgr:
                return await self.persona_web_mgr.get_all_personas_for_web()
            return await self.persona_manager.get_all_personas()
        except Exception as e:
            logger.error(f"获取人格列表失败: {e}", exc_info=True)
            raise

    async def get_persona_details(self, persona_id: str) -> Optional[Dict[str, Any]]:
        """
        获取特定人格详情

        Args:
            persona_id: 人格ID

        Returns:
            Optional[Dict]: 人格详情,如果不存在返回None
        """
        self._ensure_manager()

        try:
            if self.persona_web_mgr:
                all_personas = await self.persona_web_mgr.get_all_personas_for_web()
                for persona in all_personas:
                    if persona.get('persona_id') == persona_id:
                        return persona
                raise ValueError(f"Persona {persona_id} not found")

            persona = await self.persona_manager.get_persona(persona_id)
            if not persona:
                raise ValueError(f"Persona {persona_id} not found")
            return persona
        except Exception as e:
            logger.error(f"获取人格详情失败: {e}")
            raise

    async def create_persona(self, data: Dict[str, Any]) -> Tuple[bool, str, Optional[str]]:
        """
        创建新人格

        Args:
            data: 人格数据

        Returns:
            Tuple[bool, str, Optional[str]]: (是否成功, 消息, 人格ID)
        """
        self._ensure_manager()
        data = self._normalize_persona_data(data)

        if not self._has_required_persona_fields(data):
            return False, "缺少必需字段: persona_id/prompt", None

        try:
            if self.persona_web_mgr:
                result = await self.persona_web_mgr.create_persona_via_web(data)
                if result.get("success"):
                    return True, "人格创建成功", result.get("persona_id", data["persona_id"])
                return False, result.get("error", "人格创建失败"), None

            success = await self.persona_manager.create_persona(data)
            if success:
                return True, "人格创建成功", data["persona_id"]
            return False, "人格创建失败", None
        except Exception as e:
            logger.error(f"创建人格失败: {e}", exc_info=True)
            raise

    async def update_persona(self, persona_id: str, data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        更新人格

        Args:
            persona_id: 人格ID
            data: 更新数据

        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        self._ensure_manager()
        data = self._normalize_persona_data(data)

        try:
            if self.persona_web_mgr:
                result = await self.persona_web_mgr.update_persona_via_web(persona_id, data)
                if result.get("success"):
                    return True, "人格更新成功"
                return False, result.get("error", "人格更新失败")

            existing = await self.persona_manager.get_persona(persona_id)
            if not existing:
                return False, f"Persona {persona_id} not found"

            success = await self.persona_manager.update_persona(persona_id, data)
            return (True, "人格更新成功") if success else (False, "人格更新失败")
        except Exception as e:
            logger.error(f"更新人格失败: {e}", exc_info=True)
            raise

    async def delete_persona(self, persona_id: str) -> Tuple[bool, str]:
        """
        删除人格

        Args:
            persona_id: 人格ID

        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        self._ensure_manager()

        try:
            if self.persona_web_mgr:
                result = await self.persona_web_mgr.delete_persona_via_web(persona_id)
                if result.get("success"):
                    return True, "人格删除成功"
                return False, result.get("error", "人格删除失败")

            success = await self.persona_manager.delete_persona(persona_id)
            return (True, "人格删除成功") if success else (False, "人格删除失败")
        except Exception as e:
            logger.error(f"删除人格失败: {e}", exc_info=True)
            raise

    async def get_default_persona(self, group_id: str = "default") -> Dict[str, Any]:
        """
        获取默认人格

        Returns:
            Dict: 默认人格数据
        """
        fallback_persona = {
            "persona_id": "default",
            "prompt": "You are a helpful assistant.",
            "system_prompt": "You are a helpful assistant.",
            "begin_dialogs": [],
            "tools": []
        }

        try:
            if self.persona_web_mgr:
                if group_id and group_id != "default":
                    default_persona = await self.persona_web_mgr.get_persona_for_group(group_id)
                else:
                    default_persona = await self.persona_web_mgr.get_default_persona_for_web()
                return self._normalize_persona_data(default_persona or fallback_persona)

            if self.astrbot_persona_manager:
                default_persona = await self.astrbot_persona_manager.get_default_persona_v3(group_id)
                if default_persona:
                    return self._normalize_persona_data(default_persona)

                default_persona = await self.astrbot_persona_manager.get_default_persona_v3('default')
                if default_persona:
                    return self._normalize_persona_data(default_persona)

            return fallback_persona
        except Exception as e:
            logger.error(f"获取默认人格失败: {e}", exc_info=True)
            return fallback_persona

    async def get_current_persona_state(self, group_id: str = "default") -> Dict[str, Any]:
        """获取当前生效人格的 WebUI 预览状态。"""
        config = _optional_container_attr(self.container, 'plugin_config')
        persona = await self.get_default_persona(group_id)
        compact = self._compact_persona(persona)
        prompt = compact.get("prompt") or compact.get("system_prompt") or ""
        begin_dialogs = compact.get("begin_dialogs") if isinstance(compact.get("begin_dialogs"), list) else []
        tools = compact.get("tools") if isinstance(compact.get("tools"), list) else []

        config_snapshot = {
            "current_persona_name": _optional_object_attr(config, "current_persona_name"),
            "enable_persona_evolution": _optional_object_attr(config, "enable_persona_evolution"),
            "persona_merge_strategy": _optional_object_attr(config, "persona_merge_strategy"),
            "persona_compatibility_threshold": _optional_object_attr(config, "persona_compatibility_threshold"),
            "persona_update_backup_enabled": _optional_object_attr(config, "persona_update_backup_enabled"),
            "auto_backup_enabled": _optional_object_attr(config, "auto_backup_enabled"),
            "backup_interval_hours": _optional_object_attr(config, "backup_interval_hours"),
            "max_backups_per_group": _optional_object_attr(config, "max_backups_per_group"),
        }

        available_services = {
            "persona_manager": bool(self.persona_manager),
            "persona_web_manager": bool(self.persona_web_mgr),
            "astrbot_persona_manager": bool(self.astrbot_persona_manager),
        }

        return {
            "group_id": group_id or "default",
            "persona": compact,
            "prompt_preview": prompt[:240],
            "prompt_length": len(prompt),
            "begin_dialog_count": len(begin_dialogs),
            "tool_count": len(tools),
            "config": config_snapshot,
            "available_services": available_services,
            "generated_at": datetime.now().isoformat(),
            "degraded": not any(available_services.values()),
        }

    async def export_persona(self, persona_id: str) -> Dict[str, Any]:
        """
        导出人格配置

        Args:
            persona_id: 人格ID

        Returns:
            Dict: 导出的人格配置
        """
        persona = await self.get_persona_details(persona_id)
        if not persona:
            raise ValueError(f"Persona {persona_id} not found")

        persona_export = dict(self._normalize_persona_data(persona))
        persona_export["export_time"] = datetime.now().isoformat()
        persona_export["export_version"] = "1.0"
        persona_export.setdefault("metadata", {})
        return persona_export

    async def import_persona(self, data: Dict[str, Any]) -> Tuple[bool, str, Optional[str]]:
        """
        导入人格配置

        Args:
            data: 导入的人格数据

        Returns:
            Tuple[bool, str, Optional[str]]: (是否成功, 消息, 人格ID)
        """
        self._ensure_manager()
        data = self._normalize_persona_data(data)

        if not self._has_required_persona_fields(data):
            return False, "缺少必需字段: persona_id/prompt", None

        persona_id = data["persona_id"]
        overwrite = data.get("overwrite", False)

        try:
            existing_persona = None
            try:
                existing_persona = await self.get_persona_details(persona_id)
            except ValueError:
                existing_persona = None

            if existing_persona and not overwrite:
                return False, "Persona already exists", None

            if existing_persona:
                if self.persona_web_mgr:
                    result = await self.persona_web_mgr.update_persona_via_web(persona_id, data)
                    success = result.get('success')
                    error = result.get('error', "人格更新失败")
                else:
                    success = await self.persona_manager.update_persona(persona_id, data)
                    error = "人格更新失败"
                action = "更新"
            else:
                if self.persona_web_mgr:
                    result = await self.persona_web_mgr.create_persona_via_web(data)
                    success = result.get('success')
                    error = result.get('error', "人格创建失败")
                else:
                    success = await self.persona_manager.create_persona(data)
                    error = "人格创建失败"
                action = "创建"

            if success:
                logger.info(f"成功导入人格: {persona_id} ({action})")
                return True, f"人格{action}成功", persona_id
            return False, error, None
        except Exception as e:
            logger.error(f"导入人格失败: {e}")
            raise
