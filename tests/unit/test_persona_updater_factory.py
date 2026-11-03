"""回归测试：ComponentFactory 创建的人格更新器必须拿到数据库管理器。

``PersonaUpdater.__init__`` 的第 5 个参数是 ``db_manager``（人格更新审查记录读写与
表达模式学习都依赖它），但 ``ComponentFactory.create_persona_updater`` 早期把
``service_factory.get_prompts()``（``statics.prompts`` 模块）按位置传给了它，导致插件
实例上的 ``persona_updater.db_manager`` 实际是 prompts 模块，相关调用直接踩空。
"""

import sys
from pathlib import Path
from types import SimpleNamespace

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

import pytest  # noqa: E402

from self_learning_EterU.core import factory as factory_module  # noqa: E402
from self_learning_EterU.core.factory import ComponentFactory  # noqa: E402


def _component_factory(database_manager):
    """构造只依赖数据库管理器的最小 ComponentFactory。"""
    service_factory = SimpleNamespace(
        _service_cache={},
        _registry=SimpleNamespace(register_service=lambda *args, **kwargs: None),
        get_prompts=lambda: factory_module.prompts,
        create_database_manager=lambda: database_manager,
    )
    return ComponentFactory(SimpleNamespace(), service_factory)


@pytest.mark.unit
def test_create_persona_updater_receives_database_manager(monkeypatch):
    import self_learning_EterU.services.persona as persona_package

    captured = {}

    class _Recorder:
        def __init__(
            self,
            config,
            context,
            backup_manager,
            llm_client=None,
            db_manager=None,
        ):
            captured["config"] = config
            captured["context"] = context
            captured["backup_manager"] = backup_manager
            captured["llm_client"] = llm_client
            captured["db_manager"] = db_manager

    monkeypatch.setattr(persona_package, "PersonaUpdater", _Recorder)

    database_manager = object()
    context = object()
    backup_manager = object()
    component_factory = _component_factory(database_manager)

    component_factory.create_persona_updater(context, backup_manager)

    assert captured["db_manager"] is database_manager
    assert captured["context"] is context
    assert captured["backup_manager"] is backup_manager
    assert captured["llm_client"] is None


@pytest.mark.unit
def test_create_persona_updater_never_passes_prompts_module(monkeypatch):
    """prompts 模块不得再被当成 db_manager 传入（回归守卫）。"""
    import self_learning_EterU.services.persona as persona_package

    captured = {}

    class _Recorder:
        def __init__(self, config, context, backup_manager, llm_client=None, db_manager=None):
            captured["db_manager"] = db_manager

    monkeypatch.setattr(persona_package, "PersonaUpdater", _Recorder)

    component_factory = _component_factory(object())
    component_factory.create_persona_updater(object(), object())

    assert captured["db_manager"] is not factory_module.prompts
