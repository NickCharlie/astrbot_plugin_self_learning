"""Backward-compatible import path for the SQLAlchemy database manager.

The implementation lives in :mod:`services.database.sqlalchemy_database_manager`.
This shim keeps legacy imports and source-contract tests working after the
database layer was split into the ``services.database`` package.
"""
from typing import Any, Dict, List, Optional

try:
    from .database.sqlalchemy_database_manager import (
        SQLAlchemyDatabaseManager as _SQLAlchemyDatabaseManager,
    )
except ImportError:
    from services.database.sqlalchemy_database_manager import (
        SQLAlchemyDatabaseManager as _SQLAlchemyDatabaseManager,
    )


class SQLAlchemyDatabaseManager(_SQLAlchemyDatabaseManager):
    """Compatibility subclass preserving legacy method definitions."""

    async def save_persona_update_record(self, record_data: Dict[str, Any]) -> int:
        return await super().save_persona_update_record(record_data)

    async def update_persona_update_record_status(
        self, record_id: int, status: str, comment: str = None,
    ) -> bool:
        return await super().update_persona_update_record_status(
            record_id, status, comment,
        )

    async def delete_persona_update_record(self, record_id: int) -> bool:
        return await super().delete_persona_update_record(record_id)

    async def get_persona_update_record_by_id(
        self, record_id: int,
    ) -> Optional[Dict[str, Any]]:
        return await super().get_persona_update_record_by_id(record_id)

    async def get_reviewed_persona_update_records(
        self,
        limit: int = 50,
        offset: int = 0,
        status_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        return await super().get_reviewed_persona_update_records(
            limit=limit, offset=offset, status_filter=status_filter,
        )

    async def get_persona_backups(
        self,
        group_id: str = None,
        limit: int = 10,
        include_content: bool = False,
    ) -> List[Dict[str, Any]]:
        return await super().get_persona_backups(
            group_id=group_id,
            limit=limit,
            include_content=include_content,
        )

    async def get_persona_backup(
        self,
        backup_id: int,
        group_id: str = None,
    ) -> Optional[Dict[str, Any]]:
        return await super().get_persona_backup(backup_id, group_id=group_id)

    async def restore_persona_backup(
        self,
        group_id,
        backup_id: int = None,
    ) -> Optional[Dict[str, Any]]:
        return await super().restore_persona_backup(group_id, backup_id)

    async def delete_persona_backup(
        self,
        backup_id: int,
        group_id: str = None,
    ) -> bool:
        return await super().delete_persona_backup(backup_id, group_id=group_id)


__all__ = ["SQLAlchemyDatabaseManager"]
