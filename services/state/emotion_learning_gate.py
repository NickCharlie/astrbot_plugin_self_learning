"""情绪学习闸门：用情绪/好感度加权判断决定单条消息是否进入学习。

参考 EmotionAI Pro 的「复合评分 + 动态权重」思路，结合本插件已有的
好感度（UserAffection）、全局心情（BotMood）、情绪画像（EmotionProfile）
三个数据源，为每条进入学习流水线的消息计算一个 0~1 的加权分：

- affection  (0.35)：发言用户当前好感度归一化，无记录取中性 0.5
- sentiment  (0.25)：本条消息的情感极性，复用规则引擎（零 LLM 成本），
  正面 1.0 / 中性 0.6 / 负面 0.05
- mood       (0.20)：Bot 当前群心情的效价，按强度向中性 0.5 收敛
- stability  (0.20)：用户情绪画像的稳定性，无画像取 0.5

加权分 >= 阈值（emotion_gate_threshold，默认 0.3）才放行表达/黑话学习；
原始消息采集不受影响。任何内部异常都按放行处理（fail-open），情绪数据
缺失只影响因子取值，不会阻塞学习链路。
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, Optional

from astrbot.api import logger

try:
    from ..models.orm import (
        BotMood,
        EmotionProfile,
        LearningGateDailyStat,
        UserAffection,
    )
except ImportError:
    from models.orm import (
        BotMood,
        EmotionProfile,
        LearningGateDailyStat,
        UserAffection,
    )

# 与 AffectionManager.InteractionType 对齐的极性映射（字符串值）
POSITIVE_INTERACTIONS = {
    "compliment", "flirt", "thanks", "praise", "encourage",
    "support", "care", "gift", "comfort", "tease",
}
NEGATIVE_INTERACTIONS = {"insult", "harassment", "abuse", "threat"}

# BotMood.mood_type → 效价（0~1，0.5 为中性）
MOOD_VALENCE = {
    "happy": 1.0,
    "excited": 0.95,
    "playful": 0.9,
    "curious": 0.75,
    "calm": 0.7,
    "nostalgic": 0.55,
    "serious": 0.5,
    "anxious": 0.3,
    "sad": 0.25,
    "angry": 0.1,
}

# 本地兜底的情感关键词（当没有 AffectionManager 可复用时使用）
LOCAL_POSITIVE_KEYWORDS = (
    "好美", "漂亮", "可爱", "厉害", "真棒", "好看", "谢谢", "感谢",
    "加油", "支持", "喜欢你", "爱了", "牛", "优秀", "做得好", "关心",
)
LOCAL_NEGATIVE_KEYWORDS = (
    "蠢货", "白痴", "垃圾", "滚", "闭嘴", "恶心", "废物", "智障",
    "烦死了", "骚扰", "威胁", "打死你", "去死",
)

FACTOR_WEIGHTS = {
    "affection": 0.35,
    "sentiment": 0.25,
    "mood": 0.20,
    "stability": 0.20,
}
NEUTRAL_FACTOR = 0.5


class EmotionLearningGate:
    """按消息计算情绪加权分并决定是否放行学习。"""

    def __init__(
        self,
        config: Any = None,
        database_manager: Any = None,
        affection_manager: Any = None,
    ) -> None:
        self._config = config
        self._database_manager = database_manager
        self._affection_manager = affection_manager
        # 近期判定环形缓冲 + 累计计数（情绪板块遥测；日聚合另落库）
        self._recent: Deque[Dict[str, Any]] = deque(maxlen=50)
        self._counters: Dict[str, int] = {"accepted": 0, "skipped": 0}
        self._lock = asyncio.Lock()

    # ------ 配置读取 ------

    @property
    def enabled(self) -> bool:
        return bool(getattr(self._config, "enable_emotion_learning_gate", True))

    @property
    def threshold(self) -> float:
        raw = getattr(self._config, "emotion_gate_threshold", 0.3)
        try:
            return min(0.95, max(0.05, float(raw)))
        except (TypeError, ValueError):
            return 0.3

    # ------ 判定 ------

    async def evaluate_and_record(
        self,
        group_id: str,
        user_id: str,
        message_text: str,
    ) -> Dict[str, Any]:
        """计算加权分、记录遥测并返回判定结果。

        返回: {enabled, decision, score, threshold, factors}。
        """
        if not self.enabled:
            return {
                "enabled": False,
                "decision": True,
                "score": None,
                "threshold": self.threshold,
                "factors": {},
            }

        factors = await self._collect_factors(group_id, user_id, message_text)
        score = self._weighted_score(factors)
        decision = score >= self.threshold
        result = {
            "enabled": True,
            "decision": decision,
            "score": round(score, 4),
            "threshold": self.threshold,
            "factors": {key: round(value, 4) for key, value in factors.items()},
        }
        await self._record(group_id, user_id, result)
        return result

    def _weighted_score(self, factors: Dict[str, float]) -> float:
        total = 0.0
        for key, weight in FACTOR_WEIGHTS.items():
            value = factors.get(key, NEUTRAL_FACTOR)
            total += weight * min(1.0, max(0.0, value))
        return total

    async def _collect_factors(
        self,
        group_id: str,
        user_id: str,
        message_text: str,
    ) -> Dict[str, float]:
        affection = await self._affection_factor(group_id, user_id)
        sentiment = self._sentiment_factor(message_text)
        mood = await self._mood_factor(group_id)
        stability = await self._stability_factor(group_id, user_id)
        return {
            "affection": affection,
            "sentiment": sentiment,
            "mood": mood,
            "stability": stability,
        }

    # ------ 因子 ------

    async def _affection_factor(self, group_id: str, user_id: str) -> float:
        level = await self._read_affection_level(group_id, user_id)
        if level is None:
            return NEUTRAL_FACTOR
        # 好感度区间约 -100 ~ 100，线性归一到 0 ~ 1
        return min(1.0, max(0.0, (float(level) + 100.0) / 200.0))

    async def _read_affection_level(self, group_id: str, user_id: str) -> Optional[float]:
        if not self._database_manager:
            return None
        try:
            async with self._database_manager.get_session() as session:
                row = (
                    await session.execute(
                        UserAffection.__table__.select()
                        .where(UserAffection.group_id == group_id)
                        .where(UserAffection.user_id == user_id)
                    )
                ).first()
                if row is None:
                    return None
                return float(row.affection_level or 0)
        except Exception as exc:
            logger.debug(f"[EmotionGate] 读取好感度失败，按中性处理: {exc}")
            return None

    def _sentiment_factor(self, message_text: str) -> float:
        interaction = self._rule_interaction(message_text)
        if interaction in NEGATIVE_INTERACTIONS:
            return 0.05
        if interaction in POSITIVE_INTERACTIONS:
            return 1.0
        return 0.6  # chat / help / apology / 未知

    def _rule_interaction(self, message_text: str) -> Optional[str]:
        """复用 AffectionManager 的规则分析；不可用时退回本地关键词。"""
        analyzer = getattr(self._affection_manager, "_rule_based_interaction_analysis", None)
        if callable(analyzer):
            try:
                result = analyzer(message_text)
                return getattr(result, "value", None)
            except Exception:
                pass
        text = str(message_text or "").lower()
        if any(keyword in text for keyword in LOCAL_NEGATIVE_KEYWORDS):
            return "insult"
        if any(keyword in text for keyword in LOCAL_POSITIVE_KEYWORDS):
            return "compliment"
        return None

    async def _mood_factor(self, group_id: str) -> float:
        mood_type, intensity = await self._read_active_mood(group_id)
        if mood_type is None:
            return NEUTRAL_FACTOR
        valence = MOOD_VALENCE.get(str(mood_type), 0.5)
        try:
            intensity = min(1.0, max(0.0, float(intensity or 0.5)))
        except (TypeError, ValueError):
            intensity = 0.5
        # 强度越大，效价偏离中性越远；强度 0 时保持中性
        return 0.5 + (valence - 0.5) * (0.5 + intensity * 0.5)

    async def _read_active_mood(self, group_id: str):
        if not self._database_manager:
            return None, None
        try:
            async with self._database_manager.get_session() as session:
                result = await session.execute(
                    BotMood.__table__.select()
                    .where(BotMood.group_id == group_id)
                    .where(BotMood.is_active == 1)
                    .order_by(BotMood.timestamp.desc())
                    .limit(1)
                )
                row = result.first()
                if row is None:
                    return None, None
                return row.mood_type, row.mood_intensity
        except Exception as exc:
            logger.debug(f"[EmotionGate] 读取 Bot 心情失败，按中性处理: {exc}")
            return None, None

    async def _stability_factor(self, group_id: str, user_id: str) -> float:
        stability = await self._read_emotional_stability(group_id, user_id)
        if stability is None:
            return NEUTRAL_FACTOR
        return min(1.0, max(0.0, float(stability)))

    async def _read_emotional_stability(self, group_id: str, user_id: str) -> Optional[float]:
        if not self._database_manager:
            return None
        try:
            async with self._database_manager.get_session() as session:
                result = await session.execute(
                    EmotionProfile.__table__.select()
                    .where(EmotionProfile.group_id == group_id)
                    .where(EmotionProfile.user_id == user_id)
                )
                row = result.first()
                if row is None:
                    return None
                value = row.emotional_stability
                return None if value is None else float(value)
        except Exception as exc:
            logger.debug(f"[EmotionGate] 读取情绪画像失败，按中性处理: {exc}")
            return None

    # ------ 遥测 ------

    async def _record(self, group_id: str, user_id: str, result: Dict[str, Any]) -> None:
        entry = {
            "timestamp": time.time(),
            "group_id": group_id,
            "user_id": user_id,
            **result,
        }
        async with self._lock:
            self._recent.append(entry)
            if result.get("decision"):
                self._counters["accepted"] += 1
            else:
                self._counters["skipped"] += 1
        # 落库失败不影响判定（遥测尽力而为）
        try:
            await self._persist_daily_stat(group_id, result)
        except Exception as exc:
            logger.debug(f"[EmotionGate] 写入日统计失败（忽略）: {exc}")

    async def _persist_daily_stat(self, group_id: str, result: Dict[str, Any]) -> None:
        if not self._database_manager:
            return
        stat_date = datetime.now().strftime("%Y-%m-%d")
        factors = result.get("factors") or {}
        accepted = 1 if result.get("decision") else 0
        skipped = 0 if result.get("decision") else 1
        score = float(result.get("score") or 0.0)
        async with self._database_manager.get_session() as session:
            row = (
                await session.execute(
                    LearningGateDailyStat.__table__.select()
                    .where(LearningGateDailyStat.stat_date == stat_date)
                    .where(LearningGateDailyStat.group_id == group_id)
                )
            ).first()
            factor_sum = {}
            if row is not None and row.factor_sum_json:
                try:
                    factor_sum = json.loads(row.factor_sum_json) or {}
                except (TypeError, ValueError):
                    factor_sum = {}
            for key, value in factors.items():
                factor_sum[key] = float(factor_sum.get(key, 0.0)) + float(value or 0.0)
            if row is None:
                session.add(LearningGateDailyStat(
                    stat_date=stat_date,
                    group_id=group_id,
                    accepted_count=accepted,
                    skipped_count=skipped,
                    total_score=score,
                    total_count=1,
                    factor_sum_json=json.dumps(factor_sum, ensure_ascii=False),
                ))
            else:
                await session.execute(
                    LearningGateDailyStat.__table__.update()
                    .where(LearningGateDailyStat.id == row.id)
                    .values(
                        accepted_count=(row.accepted_count or 0) + accepted,
                        skipped_count=(row.skipped_count or 0) + skipped,
                        total_score=(row.total_score or 0.0) + score,
                        total_count=(row.total_count or 0) + 1,
                        factor_sum_json=json.dumps(factor_sum, ensure_ascii=False),
                    )
                )
            await session.commit()

    # ------ 面板读取 ------

    def telemetry(self) -> Dict[str, Any]:
        """内存遥测快照（近期判定 + 累计计数），供情绪板块展示。"""
        recent = list(self._recent)
        factor_avg: Dict[str, float] = {}
        if recent:
            keys = FACTOR_WEIGHTS.keys()
            factor_avg = {
                key: round(
                    sum(float((item.get("factors") or {}).get(key, 0.0)) for item in recent)
                    / len(recent),
                    4,
                )
                for key in keys
            }
        return {
            "enabled": self.enabled,
            "threshold": self.threshold,
            "weights": dict(FACTOR_WEIGHTS),
            "recent": recent[-20:],
            "counters": dict(self._counters),
            "recent_factor_avg": factor_avg,
        }
