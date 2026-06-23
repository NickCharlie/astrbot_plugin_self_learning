from types import SimpleNamespace
from unittest.mock import AsyncMock
import sys
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from self_learning_EterU.services.jargon.jargon_query import JargonQueryService


@pytest.mark.unit
def test_contains_jargon_matches_short_chinese_terms_inside_message():
    assert JargonQueryService._contains_jargon("这个方案直接拉满", "拉满") is True
    assert JargonQueryService._contains_jargon("xabcx", "abc") is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_jargon_uses_only_confirmed_group_and_global_terms():
    db = SimpleNamespace(
        search_jargon=AsyncMock(
            side_effect=[
                [
                    {
                        "id": 1,
                        "content": "上强度",
                        "meaning": "加大力度",
                    }
                ],
                [
                    {
                        "id": 2,
                        "content": "拉满",
                        "meaning": "做到极致",
                    }
                ],
            ]
        )
    )
    service = JargonQueryService(db)

    result = await service.query_jargon("强度", chat_id="group-a", limit=3)

    assert "上强度" in result
    assert "拉满" in result
    assert db.search_jargon.await_args_list[0].kwargs == {
        "keyword": "强度",
        "chat_id": "group-a",
        "confirmed_only": True,
        "limit": 3,
    }
    assert db.search_jargon.await_args_list[1].kwargs == {
        "keyword": "强度",
        "chat_id": None,
        "confirmed_only": True,
        "global_only": True,
        "limit": 3,
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_and_explain_jargon_includes_global_terms_for_any_group():
    db = SimpleNamespace(
        get_recent_jargon_list=AsyncMock(
            side_effect=[
                [
                    {
                        "id": 1,
                        "content": "上强度",
                        "meaning": "加大力度",
                        "is_global": False,
                    }
                ],
                [
                    {
                        "id": 2,
                        "content": "拉满",
                        "meaning": "做到极致",
                        "is_global": True,
                    }
                ],
            ]
        )
    )
    service = JargonQueryService(db)

    result = await service.check_and_explain_jargon(
        "这个方案直接拉满",
        chat_id="group-a",
    )

    assert result is not None
    assert "拉满" in result
    assert "做到极致" in result
    assert db.get_recent_jargon_list.await_args_list[0].kwargs == {
        "chat_id": "group-a",
        "limit": 100,
        "only_confirmed": True,
    }
    assert db.get_recent_jargon_list.await_args_list[1].kwargs == {
        "chat_id": None,
        "limit": 100,
        "only_confirmed": True,
        "global_only": True,
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_jargon_context_includes_global_terms():
    db = SimpleNamespace(
        get_recent_jargon_list=AsyncMock(
            side_effect=[
                [],
                [
                    {
                        "id": 2,
                        "content": "拉满",
                        "meaning": "做到极致",
                        "is_global": True,
                    }
                ],
            ]
        )
    )
    service = JargonQueryService(db)

    result = await service.get_jargon_context("group-a", limit=10)

    assert "群组/全局常用黑话" in result
    assert "拉满" in result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_group_and_global_jargon_dedupes_by_content_with_group_priority():
    db = SimpleNamespace(
        get_recent_jargon_list=AsyncMock(
            side_effect=[
                [
                    {
                        "id": 1,
                        "content": "拉满",
                        "meaning": "本群释义",
                        "is_global": False,
                    }
                ],
                [
                    {
                        "id": 2,
                        "content": "拉满",
                        "meaning": "全局释义",
                        "is_global": True,
                    },
                    {
                        "id": 3,
                        "content": "上强度",
                        "meaning": "加大力度",
                        "is_global": True,
                    },
                ],
            ]
        )
    )
    service = JargonQueryService(db)

    result = await service._get_group_and_global_jargon_list("group-a", limit=3)

    assert [item["content"] for item in result] == ["拉满", "上强度"]
    assert result[0]["meaning"] == "本群释义"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_and_explain_jargon_does_not_starve_global_terms_when_group_limit_is_full():
    db = SimpleNamespace(
        get_recent_jargon_list=AsyncMock(
            side_effect=[
                [
                    {
                        "id": idx,
                        "content": f"本群词{idx}",
                        "meaning": f"本群释义{idx}",
                        "is_global": False,
                    }
                    for idx in range(100)
                ],
                [
                    {
                        "id": 1001,
                        "content": "全局暗号",
                        "meaning": "跨群共享释义",
                        "is_global": True,
                    }
                ],
            ]
        )
    )
    service = JargonQueryService(db)

    result = await service.check_and_explain_jargon(
        "这句话包含全局暗号",
        chat_id="group-a",
    )

    assert result is not None
    assert "全局暗号" in result
    assert "跨群共享释义" in result
