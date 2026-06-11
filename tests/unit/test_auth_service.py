"""Unit tests for optional WebUI password authentication."""

from types import SimpleNamespace

import pytest

from webui.services.auth_service import (
    INITIAL_WEBUI_PASSWORD_ENV_VAR,
    AuthService,
)


class TestAuthService:
    """AuthService remains as a compatibility shim for older callers."""

    def test_init(self, mock_container):
        service = AuthService(mock_container)

        assert service.container == mock_container
        assert service.plugin_config == mock_container.plugin_config
        assert service._password_config is None

    @pytest.mark.asyncio
    async def test_login_is_passwordless(self, mock_container):
        service = AuthService(mock_container)

        success, message, extra_data = await service.login("", "127.0.0.1")

        assert success is True
        assert message == "Passwordless WebUI access granted"
        assert extra_data == {
            "must_change": False,
            "redirect": "/api/index",
        }

    @pytest.mark.asyncio
    async def test_change_password_is_disabled(self, mock_container):
        service = AuthService(mock_container)

        success, message = await service.change_password("old", "new")

        assert success is False
        assert "免密访问" in message

    def test_check_must_change_password_is_false(self, mock_container):
        service = AuthService(mock_container)

        assert service.check_must_change_password() is False

    def test_load_password_config_uses_passwordless_default(self, mock_container):
        service = AuthService(mock_container)
        mock_container.plugin_config.password_config = {}

        config = service.load_password_config()

        assert config == {}

    def test_save_password_config_keeps_legacy_compatibility(self, mock_container):
        service = AuthService(mock_container)
        new_config = {"must_change": False}

        assert service.save_password_config(new_config) is True
        assert service._password_config == new_config
        assert mock_container.plugin_config.password_config == new_config

    @pytest.mark.asyncio
    async def test_login_requires_initial_password_when_enabled(self, tmp_path, monkeypatch):
        monkeypatch.delenv(INITIAL_WEBUI_PASSWORD_ENV_VAR, raising=False)
        container = SimpleNamespace(
            plugin_config=SimpleNamespace(
                enable_webui_password=True,
                data_dir=str(tmp_path),
            )
        )
        service = AuthService(container)

        success, message, extra_data = await service.login(
            "AnyPass123!",
            "127.0.0.2",
        )

        assert success is False
        assert "尚未配置初始密码" in message
        assert extra_data == {"setup_required": True}
        assert not (tmp_path / "password.json").exists()

    @pytest.mark.asyncio
    async def test_login_uses_explicit_initial_password_when_enabled(self, tmp_path, monkeypatch):
        monkeypatch.setenv(INITIAL_WEBUI_PASSWORD_ENV_VAR, "InitialPass123!")
        container = SimpleNamespace(
            plugin_config=SimpleNamespace(
                enable_webui_password=True,
                data_dir=str(tmp_path),
            )
        )
        service = AuthService(container)

        success, message, extra_data = await service.login(
            "InitialPass123!",
            "127.0.0.4",
        )

        assert success is True
        assert "password must be changed" in message
        assert extra_data == {
            "must_change": True,
            "redirect": "/api/plugin_change_password",
        }
        assert (tmp_path / "password.json").exists()
        assert "password_hash" in container.plugin_config.password_config

    @pytest.mark.asyncio
    async def test_change_password_when_enabled_updates_login_secret(self, tmp_path, monkeypatch):
        monkeypatch.setenv(INITIAL_WEBUI_PASSWORD_ENV_VAR, "InitialPass123!")
        container = SimpleNamespace(
            plugin_config=SimpleNamespace(
                enable_webui_password=True,
                data_dir=str(tmp_path),
            )
        )
        service = AuthService(container)

        success, _, _ = await service.login("InitialPass123!", "127.0.0.3")
        assert success is True

        success, message = await service.change_password(
            "InitialPass123!",
            "NewPass123!",
        )

        assert success is True
        assert message == "密码修改成功"

        success, _, extra_data = await service.login("NewPass123!", "127.0.0.3")
        assert success is True
        assert extra_data == {
            "must_change": False,
            "redirect": "/api/index",
        }
