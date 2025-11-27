"""
人格管理服务 - 处理人格相关业务逻辑
"""
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from astrbot.api import logger


class PersonaService:
    """人格管理服务"""

    def __init__(self, container):
        """
        初始化人格管理服务

        Args:
            container: ServiceContainer 依赖注入容器
        """
        self.container = container
        self.persona_web_mgr = container.persona_web_manager
        self.persona_manager = container.persona_manager

    async def get_all_personas(self) -> List[Dict[str, Any]]:
        """
        获取所有人格列表

        Returns:
            List[Dict]: 人格列表
        """
        try:
            logger.info("开始获取人格列表...")

            if not self.persona_web_mgr:
                logger.warning("PersonaWebManager未初始化，返回空列表")
                return []

            logger.info("调用get_all_personas_for_web...")
            personas = await self.persona_web_mgr.get_all_personas_for_web()
            logger.info(f"获取到 {len(personas)} 个人格")

            return personas

        except Exception as e:
            logger.error(f"获取人格列表失败: {e}", exc_info=True)
            return []

    async def get_persona_details(self, persona_id: str) -> Optional[Dict[str, Any]]:
        """
        获取特定人格详情

        Args:
            persona_id: 人格ID

        Returns:
            Optional[Dict]: 人格详情,如果不存在返回None
        """
        if not self.persona_manager:
            raise ValueError("PersonaManager未初始化")

        try:
            persona = await self.persona_manager.get_persona(persona_id)
            if not persona:
                return None

            persona_dict = {
                "persona_id": persona.persona_id,
                "system_prompt": persona.system_prompt,
                "begin_dialogs": persona.begin_dialogs,
                "tools": persona.tools,
                "created_at": persona.created_at.isoformat() if persona.created_at else None,
                "updated_at": persona.updated_at.isoformat() if persona.updated_at else None,
            }

            return persona_dict

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
        if not self.persona_web_mgr:
            raise ValueError("人格管理功能暂不可用，请检查AstrBot PersonaManager配置")

        try:
            result = await self.persona_web_mgr.create_persona_via_web(data)

            if result["success"]:
                return True, "人格创建成功", result["persona_id"]
            else:
                return False, result["error"], None

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
        if not self.persona_web_mgr:
            raise ValueError("人格管理功能暂不可用，请检查AstrBot PersonaManager配置")

        try:
            result = await self.persona_web_mgr.update_persona_via_web(persona_id, data)

            if result["success"]:
                return True, "人格更新成功"
            else:
                return False, result["error"]

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
        if not self.persona_web_mgr:
            raise ValueError("人格管理功能暂不可用，请检查AstrBot PersonaManager配置")

        try:
            result = await self.persona_web_mgr.delete_persona_via_web(persona_id)

            if result["success"]:
                return True, "人格删除成功"
            else:
                return False, result["error"]

        except Exception as e:
            logger.error(f"删除人格失败: {e}", exc_info=True)
            raise

    async def get_default_persona(self) -> Dict[str, Any]:
        """
        获取默认人格

        Returns:
            Dict: 默认人格数据
        """
        # 基本默认人格(后备方案)
        fallback_persona = {
            "persona_id": "default",
            "system_prompt": "You are a helpful assistant.",
            "begin_dialogs": [],
            "tools": []
        }

        if not self.persona_web_mgr:
            logger.warning("PersonaWebManager未初始化，返回基本默认人格")
            return fallback_persona

        try:
            default_persona = await self.persona_web_mgr.get_default_persona_for_web()
            return default_persona

        except Exception as e:
            logger.error(f"获取默认人格失败: {e}", exc_info=True)
            return fallback_persona

    async def export_persona(self, persona_id: str) -> Dict[str, Any]:
        """
        导出人格配置

        Args:
            persona_id: 人格ID

        Returns:
            Dict: 导出的人格配置
        """
        if not self.persona_manager:
            raise ValueError("PersonaManager未初始化")

        try:
            persona = await self.persona_manager.get_persona(persona_id)
            if not persona:
                raise ValueError("人格不存在")

            persona_export = {
                "persona_id": persona.persona_id,
                "system_prompt": persona.system_prompt,
                "begin_dialogs": persona.begin_dialogs,
                "tools": persona.tools,
                "export_time": datetime.now().isoformat(),
                "export_version": "1.0"
            }

            return persona_export

        except Exception as e:
            logger.error(f"导出人格失败: {e}")
            raise

    async def import_persona(self, data: Dict[str, Any]) -> Tuple[bool, str, Optional[str]]:
        """
        导入人格配置

        Args:
            data: 导入的人格数据

        Returns:
            Tuple[bool, str, Optional[str]]: (是否成功, 消息, 人格ID)
        """
        if not self.persona_manager:
            raise ValueError("PersonaManager未初始化")

        try:
            # 验证导入数据格式
            required_fields = ["persona_id", "system_prompt"]
            for field in required_fields:
                if field not in data:
                    return False, f"缺少必需字段: {field}", None

            persona_id = data["persona_id"]
            system_prompt = data["system_prompt"]
            begin_dialogs = data.get("begin_dialogs", [])
            tools = data.get("tools", [])

            # 检查是否覆盖现有人格
            overwrite = data.get("overwrite", False)
            existing_persona = await self.persona_manager.get_persona(persona_id)

            if existing_persona and not overwrite:
                return False, "人格已存在，如要覆盖请设置overwrite=true", None

            # 创建或更新人格
            if existing_persona:
                success = await self.persona_manager.update_persona(
                    persona_id=persona_id,
                    system_prompt=system_prompt,
                    begin_dialogs=begin_dialogs,
                    tools=tools
                )
                action = "更新"
            else:
                success = await self.persona_manager.create_persona(
                    persona_id=persona_id,
                    system_prompt=system_prompt,
                    begin_dialogs=begin_dialogs,
                    tools=tools
                )
                action = "创建"

            if success:
                logger.info(f"成功导入人格: {persona_id} ({action})")
                return True, f"人格{action}成功", persona_id
            else:
                return False, f"人格{action}失败", None

        except Exception as e:
            logger.error(f"导入人格失败: {e}")
            raise
