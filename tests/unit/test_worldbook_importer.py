import json

import pytest
from sqlalchemy import select

from config import PluginConfig
from models.orm.jargon import Jargon
from models.orm.knowledge_graph import KGEntity, KGRelation
from models.orm.learning import PersonaLearningReview
from services.database.sqlalchemy_database_manager import SQLAlchemyDatabaseManager
from services.integration.worldbook_importer import WorldBookImporter


def _sample_worldbook():
    return {
        "name": "测试世界书",
        "entries": {
            "10": {
                "key": ["星门", "传送门"],
                "secondaryKeys": ["遗迹"],
                "content": "星门是一种古代交通设施。",
                "constant": False,
                "order": 20,
                "insertion_order": 3,
                "comment": "星门设定",
            },
            "2": {
                "key": "守夜人, 夜巡",
                "keysecondary": ["城墙"],
                "content": "守夜人负责夜间巡逻。",
                "constant": True,
                "disable": True,
                "order": 5,
            },
        },
    }


def _sample_worldbook_list_entries():
    return {
        "name": "数组世界书",
        "entries": [
            {
                "keys": ["灯塔"],
                "secondary_keys": "海岸",
                "content": "灯塔会在暴风雨时启动。",
                "enabled": True,
            }
        ],
    }


def test_worldbook_importer_parses_dict_entries_in_stable_order():
    package = WorldBookImporter().load_package(payload=_sample_worldbook())

    assert package.name == "测试世界书"
    assert [entry.source_id for entry in package.entries] == ["2", "10"]
    assert package.entries[0].keys == ["守夜人", "夜巡"]
    assert package.entries[0].secondary_keys == ["城墙"]
    assert package.entries[0].constant is True
    assert package.entries[0].enabled is False
    assert package.entries[1].title == "星门设定"
    assert package.entries[1].keywords == ["星门", "传送门", "遗迹"]


def test_worldbook_importer_parses_list_entries_and_string_payload():
    payload = json.dumps(_sample_worldbook_list_entries(), ensure_ascii=False)
    package = WorldBookImporter().load_package(payload=payload)

    assert len(package.entries) == 1
    assert package.entries[0].source_id == "0"
    assert package.entries[0].keys == ["灯塔"]
    assert package.entries[0].secondary_keys == ["海岸"]


def test_worldbook_importer_preview_reports_destinations_and_counts():
    summary = WorldBookImporter().preview(payload=_sample_worldbook())

    assert summary["counts"]["entries"] == 2
    assert summary["counts"]["enabled_entries"] == 1
    assert summary["counts"]["disabled_entries"] == 1
    assert summary["counts"]["constant_entries"] == 1
    assert summary["counts"]["keywords"] == 4
    assert summary["counts"]["secondary_keywords"] == 2
    assert summary["destinations"] == {
        "memories": "persona_update_reviews",
        "jargons": "jargon",
        "knowledge_graph_entities": "kg_entities",
        "knowledge_graph_relations": "kg_relations",
    }


@pytest.mark.asyncio
async def test_worldbook_importer_imports_into_existing_tables(tmp_path):
    manager = SQLAlchemyDatabaseManager(
        PluginConfig(
            data_dir=str(tmp_path / "plugin"),
            db_type="sqlite",
            enable_web_interface=False,
        )
    )
    try:
        assert await manager.start() is True
        importer = WorldBookImporter(manager)
        result = await importer.import_from_source(
            payload=_sample_worldbook(),
            default_group_id="group-1",
        )

        assert result["success"] is True
        assert result["entries_imported"] == 1
        assert result["memory_reviews_imported"] == 1
        assert result["jargons_imported"] == 3
        assert result["kg_entities_imported"] == 4
        assert result["kg_relations_imported"] == 3
        assert result["skipped"] == 1

        async with manager.get_session() as session:
            reviews = (
                await session.execute(
                    select(PersonaLearningReview).where(
                        PersonaLearningReview.update_type == "worldbook_entry"
                    )
                )
            ).scalars().all()
            jargons = (await session.execute(select(Jargon))).scalars().all()
            entities = (await session.execute(select(KGEntity))).scalars().all()
            relations = (await session.execute(select(KGRelation))).scalars().all()

        assert len(reviews) == 1
        assert reviews[0].group_id == "group-1"
        assert reviews[0].new_content == "星门是一种古代交通设施。"
        metadata = json.loads(reviews[0].metadata_)
        assert metadata["source"] == "sillytavern_worldbook"
        assert metadata["worldbook_name"] == "测试世界书"
        assert metadata["worldbook_entry_id"] == "10"
        assert {item.content for item in jargons} == {"星门", "传送门", "遗迹"}
        assert {item.entity_type for item in entities} == {"worldbook_entry", "worldbook_keyword"}
        assert {item.predicate for item in relations} == {"触发关键词"}

        history = await importer.import_history()
        assert history["total"] == 1
        assert history["items"][0]["worldbook_entry_id"] == "10"
        assert history["imports"][0]["entries"] == 1
    finally:
        await manager.stop()


@pytest.mark.asyncio
async def test_worldbook_importer_import_is_idempotent_for_memory_reviews(tmp_path):
    manager = SQLAlchemyDatabaseManager(
        PluginConfig(
            data_dir=str(tmp_path / "plugin"),
            db_type="sqlite",
            enable_web_interface=False,
        )
    )
    try:
        assert await manager.start() is True
        importer = WorldBookImporter(manager)
        first = await importer.import_from_source(
            payload=_sample_worldbook(),
            default_group_id="group-1",
        )
        second = await importer.import_from_source(
            payload=_sample_worldbook(),
            default_group_id="group-1",
        )

        assert first["entries_imported"] == 1
        assert second["entries_imported"] == 0
        assert second["skipped"] == 2

        async with manager.get_session() as session:
            count = (
                await session.execute(
                    select(PersonaLearningReview).where(
                        PersonaLearningReview.update_type == "worldbook_entry"
                    )
                )
            ).scalars().all()
        assert len(count) == 1
    finally:
        await manager.stop()


@pytest.mark.asyncio
async def test_worldbook_importer_can_backfill_jargon_after_memory_only_import(tmp_path):
    manager = SQLAlchemyDatabaseManager(
        PluginConfig(
            data_dir=str(tmp_path / "plugin"),
            db_type="sqlite",
            enable_web_interface=False,
        )
    )
    try:
        assert await manager.start() is True
        importer = WorldBookImporter(manager)
        memory_only = await importer.import_from_source(
            payload=_sample_worldbook(),
            default_group_id="group-1",
            import_memories=True,
            import_jargons=False,
            import_knowledge_graph=False,
        )
        backfill = await importer.import_from_source(
            payload=_sample_worldbook(),
            default_group_id="group-1",
            import_memories=False,
            import_jargons=True,
            import_knowledge_graph=True,
        )

        assert memory_only["memory_reviews_imported"] == 1
        assert backfill["memory_reviews_imported"] == 0
        assert backfill["jargons_imported"] == 3
        assert backfill["kg_relations_imported"] == 3

        async with manager.get_session() as session:
            reviews = (
                await session.execute(
                    select(PersonaLearningReview).where(
                        PersonaLearningReview.update_type == "worldbook_entry"
                    )
                )
            ).scalars().all()
            jargons = (await session.execute(select(Jargon))).scalars().all()

        assert len(reviews) == 1
        assert {item.content for item in jargons} == {"星门", "传送门", "遗迹"}
    finally:
        await manager.stop()
