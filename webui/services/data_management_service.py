"""
数据管理服务 — 各功能模块数据统计与清空
"""
import shutil
from pathlib import Path
from typing import Dict, Any, Tuple

from astrbot.api import logger


class DataManagementService:
    """数据管理服务"""

    _LEARNING_FILE_NAMES = {
        "learning.log",
        "persona_updates.txt",
        "cross_group_memories.json",
        "group_interests.json",
        "knowledge_graph.json",
        "knowledge_entities.json",
    }
    _LEARNING_FILE_PREFIXES = ("learning_data_export_",)
    _LEARNING_DIR_NAMES = {
        "lightrag",
        "mem0_qdrant",
        "persona_backups",
        "persona_updates",
    }
    _LEGACY_PERSONA_UPDATE_PATTERN = "group_*_incremental_updates.txt"

    def __init__(self, container):
        self.container = container
        self.database_manager = container.database_manager

    def _check_db(self):
        if not self.database_manager:
            raise ValueError('数据库管理器未初始化')

    async def get_data_statistics(self) -> Dict[str, int]:
        """获取各功能模块数据统计"""
        self._check_db()
        return await self.database_manager.get_data_statistics()

    async def clear_messages(self) -> Tuple[bool, str, int]:
        self._check_db()
        result = await self.database_manager.clear_messages_data()
        deleted = result.get('deleted', 0)
        if result.get('success'):
            logger.info(f"[DataManagement] 消息数据已清除，共 {deleted} 行")
            return True, f"已清除 {deleted} 条消息数据", deleted
        return False, "清除消息数据失败", 0

    async def clear_persona_reviews(self) -> Tuple[bool, str, int]:
        self._check_db()
        result = await self.database_manager.clear_persona_reviews_data()
        deleted = result.get('deleted', 0)
        if result.get('success'):
            logger.info(f"[DataManagement] 人格学习/审查数据已清除，共 {deleted} 行")
            return True, f"已清除 {deleted} 条人格学习/审查数据", deleted
        return False, "清除人格学习/审查数据失败", 0

    async def clear_style_learning(self) -> Tuple[bool, str, int]:
        self._check_db()
        result = await self.database_manager.clear_style_learning_data()
        deleted = result.get('deleted', 0)
        if result.get('success'):
            logger.info(f"[DataManagement] 风格学习数据已清除，共 {deleted} 行")
            return True, f"已清除 {deleted} 条风格学习数据", deleted
        return False, "清除风格学习数据失败", 0

    async def clear_jargon(self) -> Tuple[bool, str, int]:
        self._check_db()
        result = await self.database_manager.clear_jargon_data()
        deleted = result.get('deleted', 0)
        if result.get('success'):
            logger.info(f"[DataManagement] 黑话数据已清除，共 {deleted} 行")
            return True, f"已清除 {deleted} 条黑话数据", deleted
        return False, "清除黑话数据失败", 0

    async def clear_learning_history(self) -> Tuple[bool, str, int]:
        self._check_db()
        result = await self.database_manager.clear_learning_history_data()
        deleted = result.get('deleted', 0)
        if result.get('success'):
            logger.info(f"[DataManagement] 学习历史数据已清除，共 {deleted} 行")
            return True, f"已清除 {deleted} 条学习历史数据", deleted
        return False, "清除学习历史数据失败", 0

    async def clear_all(self) -> Tuple[bool, str, int]:
        self._check_db()
        self._reset_runtime_learning_state()
        result = await self.database_manager.clear_all_plugin_data()
        db_deleted = result.get('deleted', 0)
        file_deleted, file_errors = self._clear_learning_file_artifacts()
        self._reset_runtime_learning_state()

        total_deleted = db_deleted + file_deleted
        if result.get('success') and not file_errors:
            logger.info(
                f"[DataManagement] 全部数据已清除，共 {db_deleted} 行，"
                f"{file_deleted} 个文件/目录"
            )
            return True, f"已清除全部 {total_deleted} 条/项数据", total_deleted

        if file_errors:
            logger.warning(
                "[DataManagement] 部分学习文件清除失败: "
                + "; ".join(file_errors[:5])
            )
        return False, "清除全部数据失败（部分可能已清除）", total_deleted

    def _clear_learning_file_artifacts(self) -> Tuple[int, list[str]]:
        """Remove file-backed learning stores that are outside ORM tables."""
        deleted = 0
        errors: list[str] = []
        config = getattr(self.container, "plugin_config", None)
        data_dir = getattr(config, "data_dir", None)

        if data_dir:
            root = Path(data_dir).expanduser()
            try:
                root = root.resolve()
            except OSError:
                errors.append(f"无法解析数据目录: {data_dir}")
            else:
                if root.exists() and root.is_dir():
                    for child in root.iterdir():
                        if not self._is_learning_artifact(child):
                            continue
                        try:
                            if child.is_dir():
                                shutil.rmtree(child)
                            else:
                                child.unlink()
                            deleted += 1
                        except Exception as exc:
                            errors.append(f"{child.name}: {exc}")

        legacy_deleted, legacy_errors = self._clear_legacy_persona_update_files()
        deleted += legacy_deleted
        errors.extend(legacy_errors)
        return deleted, errors

    def _is_learning_artifact(self, path: Path) -> bool:
        name = path.name
        if path.is_dir():
            return name in self._LEARNING_DIR_NAMES
        if name in self._LEARNING_FILE_NAMES:
            return True
        return any(name.startswith(prefix) for prefix in self._LEARNING_FILE_PREFIXES)

    def _clear_legacy_persona_update_files(self) -> Tuple[int, list[str]]:
        """Remove old persona-learning files written to data/persona_updates."""
        update_dir = Path("data") / "persona_updates"
        try:
            update_dir = update_dir.resolve()
        except OSError:
            return 0, [f"无法解析旧版人格学习目录: {update_dir}"]

        if not update_dir.exists() or not update_dir.is_dir():
            return 0, []

        deleted = 0
        errors: list[str] = []
        for path in update_dir.glob(self._LEGACY_PERSONA_UPDATE_PATTERN):
            try:
                if path.is_file():
                    path.unlink()
                    deleted += 1
            except Exception as exc:
                errors.append(f"{path.name}: {exc}")

        try:
            if not any(update_dir.iterdir()):
                update_dir.rmdir()
        except Exception:
            pass

        return deleted, errors

    def _reset_runtime_learning_state(self) -> None:
        """Clear in-memory learning caches so deleted data is not written back."""
        for cache_name in (
            "memory", "context", "embedding_query", "relation",
            "affection", "state", "conversation", "summary", "general",
        ):
            try:
                from ...utils.cache_manager import get_cache_manager
            except ImportError:
                from utils.cache_manager import get_cache_manager
            try:
                get_cache_manager().clear(cache_name)
            except Exception:
                pass

        v2 = getattr(self.container, "v2_integration", None)
        if v2 is not None:
            self._clear_attr_mapping(v2, "_ingestion_buffer")
            for manager_name in ("_knowledge_manager", "_memory_manager", "_exemplar_library"):
                manager = getattr(v2, manager_name, None)
                self._clear_learning_manager_cache(manager)

        for attr_name in (
            "jargon_statistical_filter",
            "jargon_miner_manager",
            "jargon_query_service",
        ):
            self._clear_learning_manager_cache(getattr(self.container, attr_name, None))

        try:
            from ...services.state import EnhancedMemoryGraphManager
            from ...services.integration.knowledge_graph_manager import KnowledgeGraphManager
        except ImportError:
            from services.state import EnhancedMemoryGraphManager
            from services.integration.knowledge_graph_manager import KnowledgeGraphManager

        memory_manager = EnhancedMemoryGraphManager.get_instance()
        self._clear_learning_manager_cache(memory_manager)

        kg_manager = KnowledgeGraphManager.get_instance()
        self._clear_learning_manager_cache(kg_manager)

    def _clear_learning_manager_cache(self, manager) -> None:
        if manager is None:
            return
        for attr_name in (
            "memory_graphs",
            "entity_appear_count",
            "stored_paragraph_hashes",
            "_instances",
            "_processed_counts",
            "_stats_cache",
            "_vector_cache",
        ):
            self._clear_attr_mapping(manager, attr_name)

    @staticmethod
    def _clear_attr_mapping(obj, attr_name: str) -> None:
        value = getattr(obj, attr_name, None)
        if hasattr(value, "clear"):
            try:
                value.clear()
            except Exception:
                pass
