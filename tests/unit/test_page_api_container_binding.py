"""回归测试：内嵌插件页在 WebUI 服务容器未绑定时自愈（issue #283）。

issue #283：面板页在插件 ``__init__`` 阶段就注册，但 ``ServiceContainer`` 过去只在
独立 WebUI 服务器（7833）启动路径里绑定。WebUI 被关闭、依赖缺失或端口占用而跳过
启动时，容器保持为空，页面每个 section 都报
「数据库管理器未初始化 / Plugin config not initialized / PersonaManager未初始化」。
"""

import sys
from pathlib import Path
from types import SimpleNamespace

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from self_learning_EterU.core.page_api import PluginPageApi  # noqa: E402
from self_learning_EterU.webui.dependencies import ServiceContainer  # noqa: E402


def _fresh_container() -> ServiceContainer:
    """绕开进程级单例，避免容器状态在用例间泄漏。"""
    container = object.__new__(ServiceContainer)
    container._initialized = False
    ServiceContainer.__init__(container)
    return container


def _plugin(database_manager=None) -> SimpleNamespace:
    service_factory = SimpleNamespace(
        create_persona_manager=lambda: object(),
        create_persona_backup_manager=lambda: object(),
        create_database_manager=lambda: object(),
        create_framework_llm_adapter=lambda: object(),
        create_progressive_learning=lambda: object(),
        get_persona_updater=lambda: object(),
        get_service_registry=lambda: object(),
    )
    factory_manager = SimpleNamespace(
        get_service_factory=lambda: service_factory,
        get_component_factory=lambda: SimpleNamespace(),
    )
    return SimpleNamespace(
        plugin_config=SimpleNamespace(data_dir="./data"),
        factory_manager=factory_manager,
        db_manager=database_manager if database_manager is not None else object(),
        config=SimpleNamespace(config_path="./cmd_config.json"),
        context=SimpleNamespace(persona_manager=None),
        group_id_to_unified_origin={},
        feature_delegation=None,
        v2_integration=None,
        persona_updater=object(),
        _perf_tracker="perf",
    )


def _make_api(container, plugin) -> PluginPageApi:
    api = PluginPageApi(plugin=plugin)
    api._imports = lambda: SimpleNamespace(get_container=lambda: container)
    return api


def test_container_self_binds_when_webui_never_started():
    container = _fresh_container()
    plugin = _plugin()
    api = _make_api(container, plugin)

    assert container.bound is False

    resolved = api._container()

    assert container.bound is True
    assert resolved is container
    assert resolved.plugin_config is plugin.plugin_config
    assert resolved.database_manager is plugin.db_manager
    assert resolved.perf_collector == "perf"


def test_container_rebind_skipped_when_already_bound():
    container = _fresh_container()
    plugin = _plugin()
    api = _make_api(container, plugin)
    assert container.bind_plugin(plugin) is True

    bind_calls = []
    container.bind_plugin = lambda instance: bind_calls.append(instance) or True

    api._container()

    assert bind_calls == []


def test_container_keeps_error_when_plugin_services_not_ready():
    container = _fresh_container()
    plugin = SimpleNamespace()  # bootstrap 尚未完成
    api = _make_api(container, plugin)

    resolved = api._container()

    assert resolved.bound is False
    assert resolved.plugin_config is None


def test_container_rebind_is_throttled_between_attempts():
    """服务未就绪时不得每请求重试补绑，避免面板一次加载刷满日志。"""
    container = _fresh_container()
    api = _make_api(container, SimpleNamespace())

    attempts = []
    container.bind_plugin = lambda instance: attempts.append(instance) or False

    api._container()
    api._container()
    api._container()

    assert len(attempts) == 1
