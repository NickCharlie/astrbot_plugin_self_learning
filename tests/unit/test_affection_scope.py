"""回归测试：好感度存储维度（affection_scope）的映射与校验。

per_user 模式把所有会话的好感度统一存到固定键 __user__ 上；映射收口在
SQLAlchemyDatabaseManager._affection_scope_key，学习门直查 ORM 时也必须走
同一套映射，否则会查不到行、按中性因子处理。配置校验对非法值回退
per_group 并告警（插件加载期不宜硬失败）。
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from self_learning_EterU.config import _normalize_affection_scope
from self_learning_EterU.services.database.sqlalchemy_database_manager import (
    SQLAlchemyDatabaseManager,
)
from self_learning_EterU.services.state.emotion_learning_gate import EmotionLearningGate


def _make_manager(scope):
    config = SimpleNamespace(affection_scope=scope)
    manager = SQLAlchemyDatabaseManager.__new__(SQLAlchemyDatabaseManager)
    manager.config = config
    return manager


class TestNormalizeAffectionScope:
    def test_valid_values_passthrough(self):
        assert _normalize_affection_scope("per_group") == "per_group"
        assert _normalize_affection_scope("per_user") == "per_user"

    def test_case_and_whitespace_normalized(self):
        assert _normalize_affection_scope(" PER_USER ") == "per_user"
        assert _normalize_affection_scope("Per_Group") == "per_group"

    def test_invalid_value_falls_back_to_per_group(self):
        assert _normalize_affection_scope("per-chat") == "per_group"
        assert _normalize_affection_scope("") == "per_group"
        assert _normalize_affection_scope(None) == "per_group"


class TestScopeKeyMapping:
    def test_per_group_passthrough(self):
        manager = _make_manager("per_group")
        assert manager._affection_scope_key("12345") == "12345"

    def test_per_user_maps_to_fixed_key(self):
        manager = _make_manager("per_user")
        assert manager._affection_scope_key("12345") == "__user__"
        # 私聊（group_id 即用户号）与群聊映射到同一个键
        assert manager._affection_scope_key("67890") == "__user__"

    def test_missing_config_attr_defaults_to_per_group(self):
        manager = _make_manager(None)
        manager.config = SimpleNamespace()  # 旧配置无 affection_scope 字段
        assert manager._affection_scope_key("12345") == "12345"


class _CapturingSession:
    """记录执行语句的假 session，用于断言查询参数里的存储键。"""

    def __init__(self):
        self.statements = []

    async def execute(self, stmt=None):
        self.statements.append(stmt)

        class _Result:
            def first(self_inner):
                return None

        return _Result()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _gate_session_params(db_manager, group_id):
    """让学习门读一次好感度，返回实际下发查询中的参数值集合。"""
    session = _CapturingSession()

    class _ProxyDb:
        def __getattr__(self, name):
            return getattr(db_manager, name)

        def get_session(self):
            return session

    gate = EmotionLearningGate(
        config=SimpleNamespace(enable_emotion_learning_gate=True, emotion_gate_threshold=0.3),
        database_manager=_ProxyDb(),
    )
    level = asyncio.run(gate._read_affection_level(group_id, "u1"))

    assert level is None  # 假 session 不返回行
    assert session.statements, "应执行一次好感度查询"
    params = session.statements[0].compile().params
    return set(params.values())


class TestLearningGateUsesScopeMapping:
    def test_per_group_queries_original_group(self):
        manager = _make_manager("per_group")
        values = _gate_session_params(manager, "12345")
        assert "12345" in values
        assert "u1" in values

    def test_per_user_queries_mapped_key(self):
        manager = _make_manager("per_user")
        values = _gate_session_params(manager, "12345")
        assert "__user__" in values
        assert "12345" not in values
        assert "u1" in values

    def test_storage_without_resolver_stays_unmapped(self):
        # 兼容其他未实现 _affection_scope_key 的 IDataStorage 实现
        class _PlainDb:
            def get_session(self):
                return _CapturingSession()

        values = _gate_session_params(_PlainDb(), "12345")
        assert "12345" in values
