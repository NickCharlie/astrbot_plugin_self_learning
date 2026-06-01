from collections import defaultdict
from pathlib import Path

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy import select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.engine import make_url

from config import PluginConfig
from core.database.engine import DatabaseEngine
from models.orm import Base
from models.orm.learning import StyleLearningReview
from services.database.facades.jargon_facade import JargonFacade
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


@pytest.mark.asyncio
async def test_database_manager_start_initializes_facades_and_learning_storage(tmp_path):
    """Runtime manager startup must create tables and load domain facades."""
    manager = SQLAlchemyDatabaseManager(
        PluginConfig(data_dir=str(tmp_path), enable_web_interface=False)
    )

    try:
        assert await manager.start() is True

        async with manager.engine.engine.begin() as conn:
            created_tables = await conn.run_sync(
                lambda sync_conn: set(sa_inspect(sync_conn).get_table_names())
            )

        assert set(Base.metadata.tables) <= created_tables

        message_id = await manager.save_raw_message(
            {
                "sender_id": "user-a",
                "sender_name": "User A",
                "message": "用于数据库启动回归的学习消息",
                "group_id": "group-a",
                "timestamp": 1234567890,
                "platform": "test",
            }
        )
        assert message_id > 0

        pending_messages = await manager.get_unprocessed_messages(
            limit=10,
            group_id="group-a",
        )
        assert any(message["id"] == message_id for message in pending_messages)
        assert await manager.mark_messages_processed([message_id]) is True

        persona_review_id = await manager.add_persona_learning_review(
            {
                "timestamp": 1234567890.0,
                "group_id": "group-a",
                "update_type": "style_learning",
                "new_content": "表达风格更新",
                "proposed_content": "表达风格更新",
                "confidence_score": 0.9,
                "reason": "runtime regression",
            }
        )
        assert persona_review_id > 0

        jargon_id = await manager.save_or_update_jargon(
            "group-a",
            "测试黑话",
            {
                "raw_content": "[\"测试黑话在群里出现\"]",
                "is_jargon": True,
                "count": 1,
                "is_complete": True,
            },
        )
        assert jargon_id and jargon_id > 0

        async with manager.get_session() as session:
            session.add(
                StyleLearningReview(
                    type="style_learning",
                    group_id="group-a",
                    timestamp=1234567890.0,
                    learned_patterns="[]",
                    status="pending",
                )
            )
            await session.commit()
            rows = (
                await session.execute(select(StyleLearningReview))
            ).scalars().all()

        assert rows
    finally:
        await manager.stop()


@pytest.mark.asyncio
async def test_database_manager_falls_back_to_sqlite_when_postgresql_unavailable(
    tmp_path,
    monkeypatch,
):
    """PostgreSQL startup failures should not prevent local SQLite table setup."""
    manager = SQLAlchemyDatabaseManager(
        PluginConfig(
            data_dir=str(tmp_path),
            db_type="pgsql",
            enable_web_interface=False,
        )
    )

    async def fail_postgresql_database_check():
        raise RuntimeError("postgres unavailable")

    monkeypatch.setattr(
        manager,
        "_ensure_postgresql_database_exists",
        fail_postgresql_database_check,
    )

    try:
        assert manager._get_db_type() == "postgresql"
        assert await manager.start() is True

        url = make_url(manager.engine.database_url)
        assert url.drivername == "sqlite+aiosqlite"
        assert Path(url.database).name == "messages.db"
        assert Path(url.database).exists()

        async with manager.engine.engine.begin() as conn:
            created_tables = await conn.run_sync(
                lambda sync_conn: set(sa_inspect(sync_conn).get_table_names())
            )

        assert set(Base.metadata.tables) <= created_tables
        assert await manager.engine.health_check() is True
    finally:
        await manager.stop()


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


def test_jargon_postgresql_upsert_uses_unique_key_conflict_target():
    stmt = JargonFacade._build_postgresql_jargon_upsert(
        "1083316872",
        "小猫",
        {
            "raw_content": "[]",
            "meaning": "cute person",
            "is_jargon": True,
            "count": 1,
            "is_complete": True,
        },
        1779948680,
    )
    compiled = str(stmt.compile(dialect=postgresql.dialect()))

    assert "ON CONFLICT (chat_id, content) DO UPDATE" in compiled
    assert "RETURNING jargon.id" in compiled
    assert "created_at" in compiled
    assert "updated_at" in compiled
