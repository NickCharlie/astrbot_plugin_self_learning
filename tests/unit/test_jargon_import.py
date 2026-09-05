"""Unit tests for jargon batch import (keywords + explanations)."""

import pytest

from webui.services.jargon_service import JargonService


def make_service(database_manager=None):
    if database_manager is None:
        async def _get_jargon(chat_id, content):
            return None

        async def _insert_jargon(payload):
            return 1

        database_manager = type(
            "DB",
            (),
            {"get_jargon": staticmethod(_get_jargon), "insert_jargon": staticmethod(_insert_jargon)},
        )()
    container = type("Container", (), {"database_manager": database_manager})()
    return JargonService(container)


class TestParseImportText:
    def test_parses_common_separators(self):
        rows = JargonService.parse_import_text(
            "摸鱼 = 上班时间偷懒\nyyds：永远的神\nCP券: 情人节活动道具\n内卷\t过度竞争\nA|B 解释"
        )
        assert [row["term"] for row in rows] == ["摸鱼", "yyds", "CP券", "内卷", "A"]
        assert rows[0]["meaning"] == "上班时间偷懒"
        assert rows[1]["meaning"] == "永远的神"
        assert rows[2]["meaning"] == "情人节活动道具"
        assert rows[3]["meaning"] == "过度竞争"
        assert not any(row["error"] for row in rows)

    def test_first_separator_wins(self):
        rows = JargonService.parse_import_text("词 = 释:义|其余")
        assert rows[0]["term"] == "词"
        assert rows[0]["meaning"] == "释:义|其余"

    def test_term_only_lines_import_with_empty_meaning(self):
        rows = JargonService.parse_import_text("绝绝子")
        assert rows[0]["term"] == "绝绝子"
        assert rows[0]["meaning"] == ""
        assert not rows[0]["error"]

    def test_comments_and_blank_lines_skipped(self):
        rows = JargonService.parse_import_text("# 注释\n\n// 斜杠注释\n  \n词 = 义")
        assert len(rows) == 1
        assert rows[0]["term"] == "词"

    def test_overlong_term_reported(self):
        rows = JargonService.parse_import_text("x" * 100 + " = 义")
        assert rows[0]["error"]
        assert len(rows[0]["term"]) == 64


