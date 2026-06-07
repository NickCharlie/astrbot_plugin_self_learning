"""Package-path import coverage for AstrBot plugin loading."""
import builtins
import importlib
import importlib.util
import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[2]


def _load_plugin_package(alias: str):
    spec = importlib.util.spec_from_file_location(
        alias,
        PLUGIN_ROOT / "__init__.py",
        submodule_search_locations=[str(PLUGIN_ROOT)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


def _cleanup_alias(alias: str) -> None:
    for name in list(sys.modules):
        if name == alias or name.startswith(f"{alias}."):
            sys.modules.pop(name, None)


def test_database_modules_import_under_astrbot_package_path():
    alias = "data.plugins.astrbot_plugin_self_learning_pkgtest"
    _cleanup_alias(alias)

    try:
        _load_plugin_package(alias)

        engine_module = importlib.import_module(f"{alias}.core.database.engine")
        manager_module = importlib.import_module(
            f"{alias}.services.database.sqlalchemy_database_manager"
        )

        assert engine_module.Base.__module__.startswith(f"{alias}.models.orm")
        assert manager_module.SQLAlchemyDatabaseManager.__module__.startswith(alias)
    finally:
        _cleanup_alias(alias)


def test_webui_persona_review_service_imports_under_astrbot_package_path():
    alias = "data.plugins.astrbot_plugin_self_learning_webui_pkgtest"
    _cleanup_alias(alias)

    try:
        _load_plugin_package(alias)
        module = importlib.import_module(f"{alias}.webui.services.persona_review_service")

        assert module.UPDATE_TYPE_STYLE_LEARNING
        assert module.normalize_update_type("style_learning")
    finally:
        _cleanup_alias(alias)


def test_webui_manager_uses_deferred_annotations_for_lazy_server_import():
    """Python 3.11 evaluates annotations unless this future import is present."""
    manager_source = (PLUGIN_ROOT / "webui" / "manager.py").read_text(
        encoding="utf-8"
    )

    assert "from __future__ import annotations" in manager_source


def test_official_plugin_page_api_registers_dashboard_overview_route():
    alias = "data.plugins.astrbot_plugin_self_learning_pageapi_pkgtest"
    _cleanup_alias(alias)

    class _Context:
        def __init__(self):
            self.routes = []

        def register_web_api(self, route, handler, methods, desc):
            self.routes.append((route, handler, methods, desc))

    class _Plugin:
        def __init__(self):
            self.context = _Context()

    try:
        _load_plugin_package(alias)
        module = importlib.import_module(f"{alias}.core.page_api")
        plugin = _Plugin()
        api = module.PluginPageApi(plugin)
        api.register_routes()

        assert module.PAGE_API_PREFIX == "/astrbot_plugin_self_learning/page"
        assert plugin.context.routes == [
            (
                "/astrbot_plugin_self_learning/page/overview",
                api.get_overview,
                ["GET"],
                "Self Learning embedded dashboard overview",
            )
        ]
    finally:
        _cleanup_alias(alias)


def test_startup_imports_without_manual_optional_dependencies(monkeypatch):
    """Plugin startup modules should import before settings-triggered pip install."""
    import astrbot.api  # noqa: F401 - ensure framework logger is loaded before import guard

    alias = "data.plugins.astrbot_plugin_self_learning_optional_pkgtest"
    _cleanup_alias(alias)

    blocked_roots = {"apscheduler", "cachetools", "emoji", "psutil"}
    real_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if level == 0 and name.split(".", 1)[0] in blocked_roots:
            root = name.split(".", 1)[0]
            raise ModuleNotFoundError(f"No module named '{root}'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    try:
        _load_plugin_package(alias)

        module_names = [
            f"{alias}.utils.cache_manager",
            f"{alias}.utils.task_scheduler",
            f"{alias}.services.core_learning",
            f"{alias}.services.social.social_context_injector",
            f"{alias}.services.jargon.jargon_query",
            f"{alias}.services.monitoring.health_checker",
            f"{alias}.services.monitoring.collector",
            f"{alias}.services.analysis.multidimensional_analyzer",
            f"{alias}.services.state.enhanced_psychological_state_manager",
        ]
        modules = {
            name: importlib.import_module(name)
            for name in module_names
        }

        cache_manager = modules[f"{alias}.utils.cache_manager"].CacheManager()
        cache_manager.set("general", "startup", "ok")
        assert cache_manager.get("general", "startup") == "ok"

        scheduler = modules[f"{alias}.utils.task_scheduler"].TaskSchedulerManager()
        job = scheduler.add_interval_job(lambda: None, "startup_probe", seconds=1)
        assert job.id == "startup_probe"
    finally:
        _cleanup_alias(alias)


def test_webui_manager_imports_without_manual_web_dependencies(monkeypatch):
    """WebUI package imports must not require quart/hypercorn before manual install."""
    import astrbot.api  # noqa: F401 - ensure framework logger is loaded before import guard

    alias = "data.plugins.astrbot_plugin_self_learning_webdeps_pkgtest"
    _cleanup_alias(alias)

    blocked_roots = {"hypercorn", "quart", "quart_cors"}
    real_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if level == 0 and name.split(".", 1)[0] in blocked_roots:
            root = name.split(".", 1)[0]
            raise ModuleNotFoundError(f"No module named '{root}'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    class _Config:
        enable_web_interface = True
        web_interface_port = 7833
        web_interface_host = "127.0.0.1"

    try:
        _load_plugin_package(alias)
        webui_pkg = importlib.import_module(f"{alias}.webui")
        manager_module = importlib.import_module(f"{alias}.webui.manager")

        manager = manager_module.WebUIManager(
            plugin_config=_Config(),
            context=object(),
            factory_manager=object(),
            perf_tracker=None,
            group_id_to_unified_origin={},
        )

        assert manager.create_server() is False

        try:
            getattr(webui_pkg, "Server")
        except ModuleNotFoundError as exc:
            assert "hypercorn" in str(exc)
        else:
            raise AssertionError("Server should remain unavailable until WebUI deps exist")
    finally:
        _cleanup_alias(alias)


def test_webui_app_imports_without_quart_cors(monkeypatch):
    """WebUI app should fall back cleanly when quart_cors is absent."""
    import astrbot.api  # noqa: F401 - ensure framework logger is loaded before import guard

    alias = "data.plugins.astrbot_plugin_self_learning_webapp_pkgtest"
    _cleanup_alias(alias)

    blocked_roots = {"quart_cors"}
    real_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if level == 0 and name.split(".", 1)[0] in blocked_roots:
            root = name.split(".", 1)[0]
            raise ModuleNotFoundError(f"No module named '{root}'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    try:
        _load_plugin_package(alias)
        app_module = importlib.import_module(f"{alias}.webui.app")

        app = app_module.create_app()

        assert app is not None
        assert app.secret_key is not None
    finally:
        _cleanup_alias(alias)
