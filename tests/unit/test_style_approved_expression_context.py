"""Prompt consumers only receive expression samples with an approved review."""

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
if str(PACKAGE_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT.parent))

from self_learning_EterU.models.orm import Base, ExpressionPattern, StyleLearningReview
from self_learning_EterU.services.database.facades.expression_facade import ExpressionFacade


@pytest.mark.unit
@pytest.mark.asyncio
async def test_only_scope_matched_approved_samples_are_returned_for_injection():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    facade = ExpressionFacade(
        SimpleNamespace(engine=engine, get_session=sessions), SimpleNamespace()
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        now = time.time()
        examples = [
            ("persona-a", None, "approved context", "approved reply"),
            ("persona-a", None, "pending context", "pending reply"),
            ("persona-b", None, "other persona context", "other persona reply"),
            ("persona-a", "user-b", "other user context", "other user reply"),
        ]
        async with sessions() as session:
            session.add_all([
                ExpressionPattern(
                    group_id="group-a", persona_id=persona, user_id=user,
                    situation=situation, expression=expression, weight=1,
                    create_time=now, last_active_time=now,
                )
                for persona, user, situation, expression in examples
            ])
            session.add_all([
                StyleLearningReview(
                    type="style_learning", group_id="group-a",
                    timestamp=now, status=status,
                    learned_patterns=json.dumps([{
                        "situation": situation, "expression": expression,
                        "persona_id": persona, "user_id": user,
                    }]),
                )
                for status, persona, user, situation, expression in [
                    ("approved", "persona-a", None, "approved context", "approved reply"),
                    ("pending", "persona-a", None, "pending context", "pending reply"),
                    ("approved", "persona-b", None, "other persona context", "other persona reply"),
                    ("approved", "persona-a", "user-b", "other user context", "other user reply"),
                ]
            ])
            session.add(StyleLearningReview(
                type="style_learning", group_id="group-a", timestamp=now,
                status="approved",
                learned_patterns=json.dumps([{
                    "situation": "Legacy approved context",
                    "expression": "Legacy approved reply",
                }]),
            ))
            session.add(ExpressionPattern(
                group_id="group-a", persona_id="default", user_id=None,
                situation="Legacy approved context", expression="Legacy approved reply",
                weight=1, create_time=now, last_active_time=now,
            ))
            await session.commit()

        rows = await facade.get_recent_week_expression_patterns(
            "group-a", persona_id="persona-a", user_id=None,
        )

        assert {(row["situation"], row["expression"]) for row in rows} == {
            ("approved context", "approved reply"),
        }
        legacy = await facade.get_recent_week_expression_patterns(
            "group-a", persona_id="default", user_id=None,
        )
        assert [(row["situation"], row["expression"]) for row in legacy] == [
            ("Legacy approved context", "Legacy approved reply"),
        ]
    finally:
        await engine.dispose()
