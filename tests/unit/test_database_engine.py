from collections import defaultdict
from pathlib import Path

import pytest
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.engine import make_url

from config import PluginConfig
from core.database.engine import DatabaseEngine
from models.orm import Base
from services.database.sqlalchemy_database_manager import SQLAlchemyDatabaseManager


def test_orm_index_names_are_globally_unique():
    """SQLite/PostgreSQL require index names to be unique per database/schema."""
    index_to_tables = defaultdict(list)
    for table in Base.metadata.sorted_tables:
        for index in table.indexes:
            index_to_tables[index.name].append(table.name)

    duplicates = {
        name: tables
        for name, tables in index_to_tables.items()
        if len(tables) > 1
    }

    assert duplicates == {}


@pytest.mark.asyncio
async def test_sqlite_create_tables_creates_all_orm_tables(tmp_path):
    db_path = tmp_path / "messages.db"
    engine = DatabaseEngine(f"sqlite:///{db_path.as_posix()}")

    try:
        await engine.create_tables(enable_auto_migration=True)

        async with engine.engine.begin() as conn:
            created_tables = await conn.run_sync(
                lambda sync_conn: set(sa_inspect(sync_conn).get_table_names())
            )

        assert set(Base.metadata.tables) <= created_tables
        assert db_path.exists()
    finally:
        await engine.close()


def test_database_manager_sqlite_url_uses_aiosqlite_and_absolute_path(tmp_path):
    config = PluginConfig(data_dir=str(tmp_path))
    manager = SQLAlchemyDatabaseManager(config)

    url = make_url(manager._get_database_url())

    assert url.drivername == "sqlite+aiosqlite"
    assert Path(url.database).is_absolute()
    assert url.database.endswith("messages.db")


def test_database_manager_postgresql_url_preserves_credentials_and_schema():
    config = PluginConfig(
        db_type="postgres",
        postgresql_host="db.example.test",
        postgresql_port=5433,
        postgresql_user="bot_user",
        postgresql_password="pa:ss@word",
        postgresql_database="learning_db",
        postgresql_schema="bot_space",
    )
    manager = SQLAlchemyDatabaseManager(config)

    url = make_url(manager._get_database_url())

    assert url.drivername == "postgresql+asyncpg"
    assert url.username == "bot_user"
    assert url.password == "pa:ss@word"
    assert url.host == "db.example.test"
    assert url.port == 5433
    assert url.database == "learning_db"
    assert url.query["search_path"] == "bot_space"


def test_database_engine_normalizes_sync_postgresql_url_to_asyncpg():
    normalized = DatabaseEngine._normalize_driver_url(
        "postgresql://user:pass@localhost:5432/learning_db",
        "postgresql+asyncpg",
    )

    url = make_url(normalized)

    assert url.drivername == "postgresql+asyncpg"
    assert url.database == "learning_db"
