"""Integration tests for manual dependency installation endpoint."""
import sys
from unittest.mock import AsyncMock, patch

import pytest
from quart import Quart

from webui.blueprints.config import (
    MANUAL_DEPENDENCY_INSTALL_SOURCE,
    PIP_MIRROR_SOURCES,
    config_bp,
)


class FakeProcess:
    returncode = 0

    async def communicate(self):
        return b"installed", b""


@pytest.fixture
async def app():
    """Create test Quart application."""
    app = Quart(__name__)
    app.config["TESTING"] = True
    app.config["ENABLE_WEB_DEP_INSTALL"] = True
    app.config["ALLOWED_DEPENDENCY_PACKAGES"] = ["quart", "jieba", "networkx>=3.2,<3.5"]
    app.secret_key = "test-secret-key"
    app.register_blueprint(config_bp)
    yield app


@pytest.fixture
async def client(app):
    return app.test_client()


async def authenticate(client):
    async with client.session_transaction() as session:
        session["authenticated"] = True


class TestDependencyInstallEndpoint:
    @pytest.mark.asyncio
    async def test_install_requires_settings_confirmation(self, client):
        await authenticate(client)

        with patch(
            "webui.blueprints.config.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
        ) as create_process:
            response = await client.post("/api/dependencies/install", json={})

        assert response.status_code == 400
        create_process.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_confirmed_settings_request_runs_noninteractive_pip(self, client):
        await authenticate(client)

        with patch(
            "webui.blueprints.config.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=FakeProcess()),
        ) as create_process:
            response = await client.post(
                "/api/dependencies/install",
                json={
                    "manual_confirmed": True,
                    "source": MANUAL_DEPENDENCY_INSTALL_SOURCE,
                },
            )

        assert response.status_code == 200
        create_process.assert_awaited_once()
        cmd = create_process.await_args.args
        assert cmd[:4] == (sys.executable, "-m", "pip", "install")
        assert "--disable-pip-version-check" in cmd
        assert "--no-input" in cmd
        assert "quart" in cmd
        assert "jieba" in cmd
        assert "networkx>=3.2,<3.5" in cmd
        payload = await response.get_json()
        assert payload["tier"] == "full"
        assert payload["tier_label"] == "全能力依赖"
        assert payload["pip_mirror"] == "default"
        assert payload["pip_index_url"] is None

    @pytest.mark.asyncio
    async def test_basic_tier_installs_basic_dependency_subset(self, client):
        await authenticate(client)

        with patch(
            "webui.blueprints.config.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=FakeProcess()),
        ) as create_process:
            response = await client.post(
                "/api/dependencies/install",
                json={
                    "manual_confirmed": True,
                    "source": MANUAL_DEPENDENCY_INSTALL_SOURCE,
                    "tier": "basic",
                },
            )

        assert response.status_code == 200
        create_process.assert_awaited_once()
        cmd = create_process.await_args.args
        assert "quart" in cmd
        assert "jieba" in cmd
        assert "networkx>=3.2,<3.5" not in cmd
        payload = await response.get_json()
        assert payload["tier"] == "basic"
        assert payload["tier_label"] == "基础能力依赖"

    @pytest.mark.asyncio
    async def test_install_with_mirror_adds_index_url(self, client):
        await authenticate(client)

        with patch(
            "webui.blueprints.config.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=FakeProcess()),
        ) as create_process:
            response = await client.post(
                "/api/dependencies/install",
                json={
                    "manual_confirmed": True,
                    "source": MANUAL_DEPENDENCY_INSTALL_SOURCE,
                    "tier": "basic",
                    "pip_mirror": "tsinghua",
                },
            )

        assert response.status_code == 200
        create_process.assert_awaited_once()
        cmd = create_process.await_args.args
        assert "--index-url" in cmd
        assert PIP_MIRROR_SOURCES["tsinghua"]["index_url"] in cmd
        assert cmd.index("--index-url") < cmd.index("quart")
        payload = await response.get_json()
        assert payload["pip_mirror"] == "tsinghua"
        assert payload["pip_mirror_label"] == PIP_MIRROR_SOURCES["tsinghua"]["label"]
        assert payload["pip_index_url"] == PIP_MIRROR_SOURCES["tsinghua"]["index_url"]

    @pytest.mark.asyncio
    async def test_unknown_mirror_is_rejected(self, client):
        await authenticate(client)

        with patch(
            "webui.blueprints.config.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
        ) as create_process:
            response = await client.post(
                "/api/dependencies/install",
                json={
                    "manual_confirmed": True,
                    "source": MANUAL_DEPENDENCY_INSTALL_SOURCE,
                    "pip_mirror": "unknown",
                },
            )

        assert response.status_code == 400
        create_process.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_tier_is_rejected(self, client):
        await authenticate(client)

        with patch(
            "webui.blueprints.config.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
        ) as create_process:
            response = await client.post(
                "/api/dependencies/install",
                json={
                    "manual_confirmed": True,
                    "source": MANUAL_DEPENDENCY_INSTALL_SOURCE,
                    "tier": "unknown",
                },
            )

        assert response.status_code == 400
        create_process.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_install_can_be_disabled_even_with_confirmation(self, client, app):
        await authenticate(client)
        app.config["ENABLE_WEB_DEP_INSTALL"] = False

        with patch(
            "webui.blueprints.config.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
        ) as create_process:
            response = await client.post(
                "/api/dependencies/install",
                json={
                    "manual_confirmed": True,
                    "source": MANUAL_DEPENDENCY_INSTALL_SOURCE,
                },
            )

        assert response.status_code == 403
        create_process.assert_not_awaited()
