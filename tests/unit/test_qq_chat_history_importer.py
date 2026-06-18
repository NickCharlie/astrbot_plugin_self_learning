import json

import pytest
from sqlalchemy import select

from config import PluginConfig
from models.orm.message import RawMessage
from services.database.sqlalchemy_database_manager import SQLAlchemyDatabaseManager
from services.integration.qq_chat_history_importer import QQChatHistoryImporter


def _write_qce_export(root):
    chunks = root / "chunks"
    chunks.mkdir(parents=True)
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "metadata": {"format": "chunked-jsonl"},
                "chatInfo": {
                    "name": "AstrBot 大学",
                    "type": "group",
                    "selfUid": "bot-uid",
                    "selfName": "EterUltimate",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    messages = [
        {
            "id": "m1",
            "timestamp": 1776771236000,
            "time": "2026-04-21T11:33:56.000Z",
            "sender": {"uid": "user-1", "uin": "1001", "name": "Shirley"},
            "type": "text",
            "content": {
                "text": "这不160兆吗",
                "elements": [{"type": "text", "data": {"text": "这不160兆吗"}}],
            },
            "recalled": False,
            "system": False,
        },
        {
            "id": "m2",
            "timestamp": 1776771240000,
            "sender": {"uid": "user-1", "name": "Shirley"},
            "type": "text",
            "content": {
                "text": "[图片:demo.jpg]",
                "elements": [{"type": "image", "data": {"filename": "demo.jpg"}}],
            },
            "recalled": False,
            "system": False,
        },
        {
            "id": "m3",
            "timestamp": 1776771282000,
            "sender": {"uid": "bot-uid", "name": "EterUltimate"},
            "type": "reply",
            "content": {
                "text": "[回复消息]我也是 Windows codex",
                "elements": [
                    {
                        "type": "reply",
                        "data": {
                            "referencedMessageId": "m1",
                            "content": "这不160兆吗",
                        },
                    },
                    {"type": "text", "data": {"text": "我也是 Windows codex"}},
                ],
            },
            "recalled": False,
            "system": False,
        },
        {
            "id": "m4",
            "timestamp": 1776771292000,
            "sender": {"uid": "user-2", "name": "命令用户"},
            "type": "text",
            "content": {"text": "/help"},
            "recalled": False,
            "system": False,
        },
    ]
    (chunks / "chunk_0001.jsonl").write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in messages),
        encoding="utf-8",
    )
    (root / "train_data.json").write_text(
        json.dumps(
            [
                {
                    "instruction": "这个是纯本体",
                    "input": "",
                    "output": "所以游戏都删了",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_qq_chat_history_importer_previews_qce_chunked_jsonl(tmp_path):
    _write_qce_export(tmp_path)

    preview = QQChatHistoryImporter().preview(source_path=tmp_path)

    assert preview["source_format"] == "qce_chunked_jsonl"
    assert preview["group_id"] == "AstrBot 大学"
    assert preview["counts"]["messages"] == 2
    assert preview["counts"]["bot_messages"] == 1
    assert preview["counts"]["unique_senders"] == 2
    assert preview["samples"]["messages"][0]["message"] == "这不160兆吗"
    assert preview["samples"]["messages"][1]["reply_to"] == "m1"


def test_qq_chat_history_importer_can_include_training_pairs(tmp_path):
    _write_qce_export(tmp_path)

    preview = QQChatHistoryImporter().preview(
        source_path=tmp_path,
        include_training_pairs=True,
    )

    assert preview["counts"]["messages"] == 4
    assert preview["counts"]["bot_messages"] == 2
    assert any(
        item["message"] == "所以游戏都删了"
        for item in preview["samples"]["messages"]
    )


@pytest.mark.asyncio
async def test_qq_chat_history_importer_imports_and_deduplicates_raw_messages(tmp_path):
    export_dir = tmp_path / "qce"
    _write_qce_export(export_dir)
    manager = SQLAlchemyDatabaseManager(
        PluginConfig(
            data_dir=str(tmp_path / "plugin"),
            db_type="sqlite",
            enable_web_interface=False,
        )
    )
    try:
        assert await manager.start() is True
        importer = QQChatHistoryImporter(manager)

        first = await importer.import_from_source(source_path=export_dir)
        second = await importer.import_from_source(source_path=export_dir)

        assert first["success"] is True
        assert first["messages_seen"] == 2
        assert first["messages_imported"] == 2
        assert first["duplicate_messages"] == 0
        assert second["messages_imported"] == 0
        assert second["duplicate_messages"] == 2

        async with manager.get_session() as session:
            rows = (
                await session.execute(
                    select(RawMessage).order_by(RawMessage.timestamp.asc())
                )
            ).scalars().all()

        assert len(rows) == 2
        assert rows[0].group_id == "AstrBot 大学"
        assert rows[0].message == "这不160兆吗"
        assert rows[0].message_id.startswith("qq-history:")
        assert rows[1].reply_to == "m1"
        assert rows[1].processed is False
    finally:
        await manager.stop()


def test_qq_chat_history_importer_parses_training_json_file(tmp_path):
    training_file = tmp_path / "train_data.json"
    training_file.write_text(
        json.dumps(
            [{"instruction": "你好", "input": "上下文", "output": "你好呀"}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    preview = QQChatHistoryImporter().preview(
        source_path=training_file,
        default_group_id="group-training",
    )

    assert preview["source_format"] == "alpaca_training_json"
    assert preview["counts"]["messages"] == 2
    assert preview["group_id"] == "group-training"
    assert preview["samples"]["messages"][0]["message"] == "你好 上下文"
    assert preview["samples"]["messages"][1]["is_bot"] is True
