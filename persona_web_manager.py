"""
人格管理Web接口 - 负责处理Web界面的人格管理功能
建立Python代码与Web界面的连接
"""
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

try:
    from astrbot.core.persona_mgr import PersonaManager
except ImportError:
    # 如果无法导入PersonaManager，定义一个占位符
    PersonaManager = None


class PersonaWebManager:
    """人格管理Web接口管理器"""
    
    def __init__(self, astrbot_persona_manager: Optional[Any] = None):
        self.persona_manager = astrbot_persona_manager
        self._personas_cache = []
        self._cache_updated = None
        
    async def initialize(self):
        """初始化人格管理器"""
        if self.persona_manager:
            try:
                # 检查PersonaManager是否需要初始化
                should_initialize = False
                
                if not hasattr(self.persona_manager, 'personas'):
                    logger.info("PersonaManager缺少personas属性，需要初始化")
                    should_initialize = True
                elif not self.persona_manager.personas:
                    logger.info("PersonaManager的personas列表为空，需要初始化")
                    should_initialize = True
                elif len(self.persona_manager.personas) == 0:
                    logger.info("PersonaManager的personas列表长度为0，需要初始化")
                    should_initialize = True
                else:
                    logger.info(f"PersonaManager已初始化，当前有 {len(self.persona_manager.personas)} 个人格")
                
                if should_initialize:
                    logger.info("正在初始化PersonaManager...")
                    await self.persona_manager.initialize()
                    logger.info(f"PersonaManager初始化完成，加载了 {len(self.persona_manager.personas)} 个人格")
                
                # 刷新缓存
                await self.refresh_personas_cache()
                
            except Exception as e:
                logger.error(f"PersonaManager初始化失败: {e}", exc_info=True)
        else:
            logger.warning("persona_manager为None，无法初始化")
    
    async def refresh_personas_cache(self):
        """刷新人格缓存"""
        if not self.persona_manager:
            logger.warning("persona_manager为空，无法刷新缓存")
            return
            
        try:
            logger.info("开始刷新人格缓存...")
            self._personas_cache = await self.persona_manager.get_all_personas()
            self._cache_updated = datetime.now()
            logger.info(f"人格缓存已刷新，当前有 {len(self._personas_cache)} 个人格")
        except Exception as e:
            logger.error(f"刷新人格缓存失败: {e}", exc_info=True)
            # 确保缓存不为空，即使出错也设置为空列表
            self._personas_cache = []
    
    async def get_all_personas_for_web(self) -> List[Dict[str, Any]]:
        """获取所有人格，格式化为Web界面需要的格式"""
        try:
            logger.info("get_all_personas_for_web被调用")
            
            # 如果缓存过期或为空，刷新缓存
            needs_refresh = False
            if not self._personas_cache:
                logger.info("缓存为空，需要刷新")
                needs_refresh = True
            elif self._cache_updated and (datetime.now() - self._cache_updated).seconds > 300:
                logger.info("缓存已过期，需要刷新")
                needs_refresh = True
            
            if needs_refresh:
                await self.refresh_personas_cache()
            
            logger.info(f"当前缓存中有 {len(self._personas_cache)} 个人格")
            
            persona_list = []
            for i, persona in enumerate(self._personas_cache):
                try:
                    logger.info(f"处理人格 {i}: {getattr(persona, 'persona_id', 'unknown')}")
                    
                    persona_dict = {
                        "persona_id": getattr(persona, 'persona_id', 'unknown'),
                        "system_prompt": getattr(persona, 'system_prompt', ''),
                        "begin_dialogs": getattr(persona, 'begin_dialogs', []) or [],
                        "tools": getattr(persona, 'tools', []) or [],
                        "created_at": None,
                        "updated_at": None
                    }
                    
                    # 安全地处理datetime字段
                    if hasattr(persona, 'created_at') and persona.created_at:
                        try:
                            persona_dict["created_at"] = persona.created_at.isoformat()
                        except Exception as e:
                            logger.warning(f"转换created_at时出错: {e}")
                            
                    if hasattr(persona, 'updated_at') and persona.updated_at:
                        try:
                            persona_dict["updated_at"] = persona.updated_at.isoformat()
                        except Exception as e:
                            logger.warning(f"转换updated_at时出错: {e}")
                    
                    persona_list.append(persona_dict)
                except Exception as e:
                    logger.warning(f"处理人格 {getattr(persona, 'persona_id', 'unknown')} 时出错: {e}")
                    continue
            
            logger.info(f"返回 {len(persona_list)} 个人格给Web界面")
            return persona_list
            
        except Exception as e:
            logger.error(f"获取人格列表失败: {e}", exc_info=True)
            return []
    
    async def get_default_persona_for_web(self) -> Dict[str, Any]:
        """获取默认人格，格式化为Web界面需要的格式"""
        if not self.persona_manager:
            return {
                "persona_id": "default",
                "system_prompt": "You are a helpful assistant.",
                "begin_dialogs": [],
                "tools": []
            }
            
        try:
            default_persona = await self.persona_manager.get_default_persona_v3()
            
            if default_persona:
                return {
                    "persona_id": "default", 
                    "system_prompt": default_persona.get("prompt", ""),
                    "begin_dialogs": default_persona.get("begin_dialogs", []),
                    "tools": default_persona.get("tools", [])
                }
            else:
                return {
                    "persona_id": "default",
                    "system_prompt": "You are a helpful assistant.",
                    "begin_dialogs": [],
                    "tools": []
                }
                
        except Exception as e:
            logger.error(f"获取默认人格失败: {e}", exc_info=True)
            return {
                "persona_id": "default",
                "system_prompt": "You are a helpful assistant.",
                "begin_dialogs": [],
                "tools": []
            }
    
    async def create_persona_via_web(self, persona_data: Dict[str, Any]) -> Dict[str, Any]:
        """通过Web界面创建人格"""
        if not self.persona_manager:
            return {"success": False, "error": "PersonaManager未初始化"}
            
        try:
            persona_id = persona_data.get("persona_id")
            system_prompt = persona_data.get("system_prompt", "")
            begin_dialogs = persona_data.get("begin_dialogs", [])
            tools = persona_data.get("tools", [])
            
            if not persona_id:
                return {"success": False, "error": "人格ID不能为空"}
            
            # 检查是否已存在
            existing = await self.persona_manager.db.get_persona_by_id(persona_id)
            if existing:
                return {"success": False, "error": "人格ID已存在"}
            
            # 创建人格
            new_persona = await self.persona_manager.create_persona(
                persona_id=persona_id,
                system_prompt=system_prompt,
                begin_dialogs=begin_dialogs,
                tools=tools
            )
            
            # 刷新缓存
            await self.refresh_personas_cache()
            
            logger.info(f"通过Web界面成功创建人格: {persona_id}")
            return {"success": True, "persona_id": persona_id}
            
        except Exception as e:
            logger.error(f"通过Web界面创建人格失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    async def update_persona_via_web(self, persona_id: str, persona_data: Dict[str, Any]) -> Dict[str, Any]:
        """通过Web界面更新人格"""
        if not self.persona_manager:
            return {"success": False, "error": "PersonaManager未初始化"}
            
        try:
            # 检查人格是否存在
            existing = await self.persona_manager.db.get_persona_by_id(persona_id)
            if not existing:
                return {"success": False, "error": "人格不存在"}
            
            # 更新人格
            updated_persona = await self.persona_manager.update_persona(
                persona_id=persona_id,
                system_prompt=persona_data.get("system_prompt"),
                begin_dialogs=persona_data.get("begin_dialogs"),
                tools=persona_data.get("tools")
            )
            
            # 刷新缓存
            await self.refresh_personas_cache()
            
            logger.info(f"通过Web界面成功更新人格: {persona_id}")
            return {"success": True}
            
        except Exception as e:
            logger.error(f"通过Web界面更新人格失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    async def delete_persona_via_web(self, persona_id: str) -> Dict[str, Any]:
        """通过Web界面删除人格"""
        if not self.persona_manager:
            return {"success": False, "error": "PersonaManager未初始化"}
            
        try:
            # 检查人格是否存在
            existing = await self.persona_manager.db.get_persona_by_id(persona_id)
            if not existing:
                return {"success": False, "error": "人格不存在"}
            
            # 删除人格
            await self.persona_manager.delete_persona(persona_id)
            
            # 刷新缓存
            await self.refresh_personas_cache()
            
            logger.info(f"通过Web界面成功删除人格: {persona_id}")
            return {"success": True}
            
        except Exception as e:
            logger.error(f"通过Web界面删除人格失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}


# 全局实例
persona_web_manager: Optional[PersonaWebManager] = None


def get_persona_web_manager() -> Optional[PersonaWebManager]:
    """获取人格Web管理器实例"""
    return persona_web_manager


def set_persona_web_manager(astrbot_persona_manager: Optional[Any] = None):
    """设置人格Web管理器实例"""
    global persona_web_manager
    persona_web_manager = PersonaWebManager(astrbot_persona_manager)
    return persona_web_manager