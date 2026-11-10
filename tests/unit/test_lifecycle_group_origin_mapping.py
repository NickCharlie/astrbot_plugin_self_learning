"""回归测试：学习链路用的人格更新器必须拿到 group_id → UMO 映射表（issue #305）。

``ServiceFactory.create_persona_manager`` 把带缓存的 ``PersonaUpdater`` 注入
``PersonaManagerService``，定时风格学习经由它调用 ``update_persona_with_style``。
映射表此前只交给了 ``ComponentFactory`` 另建的 ``plugin.persona_updater``，缓存的
这一个没有映射表，``_resolve_umo`` 原样返回群号，表达模式因此按框架的回退人格保存，
与同一批风格审查记录使用的人格不一致。
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

import pytest  # noqa: E402

from self_learning_EterU.core.plugin_lifecycle import PluginLifecycle  # noqa: E402
from self_learning_EterU.exceptions import SelfLearningError  # noqa: E402
from self_learning_EterU.services.persona import (  # noqa: E402
    persona_updater as persona_updater_module,
)
from self_learning_EterU.services.persona.persona_manager import (  # noqa: E402
    PersonaManagerService,
)
from self_learning_EterU.services.persona.persona_updater import (  # noqa: E402
    PersonaUpdater,
)

GROUP_ID = "group-a"
GROUP_UMO = "aiocqhttp:GroupMessage:group-a"


def _bootstrapped_services():
    """按 bootstrap 的实际装配关系构造插件：人格管理器持有缓存的人格更新器。"""
    config = SimpleNamespace(auto_backup_enabled=False)
    context = SimpleNamespace(persona_manager=object())

    cached_updater = PersonaUpdater.__new__(PersonaUpdater)
    cached_updater.config = config
    cached_updater.context = context
    cached_updater._logger = Mock()
    cached_updater.format_persona_update_report = AsyncMock(return_value="report")

    persona_manager = PersonaManagerService(config, context, cached_updater, None)
    plugin = SimpleNamespace(
        temporary_persona_updater=SimpleNamespace(),
        progressive_learning=SimpleNamespace(),
        persona_manager=persona_manager,
        service_factory=SimpleNamespace(get_persona_updater=lambda: cached_updater),
    )
    return PluginLifecycle(plugin), persona_manager, cached_updater


@pytest.mark.unit
def test_mapping_distribution_reaches_cached_persona_updater():
    lifecycle, persona_manager, cached_updater = _bootstrapped_services()
    mapping = {GROUP_ID: GROUP_UMO}

    lifecycle._share_group_origin_mapping(mapping)

    plugin = lifecycle._plugin
    assert plugin.temporary_persona_updater.group_id_to_unified_origin is mapping
    assert plugin.progressive_learning.group_id_to_unified_origin is mapping
    assert persona_manager._resolve_umo(GROUP_ID) == GROUP_UMO
    # 映射表在收到消息时才逐步填充，必须共享同一个字典而不是拷贝。
    assert cached_updater.group_id_to_unified_origin is mapping
    assert cached_updater._resolve_umo(GROUP_ID) == GROUP_UMO


@pytest.mark.unit
def test_persona_updater_without_mapping_falls_back_to_raw_group_id():
    # 复现 #305 的失败条件：没有映射表时 _resolve_umo 原样返回群号，
    # 人格解析因此落到框架的回退人格。
    updater = PersonaUpdater.__new__(PersonaUpdater)

    assert updater._resolve_umo(GROUP_ID) == GROUP_ID


@pytest.mark.unit
@pytest.mark.asyncio
async def test_style_update_resolves_persona_with_mapped_origin(monkeypatch):
    lifecycle, persona_manager, _cached_updater = _bootstrapped_services()
    resolve_target_persona = AsyncMock(
        return_value={"persona_id": "persona-a", "prompt": "Original persona"}
    )
    monkeypatch.setattr(
        persona_updater_module, "resolve_target_persona", resolve_target_persona
    )

    lifecycle._share_group_origin_mapping({GROUP_ID: GROUP_UMO})
    assert await persona_manager.update_persona(GROUP_ID, {}, []) is True

    assert resolve_target_persona.await_args.args[2] == GROUP_UMO


class _AnyServiceFactory:
    """返回任意服务占位对象的工厂替身，隔离 bootstrap 对真实服务图的依赖。"""

    def __getattr__(self, name):
        return lambda *args, **kwargs: SimpleNamespace()


class _FakeFeatureDelegation:
    def __init__(self, *_args, **_kwargs):
        pass

    def log_status(self):
        pass

    def should_delegate_reply(self):
        return False


class _FakeFactoryManager:
    def __init__(self, *_args, **_kwargs):
        self._service_factory = _AnyServiceFactory()
        self._component_factory = _AnyServiceFactory()

    def initialize_factories(self, *_args, **_kwargs):
        pass

    def get_service_factory(self):
        return self._service_factory

    def get_component_factory(self):
        return self._component_factory


@pytest.mark.unit
def test_bootstrap_distributes_mapping_to_registered_services(monkeypatch):
    """bootstrap 必须把调用方传入的映射表原样交给分发方法（接线回归）。

    直接驱动真实 ``bootstrap``，用 spy 在映射分发处中断执行；如果 bootstrap
    不再调用分发方法、或传错映射表，这个测试会变红。其余服务用占位工厂隔离，
    避免在单测里拉起整个插件运行时。
    """
    from self_learning_EterU.core import plugin_lifecycle as lifecycle_module
    from self_learning_EterU.services import jargon as jargon_module

    recorded = []

    class _StopBootstrap(Exception):
        pass

    def spy(self, mapping):
        recorded.append(mapping)
        raise _StopBootstrap

    monkeypatch.setattr(PluginLifecycle, "_share_group_origin_mapping", spy)
    monkeypatch.setattr(lifecycle_module, "FactoryManager", _FakeFactoryManager)
    monkeypatch.setattr(lifecycle_module, "FeatureDelegation", _FakeFeatureDelegation)
    for name in ("JargonQueryService", "JargonMinerManager", "JargonStatisticalFilter"):
        monkeypatch.setattr(jargon_module, name, lambda *args, **kwargs: SimpleNamespace())
    monkeypatch.setattr(jargon_module, "build_web_definition_service", lambda *a, **k: None)

    config = SimpleNamespace(
        enable_goal_driven_chat=False,
        knowledge_engine="legacy",
        memory_engine="legacy",
    )
    mapping = {GROUP_ID: GROUP_UMO}
    plugin = SimpleNamespace()

    with pytest.raises(SelfLearningError):
        PluginLifecycle(plugin).bootstrap(config, SimpleNamespace(), mapping)

    assert recorded == [mapping]
    assert plugin.service_factory.get_persona_updater() is not None

