from types import SimpleNamespace
import sys

import pytest

from webui.dependencies import ServiceContainer


class _ServiceFactory:
    def __init__(self):
        self.created_database_manager = object()
        self.create_database_manager_called = False

    def create_persona_manager(self):
        return object()

    def create_persona_backup_manager(self):
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


def _fresh_container() -> ServiceContainer:
    """绕开进程级单例，避免容器状态在用例间泄漏。"""
    container = object.__new__(ServiceContainer)
    container._initialized = False
    ServiceContainer.__init__(container)
    return container


def _plugin_instance(database_manager=None):
    """构造一个 bootstrap 已完成、但从未启动独立 WebUI 的插件实例。"""
    service_factory = _ServiceFactory()
    return SimpleNamespace(
        plugin_config=SimpleNamespace(
            data_dir="./data",
            enable_web_interface=True,
            web_interface_host="127.0.0.1",
            web_interface_port=7833,
        ),
        factory_manager=_FactoryManager(service_factory),
        db_manager=database_manager if database_manager is not None else object(),
        config=SimpleNamespace(config_path="./cmd_config.json"),
        context=SimpleNamespace(persona_manager=None),
        group_id_to_unified_origin={"123": "Default\\QQ\\123"},
        feature_delegation=object(),
        v2_integration=None,
        persona_updater=object(),
        _perf_tracker=object(),
    )


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


def test_bind_plugin_populates_container_without_webui_server():
    """issue #283：独立 WebUI 未启动时，官方面板页也必须拿到已绑定的容器。"""
    container = _fresh_container()
    plugin = _plugin_instance()

    assert container.bound is False
    assert container.bind_plugin(plugin) is True

    assert container.bound is True
    assert container.plugin_config is plugin.plugin_config
    assert container.database_manager is plugin.db_manager
    assert container.factory_manager is plugin.factory_manager
    assert container.group_id_to_unified_origin == plugin.group_id_to_unified_origin
    assert container.webui_config is not None
    # 面板日志里的「persona_updater 不可用」同样源于容器未绑定
    assert container.persona_manager is not None
    assert container.persona_updater is not None
    assert container.persona_backup_manager is not None
    assert container.llm_adapter is not None
    assert container.progressive_learning is not None


def test_bind_plugin_reports_false_before_services_ready():
    container = _fresh_container()

    assert container.bind_plugin(None) is False
    assert container.bind_plugin(SimpleNamespace()) is False
    assert container.bound is False


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


class _StartedDatabaseManager:
    """已启动的数据库管理器，使 WebUIManager 不再尝试 start()。"""

    def __init__(self):
        self._started = True
        self.engine = object()


def _webui_manager(monkeypatch, container, plugin, *, enable_web_interface):
    from webui import dependencies as dependencies_module
    from webui.manager import WebUIManager

    monkeypatch.setattr(dependencies_module, "get_container", lambda: container)

    async def no_astrbot_persona_manager():
        return None

    plugin.plugin_config.enable_web_interface = enable_web_interface
    manager = WebUIManager(
        plugin_config=plugin.plugin_config,
        context=plugin.context,
        factory_manager=plugin.factory_manager,
        perf_tracker=plugin._perf_tracker,
        group_id_to_unified_origin=plugin.group_id_to_unified_origin,
        plugin_instance=plugin,
    )
    monkeypatch.setattr(manager, "_acquire_persona_manager", no_astrbot_persona_manager)
    return manager


def test_create_server_binds_container_when_web_interface_disabled(monkeypatch):
    """issue #283：关闭独立 WebUI 后，官方面板页仍需要已绑定的容器。"""
    container = _fresh_container()
    plugin = _plugin_instance(database_manager=_StartedDatabaseManager())

    manager = _webui_manager(
        monkeypatch, container, plugin, enable_web_interface=False
    )

    assert manager.create_server() is False
    assert container.bound is True
    assert container.database_manager is plugin.db_manager
    assert container.perf_collector is plugin._perf_tracker


def test_create_server_binds_container_when_webui_dependencies_missing(monkeypatch):
    """issue #283：WebUI 依赖（fastapi 等）缺失时服务器不创建，容器仍须绑定。

    这是线上最常见的形态：`from .server import Server` 抛 ImportError 后独立服务
    跳过创建，但 AstrBot 官方面板页依旧可访问，不能整页报「未初始化」。
    """
    container = _fresh_container()
    plugin = _plugin_instance(database_manager=_StartedDatabaseManager())
    manager = _webui_manager(
        monkeypatch, container, plugin, enable_web_interface=True
    )
    monkeypatch.setitem(sys.modules, "webui.server", None)

    assert manager.create_server() is False
    assert manager._database_manager is plugin.db_manager
    assert container.bound is True
    assert container.plugin_config is plugin.plugin_config


@pytest.mark.asyncio
async def test_setup_and_start_binds_services_when_server_not_created(monkeypatch):
    """issue #283：Server 未创建（依赖缺失/端口占用）也不能跳过容器绑定。"""
    from webui import dependencies as dependencies_module
    from webui import manager as manager_module

    container = _fresh_container()
    plugin = _plugin_instance(database_manager=_StartedDatabaseManager())
    calls = {}

    async def fake_set_plugin_services(**kwargs):
        calls.update(kwargs)

    monkeypatch.setattr(manager_module, "_server_instance", None)
    monkeypatch.setattr(
        dependencies_module, "set_plugin_services", fake_set_plugin_services
    )

    manager = _webui_manager(
        monkeypatch, container, plugin, enable_web_interface=True
    )

    await manager.setup_and_start()

    assert calls["plugin_config"] is plugin.plugin_config
    assert calls["database_manager"] is plugin.db_manager
    assert container.perf_collector is plugin._perf_tracker
