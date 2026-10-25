"""情绪板块服务：情绪/好感度状态聚合、走向分析与遗忘治理入口。

数据来源（全部只读，治理操作走 run_action）：
- BotMood / EmotionProfile / UserAffection / AffectionInteraction（数据库）
- LearningGateDailyStat（情绪学习闸门日聚合）
- plugin_instance.emotion_gate / forgetting_manager（内存遥测与治理操作）
"""

from __future__ import annotations

import json
import time
from collections import Counter
from typing import Any, Dict, List

from astrbot.api import logger

try:
    from ...models.orm import (
        AffectionInteraction,
        BotMood,
        EmotionProfile,
        LearningGateDailyStat,
        UserAffection,
    )
except ImportError:
    from models.orm import (
        AffectionInteraction,
        BotMood,
        EmotionProfile,
        LearningGateDailyStat,
        UserAffection,
    )

MAX_TREND_DAYS = 90
DEFAULT_TREND_DAYS = 14
MAX_MOOD_HISTORY = 20
MAX_LEADERBOARD = 5


def _day_key(timestamp: float) -> str:
    import datetime as _dt

    try:
        return _dt.datetime.fromtimestamp(float(timestamp)).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


class EmotionBoardService:
    """情绪板块聚合服务"""

    def __init__(self, container):
        self.container = container
        self.database_manager = container.database_manager

    # ------ 内部工具 ------

    def _plugin(self) -> Any:
        return getattr(self.container, "plugin_instance", None)

    def _gate(self) -> Any:
        return getattr(self._plugin(), "emotion_gate", None)

    def _forgetting(self) -> Any:
        return getattr(self._plugin(), "forgetting_manager", None)

    # ------ 面板 ------

    async def get_board(self) -> Dict[str, Any]:
        board: Dict[str, Any] = {
            "available": bool(self.database_manager),
            "generated_at": time.time(),
            "moods": {"active": [], "history": []},
            "affection": {"groups": [], "leaderboard": [], "bottom": []},
            "emotion_profiles": {"total": 0, "dominant_distribution": []},
            "gate": {"daily": [], "telemetry": None},
            "forgetting": None,
        }
        if not self.database_manager:
            return board
        try:
            board["moods"] = await self._load_moods()
            board["affection"] = await self._load_affection()
            board["emotion_profiles"] = await self._load_emotion_profiles()
            board["gate"]["daily"] = await self._load_gate_daily(DEFAULT_TREND_DAYS)
        except Exception as exc:
            logger.error(f"[EmotionBoard] 面板聚合失败: {exc}", exc_info=True)

        gate = self._gate()
        if gate is not None:
            try:
                board["gate"]["telemetry"] = gate.telemetry()
            except Exception as exc:
                logger.debug(f"[EmotionBoard] 读取闸门遥测失败: {exc}")
        forgetting = self._forgetting()
        if forgetting is not None:
            try:
                board["forgetting"] = await forgetting.status()
            except Exception as exc:
                logger.error(f"[EmotionBoard] 读取遗忘状态失败: {exc}", exc_info=True)
        return board

    async def _load_moods(self) -> Dict[str, Any]:
        async with self.database_manager.get_session() as session:
            active_rows = (await session.execute(
                BotMood.__table__.select()
                .where(BotMood.is_active == 1)  # noqa: E712
                .order_by(BotMood.timestamp.desc())
            )).all()
            seen_groups = set()
            active: List[Dict[str, Any]] = []
            for row in active_rows:
                if row.group_id in seen_groups:
                    continue
                seen_groups.add(row.group_id)
                active.append({
                    "group_id": row.group_id,
                    "mood_type": row.mood_type,
                    "intensity": row.mood_intensity,
                    "description": row.mood_description,
                    "start_time": row.start_time,
                    "end_time": row.end_time,
                    "timestamp": row.timestamp,
                })
            history_rows = (await session.execute(
                BotMood.__table__.select()
                .order_by(BotMood.timestamp.desc())
                .limit(MAX_MOOD_HISTORY)
            )).all()
            history = [
                {
                    "group_id": row.group_id,
                    "mood_type": row.mood_type,
                    "intensity": row.mood_intensity,
                    "description": row.mood_description,
                    "timestamp": row.timestamp,
                }
                for row in history_rows
            ]
        return {"active": active, "history": history}

    async def _load_affection(self) -> Dict[str, Any]:
        async with self.database_manager.get_session() as session:
            rows = (await session.execute(
                UserAffection.__table__.select()
            )).all()
        by_group: Dict[str, List[Any]] = {}
        for row in rows:
            by_group.setdefault(row.group_id, []).append(row)
        groups = []
        all_levels = []
        for group_id, items in sorted(by_group.items()):
            levels = [int(item.affection_level or 0) for item in items]
            all_levels.extend(levels)
            groups.append({
                "group_id": group_id,
                "total_users": len(levels),
                "average": round(sum(levels) / len(levels), 1) if levels else 0,
                "high": sum(1 for lvl in levels if lvl >= 60),
                "low": sum(1 for lvl in levels if lvl <= -20),
            })
        ranked = sorted(rows, key=lambda item: int(item.affection_level or 0))
        leaderboard = [
            {"user_id": row.user_id, "group_id": row.group_id,
             "level": int(row.affection_level or 0)}
            for row in reversed(ranked[-MAX_LEADERBOARD:])
        ]
        bottom = [
            {"user_id": row.user_id, "group_id": row.group_id,
             "level": int(row.affection_level or 0)}
            for row in ranked[:MAX_LEADERBOARD]
        ]
        overall = {
            "total_users": len(all_levels),
            "average": round(sum(all_levels) / len(all_levels), 1) if all_levels else 0,
        }
        return {"groups": groups, "leaderboard": leaderboard, "bottom": bottom, "overall": overall}

    async def _load_emotion_profiles(self) -> Dict[str, Any]:
        async with self.database_manager.get_session() as session:
            rows = (await session.execute(
                EmotionProfile.__table__.select()
            )).all()
        counter: Counter = Counter()
        parsed = 0
        for row in rows:
            if not row.dominant_emotions:
                continue
            try:
                data = json.loads(row.dominant_emotions)
            except (TypeError, ValueError):
                continue
            emotions = data if isinstance(data, list) else (
                list(data.keys()) if isinstance(data, dict) else []
            )
            for emotion in emotions[:3]:
                counter[str(emotion)] += 1
            parsed += 1
        distribution = [
            {"emotion": emotion, "count": count}
            for emotion, count in counter.most_common(8)
        ]
        return {
            "total": len(rows),
            "parsed": parsed,
            "dominant_distribution": distribution,
        }

    async def _load_gate_daily(self, days: int) -> List[Dict[str, Any]]:
        async with self.database_manager.get_session() as session:
            rows = (await session.execute(
                LearningGateDailyStat.__table__.select()
                .order_by(LearningGateDailyStat.stat_date.desc())
                .limit(min(max(days, 1), MAX_TREND_DAYS))
            )).all()
        daily = []
        for row in rows:
            total = int(row.total_count or 0)
            factor_avg = {}
            if row.factor_sum_json:
                try:
                    factor_sum = json.loads(row.factor_sum_json) or {}
                    factor_avg = {
                        key: round(value / total, 4)
                        for key, value in factor_sum.items()
                        if total and isinstance(value, (int, float))
                    }
                except (TypeError, ValueError):
                    factor_avg = {}
            accepted = int(row.accepted_count or 0)
            daily.append({
                "stat_date": row.stat_date,
                "group_id": row.group_id,
                "accepted": accepted,
                "skipped": int(row.skipped_count or 0),
                "avg_score": round(float(row.total_score or 0) / total, 4) if total else 0,
                "accept_rate": round(accepted / total, 4) if total else None,
                "factor_avg": factor_avg,
            })
        daily.reverse()
        return daily

    # ------ 走向分析 ------

    async def get_trends(self, days: int = DEFAULT_TREND_DAYS) -> Dict[str, Any]:
        days = min(max(days or DEFAULT_TREND_DAYS, 1), MAX_TREND_DAYS)
        trends: Dict[str, Any] = {
            "days": days,
            "affection_delta": [],
            "mood_changes": [],
            "gate": [],
        }
        if not self.database_manager:
            return trends
        since = time.time() - days * 86400
        try:
            async with self.database_manager.get_session() as session:
                interaction_rows = (await session.execute(
                    AffectionInteraction.__table__.select()
                    .where(AffectionInteraction.timestamp >= since)
                )).all()
                mood_rows = (await session.execute(
                    BotMood.__table__.select()
                    .where(BotMood.timestamp >= since)
                )).all()
            delta_by_day: Dict[str, float] = {}
            for row in interaction_rows:
                key = _day_key(row.timestamp)
                if key:
                    delta_by_day[key] = delta_by_day.get(key, 0.0) + float(row.affection_delta or 0)
            trends["affection_delta"] = [
                {"date": key, "delta": round(value, 1)}
                for key, value in sorted(delta_by_day.items())
            ]
            mood_by_day: Dict[str, int] = {}
            for row in mood_rows:
                key = _day_key(row.timestamp)
                if key:
                    mood_by_day[key] = mood_by_day.get(key, 0) + 1
            trends["mood_changes"] = [
                {"date": key, "count": count}
                for key, count in sorted(mood_by_day.items())
            ]
            trends["gate"] = await self._load_gate_daily(days)
        except Exception as exc:
            logger.error(f"[EmotionBoard] 走向分析失败: {exc}", exc_info=True)
        return trends

    # ------ 治理操作 ------

    async def run_action(self, body: Dict[str, Any]) -> Dict[str, Any]:
        action = str(body.get("action", "")).strip()
        if action == "set_mood":
            return await self._set_mood(body)
        forgetting = self._forgetting()
        if forgetting is None:
            return {"success": False, "message": "遗忘管理器未运行（插件可能未完整启动）"}
        if action == "run_forgetting_cycle":
            report = await forgetting.run_cycle()
            return {"success": True, "message": "遗忘周期已执行", "report": report}
        if action == "mark_dislike":
            return await forgetting.mark_dislike(
                str(body.get("kind") or ""), int(body.get("id") or 0)
            )
        if action == "reset_stage":
            return await forgetting.reset_stage(
                str(body.get("kind") or ""), int(body.get("id") or 0)
            )
        if action == "delete_item":
            return await forgetting.delete_now(
                str(body.get("kind") or ""), int(body.get("id") or 0)
            )
        return {"success": False, "message": f"未知情绪板块操作: {action or '(empty)'}"}

    async def _set_mood(self, body: Dict[str, Any]) -> Dict[str, Any]:
        group_id = str(body.get("group_id") or "").strip()
        mood_type = str(body.get("mood_type") or "").strip()
        if not group_id or not mood_type:
            return {"success": False, "message": "group_id 与 mood_type 不能为空"}
        if not self.database_manager:
            return {"success": False, "message": "数据库不可用"}
        try:
            intensity = min(1.0, max(0.0, float(body.get("intensity", 0.6))))
        except (TypeError, ValueError):
            intensity = 0.6
        now = time.time()
        try:
            async with self.database_manager.get_session() as session:
                await session.execute(
                    BotMood.__table__.update()
                    .where(BotMood.group_id == group_id)
                    .where(BotMood.is_active == 1)  # noqa: E712
                    .values(is_active=0, end_time=now)
                )
                session.add(BotMood(
                    group_id=group_id,
                    mood_type=mood_type,
                    mood_intensity=intensity,
                    mood_description=str(body.get("description") or f"手动设置为 {mood_type}"),
                    timestamp=now,
                    start_time=now,
                    is_active=1,
                ))
                await session.commit()
        except Exception as exc:
            logger.error(f"[EmotionBoard] 设置心情失败: {exc}", exc_info=True)
            return {"success": False, "message": f"设置心情失败: {exc}"}
        return {"success": True, "message": f"已将 {group_id} 心情设置为 {mood_type}"}
