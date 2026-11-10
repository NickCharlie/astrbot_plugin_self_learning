"""回归测试：group_id→unified_msg_origin 映射表必须覆盖 PersonaManagerService
内层的 PersonaUpdater（issue #305）。

背景：同一次定时风格学习会把表达模式写两遍——
1. 风格审查记录路径经 PersonaManagerService（持有映射表）解析出绑定人格，正确；
2. 人格学习分支经 PersonaUpdater.update_persona_with_style 重新解析人格，但
   PersonaUpdater 长期拿不到映射表，``_resolve_umo`` 退回原始 group_id；
   AstrBot ``get_default_persona_v3`` 对未知 umo 恒兜底返回内置 default 人格
   （astrbot/core/persona_mgr.py），于是同一批「情境＋表达」又重复写入
   default 作用域。
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

import pytest  # noqa: E402

from self_learning_EterU.core.plugin_lifecycle import (  # noqa: E402
    PluginLifecycle,
)


MAPPING = {"101": "aiocqhttp:GroupMessage:101"}
# umo → 绑定人格名（模拟 AstrBot 会话人格绑定）
BOUND_PERSONAS = {"aiocqhttp:GroupMessage:101": "astral"}


def _make_plugin(persona_updater):
    """构造映射分发所需的最小插件骨架。"""
    return SimpleNamespace(
        temporary_persona_updater=SimpleNamespace(group_id_to_unified_origin=None),
        progressive_learning=SimpleNamespace(group_id_to_unified_origin=None),
        persona_manager=SimpleNamespace(group_id_to_unified_origin=None),
        service_factory=SimpleNamespace(get_persona_updater=lambda: persona_updater),
    )


@pytest.mark.unit
def test_distribute_group_id_mapping_reaches_persona_updater():
    """映射分发必须覆盖 PersonaManagerService 内层的 PersonaUpdater。"""
    persona_updater = SimpleNamespace(group_id_to_unified_origin=None)
    plugin = _make_plugin(persona_updater)

    PluginLifecycle(plugin)._distribute_group_id_mapping(MAPPING)

    assert plugin.temporary_persona_updater.group_id_to_unified_origin is MAPPING
    assert plugin.progressive_learning.group_id_to_unified_origin is MAPPING
    assert plugin.persona_manager.group_id_to_unified_origin is MAPPING
    # issue #305：此前唯独漏掉了这个实例
    assert persona_updater.group_id_to_unified_origin is MAPPING


def _build_light_persona_updater(monkeypatch):
    """绕开重单例构造 PersonaUpdater，只保留映射相关行为。"""
    import self_learning_EterU.core.framework_llm_adapter as adapter_module
    import self_learning_EterU.services.persona.persona_updater as pu_module

    monkeypatch.setattr(
        pu_module, "PersonaManagerUpdater",
        lambda *args, **kwargs: SimpleNamespace(),
    )
    monkeypatch.setattr(
        adapter_module, "FrameworkLLMAdapter",
        lambda *args, **kwargs: SimpleNamespace(
            initialize_providers=lambda *a, **k: None
        ),
    )
    monkeypatch.setattr(
        pu_module.ExpressionPatternLearner, "get_instance",
        classmethod(lambda cls, **kwargs: SimpleNamespace()),
    )
    monkeypatch.setattr(
        pu_module.MemoryGraphManager, "get_instance",
        classmethod(lambda cls: SimpleNamespace()),
    )
    monkeypatch.setattr(
        pu_module.KnowledgeGraphManager, "get_instance",
        classmethod(lambda cls: SimpleNamespace()),
    )
    return pu_module.PersonaUpdater(
        SimpleNamespace(), SimpleNamespace(), SimpleNamespace(), None, None
    )


@pytest.mark.unit
def test_persona_updater_declares_mapping_and_resolves_umo(monkeypatch):
    """未注入映射时按原始 group_id 回退；注入后与 PersonaManagerService 同语义。"""
    updater = _build_light_persona_updater(monkeypatch)

    assert updater.group_id_to_unified_origin == {}
    assert updater._resolve_umo("101") == "101"

    updater.group_id_to_unified_origin = dict(MAPPING)
    assert updater._resolve_umo("101") == "aiocqhttp:GroupMessage:101"
    # 映射表缺项仍回退原始 group_id，不猜测
    assert updater._resolve_umo("404") == "404"


async def _run_update_persona_with_style(monkeypatch, updater, umo_bindings):
    """跑通 update_persona_with_style，返回 trigger_learning_for_group 的调用参数。"""
    import self_learning_EterU.services.persona.persona_updater as pu_module

    async def fake_resolve_target_persona(persona_manager, config, umo,
                                          *, require_existing=False, log=None):
        # 模拟 AstrBot get_default_persona_v3 的兜底语义：未知 umo 恒返回
        # 内置 default 人格，绝不返回 None（astrbot/core/persona_mgr.py）。
        bound = umo_bindings.get(str(umo))
        if bound:
            return {"persona_id": bound, "name": bound, "prompt": f"{bound} prompt"}
        return {"persona_id": "default", "name": "default", "prompt": "default"}

    monkeypatch.setattr(
        pu_module, "resolve_target_persona", fake_resolve_target_persona
    )

    style_analysis = {"pattern_count": 1}
    messages = [SimpleNamespace()]
    ok = await updater.update_persona_with_style(
        "101", style_analysis, messages, expression_messages=messages,
    )
    assert ok is True
    return updater.expression_learner.trigger_learning_for_group.await_args


@pytest.mark.unit
async def test_update_persona_with_style_uses_bound_persona_for_expressions(monkeypatch):
    """有映射表时，表达模式学习拿到绑定人格，不再重复写 default 作用域。"""
    updater = _build_light_persona_updater(monkeypatch)
    updater.context = SimpleNamespace(persona_manager=SimpleNamespace())
    updater.config = SimpleNamespace(
        current_persona_name="",  # 「当前目标人格」留空，复现 issue #305 场景
        auto_backup_enabled=False,
        persona_merge_strategy="append",
    )
    updater.group_id_to_unified_origin = dict(MAPPING)
    updater.expression_learner = SimpleNamespace(
        trigger_learning_for_group=AsyncMock(return_value=True)
    )
    updater.memory_graph_manager = SimpleNamespace(
        add_memory_from_message=AsyncMock(return_value=None)
    )
    updater.knowledge_graph_manager = SimpleNamespace(
        add_entity=AsyncMock(return_value=None)
    )
    updater.format_persona_update_report = AsyncMock(return_value="report")

    await_args = await _run_update_persona_with_style(
        monkeypatch, updater, BOUND_PERSONAS
    )
    assert await_args.kwargs["persona_id"] == "astral"


@pytest.mark.unit
async def test_update_persona_without_mapping_degrades_to_default(monkeypatch):
    """缺映射表时复现 issue #305：表达模式学习降级到 default 人格。"""
    updater = _build_light_persona_updater(monkeypatch)
    updater.context = SimpleNamespace(persona_manager=SimpleNamespace())
    updater.config = SimpleNamespace(
        current_persona_name="",
        auto_backup_enabled=False,
        persona_merge_strategy="append",
    )
    updater.expression_learner = SimpleNamespace(
        trigger_learning_for_group=AsyncMock(return_value=True)
    )
    updater.memory_graph_manager = SimpleNamespace(
        add_memory_from_message=AsyncMock(return_value=None)
    )
    updater.knowledge_graph_manager = SimpleNamespace(
        add_entity=AsyncMock(return_value=None)
    )
    updater.format_persona_update_report = AsyncMock(return_value="report")

    await_args = await _run_update_persona_with_style(
        monkeypatch, updater, BOUND_PERSONAS
    )
    assert updater._resolve_umo("101") == "101"  # 未注入映射，退回原始 group_id
    assert await_args.kwargs["persona_id"] == "default"
