"""Style counters count saved human expression samples independently of reviews."""

from pathlib import Path
from types import SimpleNamespace
import sys

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
if str(PACKAGE_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT.parent))

from self_learning_EterU.models.orm import Base, ExpressionPattern, StyleLearningReview
from self_learning_EterU.services.database.facades.expression_facade import ExpressionFacade
from self_learning_EterU.services.database.facades.learning_facade import LearningFacade
from self_learning_EterU.webui.services.learning_service import LearningService


@pytest.mark.asyncio
@pytest.mark.parametrize("pattern_count,review_statuses,use_pattern_facade", [
    (0, [], True),
    (3, [], True),
    (0, ["pending", "approved", "rejected"], True),
    (2, ["pending", "pending", "approved", "approved", "rejected"], True),
    (2, ["approved"], False),
])
async def test_style_statistics_count_saved_patterns_not_review_rows(
    pattern_count, review_statuses, use_pattern_facade,
):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    facade_engine = SimpleNamespace(engine=engine, get_session=sessions)
    learning = LearningFacade(facade_engine, SimpleNamespace())
    expressions = ExpressionFacade(facade_engine, SimpleNamespace())
    database = SimpleNamespace(
        get_style_learning_statistics=learning.get_style_learning_statistics,
        get_style_progress_data=learning.get_style_progress_data,
        get_session=sessions,
    )
    if use_pattern_facade:
        database.get_expression_patterns_statistics = expressions.get_expression_patterns_statistics
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            session.add_all([
                ExpressionPattern(
                    group_id=f"group-{index % 2}",
                    persona_id=f"persona-{index}",
                    situation=f"Human context {index}",
                    expression=f"Human response {index}",
                    weight=1.0,
                    create_time=1_700_000_000 + index,
                    last_active_time=1_700_000_000 + index,
                )
                for index in range(pattern_count)
            ])
            session.add_all([
                StyleLearningReview(
                    type="style_learning",
                    group_id="group-0",
                    timestamp=1_700_000_000 + index,
                    status=status,
                )
                for index, status in enumerate(review_statuses)
            ])
            await session.commit()

        service = LearningService(SimpleNamespace(database_manager=database))
        result = await service.get_style_learning_results()

        assert result["statistics"]["unique_styles"] == pattern_count
        assert result["statistics"]["total_samples"] == pattern_count
        assert result["statistics"]["total_reviews"] == len(review_statuses)
        assert result["statistics"]["pending_reviews"] == review_statuses.count("pending")
        assert result["statistics"]["approved_reviews"] == review_statuses.count("approved")
        assert result["style_progress"] == []
    finally:
        await engine.dispose()
