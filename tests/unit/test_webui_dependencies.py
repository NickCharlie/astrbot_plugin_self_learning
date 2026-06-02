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


class _ComponentFactory:
    pass


class _FactoryManager:
    def __init__(self, service_factory):
        self.service_factory = service_factory
        self.component_factory = _ComponentFactory()

    def get_service_factory(self):
        return self.service_factory

    def get_component_factory(self):
        return self.component_factory


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
    assert container.database_degraded is False
    assert container.database_start_error is None
    assert service_factory.create_database_manager_called is False


def test_service_container_records_v2_integration():
    container = ServiceContainer()
    service_factory = _ServiceFactory()
    v2_integration = object()
    plugin_config = SimpleNamespace(data_dir="./data")

    container.initialize(
        plugin_config=plugin_config,
        factory_manager=_FactoryManager(service_factory),
        v2_integration=v2_integration,
    )

    assert container.v2_integration is v2_integration


def test_service_container_exposes_component_factory():
    container = ServiceContainer()
    service_factory = _ServiceFactory()
    factory_manager = _FactoryManager(service_factory)
    plugin_config = SimpleNamespace(data_dir="./data")

    container.initialize(
        plugin_config=plugin_config,
        factory_manager=factory_manager,
    )

    assert container.factory_manager is factory_manager
    assert container.component_factory is factory_manager.component_factory


def test_service_container_records_database_degraded_state():
    container = ServiceContainer()
    service_factory = _ServiceFactory()
    injected_database_manager = object()
    plugin_config = SimpleNamespace(data_dir="./data")

    container.initialize(
        plugin_config=plugin_config,
        factory_manager=_FactoryManager(service_factory),
        database_manager=injected_database_manager,
        database_degraded=True,
        database_start_error="connection was closed in the middle of operation",
    )

    assert container.database_manager is injected_database_manager
    assert container.database_degraded is True
    assert container.database_start_error == "connection was closed in the middle of operation"


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


@pytest.mark.asyncio
async def test_webui_manager_passes_v2_integration(monkeypatch):
    from webui import dependencies as dependencies_module
    from webui.manager import WebUIManager

    calls = {}
    webui_container = SimpleNamespace(perf_collector=None)
    database_manager = object()
    v2_integration = object()
    plugin_instance = SimpleNamespace(
        db_manager=database_manager,
        v2_integration=v2_integration,
    )

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

    assert calls["v2_integration"] is v2_integration


@pytest.mark.asyncio
async def test_webui_manager_starts_plugin_database_manager_before_registration(monkeypatch):
    from webui import dependencies as dependencies_module
    from webui.manager import WebUIManager

    class _DatabaseManager:
        def __init__(self):
            self._started = False
            self.engine = None
            self.start_calls = 0

        async def start(self):
            self.start_calls += 1
            self._started = True
            self.engine = object()
            return True

    calls = {}
    webui_container = SimpleNamespace(perf_collector=None)
    database_manager = _DatabaseManager()
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

    assert database_manager.start_calls == 1
    assert database_manager._started is True
    assert calls["database_manager"] is database_manager
    assert calls["database_degraded"] is False
    assert calls["database_start_error"] is None


@pytest.mark.asyncio
async def test_webui_manager_registers_services_when_database_start_returns_false(monkeypatch):
    from webui import dependencies as dependencies_module
    from webui.manager import WebUIManager

    class _DatabaseManager:
        def __init__(self):
            self._started = False
            self.engine = None
            self.start_calls = 0

        async def start(self):
            self.start_calls += 1
            return False

    calls = {}
    webui_container = SimpleNamespace(perf_collector=None)
    database_manager = _DatabaseManager()
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

    assert database_manager.start_calls == 1
    assert calls["database_manager"] is database_manager
    assert calls["database_degraded"] is True
    assert calls["database_start_error"] == "数据库管理器启动返回 False"
    assert webui_container.perf_collector == "perf"


@pytest.mark.asyncio
async def test_webui_manager_registers_services_when_database_start_raises(monkeypatch):
    from webui import dependencies as dependencies_module
    from webui.manager import WebUIManager

    class _DatabaseManager:
        def __init__(self):
            self._started = False
            self.engine = None
            self.start_calls = 0

        async def start(self):
            self.start_calls += 1
            raise ConnectionError("connection was closed in the middle of operation")

    calls = {}
    webui_container = SimpleNamespace(perf_collector=None)
    database_manager = _DatabaseManager()
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

    assert database_manager.start_calls == 1
    assert calls["database_manager"] is database_manager
    assert calls["database_degraded"] is True
    assert calls["database_start_error"] == "connection was closed in the middle of operation"
    assert webui_container.perf_collector == "perf"
