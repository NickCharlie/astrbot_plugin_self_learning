"""Read-only, scoped affection queries. Does not enable the learning hook suite."""

import asyncio
import time

from sqlalchemy import func, select

from astrbot.api import logger
from astrbot.api.platform import MessageType

try:  # astrbot.api 未导出 AiocqhttpMessageEvent（截至 v4.29），只能引用内部路径
    from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
        AiocqhttpMessageEvent,
    )
except ImportError:  # 内部路径变动时仅禁用 QQ 查询入口，不阻断插件加载
    AiocqhttpMessageEvent = None

from .models.orm.affection import UserAffection


def qq_id(value):
    text = str(value).strip()
    return (
        text
        if text.isascii() and text.isdigit() and 0 < len(text) <= 16 and int(text) > 0
        else ""
    )


def is_admin(plugin, event):
    return event.role == "admin" and str(event.get_sender_id()) in {
        str(x) for x in plugin.context.get_config().get("admins_id", [])
    }


def add_guidance(plugin, event, req):
    cfg = getattr(plugin, "plugin_config", None)
    if (
        req is None
        or not cfg
        or not cfg.enable_affection_system
        or AiocqhttpMessageEvent is None
        or not isinstance(event, AiocqhttpMessageEvent)
    ):
        return
    marker = "<affection_query_capability>"
    scope_text = (
        "分数按用户统一保存，私聊与所有群聊共用一份分数；切换前的旧分组记录不会自动合并。"
        if getattr(cfg, "affection_scope", "per_group") == "per_user"
        else "分数按会话/群分别保存，非跨群统一分数。"
    )
    if marker not in (req.system_prompt or ""):
        req.system_prompt = (req.system_prompt or "") + (
            "\n"
            + marker
            + "本机器人已启用 self-learning 好感度系统，"
            + scope_text
            + "用户询问实际好感度或排行时，先调用 query_affection 读取数据库；不要凭旧回复说系统不存在，"
            "也不要编造初始分数、排行榜或把记忆中的数字当成实时值。"
            "user 查本人；ranking 查当前作用域排行（沿用管理员权限）。管理员私聊可明确指定机器人已加入的群号。"
            "用户要求完整或全部榜单时，调用 mode=ranking、limit=0；只查前几名时 limit 可用 1 至 20，默认 10。"
            "not_recorded/empty 表示该范围暂无记录，不是没有系统；unavailable 表示暂时查不到。"
            "不主动公开分数；只按本次查询返回结果作答。工具是只读查询，不会加减分。"
            "</affection_query_capability>"
        )


async def read_snapshot(db, scope_key, user_id, mode, limit):
    # scope_key 已由 query() 按 affection_scope 解析；缺解析支持时不会走到这里。
    # Column-only SELECT avoids loading interaction history via ORM relationships.
    async with db.get_session() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(UserAffection)
            .where(UserAffection.group_id == scope_key)
        )
        columns = (
            UserAffection.user_id,
            UserAffection.affection_level,
            UserAffection.max_affection,
            UserAffection.updated_at,
        )
        stmt = select(*columns).where(UserAffection.group_id == scope_key)
        if mode == "user":
            row = (
                (await session.execute(stmt.where(UserAffection.user_id == user_id)))
                .mappings()
                .first()
            )
            if row is None:
                return {
                    "status": "not_recorded",
                    "user_id": user_id,
                    "record_count": count,
                    "message": "该会话范围尚无此用户的好感度记录；不能声称系统不存在，也不将缺失值编造成 0 分。",
                }
            item = dict(row)
            greater = await session.scalar(
                select(func.count())
                .select_from(UserAffection)
                .where(
                    UserAffection.group_id == scope_key,
                    UserAffection.affection_level > item["affection_level"],
                )
            )
            item["rank"] = int(greater) + 1
            return {"status": "ok", "user": item, "record_count": count}
        stmt = stmt.order_by(UserAffection.affection_level.desc(), UserAffection.user_id.asc())
        if limit:
            stmt = stmt.limit(limit)
        rows = (await session.execute(stmt)).mappings().all()
        ranked = []
        previous = None
        rank = 0
        for index, raw in enumerate(rows, 1):
            item = dict(raw)
            if previous != item["affection_level"]:
                rank = index
            previous = item["affection_level"]
            item["rank"] = rank
            ranked.append(item)
        return {
            "status": "ok" if ranked else "empty",
            "ranking": ranked,
            "record_count": count,
            "truncated": int(count) > len(ranked),
            "message": "仅含该作用域已有记录的用户，同分并列；未记录的成员不按零分参与排名。",
        }


