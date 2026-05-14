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


__all__ = ["SQLAlchemyDatabaseManager"]
