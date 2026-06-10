import json
import sqlite3

import pytest
from sqlalchemy import select

from config import PluginConfig
from models.orm.expression import ExpressionPattern
from models.orm.jargon import Jargon
from models.orm.learning import PersonaLearningReview, StyleLearningReview
from services.database.sqlalchemy_database_manager import SQLAlchemyDatabaseManager
from services.integration.maibot_learning_importer import MaiBotLearningImporter


def _create_maibot_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE chat_sessions (
            id INTEGER PRIMARY KEY,
            session_id TEXT NOT NULL,
            group_id TEXT,
            user_id TEXT,
            platform TEXT,
            group_name TEXT,
            scope TEXT
        );
        CREATE TABLE expressions (
            id INTEGER PRIMARY KEY,
            situation TEXT NOT NULL,
            style TEXT NOT NULL,
            content_list TEXT NOT NULL,
            count INTEGER NOT NULL,
            session_id TEXT,
            checked BOOLEAN NOT NULL,
            modified_by TEXT,
            create_time TEXT,
            last_active_time TEXT
        );
        CREATE TABLE jargons (
            id INTEGER PRIMARY KEY,
            content TEXT NOT NULL,
            raw_content TEXT,
            meaning TEXT,
            session_id_dict TEXT NOT NULL,
            count INTEGER NOT NULL,
            is_jargon BOOLEAN,
            is_complete BOOLEAN NOT NULL,
            is_global BOOLEAN NOT NULL,
            last_inference_count INTEGER NOT NULL,
            created_by TEXT,
            created_timestamp TEXT,
            updated_timestamp TEXT
        );
        CREATE TABLE chat_history (
            id INTEGER PRIMARY KEY,
            session_id TEXT NOT NULL,
            start_timestamp TEXT,
            end_timestamp TEXT,
            participants TEXT,
            theme TEXT,
            keywords TEXT,
            summary TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO chat_sessions(session_id, group_id, user_id, platform, group_name, scope) VALUES (?, ?, ?, ?, ?, ?)",
        ("sess-1", "group-1", "", "qq", "测试群", "group"),
    )
    conn.execute(
        "INSERT INTO expressions(situation, style, content_list, count, session_id, checked, modified_by, create_time, last_active_time) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "有人开玩笑时",
            "轻轻吐槽一句",
            json.dumps(["也太会了吧"], ensure_ascii=False),
            3,
            "sess-1",
            1,
            "AI",
            "2026-01-01T00:00:00",
            "2026-01-02T00:00:00",
        ),
    )
    conn.execute(
        "INSERT INTO jargons(content, raw_content, meaning, session_id_dict, count, is_jargon, is_complete, is_global, last_inference_count, created_by, created_timestamp, updated_timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "强度",
            json.dumps(["这个强度可以"], ensure_ascii=False),
            "表示程度很高",
            json.dumps({"sess-1": 4}),
            4,
            1,
            1,
            0,
            4,
            "AI",
            "2026-01-01T00:00:00",
            "2026-01-02T00:00:00",
        ),
    )
    conn.execute(
        "INSERT INTO chat_history(session_id, start_timestamp, end_timestamp, participants, theme, keywords, summary) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "sess-1",
            "2026-01-01T00:00:00",
            "2026-01-01T01:00:00",
            json.dumps(["alice", "bot"], ensure_ascii=False),
            "偏好讨论",
            json.dumps(["温和", "简洁"], ensure_ascii=False),
            "用户偏好温和简洁的互动方式。",
        ),
    )
    conn.commit()
    conn.close()


