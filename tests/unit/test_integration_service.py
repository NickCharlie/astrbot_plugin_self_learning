import sys
from pathlib import Path
from types import SimpleNamespace

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from self_learning_EterU.webui.services.integration_service import IntegrationService


def _star(name, plugin, *, root_dir_name=None):
    return SimpleNamespace(
        name=name,
        display_name=name,
        root_dir_name=root_dir_name or name,
        module_path=f"data.plugins.{root_dir_name or name}.main",
        star_cls=plugin,
    )


def test_integration_service_reports_companion_dashboards_and_dev_apis():
    livingmemory = SimpleNamespace(
        config_manager=SimpleNamespace(
            webui_settings={
                "enabled": True,
                "host": "0.0.0.0",
                "port": 8888,
            }
        )
    )
    group_chat_plus = SimpleNamespace(
        enable_web_panel=True,
        web_panel_host="0.0.0.0",
        web_panel_port=8787,
    )
    livingmemory_star = _star(
        "LivingMemory",
        livingmemory,
        root_dir_name="astrbot_plugin_livingmemory",
    )
    group_chat_plus_star = _star(
        "astrbot_plugin_group_chat_plus",
        group_chat_plus,
    )
    delegation = SimpleNamespace(
        status=lambda: {
            "memory_delegated": True,
            "memory_plugin": "LivingMemory",
            "reply_delegated": True,
            "reply_plugin": "astrbot_plugin_group_chat_plus",
        },
        memory_plugin=lambda: livingmemory_star,
        reply_plugin=lambda: group_chat_plus_star,
    )
    container = SimpleNamespace(
        plugin_config=SimpleNamespace(
            delegate_memory_to_livingmemory=True,
            livingmemory_plugin_name="LivingMemory",
            disable_local_memory_when_delegated=True,
            delegate_reply_to_group_chat_plus=True,
            group_chat_plus_plugin_name="astrbot_plugin_group_chat_plus",
            disable_local_reply_when_delegated=True,
        ),
        webui_config=SimpleNamespace(host="127.0.0.1", port=8989),
        feature_delegation=delegation,
    )

    payload = IntegrationService(container).get_status()

    dashboards = {item["id"]: item for item in payload["dashboards"]}
    assert payload["delegation"]["memory_delegated"] is True
    assert dashboards["self_learning"]["dev_api"]["base"] == "/api"
    assert dashboards["livingmemory"]["dashboard"]["url"] == "http://127.0.0.1:8888"
    assert dashboards["livingmemory"]["dev_api"]["base"] == "/astrbot_plugin_livingmemory/page"
    assert "POST /astrbot_plugin_livingmemory/page/graph/query" in dashboards["livingmemory"]["dev_api"]["endpoints"]
    assert dashboards["group_chat_plus"]["dashboard"]["url"] == "http://127.0.0.1:8787"
    assert "GET /api/data/overview" in dashboards["group_chat_plus"]["dev_api"]["endpoints"]
