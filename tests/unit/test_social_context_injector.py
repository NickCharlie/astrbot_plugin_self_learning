import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from self_learning_EterU.services.social.social_context_injector import (
    SocialContextInjector,
)


class _DB:
    async def get_user_affection(self, group_id, user_id):
        return {
            "affection_level": 42,
            "max_affection": 100,
            "rank": "friend",
        }

    async def get_user_social_relations(self, group_id, user_id):
        return {
            "relations": [
                {
                    "from_user_id": user_id,
                    "to_user_id": "friend",
                    "relation_type": "reply",
                    "value": 2.0,
                    "frequency": 5,
                }
            ]
        }


class _ExpressionDB:
    def __init__(self):
        self.calls = []

    async def get_recent_week_expression_patterns(
        self,
        group_id=None,
        limit=50,
        hours=168,
        persona_id="default",
    ):
        self.calls.append(
            {
                "group_id": group_id,
                "limit": limit,
                "hours": hours,
                "persona_id": persona_id,
            }
        )
        return [
            {
                "situation": f"{group_id or 'global'}-{persona_id}-{hours}",
                "expression": f"expr-{persona_id}-{hours}",
            }
        ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_format_complete_context_uses_stable_section_order(monkeypatch):
    injector = SocialContextInjector(
        database_manager=_DB(),
        affection_manager=object(),
        mood_manager=object(),
        psychological_state_manager=object(),
        goal_manager=object(),
        config=SimpleNamespace(expression_patterns_hours=24),
    )

    async def slow_psych(group_id):
        await asyncio.sleep(0.03)
        return "心理状态段"

    async def slow_mood(group_id):
        await asyncio.sleep(0.02)
        return "情绪段"

    async def fast_affection(group_id, user_id):
        return "好感段"

    async def fast_social(group_id, user_id):
        return "社交段"

    async def fast_expression(group_id, persona_id="default", enable_protection=True):
        return "表达风格特征段"

    async def fast_goal(group_id, user_id):
        return "对话目标段"

    async def fast_behavior(group_id, user_id):
        return "行为指导段"

    monkeypatch.setattr(injector, "_build_psychological_context", slow_psych)
    monkeypatch.setattr(injector, "_format_mood_context", slow_mood)
    monkeypatch.setattr(injector, "_format_affection_context", fast_affection)
    monkeypatch.setattr(injector, "format_social_context", fast_social)
    monkeypatch.setattr(injector, "_format_expression_patterns_context", fast_expression)
    monkeypatch.setattr(injector, "_format_conversation_goal_context", fast_goal)
    monkeypatch.setattr(injector, "_build_behavior_guidance", fast_behavior)

    text = await injector.format_complete_context(
        group_id="group-a",
        user_id="user-a",
        persona_id="bot-a",
        include_conversation_goal=True,
        enable_protection=False,
    )

    assert text is not None
    positions = [text.index(part) for part in (
        "心理状态段",
        "情绪段",
        "好感段",
        "社交段",
        "对话目标段",
        "行为指导段",
        "表达风格特征段",
    )]
    assert positions == sorted(positions)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_expression_pattern_cache_key_includes_hours_protection_and_fallback():
    db = _ExpressionDB()
    injector = SocialContextInjector(
        database_manager=db,
        config=SimpleNamespace(expression_patterns_hours=24),
    )

    first = await injector._format_expression_patterns_context(
        "group-a",
        persona_id="bot-a",
        enable_protection=False,
        enable_global_fallback=True,
    )
    second = await injector._format_expression_patterns_context(
        "group-a",
        persona_id="bot-a",
        enable_protection=False,
        enable_global_fallback=True,
    )

    assert first == second
    assert len(db.calls) == 1

    injector.config.expression_patterns_hours = 48
    changed_hours = await injector._format_expression_patterns_context(
        "group-a",
        persona_id="bot-a",
        enable_protection=False,
        enable_global_fallback=True,
    )

    assert changed_hours != first
    assert len(db.calls) == 2

    changed_fallback_scope = await injector._format_expression_patterns_context(
        "group-a",
        persona_id="bot-a",
        enable_protection=False,
        enable_global_fallback=False,
    )

    assert changed_fallback_scope == changed_hours
    assert len(db.calls) == 3

