"""Real SQLAlchemy reads on temporary SQLite, no QQ or LLM network access."""

import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from self_learning_EterU.affection_query import add_guidance, query
from self_learning_EterU.models.orm.affection import UserAffection
from sqlalchemy import event as sql_event
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from astrbot.core.message.components import Plain
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)


class AffectionQueryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.engine = create_async_engine(
            "sqlite+aiosqlite:///" + str(Path(self.tmp.name) / "test.sqlite3")
        )
        async with self.engine.begin() as conn:
            await conn.run_sync(UserAffection.__table__.create)
            await conn.execute(
                insert(UserAffection),
                [
                    {
                        "group_id": group,
                        "user_id": user,
                        "affection_level": value,
                        "max_affection": 100,
                        "created_at": 1,
                        "updated_at": 2,
                    }
                    for group, user, value in [
                        ("101", "90001", 7),
                        ("101", "70001", 9),
                        ("101", "70002", 9),
                        ("101", "70003", 0),
                        ("102", "90001", 88),
                        ("90001", "90001", 12),
                    ]
                ],
            )
        self.session = async_sessionmaker(self.engine, expire_on_commit=False)

        @asynccontextmanager
        async def get_session():
            async with self.session() as session:
                yield session

        self.db = SimpleNamespace(is_ready=True, get_session=get_session)
        self.plugin = SimpleNamespace(
            db_manager=self.db,
            _shutting_down=False,
            plugin_config=SimpleNamespace(
                enable_affection_system=True, enable_llm_hooks=False
            ),
            context=SimpleNamespace(get_config=lambda: {"admins_id": ["90001"]}),
        )
        self.statements = []
        sql_event.listen(
            self.engine.sync_engine,
            "before_cursor_execute",
            lambda conn, cursor, statement, *args: self.statements.append(statement),
        )

    async def asyncTearDown(self):
        await self.engine.dispose()

    def event(self, group="101", user="90001", role="admin"):
        msg = AstrBotMessage()
        msg.type = MessageType.GROUP_MESSAGE if group else MessageType.FRIEND_MESSAGE
        msg.group_id = group
        msg.self_id = "99999"
        msg.sender = MessageMember(user_id=user, nickname="Synthetic")
        msg.session_id = group or user
        msg.message_id = "5001"
        msg.message_str = "查询好感度"
        msg.message = [Plain(msg.message_str)]
        e = AiocqhttpMessageEvent(
            msg.message_str,
            msg,
            PlatformMetadata(name="aiocqhttp", description="offline", id="qq-test"),
            msg.session_id,
            SimpleNamespace(
                get_group_list=AsyncMock(
                    return_value=[{"group_id": 101}, {"group_id": 102}]
                )
            ),
        )
        e.role = role
        return e

    async def test_user_score_and_rank_are_real_database_values(self):
        r = await query(self.plugin, self.event())
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["user"]["affection_level"], 7)
        self.assertEqual(r["user"]["rank"], 3)
        self.assertEqual(r["record_count"], 4)
        self.assertTrue(r["read_only"])

    async def test_upstream_per_user_scope_is_respected_without_migrating_old_rows(
        self,
    ):
        async with self.session() as session:
            await session.execute(
                insert(UserAffection),
                [
                    {
                        "group_id": "__user__",
                        "user_id": "90001",
                        "affection_level": 45,
                        "max_affection": 100,
                        "created_at": 1,
                        "updated_at": 2,
                    }
                ],
            )
            await session.commit()
        self.statements.clear()
        self.plugin.plugin_config.affection_scope = "per_user"
        self.db._affection_scope_key = lambda group: "__user__"
        for group in ["101", "102", ""]:
            result = await query(self.plugin, self.event(group=group))
            self.assertEqual(result["user"]["affection_level"], 45)
            self.assertEqual(result["scope_kind"], "user")
            self.assertEqual(result["scope"], "__user__")
        self.assertTrue(
            all(s.lstrip().upper().startswith("SELECT") for s in self.statements)
        )
        req = SimpleNamespace(system_prompt="")
        add_guidance(self.plugin, self.event(), req)
        self.assertIn("按用户统一保存", req.system_prompt)
        self.assertNotIn("非跨群统一", req.system_prompt)

    async def test_ranking_preserves_ties_and_zero_values(self):
        r = await query(self.plugin, self.event(), mode="ranking")
        self.assertEqual([x["rank"] for x in r["ranking"]], [1, 1, 3, 4])
        self.assertEqual([x["affection_level"] for x in r["ranking"]], [9, 9, 7, 0])
        self.assertFalse(r["truncated"])
        self.assertEqual(r["scope"], "101")

    async def test_ranking_limit_and_record_count(self):
        r = await query(self.plugin, self.event(), mode="ranking", limit=2)
        self.assertEqual(len(r["ranking"]), 2)
        self.assertEqual(r["record_count"], 4)
        self.assertTrue(r["truncated"])

    async def test_missing_record_not_fabricated_as_zero_or_system_disabled(self):
        r = await query(self.plugin, self.event(user="70004", role="member"))
        self.assertEqual(r["status"], "not_recorded")
        self.assertTrue(r["system_enabled"])
        self.assertNotIn("user", r)

    async def test_empty_group_reports_empty_instead_of_no_system(self):
        r = await query(self.plugin, self.event(group="103"), mode="ranking")
        self.assertEqual(r["status"], "empty")
        self.assertEqual(r["record_count"], 0)
        self.assertTrue(r["system_enabled"])

    async def test_private_scope_is_separate_from_group(self):
        r = await query(self.plugin, self.event(group=""))
        self.assertEqual(r["scope_kind"], "private")
        self.assertEqual(r["user"]["affection_level"], 12)

    async def test_admin_private_can_query_confirmed_group_without_merging(self):
        e = self.event(group="")
        r = await query(self.plugin, e, group_id="102")
        self.assertEqual(r["user"]["affection_level"], 88)
        self.assertEqual(r["scope"], "102")
        e.bot.get_group_list.assert_awaited_once()

    async def test_group_cannot_read_another_groups_scores(self):
        r = await query(self.plugin, self.event(), group_id="102")
        self.assertEqual(r["status"], "denied")
        self.assertEqual(self.statements, [])

    async def test_members_can_read_self_but_not_other_people_or_ranking(self):
        e = self.event(user="70001", role="member")
        self.assertEqual((await query(self.plugin, e))["status"], "ok")
        self.assertEqual(
            (await query(self.plugin, e, user_id="90001"))["status"], "denied"
        )
        self.assertEqual(
            (await query(self.plugin, e, mode="ranking"))["status"], "denied"
        )

    async def test_role_alone_does_not_grant_administrator_privilege(self):
        r = await query(
            self.plugin, self.event(user="70001", role="admin"), mode="ranking"
        )
        self.assertEqual(r["status"], "denied")

    async def test_unjoined_group_and_group_lookup_failure_are_not_read(self):
        e = self.event(group="")
        self.assertEqual(
            (await query(self.plugin, e, group_id="999"))["status"], "invalid"
        )
        e.bot.get_group_list.side_effect = RuntimeError("synthetic")
        self.assertEqual(
            (await query(self.plugin, e, group_id="101"))["status"], "unavailable"
        )
        self.assertEqual(self.statements, [])

    async def test_private_ranking_requires_explicit_group(self):
        self.assertEqual(
            (await query(self.plugin, self.event(group=""), mode="ranking"))["status"],
            "invalid",
        )

    async def test_invalid_mode_ids_and_limits_rejected(self):
        for kwargs in (
            {"mode": "modify"},
            {"user_id": "nickname"},
            {"group_id": "101 OR 1=1"},
            {"limit": -1},
            {"limit": "0"},
            {"limit": 1.5},
            {"limit": 21},
            {"limit": True},
        ):
            self.assertEqual(
                (await query(self.plugin, self.event(), **kwargs))["status"], "invalid"
            )
        self.assertEqual(self.statements, [])

    async def test_disabled_and_unready_are_distinct_from_missing_records(self):
        self.plugin.plugin_config.enable_affection_system = False
        self.assertEqual((await query(self.plugin, self.event()))["status"], "disabled")
        self.plugin.plugin_config.enable_affection_system = True
        self.db.is_ready = False
        self.assertEqual(
            (await query(self.plugin, self.event()))["status"], "unavailable"
        )

    async def test_database_exception_is_not_misreported_as_no_affection(self):
        @asynccontextmanager
        async def broken():
            raise RuntimeError("synthetic database failure")
            yield

        self.db.get_session = broken
        r = await query(self.plugin, self.event())
        self.assertEqual(r["status"], "unavailable")
        self.assertTrue(r["system_enabled"])

    async def test_read_only_queries_emit_selects_without_writes(self):
        await query(self.plugin, self.event())
        await query(self.plugin, self.event(), mode="ranking")
        self.assertTrue(self.statements)
        self.assertTrue(
            all(s.lstrip().upper().startswith("SELECT") for s in self.statements)
        )

    def test_guidance_works_with_general_hook_disabled_without_enabling_it(self):
        req = SimpleNamespace(system_prompt="Original persona")
        add_guidance(self.plugin, self.event(), req)
        add_guidance(self.plugin, self.event(), req)
        self.assertEqual(req.system_prompt.count("<affection_query_capability>"), 1)
        self.assertIn("Original persona", req.system_prompt)
        self.assertIn("query_affection", req.system_prompt)
        self.assertFalse(self.plugin.plugin_config.enable_llm_hooks)

    def test_guidance_does_not_advertise_disabled_system(self):
        self.plugin.plugin_config.enable_affection_system = False
        req = SimpleNamespace(system_prompt="Original")
        add_guidance(self.plugin, self.event(), req)
        self.assertEqual(req.system_prompt, "Original")

    async def test_zero_limit_returns_all_thirty_records_for_administrator(self):
        async with self.session() as session:
            await session.execute(
                insert(UserAffection),
                [
                    dict(
                        group_id="101",
                        user_id=str(81000 + i),
                        affection_level=100 if i < 2 else 30 - i,
                        max_affection=100,
                        created_at=1,
                        updated_at=2,
                    )
                    for i in range(26)
                ],
            )
            await session.commit()
        self.statements.clear()
        result = await query(self.plugin, self.event(), mode="ranking", limit=0)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["record_count"], 30)
        self.assertEqual(len(result["ranking"]), 30)
        self.assertFalse(result["truncated"])
        self.assertEqual([row["user_id"] for row in result["ranking"][:2]], ["81000", "81001"])
        self.assertEqual([row["rank"] for row in result["ranking"][:3]], [1, 1, 3])
        self.assertEqual(result["ranking"][-1]["affection_level"], 0)
        self.assertTrue(self.statements)
        self.assertTrue(all(s.lstrip().upper().startswith("SELECT") for s in self.statements))
        self.assertFalse(any("LIMIT" in s.upper() for s in self.statements))
        for limit in (1, 20):
            limited = await query(self.plugin, self.event(), mode="ranking", limit=limit)
            self.assertEqual(limited["ranking"], result["ranking"][:limit])
            self.assertEqual(limited["record_count"], 30)
            self.assertTrue(limited["truncated"])

    async def test_zero_limit_preserves_member_and_cross_group_permissions(self):
        member = self.event(user="70001", role="member")
        result = await query(self.plugin, member, mode="ranking", limit=0)
        self.assertEqual(result["status"], "denied")
        result = await query(self.plugin, self.event(), mode="ranking", group_id="102", limit=0)
        self.assertEqual(result["status"], "denied")
        self.assertEqual(self.statements, [])

    def test_guidance_explains_full_ranking_without_changing_admin_policy(self):
        req = SimpleNamespace(system_prompt="Original")
        add_guidance(self.plugin, self.event(), req)
        self.assertIn("limit=0", req.system_prompt)
        self.assertIn("沿用管理员权限", req.system_prompt)


