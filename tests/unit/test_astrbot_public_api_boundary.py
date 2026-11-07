"""回归测试：插件只通过公开接口依赖 AstrBot 本体（不对 core 形成硬依赖）。

AstrBot 的公开门面是 ``astrbot.api.*``。``astrbot.core.*`` 属于内部实现，
版本升级时可能重构；插件对它的任何**未加守卫**的导入都会在路径变动时
直接导致整个插件加载失败。本组用例锁定两条约束：

1. 生产代码中的 ``astrbot.core`` 导入必须位于 ``try/except ImportError`` 内，
   且仅限公开门面确实未导出的符号（白名单）；
2. 公开门面已导出的符号（Provider/LLMResponse/ProviderType/Personality/
   MessageType/Plain）必须走 ``astrbot.api``。
"""

import ast
import sys
from pathlib import Path
from types import SimpleNamespace

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

SKIP_DIRS = {"tests", "self_learning_EterU", "__pycache__", ".git", "node_modules", "web_src", "htmlcov"}

# 截至 AstrBot v4.29，astrbot.api 未导出、只能引用内部路径的符号
INTERNAL_ONLY_ALLOWLIST = {
    "astrbot.core.utils.astrbot_path": {"get_astrbot_data_path"},
    "astrbot.core.provider.provider": {"EmbeddingProvider", "RerankProvider"},
    "astrbot.core.provider.entities": {"RerankResult"},
    "astrbot.core.agent.message": {"TextPart"},
    "astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event": {"AiocqhttpMessageEvent"},
}

# 公开门面已导出的符号：禁止再从 core 导入
PUBLIC_FACADE = {"Provider", "LLMResponse", "ProviderType", "Personality", "MessageType", "Plain"}


def _production_files():
    for path in PACKAGE_ROOT.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.relative_to(PACKAGE_ROOT).parts):
            continue
        yield path


def _core_imports(tree):
    """Yield (node, guarded) for every astrbot.core import in the module."""
    guarded_nodes = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            catches_import_error = any(
                handler.type is not None
                and any(
                    isinstance(name, ast.Name) and name.id in {"ImportError", "ModuleNotFoundError", "Exception"}
                    for name in (handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type])
                )
                for handler in node.handlers
            )
            if catches_import_error:
                for child in node.body:
                    for sub in ast.walk(child):
                        guarded_nodes.add(id(sub))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("astrbot.core"):
            yield node, id(node) in guarded_nodes
        elif isinstance(node, ast.Import) and any(a.name.startswith("astrbot.core") for a in node.names):
            yield node, id(node) in guarded_nodes


def test_no_unguarded_astrbot_core_imports():
    offenders = []
    for path in _production_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node, guarded in _core_imports(tree):
            if not guarded:
                offenders.append(f"{path.relative_to(PACKAGE_ROOT)}:{node.lineno}")
    assert offenders == [], f"未加 try/except 守卫的 astrbot.core 导入: {offenders}"


def test_core_imports_limited_to_internal_only_symbols():
    violations = []
    for path in _production_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node, _ in _core_imports(tree):
            if not isinstance(node, ast.ImportFrom):
                violations.append(f"{path.relative_to(PACKAGE_ROOT)}:{node.lineno} import astrbot.core.*")
                continue
            allowed = INTERNAL_ONLY_ALLOWLIST.get(node.module, set())
            for alias in node.names:
                if alias.name in PUBLIC_FACADE or alias.name not in allowed:
                    violations.append(f"{path.relative_to(PACKAGE_ROOT)}:{node.lineno} {node.module}.{alias.name}")
    assert violations == [], f"应改走 astrbot.api 公开门面或补充白名单说明: {violations}"


def test_public_facade_reexports_identical_classes():
    """公开门面重导出的就是同一个类：替换导入路径行为零差异。"""
    from astrbot.api.message_components import Plain as PublicPlain
    from astrbot.api.platform import MessageType as PublicMessageType
    from astrbot.api.provider import LLMResponse, Personality, Provider, ProviderType
    from astrbot.core.db.po import Personality as CorePersonality
    from astrbot.core.message.components import Plain as CorePlain
    from astrbot.core.platform.message_type import MessageType as CoreMessageType
    from astrbot.core.provider.entities import LLMResponse as CoreLLMResponse
    from astrbot.core.provider.entities import ProviderType as CoreProviderType
    from astrbot.core.provider.provider import Provider as CoreProvider

    assert PublicPlain is CorePlain
    assert PublicMessageType is CoreMessageType
    assert LLMResponse is CoreLLMResponse
    assert Personality is CorePersonality
    assert Provider is CoreProvider
    assert ProviderType is CoreProviderType


def test_data_root_falls_back_to_star_tools_contract(monkeypatch, tmp_path):
    """内部 get_astrbot_data_path 不可用时，由公开 StarTools 契约推导数据根。"""
    import self_learning_EterU.main as plugin_main

    plugin_dir = tmp_path / "data" / "plugin_data" / "astrbot_plugin_self_learning"
    monkeypatch.setattr(plugin_main, "get_astrbot_data_path", None)
    monkeypatch.setattr(plugin_main, "StarTools", SimpleNamespace(get_data_dir=lambda: plugin_dir))

    assert Path(plugin_main._astrbot_data_root()) == tmp_path / "data"


def test_data_root_prefers_internal_tool_for_identical_behavior(monkeypatch, tmp_path):
    import self_learning_EterU.main as plugin_main

    monkeypatch.setattr(plugin_main, "get_astrbot_data_path", lambda: str(tmp_path / "astrbot-data"))

    assert plugin_main._astrbot_data_root() == str(tmp_path / "astrbot-data")
