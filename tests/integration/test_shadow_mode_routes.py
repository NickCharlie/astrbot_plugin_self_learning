import time
from types import SimpleNamespace

import pytest
from quart import Quart

from config import PluginConfig
from models.orm.message import RawMessage
from services.database.sqlalchemy_database_manager import SQLAlchemyDatabaseManager
import webui.blueprints.shadow_mode as shadow_module
from webui.blueprints.shadow_mode import shadow_mode_bp


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
        shadow_module,
        "get_container",
        lambda: SimpleNamespace(database_manager=manager),
    )
    now = int(time.time())
    async with manager.get_session() as session:
        for index, text in enumerate(["收到", "马上看", "确实可以", "晚点说"]):
            session.add(
                RawMessage(
                    sender_id="778899",
                    sender_name="群友甲",
                    sender_qq="778899",
                    message=text,
                    group_id="route-group",
                    timestamp=now + index,
                    platform="qq",
                    message_id=f"live-route:{index}",
                    created_at=now,
                    processed=True,
                )
            )
        await session.commit()

    test_app = Quart(__name__)
    test_app.config["TESTING"] = True
    test_app.secret_key = "test-secret-key"
    test_app.register_blueprint(shadow_mode_bp)
    try:
        yield test_app
    finally:
        await manager.stop()


@pytest.mark.asyncio
async def test_shadow_mode_candidate_learn_and_disable_routes(app):
    client = app.test_client()
    candidates_response = await client.get(
        "/api/shadow-mode/candidates?source=live&group_id=route-group"
    )
    assert candidates_response.status_code == 200
    candidates = (await candidates_response.get_json())["data"]["candidates"]
    assert candidates[0]["sender_name"] == "群友甲"
    assert candidates[0]["sender_qq"] == "778899"

    learn_response = await client.post(
        "/api/shadow-mode/profiles",
        json={
            "source_type": "live",
            "source_group_id": "route-group",
            "target_group_id": "route-group",
            "sender_id": "778899",
        },
    )
    assert learn_response.status_code == 201
    profile = (await learn_response.get_json())["data"]
    assert profile["enabled"] is True

    disable_response = await client.put(
        f"/api/shadow-mode/profiles/{profile['id']}",
        json={"enabled": False},
    )
    assert disable_response.status_code == 200
    assert (await disable_response.get_json())["data"]["enabled"] is False