def test_tool_returns_query_snapshot_with_general_hook_disabled(monkeypatch):
    import asyncio
    import importlib
    import json
    import sys
    from unittest.mock import AsyncMock

    # Match the supported optional-dependency-absent environment.
    monkeypatch.setitem(sys.modules, "guardrails", None)
    main = importlib.import_module("self_learning_EterU.main")
    snapshot = AsyncMock(return_value={"status": "ok", "read_only": True})
    monkeypatch.setattr(main, "query_affection_snapshot", snapshot)
    plugin = main.SelfLearningPlugin.__new__(main.SelfLearningPlugin)
    plugin.plugin_config = SimpleNamespace(enable_llm_hooks=False)
    event = object()
    result = asyncio.run(plugin.query_affection(event, "user", "", "", 10))
    assert json.loads(result) == {"status": "ok", "read_only": True}
    snapshot.assert_awaited_once_with(plugin, event, "user", "", "", 10)
    assert plugin.plugin_config.enable_llm_hooks is False

    async def test_per_user_without_scope_resolver_is_unavailable_not_misread(self):
        """per_user 配置但数据库管理器缺范围解析：显式不可用，绝不按群行冒充统一分数。"""
        self.plugin.plugin_config.affection_scope = "per_user"
        # self.db 默认（SimpleNamespace）没有 _affection_scope_key
        self.statements.clear()
        result = await query(self.plugin, self.event(group="101"))
        self.assertEqual(result["status"], "unavailable")
        self.assertTrue(result["system_enabled"])
        # 未发起任何 SQL 读取：宁可不可用，也不把按群行冒充统一分数
        self.assertEqual(self.statements, [])

    async def test_per_group_without_scope_resolver_still_reads_group_scope(self):
        """per_group（默认）本就不需要解析器：行为与此前一致。"""
        self.plugin.plugin_config.affection_scope = "per_group"
        result = await query(self.plugin, self.event(group="101"), mode="user")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["scope"], "101")
        self.assertEqual(result["scope_kind"], "group")
        self.assertEqual(result["user"]["affection_level"], 12)