class TestImportJargons:
    @pytest.mark.asyncio
    async def test_import_new_terms_inserts_confirmed_rows(self):
        inserted = []

        async def get_jargon(chat_id, content):
            return None

        async def insert_jargon(payload):
            inserted.append(payload)
            return len(inserted)

        service = make_service(type("DB", (), {"get_jargon": staticmethod(get_jargon), "insert_jargon": staticmethod(insert_jargon)})())

        result = await service.import_jargons({
            "text": "摸鱼 = 上班时间偷懒\nyyds：永远的神",
            "group_id": "group-a",
            "is_global": False,
        })

        assert result["success"] is True
        assert result["details"]["imported"] == 2
        assert len(inserted) == 2
        for payload in inserted:
            assert payload["is_jargon"] is True
            assert payload["is_complete"] is True
            assert payload["chat_id"] == "group-a"
            assert payload["is_global"] is False

    @pytest.mark.asyncio
    async def test_import_global_scope_sets_flag_and_empty_chat_id(self):
        inserted = []

        async def get_jargon(chat_id, content):
            return None

        async def insert_jargon(payload):
            inserted.append(payload)
            return 1

        service = make_service(type("DB", (), {"get_jargon": staticmethod(get_jargon), "insert_jargon": staticmethod(insert_jargon)})())

        await service.import_jargons({"text": "词 = 义", "group_id": "", "is_global": True})

        assert inserted[0]["is_global"] is True
        assert inserted[0]["chat_id"] == ""

    @pytest.mark.asyncio
    async def test_existing_confirmed_term_is_skipped(self):
        async def get_jargon(chat_id, content):
            return {"id": 9, "content": content, "is_jargon": True, "meaning": "旧释义"}

        async def update_jargon(payload):
            raise AssertionError("confirmed rows must not be updated")

        service = make_service(type("DB", (), {"get_jargon": staticmethod(get_jargon), "update_jargon": staticmethod(update_jargon)})())

        result = await service.import_jargons({"text": "旧词 = 新释义", "group_id": "g"})

        assert result["success"] is True
        assert result["details"]["skipped"] == 1
        assert result["details"]["imported"] == 0

    @pytest.mark.asyncio
    async def test_existing_candidate_is_upgraded_with_meaning(self):
        updates = []

        async def get_jargon(chat_id, content):
            return {"id": 5, "content": content, "is_jargon": False, "meaning": None}

        async def update_jargon(payload):
            updates.append(payload)
            return True

        service = make_service(type("DB", (), {"get_jargon": staticmethod(get_jargon), "update_jargon": staticmethod(update_jargon)})())

        result = await service.import_jargons({"text": "候选词 = 新释义", "group_id": "g"})

        assert result["details"]["updated"] == 1
        assert updates[0]["id"] == 5
        assert updates[0]["is_jargon"] is True
        assert updates[0]["is_complete"] is True
        assert updates[0]["meaning"] == "新释义"

    @pytest.mark.asyncio
    async def test_blank_text_is_rejected(self):
        service = make_service()
        result = await service.import_jargons({"text": "# 只有注释\n\n"})
        assert result["success"] is False
        assert "没有可导入的条目" in result["error"]

    @pytest.mark.asyncio
    async def test_query_cache_invalidated_on_write(self):
        invalidated = []

        async def get_jargon(chat_id, content):
            return None

        async def insert_jargon(payload):
            return 1

        plugin = type("Plugin", (), {})()
        plugin.jargon_query_service = type("Query", (), {"clear_cache": staticmethod(lambda: invalidated.append(1))})()

        service = make_service(type("DB", (), {"get_jargon": staticmethod(get_jargon), "insert_jargon": staticmethod(insert_jargon)})())
        service.container.plugin_instance = plugin

        await service.import_jargons({"text": "词 = 义", "group_id": "g"})

        assert invalidated


class TestCoerceIsGlobal:
    def test_bool_passthrough(self):
        assert JargonService._coerce_is_global(True) is True
        assert JargonService._coerce_is_global(False) is False

    def test_string_forms(self):
        assert JargonService._coerce_is_global("true") is True
        assert JargonService._coerce_is_global(" TRUE ") is True
        assert JargonService._coerce_is_global("1") is True
        assert JargonService._coerce_is_global("false") is False
        assert JargonService._coerce_is_global("no") is False


class TestImportFailureReporting:
    @pytest.mark.asyncio
    async def test_parser_error_rows_reported_alongside_valid_rows(self):
        inserted = []

        async def get_jargon(chat_id, content):
            return None

        async def insert_jargon(payload):
            inserted.append(payload)
            return 1

        service = make_service(type("DB", (), {"get_jargon": staticmethod(get_jargon), "insert_jargon": staticmethod(insert_jargon)})())

        result = await service.import_jargons({
            "text": "好词 = 好义\n" + "x" * 100 + " = 超长\n= 没有关键词",
            "group_id": "g",
        })

        assert result["success"] is True
        details = result["details"]
        assert details["imported"] == 1
        assert details["failed"] and len(details["failed"]) == 2
        assert details["total"] == 3

    @pytest.mark.asyncio
    async def test_all_invalid_rows_return_details(self):
        service = make_service()

        result = await service.import_jargons({"text": "x" * 100 + " = 超长\n= 没有关键词", "group_id": "g"})

        assert result["success"] is False
        details = result["details"]
        assert len(details["failed"]) == 2
        assert details["total"] == 2

    @pytest.mark.asyncio
    async def test_is_global_string_false_is_not_truthy(self):
        captured = {}

        async def get_jargon(chat_id, content):
            return None

        async def insert_jargon(payload):
            captured.update(payload)
            return 1

        service = make_service(type("DB", (), {"get_jargon": staticmethod(get_jargon), "insert_jargon": staticmethod(insert_jargon)})())

        # 字符串 "false" 不得被 bool() 误判为全局
        await service.import_jargons({"text": "词 = 义", "group_id": "g", "is_global": "false"})
        assert captured["is_global"] is False
