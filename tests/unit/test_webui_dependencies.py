from types import SimpleNamespace

import pytest

from webui.dependencies import ServiceContainer


class _ServiceFactory:
    def __init__(self):
        self.created_database_manager = object()
        self.create_database_manager_called = False

    def create_persona_manager(self):
        return object()

    def create_database_manager(self):
        self.create_database_manager_called = True
        return self.created_database_manager

    def create_framework_llm_adapter(self):
        return object()

    def create_progressive_learning(self):
        return object()

    def get_persona_updater(self):
        return object()

    def get_service_registry(self):
        return object()


class _FactoryManager:
    def __init__(self, service_factory):
        self.service_factory = service_factory

    def get_service_factory(self):
        return self.service_factory


def test_service_container_uses_injected_database_manager():
    container = ServiceContainer()
    service_factory = _ServiceFactory()
    injected_database_manager = object()
    plugin_config = SimpleNamespace(data_dir="./data")

    container.initialize(
        plugin_config=plugin_config,
        factory_manager=_FactoryManager(service_factory),
        database_manager=injected_database_manager,
    )

    assert container.database_manager is injected_database_manager
    assert service_factory.create_database_manager_called is False


def test_service_container_falls_back_to_factory_database_manager():
    container = ServiceContainer()
    service_factory = _ServiceFactory()
    plugin_config = SimpleNamespace(data_dir="./data")

    container.initialize(
        plugin_config=plugin_config,
        factory_manager=_FactoryManager(service_factory),
    )

    assert container.database_manager is service_factory.created_database_manager
    assert service_factory.create_database_manager_called is True


@pytest.mark.asyncio
async def test_webui_manager_passes_plugin_database_manager(monkeypatch):
    from webui import dependencies as dependencies_module
    from webui.manager import WebUIManager

    calls = {}
    webui_container = SimpleNamespace(perf_collector=None)
    database_manager = object()
    plugin_instance = SimpleNamespace(db_manager=database_manager)

    async def fake_set_plugin_services(**kwargs):
        calls.update(kwargs)

    monkeypatch.setattr(
        dependencies_module,
        "set_plugin_services",
        fake_set_plugin_services,
    )
    monkeypatch.setattr(
        dependencies_module,
        "get_container",
        lambda: webui_container,
    )

    manager = WebUIManager(
        plugin_config=SimpleNamespace(data_dir="./data"),
        context=object(),
        factory_manager=object(),
        perf_tracker="perf",
        group_id_to_unified_origin={},
        plugin_instance=plugin_instance,
    )

    await manager._setup_services(astrbot_persona_manager=None)

    assert calls["database_manager"] is database_manager
    assert webui_container.perf_collector == "perf"
