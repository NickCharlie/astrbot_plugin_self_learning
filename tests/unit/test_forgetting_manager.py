"""回归测试：三阶段遗忘（ForgettingManager）的周期推进与治理操作。

锁定核心规则：使用/正向反馈重置为 0；连续三个周期无信号删除；
负反馈快速进入二期；宽限期与高权重/全局保护；治理操作直达。
"""

import asyncio
import sys
import time
from pathlib import Path
from types import SimpleNamespace

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from self_learning_EterU.services.learning.forgetting_manager import ForgettingManager

DAY = 86400.0


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, results):
        self.results = list(results)
        self.statements = []
        self.added = []
        self.commits = 0

    async def execute(self, stmt=None):
        self.statements.append(stmt)
        return self.results.pop(0) if self.results else _FakeResult([])

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def texts(self):
        return [str(stmt) for stmt in self.statements]

    def first_update(self, table: str):
        prefix = f"UPDATE {table}"
        for stmt in self.statements:
            if str(stmt).startswith(prefix):
                return stmt
        return None


class _FakeDb:
    def __init__(self, session):
        self.session = session
        self.borrowed = 0

    def get_session(self):
        self.borrowed += 1
        return self.session


def _config(**overrides):
    base = {
        "enable_expression_forgetting": True,
        "forgetting_cycle_days": 7,
        "forgetting_grace_days": 14,
        "forgetting_protect_global_jargon": True,
        "forgetting_negative_fast_track": True,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _pattern(pid, *, created_days_ago=30, active_days_ago=20, stage=0, weight=1.0):
    now = time.time()
    return SimpleNamespace(
        id=pid,
        group_id="g1",
        expression=f"表达{pid}",
        situation="场景",
        weight=weight,
        last_active_time=now - active_days_ago * DAY,
        create_time=now - created_days_ago * DAY,
        forget_stage=stage,
    )


def _jargon(jid, *, confirmed=True, is_global=False, updated_days_ago=20, created_days_ago=30, stage=0):
    now = time.time()
    return SimpleNamespace(
        id=jid,
        content=f"黑话{jid}",
        meaning="释义",
        is_jargon=confirmed,
        is_global=is_global,
        updated_at=now - updated_days_ago * DAY,
        created_at=now - created_days_ago * DAY,
        forget_stage=stage,
        chat_id="g1",
    )


def _feedback(pattern_id, kind, days_ago=1):
    return SimpleNamespace(
        pattern_id=pattern_id,
        user_feedback=kind,
        generated_at=time.time() - days_ago * DAY,
    )


def _make_manager(session, **config_overrides):
    db = _FakeDb(session)
    return ForgettingManager(config=_config(**config_overrides), database_manager=db), db


def test_cycle_advances_resets_and_deletes_expressions():
    session = _FakeSession([
        _FakeResult([  # 表达列表
            _pattern(1, active_days_ago=20, stage=0),   # 未使用 → 推进到 1
            _pattern(2, active_days_ago=1, stage=2),    # 使用 → 重置 0
            _pattern(3, active_days_ago=20, stage=2),   # 未使用 → 达到 3 → 删除
            _pattern(4, created_days_ago=2),            # 宽限期内 → 跳过
            _pattern(5, weight=5.0, stage=1),           # 高权重 → 保护并归零
        ]),
        _FakeResult([]),  # 窗口内无反馈
        _FakeResult([]),  # 黑话列表：空
    ])
    manager, _ = _make_manager(session)
    report = asyncio.run(manager.run_cycle())

    expr = report["expression"]
    assert expr["checked"] == 5
    assert expr["reset"] == 1          # pattern 2
    assert expr["deleted"] == 1        # pattern 3
    assert expr["protected"] == 1      # pattern 5
    assert expr["advanced"] >= 1       # pattern 1 推进 / pattern 3 计入
    joined = "\n".join(session.texts())
    assert "UPDATE expression_patterns" in joined
    assert "DELETE FROM expression_generation_results" in joined  # 删除连带子记录
    assert "DELETE FROM expression_patterns" in joined
    assert session.commits >= 1


def test_cycle_negative_feedback_fast_tracks_to_stage_two():
    session = _FakeSession([
        _FakeResult([_pattern(1, active_days_ago=20, stage=0)]),
        _FakeResult([_feedback(1, "negative", days_ago=1)]),
        _FakeResult([]),
    ])
    manager, _ = _make_manager(session)
    report = asyncio.run(manager.run_cycle())

    assert report["expression"]["advanced"] >= 1
    # 阶段 0 → 负反馈直达 2（下一个空周期即删）
    update = session.first_update("expression_patterns")
    assert update is not None
    assert update.compile().params["forget_stage"] == 2


def test_cycle_positive_feedback_resets_stage():
    session = _FakeSession([
        _FakeResult([_pattern(1, active_days_ago=20, stage=2)]),
        _FakeResult([_feedback(1, "positive", days_ago=1)]),
        _FakeResult([]),
    ])
    manager, _ = _make_manager(session)
    report = asyncio.run(manager.run_cycle())

    assert report["expression"]["reset"] == 1
    assert report["expression"]["deleted"] == 0


def test_cycle_jargon_stages_and_protection():
    session = _FakeSession([
        _FakeResult([]),  # 表达为空
        _FakeResult([]),
        _FakeResult([  # 已确认黑话
            _jargon(11, updated_days_ago=20, stage=1),  # 未复现 → 推进 2
            _jargon(12, updated_days_ago=1, stage=2),   # 复现 → 重置
            _jargon(13, updated_days_ago=20, stage=2),  # 未复现 → 删除
            _jargon(14, is_global=True, stage=2),       # 全局 → 保护
        ]),
    ])
    manager, _ = _make_manager(session)
    report = asyncio.run(manager.run_cycle())

    jargon = report["jargon"]
    assert jargon["reset"] == 1
    assert jargon["deleted"] == 1
    assert jargon["protected"] == 1
    joined = "\n".join(session.texts())
    assert "DELETE FROM jargon_usage_frequency" in joined
    assert "DELETE FROM jargon" in joined


def test_cycle_global_jargon_unprotected_when_disabled():
    session = _FakeSession([
        _FakeResult([]),
        _FakeResult([]),
        _FakeResult([_jargon(21, is_global=True, updated_days_ago=20, stage=2)]),
    ])
    manager, _ = _make_manager(session, forgetting_protect_global_jargon=False)
    report = asyncio.run(manager.run_cycle())

    assert report["jargon"]["deleted"] == 1


def test_governance_actions_apply_stages():
    session = _FakeSession([])
    manager, _ = _make_manager(session)

    result = asyncio.run(manager.mark_dislike("expression", 7))
    assert result["success"] is True and result["stage"] == 2

    result = asyncio.run(manager.reset_stage("jargon", 8))
    assert result["success"] is True and result["stage"] == 0

    result = asyncio.run(manager.delete_now("jargon", 9))
    assert result["success"] is True
    joined = "\n".join(session.texts())
    assert "DELETE FROM jargon" in joined

    result = asyncio.run(manager.mark_dislike("unknown", 1))
    assert result["success"] is False


def test_status_reports_disabled_state():
    manager = ForgettingManager(config=_config(enable_expression_forgetting=False), database_manager=None)
    status = asyncio.run(manager.status())
    assert status["enabled"] is False
    assert status["running"] is False
    assert status["config"]["cycle_days"] == 7


def test_disabled_manager_does_not_start_loop():
    manager = ForgettingManager(config=_config(enable_expression_forgetting=False), database_manager=None)
    started = asyncio.run(manager.start())
    assert started is False
    assert manager._task is None