def _create_memorix_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE paragraphs (
            hash TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            metadata TEXT,
            source TEXT,
            knowledge_type TEXT,
            created_at REAL,
            updated_at REAL,
            is_deleted INTEGER DEFAULT 0
        );
        """
    )
    conn.execute(
        "INSERT INTO paragraphs(hash, content, metadata, source, knowledge_type, created_at, updated_at, is_deleted) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "para-1",
            "用户喜欢温和简洁的回复。",
            json.dumps({"group_id": "group-1"}, ensure_ascii=False),
            "chat",
            "preference",
            1767225600,
            1767312000,
            0,
        ),
    )
    conn.commit()
    conn.close()


def test_maibot_learning_importer_exports_normalized_package(tmp_path):
    maibot_db = tmp_path / "maibot.db"
    memorix_db = tmp_path / "metadata.db"
    _create_maibot_db(maibot_db)
    _create_memorix_db(memorix_db)

    importer = MaiBotLearningImporter()
    package = importer.load_package(db_path=maibot_db, memorix_db_path=memorix_db)
    summary = importer.package_summary(package)

    assert summary["counts"]["sessions"] == 1
    assert summary["counts"]["expressions"] == 1
    assert summary["counts"]["checked_expressions"] == 1
    assert summary["counts"]["jargons"] == 1
    assert summary["counts"]["memories"] == 2
    assert package.expressions[0].group_id == "group-1"
    assert package.jargons[0].group_ids == ["group-1"]


def test_maibot_learning_importer_exports_chat_history_memories_without_memorix(tmp_path):
    maibot_db = tmp_path / "maibot.db"
    _create_maibot_db(maibot_db)

    importer = MaiBotLearningImporter()
    package = importer.load_package(db_path=maibot_db)

    assert len(package.memories) == 1
    assert package.memories[0].knowledge_type == "chat_summary"
    assert package.memories[0].metadata["group_id"] == "group-1"
    assert "用户偏好温和简洁" in package.memories[0].content


def test_maibot_learning_importer_discovers_maibot_root_defaults(tmp_path):
    maibot_root = tmp_path / "MaiBot"
    maibot_db = maibot_root / "data" / "MaiBot.db"
    memorix_db = maibot_root / "data" / "a-memorix" / "metadata" / "metadata.db"
    maibot_db.parent.mkdir(parents=True)
    memorix_db.parent.mkdir(parents=True)
    _create_maibot_db(maibot_db)
    _create_memorix_db(memorix_db)

    importer = MaiBotLearningImporter()
    package = importer.load_package(maibot_root=maibot_root)

    assert package.source_paths["maibot_db"] == str(maibot_db.resolve())
    assert package.source_paths["memorix_db"] == str(memorix_db.resolve())
    assert len(package.expressions) == 1
    assert len(package.memories) == 2


def test_maibot_learning_importer_discovers_memorix_config_data_dir(tmp_path):
    maibot_root = tmp_path / "MaiBot"
    maibot_db = maibot_root / "data" / "MaiBot.db"
    memorix_db = maibot_root / "custom-memory" / "metadata" / "metadata.db"
    maibot_db.parent.mkdir(parents=True)
    memorix_db.parent.mkdir(parents=True)
    (maibot_root / "config").mkdir(parents=True)
    (maibot_root / "config" / "a_memorix.toml").write_text(
        '[storage]\ndata_dir = "custom-memory"\n',
        encoding="utf-8",
    )
    _create_maibot_db(maibot_db)
    _create_memorix_db(memorix_db)

    importer = MaiBotLearningImporter()
    package = importer.load_package(maibot_root=maibot_root)

    assert package.source_paths["memorix_db"] == str(memorix_db.resolve())
    assert len(package.memories) == 2


@pytest.mark.asyncio
async def test_maibot_learning_importer_imports_into_plugin_tables(tmp_path):
    maibot_db = tmp_path / "maibot.db"
    memorix_db = tmp_path / "metadata.db"
    _create_maibot_db(maibot_db)
    _create_memorix_db(memorix_db)

    manager = SQLAlchemyDatabaseManager(
        PluginConfig(
            data_dir=str(tmp_path / "plugin"),
            db_type="sqlite",
            enable_web_interface=False,
        )
    )
    try:
        assert await manager.start() is True
        importer = MaiBotLearningImporter(manager)
        package = importer.load_package(db_path=maibot_db, memorix_db_path=memorix_db)
        result = await importer.import_package(package)

        assert result["success"] is True
        assert result["expressions_imported"] == 1
        assert result["expression_patterns_imported"] == 1
        assert result["jargons_imported"] == 1
        assert result["memory_reviews_imported"] == 2
        assert result["destinations"] == {
            "expressions": "style_learning_reviews",
            "approved_expression_patterns": "expression_patterns",
            "jargons": "jargon",
            "memories": "persona_update_reviews",
        }
        assert result["review_breakdown"] == {
            "style_learning_reviews": 1,
            "jargon_candidates": 1,
            "persona_memory_reviews": 2,
        }

        async with manager.get_session() as session:
            style_reviews = (await session.execute(select(StyleLearningReview))).scalars().all()
            expression_patterns = (await session.execute(select(ExpressionPattern))).scalars().all()
            jargons = (await session.execute(select(Jargon))).scalars().all()
            persona_reviews = (
                await session.execute(
                    select(PersonaLearningReview).where(
                        PersonaLearningReview.update_type == "maibot_memory"
                    )
                )
            ).scalars().all()

        assert style_reviews[0].status == "approved"
        assert expression_patterns[0].expression == "轻轻吐槽一句"
        assert jargons[0].content == "强度"
        assert jargons[0].chat_id == "group-1"
        assert persona_reviews[0].group_id == "group-1"
    finally:
        await manager.stop()


@pytest.mark.asyncio
async def test_maibot_learning_importer_import_from_source_parses_string_flags(tmp_path):
    maibot_db = tmp_path / "maibot.db"
    memorix_db = tmp_path / "metadata.db"
    _create_maibot_db(maibot_db)
    _create_memorix_db(memorix_db)

    manager = SQLAlchemyDatabaseManager(
        PluginConfig(
            data_dir=str(tmp_path / "plugin"),
            db_type="sqlite",
            enable_web_interface=False,
        )
    )
    try:
        assert await manager.start() is True
        importer = MaiBotLearningImporter(manager)
        package = importer.load_package(db_path=maibot_db, memorix_db_path=memorix_db)
        result = await importer.import_from_source(
            payload=package.to_dict(),
            import_expressions="false",
            import_jargons="false",
            import_memories="true",
        )

        assert result["success"] is True
        assert result["expressions_imported"] == 0
        assert result["jargons_imported"] == 0
        assert result["memory_reviews_imported"] == 2
        assert result["review_breakdown"] == {
            "style_learning_reviews": 0,
            "jargon_candidates": 0,
            "persona_memory_reviews": 2,
        }

        async with manager.get_session() as session:
            style_reviews = (await session.execute(select(StyleLearningReview))).scalars().all()
            jargons = (await session.execute(select(Jargon))).scalars().all()
            persona_reviews = (
                await session.execute(
                    select(PersonaLearningReview).where(
                        PersonaLearningReview.update_type == "maibot_memory"
                    )
                )
            ).scalars().all()

        assert style_reviews == []
        assert jargons == []
        assert len(persona_reviews) == 2
    finally:
        await manager.stop()


def test_maibot_learning_importer_preview_reports_destinations(tmp_path):
    maibot_db = tmp_path / "maibot.db"
    memorix_db = tmp_path / "metadata.db"
    _create_maibot_db(maibot_db)
    _create_memorix_db(memorix_db)

    importer = MaiBotLearningImporter()
    package = importer.load_package(db_path=maibot_db, memorix_db_path=memorix_db)
    summary = importer.package_summary(package)

    assert summary["destinations"]["expressions"] == "style_learning_reviews"
    assert summary["destinations"]["jargons"] == "jargon"
    assert summary["destinations"]["memories"] == "persona_update_reviews"
    assert summary["review_breakdown"] == {
        "style_learning_reviews": 1,
        "jargon_candidates": 1,
        "persona_memory_reviews": 2,
    }