async def query(plugin, event, mode="user", user_id="", group_id="", limit=10):
    if AiocqhttpMessageEvent is None or not isinstance(event, AiocqhttpMessageEvent):
        return {"status": "unsupported", "message": "此查询入口目前仅支持 QQ 会话。"}
    cfg = getattr(plugin, "plugin_config", None)
    if not cfg or getattr(plugin, "_shutting_down", False):
        return {"status": "unavailable", "message": "好感度查询服务暂未就绪。"}
    if not cfg.enable_affection_system:
        return {"status": "disabled", "message": "好感度系统当前未启用。"}
    if mode not in {"user", "ranking"}:
        return {"status": "invalid", "message": "mode 只能是 user 或 ranking。"}
    admin = is_admin(plugin, event)
    if mode == "ranking" and not admin:
        return {"status": "denied", "message": "好感度排行沿用插件原有管理员查询权限。"}
    current_group = qq_id(event.get_group_id())
    sender = qq_id(event.get_sender_id())
    target = qq_id(user_id) if user_id else sender
    if not sender or not target or (group_id and not qq_id(group_id)):
        return {
            "status": "invalid",
            "message": "请提供准确 QQ 号或群号，不使用昵称猜测目标。",
        }
    if target != sender and not admin:
        return {"status": "denied", "message": "普通成员只能查询本人好感度。"}
    scope = current_group or sender
    scope_kind = "group" if current_group else "private"
    requested = qq_id(group_id)
    if requested and requested != current_group:
        if (
            current_group
            or not admin
            or event.get_message_type() != MessageType.FRIEND_MESSAGE
        ):
            return {
                "status": "denied",
                "message": "跨群好感度查询仅限管理员私聊明确指定群号。",
            }
        try:
            groups = await asyncio.wait_for(event.bot.get_group_list(), 15)
            if not isinstance(groups, list) or not any(
                qq_id(g.get("group_id")) == requested for g in groups
            ):
                return {
                    "status": "invalid",
                    "message": "没有在机器人已加入的群中找到该群号。",
                }
        except Exception:
            return {"status": "unavailable", "message": "暂时无法核实目标群。"}
        scope = requested
        scope_kind = "group"
    if scope_kind == "private" and (mode == "ranking" or target != sender):
        return {
            "status": "invalid",
            "message": "私聊好感度与群内记录分开；查询群排行请由管理员明确提供群号。",
        }
    if isinstance(limit, bool) or not isinstance(limit, int) or not 0 <= limit <= 20:
        return {
            "status": "invalid",
            "message": "limit 必须为 0 到 20 的整数；0 表示返回该作用域全部已有记录。",
        }
    db = getattr(plugin, "db_manager", None)
    if db is None or not db.is_ready:
        return {
            "status": "unavailable",
            "message": "好感度数据库未就绪，不能说数据不存在。",
        }
    per_user = (
        str(getattr(cfg, "affection_scope", "per_group")).lower() == "per_user"
    )
    resolver = getattr(db, "_affection_scope_key", None)
    if per_user and not callable(resolver):
        # 按用户统一存储依赖数据库管理器的范围解析；缺支持时做猜测性读取
        # 会把按群行当成统一分数返回，宁可不读。
        return {
            "status": "unavailable",
            "system_enabled": True,
            "message": "按用户统一存储缺少数据库范围解析支持，无法可靠读取；本次不做猜测性读取。",
        }
    if per_user:
        scope = resolver(scope)
        scope_kind = "user"
    try:
        result = await asyncio.wait_for(
            read_snapshot(db, scope, target, mode, limit), 5
        )
        return dict(
            result,
            system_enabled=True,
            scope=scope,
            scope_kind=scope_kind,
            read_only=True,
            observed_at=int(time.time()),
        )
    except Exception as exc:
        logger.warning("好感度只读查询失败 (%s)", type(exc).__name__)
        return {
            "status": "unavailable",
            "system_enabled": True,
            "message": "本次读取失败，不等于没有好感度系统或没有记录。",
        }
