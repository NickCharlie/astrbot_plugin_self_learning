"""回归测试：情绪学习闸门（EmotionLearningGate）的因子计算与判定。

闸门在每条消息进入学习流水线前计算加权分（好感 35% / 消息情感 25% /
Bot 心情 20% / 情绪稳定性 20%），低于阈值跳过学习。此处用脚本化的假
session 锁定因子取值、判定边界与遥测计数。
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from self_learning_EterU.services.state.emotion_learning_gate import EmotionLearningGate


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
        self.executed = []
        self.added = []
        self.commits = 0

    async def execute(self, stmt=None):
        self.executed.append(stmt)
        return self.results.pop(0) if self.results else _FakeResult([])

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeDb:
    def __init__(self, sessions):
        self.sessions = list(sessions)
        self.borrowed = 0

    def get_session(self):
        self.borrowed += 1
        if self.sessions:
            return self.sessions.pop(0)
        return _FakeSession([])


def _row(**kwargs):
    return SimpleNamespace(**kwargs)


def test_gate_positive_combination_passes_and_records():
    db = _FakeDb([
        _FakeSession([_FakeResult([_row(affection_level=80)])]),      # 好感度
        _FakeSession([_FakeResult([_row(mood_type="happy", mood_intensity=1.0)])]),  # 心情
        _FakeSession([_FakeResult([_row(emotional_stability=0.8)])]),  # 稳定性
        _FakeSession([_FakeResult([])]),                               # 日统计查询（无行）
    ])
    gate = EmotionLearningGate(
        config=SimpleNamespace(enable_emotion_learning_gate=True, emotion_gate_threshold=0.3),
        database_manager=db,
    )
    result = asyncio.run(gate.evaluate_and_record("g1", "u1", "你真棒，太厉害了"))

    assert result["enabled"] is True
    assert result["decision"] is True
    # 0.35*0.9 + 0.25*1.0 + 0.2*1.0 + 0.2*0.8 = 0.925
    assert abs(result["score"] - 0.925) < 1e-6
    assert result["factors"]["affection"] == 0.9
    assert result["factors"]["mood"] == 1.0
    assert result["factors"]["stability"] == 0.8
    telemetry = gate.telemetry()
    assert telemetry["counters"] == {"accepted": 1, "skipped": 0}
    # 日统计写入：新增行 + 提交
    persist_session = db.sessions  # 已全部借出
    assert persist_session == []
    assert db.borrowed == 4


def test_gate_negative_combination_is_skipped():
    db = _FakeDb([
        _FakeSession([_FakeResult([_row(affection_level=-60)])]),     # 好感度很低
        _FakeSession([_FakeResult([_row(mood_type="angry", mood_intensity=1.0)])]),
        _FakeSession([_FakeResult([])]),                              # 无情绪画像
        _FakeSession([_FakeResult([])]),
    ])
    gate = EmotionLearningGate(
        config=SimpleNamespace(enable_emotion_learning_gate=True, emotion_gate_threshold=0.3),
        database_manager=db,
    )
    result = asyncio.run(gate.evaluate_and_record("g1", "u1", "你就是个垃圾"))

    assert result["decision"] is False
    # 0.35*0.2 + 0.25*0.05 + 0.2*0.1 + 0.2*0.5 = 0.2025
    assert abs(result["score"] - 0.2025) < 1e-6
    assert gate.telemetry()["counters"] == {"accepted": 0, "skipped": 1}


def test_gate_missing_data_uses_neutral_factors():
    db = _FakeDb([_FakeSession([]), _FakeSession([]), _FakeSession([]), _FakeSession([])])
    gate = EmotionLearningGate(
        config=SimpleNamespace(enable_emotion_learning_gate=True, emotion_gate_threshold=0.3),
        database_manager=db,
    )
    result = asyncio.run(gate.evaluate_and_record("g1", "u1", "今天天气如何"))

    # 无好感(0.5) + 中性情感(0.6) + 无心情(0.5) + 无画像(0.5)
    expected = 0.35 * 0.5 + 0.25 * 0.6 + 0.2 * 0.5 + 0.2 * 0.5
    assert abs(result["score"] - expected) < 1e-6
    assert result["decision"] is True  # 中性消息默认放行


def test_gate_disabled_short_circuits_without_reads():
    db = _FakeDb([])
    gate = EmotionLearningGate(
        config=SimpleNamespace(enable_emotion_learning_gate=False, emotion_gate_threshold=0.3),
        database_manager=db,
    )
    result = asyncio.run(gate.evaluate_and_record("g1", "u1", "任何消息"))

    assert result == {
        "enabled": False,
        "decision": True,
        "score": None,
        "threshold": 0.3,
        "factors": {},
    }
    assert db.borrowed == 0


def test_gate_threshold_is_clamped():
    gate = EmotionLearningGate(
        config=SimpleNamespace(enable_emotion_learning_gate=True, emotion_gate_threshold="9.9"),
        database_manager=None,
    )
    assert gate.threshold == 0.95
    gate2 = EmotionLearningGate(
        config=SimpleNamespace(enable_emotion_learning_gate=True, emotion_gate_threshold="not-a-number"),
        database_manager=None,
    )
    assert gate2.threshold == 0.3


def test_gate_database_failure_fails_open_to_neutral():
    class _BrokenDb:
        def get_session(self):
            raise RuntimeError("database offline")

    gate = EmotionLearningGate(
        config=SimpleNamespace(enable_emotion_learning_gate=True, emotion_gate_threshold=0.3),
        database_manager=_BrokenDb(),
    )
    result = asyncio.run(gate.evaluate_and_record("g1", "u1", "普通聊天"))
    # 全部因子回退中性 → 放行（fail-open）
    assert result["decision"] is True


def test_gate_reuses_affection_manager_rule_analysis():
    from self_learning_EterU.services.state.affection_manager import InteractionType

    db = _FakeDb([_FakeSession([]), _FakeSession([]), _FakeSession([]), _FakeSession([])])

    class _FakeAffectionManager:
        @staticmethod
        def _rule_based_interaction_analysis(message):
            if "谢谢" in message:
                return InteractionType.THANKS
            return None

    gate = EmotionLearningGate(
        config=SimpleNamespace(enable_emotion_learning_gate=True, emotion_gate_threshold=0.3),
        database_manager=db,
        affection_manager=_FakeAffectionManager(),
    )
    factors = asyncio.run(gate._collect_factors("g1", "u1", "谢谢款待"))
    assert factors["sentiment"] == 1.0
