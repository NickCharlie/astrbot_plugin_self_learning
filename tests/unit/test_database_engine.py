from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.engine import make_url

from config import PluginConfig
from core.database.engine import DatabaseEngine
from models.orm import Base
from models.orm.learning import StyleLearningReview
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
        PluginConfig(
            data_dir=str(tmp_path),
            enable_web_interface=False,
            db_type="sqlite",
        )
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


def test_database_manager_sqlite_url_uses_aiosqlite_and_absolute_path(tmp_path):
    config = PluginConfig(data_dir=str(tmp_path), db_type="sqlite")
    manager = SQLAlchemyDatabaseManager(config)

    url = make_url(manager._get_database_url())

    assert url.drivername == "sqlite+aiosqlite"
    assert Path(url.database).is_absolute()
    assert url.database.endswith("messages.db")


def test_database_manager_default_url_uses_postgresql():
    manager = SQLAlchemyDatabaseManager(PluginConfig())

    url = make_url(manager._get_database_url())

    assert url.drivername == "postgresql+asyncpg"
    assert url.username == "postgres"
    assert url.host == "localhost"
    assert url.port == 5432
    assert url.database == "astrbot_self_learning"


@pytest.mark.parametrize("alias", ["postgres", "pg", "pgsql", "postgresql"])
def test_database_manager_accepts_postgresql_aliases(alias):
    manager = SQLAlchemyDatabaseManager(PluginConfig(db_type=alias))

    assert manager._get_db_type() == "postgresql"


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


@pytest.mark.asyncio
async def test_ensure_postgresql_database_exists_creates_missing_database(monkeypatch):
    executed = []

    class FakeConnection:
        async def fetchval(self, query, database):
            assert query == "SELECT 1 FROM pg_database WHERE datname = $1"
            assert database == "learning_db"
            return None

        async def execute(self, query):
            executed.append(query)

        async def close(self):
            executed.append("closed")

    async def fake_connect(**kwargs):
        assert kwargs["host"] == "localhost"
        assert kwargs["port"] == 5432
        assert kwargs["user"] == "postgres"
        assert kwargs["database"] == "postgres"
        return FakeConnection()

    manager = SQLAlchemyDatabaseManager(
        PluginConfig(
            db_type="postgresql",
            postgresql_database="learning_db",
        )
    )
    monkeypatch.setattr(
        manager,
        "_connect_postgresql",
        lambda asyncpg, database: fake_connect(
            host=manager.config.postgresql_host,
            port=manager.config.postgresql_port,
            user=manager.config.postgresql_user,
            password=manager.config.postgresql_password,
            database=database,
        ),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "asyncpg",
        SimpleNamespace(connect=fake_connect),
    )

    await manager._ensure_postgresql_database_exists()

    assert executed == ['CREATE DATABASE "learning_db"', "closed"]


@pytest.mark.asyncio
async def test_ensure_postgresql_database_exists_skips_existing_database(monkeypatch):
    executed = []

    class FakeConnection:
        async def fetchval(self, query, database):
            assert query == "SELECT 1 FROM pg_database WHERE datname = $1"
            assert database == "learning_db"
            return 1

        async def execute(self, query):
            executed.append(query)

        async def close(self):
            executed.append("closed")

    async def fake_connect(**kwargs):
        assert kwargs["host"] == "localhost"
        assert kwargs["port"] == 5432
        assert kwargs["user"] == "postgres"
        assert kwargs["database"] == "postgres"
        return FakeConnection()

    manager = SQLAlchemyDatabaseManager(
        PluginConfig(
            db_type="pgsql",
            postgresql_database="learning_db",
        )
    )
    monkeypatch.setattr(
        manager,
        "_connect_postgresql",
        lambda asyncpg, database: fake_connect(
            host=manager.config.postgresql_host,
            port=manager.config.postgresql_port,
            user=manager.config.postgresql_user,
            password=manager.config.postgresql_password,
            database=database,
        ),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "asyncpg",
        SimpleNamespace(connect=fake_connect),
    )

    await manager._ensure_postgresql_database_exists()

    assert executed == ["closed"]


def test_database_engine_normalizes_sync_postgresql_url_to_asyncpg():
    normalized = DatabaseEngine._normalize_driver_url(
        "postgresql://user:pass@localhost:5432/learning_db",
        "postgresql+asyncpg",
    )

    url = make_url(normalized)

    assert url.drivername == "postgresql+asyncpg"
    assert url.database == "learning_db"


def test_database_engine_mysql_uses_aiomysql_without_pool_pre_ping(monkeypatch):
    captured = {}

    def fake_create_async_engine(db_url, **kwargs):
        captured["db_url"] = db_url
        captured.update(kwargs)
        return SimpleNamespace(pool=SimpleNamespace())

    monkeypatch.setattr(
        "core.database.engine.create_async_engine",
        fake_create_async_engine,
    )

    engine = object.__new__(DatabaseEngine)
    engine.database_url = "mysql://user:pass@localhost:3306/learning_db"
    engine.echo = False

    created = engine._create_mysql_engine()
    url = make_url(captured["db_url"])

    assert created is not None
    assert url.drivername == "mysql+aiomysql"
    assert captured["pool_pre_ping"] is False
    assert captured["connect_args"]["charset"] == "utf8mb4"
