"""回归测试：affection_status 前五名必须按好感度降序。

背景：get_all_user_affections 底层 find_many 不带 order_by，数据库返回
无序；get_affection_status 曾直接切片 [:5] 导致"前5名"实为任意行。
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from self_learning_EterU.services.state.affection_manager import AffectionManager


def _make_manager(rows):
    async def _get_all(group_id):
        return [dict(r) for r in rows]

    async def _get_mood(group_id):
        return None

    db = SimpleNamespace(
        get_all_user_affections=_get_all,
        get_current_bot_mood=_get_mood,
    )
    config = SimpleNamespace(max_total_affection=1000)
    return AffectionManager(config=config, database_manager=db)


def _row(user_id, level):
    return {
        "group_id": "g1",
        "user_id": user_id,
        "affection_level": level,
        "max_affection": 100,
        "created_at": None,
        "updated_at": None,
    }


def test_top_users_sorted_descending():
    # 数据库返回按 user_id 字典序（好感度升序），模拟无序返回
    rows = [
        _row("user_a", 5),
        _row("user_b", 95),
        _row("user_c", 30),
        _row("user_d", 80),
        _row("user_e", 1),
        _row("user_f", 60),
        _row("user_g", 42),
    ]
    manager = _make_manager(rows)

    status = asyncio.run(manager.get_affection_status("g1"))

    assert status["user_count"] == 7
    assert status["total_affection"] == sum(r["affection_level"] for r in rows)
    top = status["top_users"]
    assert [u["user_id"] for u in top] == [
        "user_b", "user_d", "user_f", "user_g", "user_c",
    ]
    levels = [u["affection_level"] for u in top]
    assert levels == sorted(levels, reverse=True)


def test_top_users_fewer_than_five_returns_all():
    rows = [_row("u1", 10), _row("u2", 20)]
    manager = _make_manager(rows)

    status = asyncio.run(manager.get_affection_status("g1"))

    assert [u["user_id"] for u in status["top_users"]] == ["u2", "u1"]
    assert status["user_count"] == 2
