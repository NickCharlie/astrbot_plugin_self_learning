"""Integration tests for manual dependency installation endpoint."""
import sys
from unittest.mock import AsyncMock, patch

import pytest
from quart import Quart

from webui.blueprints.config import (
    MANUAL_DEPENDENCY_INSTALL_SOURCE,
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
    app.config["ALLOWED_DEPENDENCY_PACKAGES"] = ["quart"]
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
