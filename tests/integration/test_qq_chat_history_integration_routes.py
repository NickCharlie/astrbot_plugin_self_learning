import json
from types import SimpleNamespace

import pytest
from quart import Quart
from sqlalchemy import select

from config import PluginConfig
from models.orm.message import RawMessage
from services.database.sqlalchemy_database_manager import SQLAlchemyDatabaseManager
import webui.blueprints.integrations as integrations_module
from webui.blueprints.integrations import _qq_chat_source_args, integrations_bp


def _write_qce_export(root):
    chunks = root / "chunks"
    chunks.mkdir(parents=True)
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "chatInfo": {
                    "name": "AstrBot 大学",
                    "selfUid": "bot-uid",
                    "selfName": "EterUltimate",
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    items = [
        {
            "id": "q1",
            "timestamp": 1776771236000,
            "sender": {"uid": "user-1", "name": "Shirley"},
            "type": "text",
            "content": {"text": "这不160兆吗"},
            "recalled": False,
            "system": False,
        },
        {
            "id": "q2",
            "timestamp": 1776771282000,
            "sender": {"uid": "bot-uid", "name": "EterUltimate"},
            "type": "text",
            "content": {"text": "所以游戏都删了"},
            "recalled": False,
            "system": False,
        },
    ]
    (chunks / "chunk_0001.jsonl").write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in items),
        encoding="utf-8",
    )


def test_qq_chat_source_args_accepts_local_history_path():
    args = _qq_chat_source_args(
        {
            "source_path": "C:/Users/example/chat",
            "payload": {"messages": []},
            "json_text": "[]",
        }
    )

    assert args["source_path"] == "C:/Users/example/chat"
    assert args["payload"] == {"messages": []}
    assert args["json_text"] == "[]"


@pytest.fixture
async def app(monkeypatch, tmp_path):
    manager = SQLAlchemyDatabaseManager(
        PluginConfig(
            data_dir=str(tmp_path / "plugin"),
            db_type="sqlite",
            enable_web_interface=False,
        )
    )
    assert await manager.start() is True
    monkeypatch.setattr(
        integrations_module,
        "get_container",
        lambda: SimpleNamespace(database_manager=manager),
    )

    app = Quart(__name__)
    app.config["TESTING"] = True
    app.secret_key = "test-secret-key"
    app.register_blueprint(integrations_bp)
    app.database_manager = manager
    try:
        yield app
    finally:
        await manager.stop()


@pytest.fixture
async def client(app):
    return app.test_client()


@pytest.mark.asyncio
async def test_qq_chat_history_preview_route_reports_counts(client, tmp_path):
    export_dir = tmp_path / "qce"
    _write_qce_export(export_dir)

    response = await client.post(
        "/api/integrations/qq-chat-history/preview",
        json={"source_path": str(export_dir)},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["success"] is True
    assert data["data"]["counts"]["messages"] == 2
    assert data["data"]["counts"]["bot_messages"] == 1
    assert data["data"]["group_id"] == "AstrBot 大学"


@pytest.mark.asyncio
async def test_qq_chat_history_import_route_writes_raw_messages(client, app, tmp_path):
    export_dir = tmp_path / "qce"
    _write_qce_export(export_dir)

    response = await client.post(
        "/api/integrations/qq-chat-history/import",
        json={"source_path": str(export_dir), "default_group_id": "group-route"},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["success"] is True
    assert data["data"]["messages_imported"] == 2

    async with app.database_manager.get_session() as session:
        rows = (
            await session.execute(select(RawMessage).order_by(RawMessage.timestamp.asc()))
        ).scalars().all()

    assert len(rows) == 2
    assert {row.group_id for row in rows} == {"group-route"}
    assert rows[0].message == "这不160兆吗"
