"""回归测试：情绪的强度衰减、按强度消退，以及并存情绪。

背景：
1. 情绪表里存的是写入时的强度，过去在整个 mood_persistence_hours 内保持不变，
   「被哄之后慢慢消气」不可能发生。这里引入可选半衰期：
   读取时按 0.5 ** (经过分钟 / 半衰期) 折算。
2. 单条情绪无法表达「赌气 + 黏人」这类复合状态，因此增加了可选的并存情绪
   （mood_max_concurrent 大于 1 时才会保留）。

两项都默认关闭，不配置时行为与旧版本一致。
"""

import sys
import time
from pathlib import Path
from types import SimpleNamespace

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from self_learning_EterU.services.state.affection_manager import (
    AffectionManager,
    BotMood,
    MoodType,
)

BASE_TS = 1_000_000.0


def _mood(**kwargs):
    base = dict(
        mood_type=MoodType.HAPPY,
        intensity=0.8,
        description="开心",
        start_time=BASE_TS,
        duration_hours=24,
    )
    base.update(kwargs)
    return BotMood(**base)


def _manager(max_concurrent: int):
    manager = AffectionManager.__new__(AffectionManager)
    manager.config = SimpleNamespace(
        mood_max_concurrent=max_concurrent,
        mood_half_life_minutes=0,
        mood_fade_threshold=0,
        mood_persistence_hours=24,
    )
    manager.current_moods = {}
    return manager


class TestEffectiveIntensity:
    def test_disabled_by_default(self):
        assert _mood(intensity=0.8).effective_intensity(now=BASE_TS + 6 * 3600) == 0.8

    def test_half_life_halves_intensity(self):
        mood = _mood(intensity=0.8, half_life_minutes=12)
        assert mood.effective_intensity(now=BASE_TS) == 0.8
        assert abs(mood.effective_intensity(now=BASE_TS + 12 * 60) - 0.4) < 1e-6
        assert abs(mood.effective_intensity(now=BASE_TS + 24 * 60) - 0.2) < 1e-6

    def test_bounds(self):
        mood = _mood(intensity=0.9, half_life_minutes=1)
        assert mood.effective_intensity(now=BASE_TS + 10**6) == 0.0


class TestFadeThreshold:
    def test_ignored_when_disabled(self):
        assert _mood(intensity=0.01, half_life_minutes=1).is_faded(now=BASE_TS + 3600) is False

    def test_faded_below_threshold(self):
        mood = _mood(intensity=0.5, half_life_minutes=12, fade_threshold=0.15)
        assert mood.is_faded(now=BASE_TS) is False
        assert mood.is_faded(now=BASE_TS + 24 * 60) is True


class TestIsActive:
    def test_duration_expiry(self):
        mood = _mood(duration_hours=1)
        assert mood.is_active(now=BASE_TS + 1800) is True
        assert mood.is_active(now=BASE_TS + 3600) is False

    def test_faded_mood_is_not_active(self):
        mood = _mood(intensity=0.6, half_life_minutes=12, fade_threshold=0.2)
        assert mood.is_active(now=BASE_TS) is True
        assert mood.is_active(now=BASE_TS + 30 * 60) is False


class TestSecondaryMoods:
    def test_decay_and_filter(self):
        mood = _mood(
            half_life_minutes=12,
            fade_threshold=0.15,
            secondary_moods=[{"type": "clingy", "intensity": 0.6, "start_time": BASE_TS}],
        )
        active = mood.active_secondaries(now=BASE_TS + 24 * 60)
        assert len(active) == 1
        assert abs(active[0]["intensity"] - 0.15) < 0.01
        assert mood.active_secondaries(now=BASE_TS + 60 * 60) == []

    def test_disabled_when_max_concurrent_is_one(self):
        manager = _manager(max_concurrent=1)
        manager.current_moods["g"] = _mood(start_time=time.time())
        assert manager._compose_secondary("g", MoodType.ANGRY, 0.6) == []

    def test_old_mood_becomes_secondary_when_enabled(self):
        manager = _manager(max_concurrent=2)
        manager.current_moods["g"] = _mood(mood_type=MoodType.PLAYFUL, intensity=0.7, start_time=time.time())
        secondary = manager._compose_secondary("g", MoodType.ANGRY, 0.6)
        assert len(secondary) == 1
        assert secondary[0]["type"] == "playful"

    def test_same_type_keeps_existing_secondary(self):
        manager = _manager(max_concurrent=2)
        existing = [{"type": "sleepy", "intensity": 0.4, "start_time": time.time()}]
        manager.current_moods["g"] = _mood(secondary_moods=existing, start_time=time.time())
        secondary = manager._compose_secondary("g", MoodType.HAPPY, 0.5)
        assert [x["type"] for x in secondary] == ["sleepy"]

    def test_caps_at_limit(self):
        manager = _manager(max_concurrent=2)
        existing = [
            {"type": "sleepy", "intensity": 0.3, "start_time": time.time()},
            {"type": "sad", "intensity": 0.2, "start_time": time.time()},
        ]
        manager.current_moods["g"] = _mood(secondary_moods=existing, start_time=time.time())
        secondary = manager._compose_secondary("g", MoodType.HAPPY, 0.5)
        assert len(secondary) == 1
        assert secondary[0]["type"] == "sleepy"