"""Integration tests for learning-content dashboard routes."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from quart import Quart
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import webui.blueprints.learning as learning_module
from webui.blueprints.learning import learning_bp
from models.orm import Base, ExpressionPattern, LearningBatch, RawMessage, StyleLearningReview


@pytest.fixture
async def app(monkeypatch):
    monkeypatch.setattr(
        learning_module,
        "get_container",
        lambda: SimpleNamespace(database_manager=None),
    )

    app = Quart(__name__)
    app.config["TESTING"] = True
    app.secret_key = "test-secret-key"
    app.register_blueprint(learning_bp)
    yield app


@pytest.fixture
async def client(app):
    return app.test_client()


@pytest.mark.asyncio
async def test_learning_content_route_returns_all_buckets(client):
    response = await client.get("/api/style_learning/content_text")

    assert response.status_code == 200
    data = await response.get_json()
    assert set(data) == {"dialogues", "analysis", "features", "history"}
    assert data["dialogues"] == []
    assert data["analysis"] == []
    assert data["features"] == []
    assert data["history"] == []


@pytest.mark.asyncio
async def test_learning_content_route_returns_database_rows(client, monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        session.add_all(
            [
                RawMessage(
                    sender_id="u1",
                    sender_name="Alice",
                    message="这是一条用于学习的群聊原始消息",
                    group_id="g1",
                    timestamp=1710000000,
                    platform="aiocqhttp",
                    created_at=1710000000,
                    processed=True,
                ),
                StyleLearningReview(
                    type="mood_imitation",
                    group_id="g1",
                    timestamp=1710000010,
                    learned_patterns='["短句", "口癖"]',
                    few_shots_content="用户: 好耶\nBot: 好耶",
                    status="pending",
                    description="风格审查样本",
                ),
                ExpressionPattern(
                    group_id="g1",
                    situation="夸赞时",
                    expression="太会了",
                    weight=0.9,
                    last_active_time=1710000020,
                    create_time=1710000005,
                ),
                LearningBatch(
                    batch_id="batch-1",
                    batch_name="首次学习",
                    group_id="g1",
                    start_time=1710000030,
                    end_time=1710000040,
                    quality_score=0.88,
                    processed_messages=12,
                    message_count=15,
                    filtered_count=3,
                    success=True,
                    status="completed",
                ),
            ]
        )
        await session.commit()

    database_manager = SimpleNamespace(get_session=session_factory)
    monkeypatch.setattr(
        learning_module,
        "get_container",
        lambda: SimpleNamespace(database_manager=database_manager),
    )

    try:
        response = await client.get("/api/style_learning/content_text")

        assert response.status_code == 200
        data = await response.get_json()
        assert data["dialogues"][0]["title"] == "Alice"
        assert data["dialogues"][0]["raw"]["processed"] is True
        assert data["analysis"][0]["patterns"] == ["短句", "口癖"]
        assert data["features"][0]["raw"]["weight"] == 0.9
        assert data["history"][0]["raw"]["batch_id"] == "batch-1"
    finally:
        await engine.dispose()
