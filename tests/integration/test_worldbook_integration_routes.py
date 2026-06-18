from types import SimpleNamespace

import pytest
from quart import Quart

from config import PluginConfig
from services.database.sqlalchemy_database_manager import SQLAlchemyDatabaseManager
import webui.blueprints.integrations as integrations_module
from webui.blueprints.integrations import _worldbook_source_args, integrations_bp


def _worldbook_payload():
    return {
        "name": "路线世界书",
        "entries": [
            {
                "key": ["月港"],
                "secondaryKeys": ["潮汐"],
                "content": "月港在退潮时开放。",
                "comment": "月港设定",
            }
        ],
    }


def test_worldbook_source_args_ignores_server_side_paths():
    args = _worldbook_source_args(
        {
            "payload": _worldbook_payload(),
            "json_path": "C:/Windows/win.ini",
            "worldbook_path": "C:/Windows/system.ini",
        }
    )

    assert args["payload"]["name"] == "路线世界书"
    assert args["json_path"] is None


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
async def test_worldbook_preview_route_reports_counts(client):
    response = await client.post(
        "/api/integrations/worldbook/preview",
        json={"payload": _worldbook_payload()},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["success"] is True
    assert data["data"]["counts"]["entries"] == 1
    assert data["data"]["counts"]["keywords"] == 1
    assert data["data"]["counts"]["secondary_keywords"] == 1


@pytest.mark.asyncio
async def test_worldbook_import_and_history_routes(client):
    import_response = await client.post(
        "/api/integrations/worldbook/import",
        json={
            "payload": _worldbook_payload(),
            "default_group_id": "group-route",
            "import_memories": True,
            "import_jargons": True,
            "import_knowledge_graph": True,
        },
    )
    history_response = await client.get("/api/integrations/worldbook/imports?limit=5")

    assert import_response.status_code == 200
    import_data = await import_response.get_json()
    assert import_data["success"] is True
    assert import_data["data"]["entries_imported"] == 1
    assert import_data["data"]["memory_reviews_imported"] == 1
    assert import_data["data"]["jargons_imported"] == 2

    assert history_response.status_code == 200
    history_data = await history_response.get_json()
    assert history_data["success"] is True
    assert history_data["data"]["total"] == 1
    assert history_data["data"]["items"][0]["group_id"] == "group-route"
    assert history_data["data"]["items"][0]["worldbook_name"] == "路线世界书"
