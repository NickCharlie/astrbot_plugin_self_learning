"""三阶段遗忘：按周期清理长期未使用 / 被明确反感的表达与黑话。

周期（forgetting_cycle_days，默认 7 天）执行一次，每次对候选条目推进状态：

- 本周期内「有使用」（表达 last_active_time / 黑话 updated_at 落在窗口内）
  或「有正向反馈」（表达生成结果 user_feedback=positive）→ 阶段重置为 0；
- 否则阶段 +1；阶段达到 3（连续三个周期无使用/正向反馈）→ 删除；
- 「明显反感」（生成结果 negative 反馈，或 WebUI 手动标记）在
  forgetting_negative_fast_track 开启时直接跳到阶段 2，再有一个空周期即删。

保护规则：新建条目在宽限期（forgetting_grace_days，默认 14 天）内不参与
遗忘；高权重表达（weight >= 3）视为核心资产永不删除；全局黑话可配置
保护；未过审黑话仍归审查流程管，不参与遗忘。
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

from astrbot.api import logger

try:
    from ...models.orm import (
        ExpressionGenerationResult,
        ExpressionPattern,
        Jargon,
        JargonUsageFrequency,
    )
except ImportError:
    from models.orm import (
        ExpressionGenerationResult,
        ExpressionPattern,
        Jargon,
        JargonUsageFrequency,
    )

STAGES = (0, 1, 2, 3)
STAGE_LABELS = {0: "新鲜", 1: "遗忘观察一期", 2: "遗忘观察二期", 3: "待删除"}
HIGH_VALUE_WEIGHT = 3.0  # 表达权重达到该值视为核心资产，永不遗忘
MAX_CANDIDATES_IN_STATUS = 60


class ForgettingManager:
    """表达/黑话三阶段遗忘的周期任务与治理入口。"""

    def __init__(self, config: Any = None, database_manager: Any = None) -> None:
        self._config = config
        self._database_manager = database_manager
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._last_report: Optional[Dict[str, Any]] = None
        self._last_run_at: Optional[float] = None

    # ------ 配置 ------

    @property
    def enabled(self) -> bool:
        return bool(getattr(self._config, "enable_expression_forgetting", True))

    @property
    def cycle_days(self) -> int:
        raw = getattr(self._config, "forgetting_cycle_days", 7)
        try:
            return min(90, max(1, int(raw)))
        except (TypeError, ValueError):
            return 7

    @property
    def grace_days(self) -> int:
        raw = getattr(self._config, "forgetting_grace_days", 14)
        try:
            return min(365, max(1, int(raw)))
        except (TypeError, ValueError):
            return 14

    @property
    def protect_global_jargon(self) -> bool:
        return bool(getattr(self._config, "forgetting_protect_global_jargon", True))

    @property
    def negative_fast_track(self) -> bool:
        return bool(getattr(self._config, "forgetting_negative_fast_track", True))

    # ------ 生命周期 ------

    async def start(self) -> bool:
        if not self.enabled:
            logger.info("[ForgettingManager] 三阶段遗忘未启用，跳过周期任务")
            return False
        if self._task is not None and not self._task.done():
            return True
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            f"[ForgettingManager] 三阶段遗忘已启动：周期 {self.cycle_days} 天，"
            f"宽限 {self.grace_days} 天"
        )
        return True

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    async def _run_loop(self) -> None:
        interval = self.cycle_days * 86400
        # 启动后先等一个完整周期再首次执行，避免重启即清理
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
            return  # stop 被触发
        except asyncio.TimeoutError:
            pass
        while not self._stop_event.is_set():
            try:
                await self.run_cycle()
            except Exception as exc:
                logger.error(f"[ForgettingManager] 遗忘周期执行失败: {exc}", exc_info=True)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
                return
            except asyncio.TimeoutError:
                continue

    # ------ 周期执行 ------

    async def run_cycle(self) -> Dict[str, Any]:
        now = time.time()
        window_start = now - self.cycle_days * 86400
        grace_start = now - self.grace_days * 86400
        report: Dict[str, Any] = {
            "ran_at": now,
            "window_start": window_start,
            "expression": {"checked": 0, "reset": 0, "advanced": 0, "deleted": 0, "protected": 0},
            "jargon": {"checked": 0, "reset": 0, "advanced": 0, "deleted": 0, "protected": 0},
        }
        if not self._database_manager:
            report["skipped"] = "数据库不可用"
            self._last_report = report
            return report

        await self._cycle_expressions(window_start, grace_start, report)
        await self._cycle_jargon(window_start, grace_start, report)
        self._last_report = report
        self._last_run_at = now
        logger.info(
            "[ForgettingManager] 遗忘周期完成: "
            f"表达 重置{report['expression']['reset']}/推进{report['expression']['advanced']}/删除{report['expression']['deleted']}, "
            f"黑话 重置{report['jargon']['reset']}/推进{report['jargon']['advanced']}/删除{report['jargon']['deleted']}"
        )
        return report

    async def _cycle_expressions(
        self, window_start: float, grace_start: float, report: Dict[str, Any]
    ) -> None:
        async with self._database_manager.get_session() as session:
            patterns: List[ExpressionPattern] = list(
                (await session.execute(
                    ExpressionPattern.__table__.select()
                )).all()
            )
            # 批量取窗口内反馈，避免逐条 N+1
            feedback_rows = (await session.execute(
                ExpressionGenerationResult.__table__.select()
                .where(ExpressionGenerationResult.generated_at >= window_start)
                .where(ExpressionGenerationResult.user_feedback.in_(("positive", "negative")))
            )).all()
            positive_ids = {
                row.pattern_id for row in feedback_rows if row.user_feedback == "positive"
            }
            negative_ids = {
                row.pattern_id for row in feedback_rows if row.user_feedback == "negative"
            }

            delete_ids: List[int] = []
            for pattern in patterns:
                report["expression"]["checked"] += 1
                create_time = float(pattern.create_time or 0)
                last_active = float(pattern.last_active_time or 0)
                stage = int(pattern.forget_stage or 0)
                weight = float(pattern.weight or 1.0)

                if create_time >= grace_start:
                    continue  # 宽限期内不参与遗忘
                if weight >= HIGH_VALUE_WEIGHT:
                    if stage != 0:
                        await self._set_expression_stage(session, pattern.id, 0)
                    report["expression"]["protected"] += 1
                    continue

                used = last_active >= window_start
                positive = pattern.id in positive_ids
                negative = pattern.id in negative_ids

                if negative and self.negative_fast_track:
                    new_stage = max(stage + 1, 2)
                    reason = "negative_feedback"
                elif used or positive:
                    new_stage = 0
                    reason = "used_or_positive"
                else:
                    new_stage = min(3, stage + 1)
                    reason = "unused"

                if new_stage >= 3:
                    delete_ids.append(pattern.id)
                    report["expression"]["advanced"] += 1
                    continue
                if new_stage != stage:
                    await self._set_expression_stage(session, pattern.id, new_stage)
                    if reason == "used_or_positive":
                        report["expression"]["reset"] += 1
                    else:
                        # unused / negative_feedback 均视为一次遗忘推进
                        report["expression"]["advanced"] += 1

            for pattern_id in delete_ids:
                await session.execute(
                    ExpressionGenerationResult.__table__.delete()
                    .where(ExpressionGenerationResult.pattern_id == pattern_id)
                )
                await session.execute(
                    ExpressionPattern.__table__.delete()
                    .where(ExpressionPattern.id == pattern_id)
                )
                report["expression"]["deleted"] += 1

            await session.commit()

    async def _cycle_jargon(
        self, window_start: float, grace_start: float, report: Dict[str, Any]
    ) -> None:
        async with self._database_manager.get_session() as session:
            jargons: List[Jargon] = list(
                (await session.execute(
                    Jargon.__table__.select().where(Jargon.is_jargon == True)  # noqa: E712
                )).all()
            )
            delete_ids: List[int] = []
            for jargon in jargons:
                report["jargon"]["checked"] += 1
                # 只处理已确认为黑话的词条；未过审的归审查流程
                created = float(jargon.created_at or 0)
                updated = float(jargon.updated_at or 0)
                stage = int(jargon.forget_stage or 0)

                if created >= grace_start:
                    continue
                if jargon.is_global and self.protect_global_jargon:
                    if stage != 0:
                        await self._set_jargon_stage(session, jargon.id, 0)
                    report["jargon"]["protected"] += 1
                    continue

                # 黑话重新出现（count 增长会刷新 updated_at）视为使用
                used = updated >= window_start
                if used:
                    if stage != 0:
                        await self._set_jargon_stage(session, jargon.id, 0)
                        report["jargon"]["reset"] += 1
                    continue

                new_stage = min(3, stage + 1)
                if new_stage >= 3:
                    delete_ids.append(jargon.id)
                    report["jargon"]["advanced"] += 1
                    continue
                if new_stage != stage:
                    await self._set_jargon_stage(session, jargon.id, new_stage)
                    report["jargon"]["advanced"] += 1

            for jargon_id in delete_ids:
                await session.execute(
                    JargonUsageFrequency.__table__.delete()
                    .where(JargonUsageFrequency.jargon_id == jargon_id)
                )
                await session.execute(
                    Jargon.__table__.delete().where(Jargon.id == jargon_id)
                )
                report["jargon"]["deleted"] += 1

            await session.commit()

    @staticmethod
    async def _set_expression_stage(session: Any, pattern_id: int, stage: int) -> None:
        await session.execute(
            ExpressionPattern.__table__.update()
            .where(ExpressionPattern.id == pattern_id)
            .values(forget_stage=stage, forget_updated_at=time.time())
        )

    @staticmethod
    async def _set_jargon_stage(session: Any, jargon_id: int, stage: int) -> None:
        await session.execute(
            Jargon.__table__.update()
            .where(Jargon.id == jargon_id)
            .values(forget_stage=stage, forget_updated_at=int(time.time()))
        )

    # ------ 治理操作（WebUI） ------

    async def mark_dislike(self, kind: str, item_id: int) -> Dict[str, Any]:
        """标记反感：直接推进到阶段 2，下一个空周期即删除。"""
        return await self._apply_stage(kind, item_id, 2, reason="marked_dislike")

    async def reset_stage(self, kind: str, item_id: int) -> Dict[str, Any]:
        """手动重置为新鲜阶段。"""
        return await self._apply_stage(kind, item_id, 0, reason="manual_reset")

    async def delete_now(self, kind: str, item_id: int) -> Dict[str, Any]:
        """立即删除（连带子记录）。"""
        if not self._database_manager:
            return {"success": False, "message": "数据库不可用"}
        async with self._database_manager.get_session() as session:
            if kind == "expression":
                await session.execute(
                    ExpressionGenerationResult.__table__.delete()
                    .where(ExpressionGenerationResult.pattern_id == item_id)
                )
                await session.execute(
                    ExpressionPattern.__table__.delete()
                    .where(ExpressionPattern.id == item_id)
                )
            elif kind == "jargon":
                await session.execute(
                    JargonUsageFrequency.__table__.delete()
                    .where(JargonUsageFrequency.jargon_id == item_id)
                )
                await session.execute(
                    Jargon.__table__.delete().where(Jargon.id == item_id)
                )
            else:
                return {"success": False, "message": f"未知类型: {kind}"}
            await session.commit()
        return {"success": True, "message": "已删除"}

    async def _apply_stage(
        self, kind: str, item_id: int, stage: int, reason: str
    ) -> Dict[str, Any]:
        if not self._database_manager:
            return {"success": False, "message": "数据库不可用"}
        async with self._database_manager.get_session() as session:
            if kind == "expression":
                await self._set_expression_stage(session, item_id, stage)
            elif kind == "jargon":
                await self._set_jargon_stage(session, item_id, stage)
            else:
                return {"success": False, "message": f"未知类型: {kind}"}
            await session.commit()
        label = STAGE_LABELS.get(stage, str(stage))
        return {"success": True, "message": f"已标记为「{label}」（{reason}）", "stage": stage}

    # ------ 状态读取 ------

    async def status(self) -> Dict[str, Any]:
        distribution = {"expression": {str(s): 0 for s in STAGES}, "jargon": {str(s): 0 for s in STAGES}}
        candidates: Dict[str, List[Dict[str, Any]]] = {"expression": [], "jargon": []}
        if self._database_manager:
            try:
                async with self._database_manager.get_session() as session:
                    for row in (await session.execute(
                        ExpressionPattern.__table__.select()
                        .where(ExpressionPattern.forget_stage > 0)
                        .order_by(ExpressionPattern.forget_stage.desc())
                        .order_by(ExpressionPattern.last_active_time.asc())
                        .limit(MAX_CANDIDATES_IN_STATUS)
                    )).all():
                        stage = str(int(row.forget_stage or 0))
                        distribution["expression"][stage] = distribution["expression"].get(stage, 0) + 1
                        candidates["expression"].append({
                            "id": row.id,
                            "kind": "expression",
                            "group_id": row.group_id,
                            "title": (row.expression or "")[:80],
                            "detail": (row.situation or "")[:80],
                            "stage": int(row.forget_stage or 0),
                            "last_used": row.last_active_time,
                            "created": row.create_time,
                        })
                    for row in (await session.execute(
                        Jargon.__table__.select()
                        .where(Jargon.forget_stage > 0)
                        .order_by(Jargon.forget_stage.desc())
                        .order_by(Jargon.updated_at.asc())
                        .limit(MAX_CANDIDATES_IN_STATUS)
                    )).all():
                        stage = str(int(row.forget_stage or 0))
                        distribution["jargon"][stage] = distribution["jargon"].get(stage, 0) + 1
                        candidates["jargon"].append({
                            "id": row.id,
                            "kind": "jargon",
                            "group_id": row.chat_id,
                            "title": (row.content or "")[:80],
                            "detail": (row.meaning or "")[:80],
                            "stage": int(row.forget_stage or 0),
                            "last_used": row.updated_at,
                            "created": row.created_at,
                        })
            except Exception as exc:
                logger.warning(f"[ForgettingManager] 读取遗忘状态失败: {exc}")

        return {
            "enabled": self.enabled,
            "config": {
                "cycle_days": self.cycle_days,
                "grace_days": self.grace_days,
                "protect_global_jargon": self.protect_global_jargon,
                "negative_fast_track": self.negative_fast_track,
                "high_value_weight": HIGH_VALUE_WEIGHT,
            },
            "stage_labels": STAGE_LABELS,
            "last_run_at": self._last_run_at,
            "next_run_interval_days": self.cycle_days,
            "last_report": self._last_report,
            "distribution": distribution,
            "candidates": candidates,
            "running": self._task is not None and not self._task.done(),
        }
