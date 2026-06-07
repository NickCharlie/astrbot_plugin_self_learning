from pathlib import Path
from types import SimpleNamespace
import sys

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from self_learning_EterU.webui.manager import WebUIManager


def _manager() -> WebUIManager:
    return WebUIManager(
        plugin_config=SimpleNamespace(enable_web_interface=True),
        context=SimpleNamespace(),
        factory_manager=object(),
        perf_tracker="perf",
        group_id_to_unified_origin={},
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_webui_manager_continues_when_database_start_returns_false():
    class _DatabaseManager:
        def __init__(self):
            self.engine = None
            self.start_calls = 0

        async def start(self):
            self.start_calls += 1
            return False

    manager = _manager()
    database_manager = _DatabaseManager()

    result = await manager._ensure_database_manager_started(database_manager)

    assert result is database_manager
    assert database_manager.start_calls == 1
    assert manager._database_degraded is True
    assert manager._database_start_error == "数据库管理器启动返回 False"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_webui_manager_continues_when_database_start_raises():
    class _DatabaseManager:
        def __init__(self):
            self.engine = None
            self.start_calls = 0

        async def start(self):
            self.start_calls += 1
            raise ConnectionError("connection was closed in the middle of operation")

    manager = _manager()
    database_manager = _DatabaseManager()

    result = await manager._ensure_database_manager_started(database_manager)

    assert result is database_manager
    assert database_manager.start_calls == 1
    assert manager._database_degraded is True
    assert manager._database_start_error == "connection was closed in the middle of operation"


def test_webui_manager_registers_astrbot_plugin_page_dashboard_url_api():
    calls = []
    context = SimpleNamespace(
        register_web_api=lambda route, handler, methods, desc: calls.append(
            (route, handler, methods, desc)
        )
    )
    config = SimpleNamespace(
        enable_web_interface=True,
        web_interface_host="0.0.0.0",
        web_interface_port=7833,
    )

    WebUIManager(
        plugin_config=config,
        context=context,
        factory_manager=object(),
        perf_tracker="perf",
        group_id_to_unified_origin={},
        plugin_instance=SimpleNamespace(name="astrbot_plugin_self_learning"),
    )

    routes = {item[0] for item in calls}
    assert "astrbot_plugin_self_learning/dashboard_url" in routes
    assert any(item[2] == ["GET"] for item in calls)


def test_webui_manager_public_webui_url_uses_configured_host():
    manager = WebUIManager(
        plugin_config=SimpleNamespace(
            enable_web_interface=True,
            web_interface_host="203.0.113.10",
            web_interface_port=7833,
        ),
        context=SimpleNamespace(),
        factory_manager=object(),
        perf_tracker="perf",
        group_id_to_unified_origin={},
    )

    assert manager._public_webui_base_url() == "http://203.0.113.10:7833"


def test_webui_manager_dashboard_asset_version_uses_dashboard_file_mtime():
    manager = _manager()

    version = manager._dashboard_asset_version()

    assert version.isdigit()
    assert int(version) > 0
