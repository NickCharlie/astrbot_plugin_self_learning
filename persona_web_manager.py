"""
人格管理Web接口 - 负责处理Web界面的人格管理功能
建立Python代码与Web界面的连接

注意：WebUI 运行在独立的守护线程（独立事件循环）中，
所有对框架 PersonaManager 的异步调用必须调度到主事件循环执行，
否则会因跨线程异步 DB 访问导致失败。
"""
import asyncio
from datetime import datetime
from typing import List, Dict, Optional, Any

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class PersonaWebManager:
    """人格管理Web接口管理器"""

    def __init__(self, astrbot_persona_manager: Optional[Any] = None):
        self.persona_manager = astrbot_persona_manager
        self._personas_cache = []
        self._cache_updated = None
        # 主事件循环引用，initialize() 时捕获
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None

    async def _run_on_main_loop(self, coro):
        """
        将协程调度到主事件循环执行（解决 WebUI 守护线程跨线程 DB 访问问题）。
        如果当前已在主循环中，直接 await。
        """
        current_loop = asyncio.get_event_loop()

        # 如果当前就是主循环，或者没有保存主循环引用，直接执行
        if self._main_loop is None or self._main_loop is current_loop or self._main_loop.is_closed():
            return await coro

        # 从 WebUI 线程调度到主线程
        future = asyncio.run_coroutine_threadsafe(coro, self._main_loop)
        return await asyncio.wrap_future(future, loop=current_loop)

    async def initialize(self):
        """初始化人格管理器（在主线程中调用）"""
        # 捕获主事件循环
        self._main_loop = asyncio.get_event_loop()

        if self.persona_manager:
            try:
                if not hasattr(self.persona_manager, 'personas') or not self.persona_manager.personas:
                    logger.debug("正在初始化PersonaManager...")
                    await self.persona_manager.initialize()
                    logger.debug(f"PersonaManager初始化完成，加载了 {len(self.persona_manager.personas)} 个人格")
                else:
                    logger.debug(f"PersonaManager已初始化，当前有 {len(self.persona_manager.personas)} 个人格")

                # 从内存列表刷新缓存（无需 DB 调用）
                self._sync_cache_from_memory()

            except Exception as e:
                logger.error(f"PersonaManager初始化失败: {e}", exc_info=True)
        else:
            logger.warning("persona_manager为None，无法初始化")

    def _sync_cache_from_memory(self):
        """从 PersonaManager 的内存 personas 列表同步缓存（线程安全，无 async DB 调用）"""
        if self.persona_manager and hasattr(self.persona_manager, 'personas'):
            self._personas_cache = list(self.persona_manager.personas)
            self._cache_updated = datetime.now()
            logger.debug(f"人格缓存已同步，当前有 {len(self._personas_cache)} 个人格")

    async def refresh_personas_cache(self):
        """刷新人格缓存 - 优先从内存读取，避免跨线程 DB 调用"""
        if not self.persona_manager:
            logger.warning("persona_manager为空，无法刷新缓存")
            return

        # 优先从内存列表读取（线程安全，PersonaManager 在 CRUD 时会更新此列表）
        if hasattr(self.persona_manager, 'personas') and self.persona_manager.personas:
            self._sync_cache_from_memory()
            return

        # 内存为空时，尝试通过主事件循环从 DB 加载
        try:
            self._personas_cache = await self._run_on_main_loop(
                self.persona_manager.get_all_personas()
            )
            self._cache_updated = datetime.now()
            logger.debug(f"人格缓存已从DB刷新，当前有 {len(self._personas_cache)} 个人格")
        except Exception as e:
            logger.error(f"刷新人格缓存失败: {e}", exc_info=True)
            self._personas_cache = []

    async def get_all_personas_for_web(self) -> List[Dict[str, Any]]:
        """获取所有人格，格式化为Web界面需要的格式"""
        try:
            # 如果缓存过期或为空，刷新缓存
            if not self._personas_cache:
                await self.refresh_personas_cache()
            elif self._cache_updated and (datetime.now() - self._cache_updated).seconds > 30:
                # 30秒缓存，通过内存同步（很快）
                self._sync_cache_from_memory()

            persona_list = []
            for persona in self._personas_cache:
                try:
                    persona_dict = {
                        "persona_id": getattr(persona, 'persona_id', 'unknown'),
                        "system_prompt": getattr(persona, 'system_prompt', ''),
                        "begin_dialogs": getattr(persona, 'begin_dialogs', []) or [],
                        "tools": getattr(persona, 'tools', []) or [],
                        "created_at": None,
                        "updated_at": None
                    }

                    if hasattr(persona, 'created_at') and persona.created_at:
                        try:
                            persona_dict["created_at"] = persona.created_at.isoformat()
                        except Exception:
                            pass

                    if hasattr(persona, 'updated_at') and persona.updated_at:
                        try:
                            persona_dict["updated_at"] = persona.updated_at.isoformat()
                        except Exception:
                            pass

                    persona_list.append(persona_dict)
                except Exception as e:
                    logger.warning(f"处理人格 {getattr(persona, 'persona_id', 'unknown')} 时出错: {e}")
                    continue

            return persona_list

        except Exception as e:
            logger.error(f"获取人格列表失败: {e}", exc_info=True)
            return []

    async def get_default_persona_for_web(self) -> Dict[str, Any]:
        """获取默认人格，格式化为Web界面需要的格式"""
        fallback = {
            "persona_id": "default",
            "system_prompt": "You are a helpful assistant.",
            "begin_dialogs": [],
            "tools": []
        }

        if not self.persona_manager:
            return fallback

        try:
            default_persona = await self._run_on_main_loop(
                self.persona_manager.get_default_persona_v3()
            )

            if default_persona:
                return {
                    "persona_id": "default",
                    "system_prompt": default_persona.get("prompt", ""),
                    "begin_dialogs": default_persona.get("begin_dialogs", []),
                    "tools": default_persona.get("tools", [])
                }
            return fallback

        except Exception as e:
            logger.error(f"获取默认人格失败: {e}", exc_info=True)
            return fallback

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
            try:
                existing = await self._run_on_main_loop(
                    self.persona_manager.db.get_persona_by_id(persona_id)
                )
                if existing:
                    return {"success": False, "error": "人格ID已存在"}
            except Exception:
                pass

            # 创建人格（通过主事件循环）
            await self._run_on_main_loop(
                self.persona_manager.create_persona(
                    persona_id=persona_id,
                    system_prompt=system_prompt,
                    begin_dialogs=begin_dialogs,
                    tools=tools
                )
            )

            # 同步内存缓存
            self._sync_cache_from_memory()

            logger.debug(f"通过Web界面成功创建人格: {persona_id}")
            return {"success": True, "persona_id": persona_id}

        except Exception as e:
            logger.error(f"通过Web界面创建人格失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def update_persona_via_web(self, persona_id: str, persona_data: Dict[str, Any]) -> Dict[str, Any]:
        """通过Web界面更新人格"""
        if not self.persona_manager:
            return {"success": False, "error": "PersonaManager未初始化"}

        try:
            # 更新人格（通过主事件循环）
            await self._run_on_main_loop(
                self.persona_manager.update_persona(
                    persona_id=persona_id,
                    system_prompt=persona_data.get("system_prompt"),
                    begin_dialogs=persona_data.get("begin_dialogs"),
                    tools=persona_data.get("tools")
                )
            )

            # 同步内存缓存
            self._sync_cache_from_memory()

            logger.debug(f"通过Web界面成功更新人格: {persona_id}")
            return {"success": True}

        except Exception as e:
            logger.error(f"通过Web界面更新人格失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def delete_persona_via_web(self, persona_id: str) -> Dict[str, Any]:
        """通过Web界面删除人格"""
        if not self.persona_manager:
            return {"success": False, "error": "PersonaManager未初始化"}

        try:
            # 删除人格（通过主事件循环）
            await self._run_on_main_loop(
                self.persona_manager.delete_persona(persona_id)
            )

            # 同步内存缓存
            self._sync_cache_from_memory()

            logger.debug(f"通过Web界面成功删除人格: {persona_id}")
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
