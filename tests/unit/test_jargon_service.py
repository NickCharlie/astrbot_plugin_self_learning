from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from webui.services.jargon_service import JargonService


@pytest.mark.unit
def test_format_jargon_for_frontend_keeps_legacy_and_macos_fields():
    formatted = JargonService._format_jargon_for_frontend(
        {
            "id": 1,
            "content": "yyds",
            "meaning": "永远的神",
            "is_jargon": True,
            "is_global": False,
            "count": 3,
            "chat_id": "group-a",
            "raw_content": '["上下文"]',
            "last_inference_count": 3,
            "is_complete": True,
            "updated_at": 1234567890,
        }
    )

    assert formatted["term"] == "yyds"
    assert formatted["content"] == "yyds"
    assert formatted["is_confirmed"] is True
    assert formatted["is_jargon"] is True
    assert formatted["occurrences"] == 3
    assert formatted["count"] == 3
    assert formatted["group_id"] == "group-a"
    assert formatted["chat_id"] == "group-a"
    assert formatted["context_examples"] == ["上下文"]
    assert formatted["definition"] == "永远的神"
    assert formatted["review_detail"] == "永远的神"
    assert formatted["is_complete"] is True


@pytest.mark.unit
def test_format_jargon_empty_meaning_falls_back_review_detail():
    formatted = JargonService._format_jargon_for_frontend(
        {
            "id": 2,
            "content": "待解释",
            "meaning": "",
            "is_jargon": False,
            "is_global": False,
            "count": 1,
            "chat_id": "group-a",
            "raw_content": '["上下文"]',
            "is_complete": True,
        }
    )

    assert formatted["definition"] == ""
    assert formatted["review_detail"] == "暂无释义"
    assert formatted["context_examples"] == ["上下文"]
    assert formatted["is_complete"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_jargon_groups_adds_legacy_count_aliases():
    database_manager = SimpleNamespace(
        get_jargon_groups=AsyncMock(
            return_value=[
                {
                    "group_id": "group-a",
                    "chat_id": "group-a",
                    "count": 2,
                }
            ]
        )
    )
    service = JargonService(SimpleNamespace(database_manager=database_manager))

    groups = await service.get_jargon_groups()

    assert groups == [
        {
            "group_id": "group-a",
            "group_name": "group-a",
            "id": "group-a",
            "chat_id": "group-a",
            "count": 2,
            "confirmed_jargon": 2,
            "total_candidates": 2,
        }
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_review_jargon_updates_candidate_status():
    database_manager = SimpleNamespace(
        get_jargon_by_id=AsyncMock(
            side_effect=[
                {
                    "id": 7,
                    "content": "上强度",
                    "meaning": "",
                    "is_jargon": False,
                    "count": 4,
                    "chat_id": "group-a",
                    "raw_content": "[]",
                },
                {
                    "id": 7,
                    "content": "上强度",
                    "meaning": "加大力度",
                    "is_jargon": True,
                    "count": 4,
                    "chat_id": "group-a",
                    "raw_content": "[]",
                },
            ]
        ),
        update_jargon=AsyncMock(return_value=True),
    )
    service = JargonService(SimpleNamespace(database_manager=database_manager))

    success, message, item = await service.review_jargon(
        7,
        "approve",
        meaning="加大力度",
    )

    assert success is True
    assert "已确认" in message
    assert item["is_confirmed"] is True
    assert item["meaning"] == "加大力度"
    database_manager.update_jargon.assert_awaited_once_with(
        {
            "id": 7,
            "is_jargon": True,
            "is_complete": True,
            "meaning": "加大力度",
        }
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_batch_review_jargon_reviews_each_candidate():
    database_manager = SimpleNamespace(
        get_jargon_by_id=AsyncMock(
            side_effect=[
                {
                    "id": 7,
                    "content": "上强度",
                    "meaning": "",
                    "is_jargon": False,
                    "count": 4,
                    "chat_id": "group-a",
                    "raw_content": "[]",
                },
                {
                    "id": 7,
                    "content": "上强度",
                    "meaning": "",
                    "is_jargon": True,
                    "is_complete": True,
                    "count": 4,
                    "chat_id": "group-a",
                    "raw_content": "[]",
                },
                {
                    "id": 8,
                    "content": "绷不住",
                    "meaning": "",
                    "is_jargon": False,
                    "count": 2,
                    "chat_id": "group-a",
                    "raw_content": "[]",
                },
                {
                    "id": 8,
                    "content": "绷不住",
                    "meaning": "",
                    "is_jargon": True,
                    "is_complete": True,
                    "count": 2,
                    "chat_id": "group-a",
                    "raw_content": "[]",
                },
            ]
        ),
        update_jargon=AsyncMock(return_value=True),
    )
    service = JargonService(SimpleNamespace(database_manager=database_manager))

    result = await service.batch_review_jargon([7, "8"], "approve")

    assert result["success"] is True
    assert result["details"]["success_count"] == 2
    assert result["details"]["failed_count"] == 0
    assert database_manager.update_jargon.await_args_list[0].args[0] == {
        "id": 7,
        "is_jargon": True,
        "is_complete": True,
    }
    assert database_manager.update_jargon.await_args_list[1].args[0] == {
        "id": 8,
        "is_jargon": True,
        "is_complete": True,
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_jargon_list_can_filter_pending_candidates():
    database_manager = SimpleNamespace(
        get_jargon_count=AsyncMock(return_value=3),
        get_recent_jargon_list=AsyncMock(
            return_value=[
                {
                    "id": 1,
                    "content": "待审",
                    "is_jargon": False,
                    "is_complete": False,
                    "count": 1,
                    "chat_id": "group-a",
                    "raw_content": "[]",
                },
                {
                    "id": 2,
                    "content": "已驳回",
                    "is_jargon": False,
                    "is_complete": True,
                    "count": 1,
                    "chat_id": "group-a",
                    "raw_content": "[]",
                },
                {
                    "id": 3,
                    "content": "已确认",
                    "is_jargon": True,
                    "is_complete": True,
                    "count": 1,
                    "chat_id": "group-a",
                    "raw_content": "[]",
                },
            ]
        ),
    )
    service = JargonService(SimpleNamespace(database_manager=database_manager))

    result = await service.get_jargon_list(
        "group-a",
        confirmed=False,
        page=1,
        page_size=10,
        pending_only=True,
    )

    assert result["total"] == 1
    assert [item["term"] for item in result["jargon_list"]] == ["待审"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_jargon_forwards_scope_filters_to_database():
    database_manager = SimpleNamespace(search_jargon=AsyncMock(return_value=[]))
    service = JargonService(SimpleNamespace(database_manager=database_manager))

    await service.search_jargon(
        "术语",
        chat_id="group-a",
        confirmed_only=True,
        global_only=True,
    )

    database_manager.search_jargon.assert_awaited_once_with(
        "术语",
        chat_id="group-a",
        confirmed_only=True,
        pending_only=False,
        global_only=True,
        local_only=False,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_jargon_can_filter_review_status():
    database_manager = SimpleNamespace(
        search_jargon=AsyncMock(
            return_value=[
                {
                    "id": 1,
                    "content": "已确认",
                    "is_jargon": True,
                    "is_complete": True,
                    "count": 1,
                    "chat_id": "group-a",
                    "raw_content": "[]",
                },
                {
                    "id": 2,
                    "content": "已驳回",
                    "is_jargon": False,
                    "is_complete": True,
                    "count": 1,
                    "chat_id": "group-a",
                    "raw_content": "[]",
                },
                {
                    "id": 3,
                    "content": "待审",
                    "is_jargon": False,
                    "is_complete": False,
                    "count": 1,
                    "chat_id": "group-a",
                    "raw_content": "[]",
                },
            ]
        )
    )
    service = JargonService(SimpleNamespace(database_manager=database_manager))

    unconfirmed = await service.search_jargon("词", unconfirmed_only=True)
    pending = await service.search_jargon("词", pending_only=True)

    assert [item["term"] for item in unconfirmed] == ["已驳回", "待审"]
    assert [item["term"] for item in pending] == ["待审"]
