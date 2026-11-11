"""回归测试：启动时是否沿用「淡化但未过期」的情绪。

背景：
情绪加上半衰期之后，强度会先降到阈值以下、再到时间过期。如果启动时只用
`is_active()` 判断，淡化阶段的情绪会被当成「没有情绪」，随即被替换成一个
新的随机情绪——等于把刚消下去的余温抹掉。

这里把「过期」和「淡化」拆成两个判断，并新增
`mood_startup_respect_existing`：开启后，未过期的淡化情绪会被沿用
（不再注入提示词，但不会触发随机重掷）。默认关闭，保持旧行为。
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

from self_learning_EterU.services.state.affection_manager import (
    AffectionManager,
    BotMood,
    MoodType,
)

BASE_TS = 1_000_000.0


def _mood(**kwargs):
    base = dict(
        mood_type=MoodType.HAPPY,
        intensity=0.5,
        description="开心",
        start_time=BASE_TS,
        duration_hours=24,
        half_life_minutes=12,
        fade_threshold=0.15,
    )
    base.update(kwargs)
    return BotMood(**base)


def _manager(respect_existing: bool):
    manager = AffectionManager.__new__(AffectionManager)
    manager.config = SimpleNamespace(
        mood_startup_respect_existing=respect_existing,
        mood_half_life_minutes=12,
        mood_fade_threshold=0.15,
        mood_max_concurrent=1,
        mood_persistence_hours=24,
    )
    manager.current_moods = {}

    async def _no_db_mood(_group_id):
        return None

    manager.db_manager = SimpleNamespace(get_current_bot_mood=_no_db_mood)
    manager._logger = SimpleNamespace(
        debug=lambda *a, **k: None,
        info=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        error=lambda *a, **k: None,
    )
    return manager


class TestExpiredVersusFaded:
    def test_faded_is_not_expired(self):
        mood = _mood()  # 0.5，半衰期 12 分钟
        now = BASE_TS + 30 * 60  # 强度约 0.09，仍远未到 24 小时
        assert mood.is_faded(now) is True
        assert mood.is_expired(now) is False
        assert mood.is_active(now) is False

    def test_expired_when_duration_passed(self):
        assert _mood().is_expired(BASE_TS + 25 * 3600) is True


class TestAllowFaded:
    def test_default_hides_faded_mood(self):
        manager = _manager(respect_existing=False)
        manager.current_moods["g"] = _mood(start_time=time.time() - 30 * 60)
        assert asyncio.run(manager.get_current_mood("g")) is None

    def test_allow_faded_returns_mood(self):
        manager = _manager(respect_existing=False)
        manager.current_moods["g"] = _mood(start_time=time.time() - 30 * 60)
        mood = asyncio.run(manager.get_current_mood("g", allow_faded=True))
        assert mood is not None
        assert mood.effective_intensity() < 0.15

    def test_expired_mood_never_returned(self):
        manager = _manager(respect_existing=False)
        manager.current_moods["g"] = _mood(start_time=time.time() - 48 * 3600)
        assert asyncio.run(manager.get_current_mood("g", allow_faded=True)) is None


class TestStartupRespectExisting:
    def _run_init(self, manager, group_id="g"):
        """跑一次启动初始化，返回随机情绪被调用的次数。"""
        calls = []

        async def fake_active_groups():
            return [group_id]

        async def fake_set_random(gid):
            calls.append(gid)
            return _mood(start_time=time.time())

        manager._get_active_groups = fake_active_groups
        manager.set_random_daily_mood = fake_set_random
        asyncio.run(manager._initialize_random_moods_for_active_groups())
        return len(calls)

    def test_disabled_rerolls_faded_mood(self):
        manager = _manager(respect_existing=False)
        manager.current_moods["g"] = _mood(start_time=time.time() - 30 * 60)
        assert self._run_init(manager) == 1

    def test_enabled_keeps_faded_mood(self):
        manager = _manager(respect_existing=True)
        manager.current_moods["g"] = _mood(start_time=time.time() - 30 * 60)
        assert self._run_init(manager) == 0