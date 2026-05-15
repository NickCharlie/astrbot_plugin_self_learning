"""Package-path import coverage for AstrBot plugin loading."""
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
