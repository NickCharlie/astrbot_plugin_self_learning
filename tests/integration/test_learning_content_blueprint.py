"""Integration tests for learning-content dashboard routes."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

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
async def test_style_learning_batch_review_route_calls_service(client, monkeypatch):
    calls = []

    class _FakeLearningService:
        def __init__(self, container):
            self.container = container

        async def batch_review_style_learning_reviews(self, review_ids, action, comment=""):
            calls.append((review_ids, action, comment))
            return {
                "success": True,
                "message": "批量审查完成",
                "details": {"success_count": len(review_ids), "failed_count": 0},
            }

    monkeypatch.setattr(
        learning_module,
        "get_container",
        lambda: SimpleNamespace(database_manager=SimpleNamespace()),
    )
    monkeypatch.setattr(learning_module, "LearningService", _FakeLearningService)

    response = await client.post(
        "/api/style_learning/reviews/batch_review",
        json={"review_ids": [1, 2], "action": "approve", "comment": "batch"},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["success"] is True
    assert calls == [([1, 2], "approve", "batch")]


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
        assert data["history"][0]["raw"]["quality_score"] == 0.88
        assert data["history"][0]["raw"]["raw_quality_score"] == 0.88
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_learning_content_route_derives_successful_zero_batch_quality(client, monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        session.add(
            LearningBatch(
                batch_id="batch-zero",
                batch_name="旧零分批次",
                group_id="g1",
                start_time=1710000030,
                end_time=1710000040,
                quality_score=0.0,
                processed_messages=200,
                message_count=200,
                filtered_count=120,
                success=True,
                status="completed",
            )
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
        content_data = await response.get_json()
        quality = content_data["history"][0]["raw"]["quality_score"]
        assert quality > 0
        assert content_data["history"][0]["raw"]["raw_quality_score"] == 0.0

        response = await client.get("/api/batches")
        assert response.status_code == 200
        batch_data = await response.get_json()
        batch = batch_data["data"]["batches"][0]
        assert batch["quality_score"] == quality
        assert batch["raw_quality_score"] == 0.0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_learning_content_delete_removes_database_rows(client, monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        rows = {
            "dialogues": RawMessage(
                sender_id="u1",
                sender_name="Alice",
                message="这是一条待删除的群聊原始消息",
                group_id="g1",
                timestamp=1710000000,
                platform="aiocqhttp",
                created_at=1710000000,
                processed=True,
            ),
            "analysis": StyleLearningReview(
                type="mood_imitation",
                group_id="g1",
                timestamp=1710000010,
                learned_patterns='["短句"]',
                few_shots_content="用户: 好耶\nBot: 好耶",
                status="pending",
                description="待删除风格审查样本",
            ),
            "features": ExpressionPattern(
                group_id="g1",
                situation="夸赞时",
                expression="太会了",
                weight=0.9,
                last_active_time=1710000020,
                create_time=1710000005,
            ),
            "history": LearningBatch(
                batch_id="batch-delete",
                batch_name="待删除批次",
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
        }
        session.add_all(rows.values())
        await session.commit()
        ids = {bucket: row.id for bucket, row in rows.items()}

    database_manager = SimpleNamespace(get_session=session_factory)
    monkeypatch.setattr(
        learning_module,
        "get_container",
        lambda: SimpleNamespace(database_manager=database_manager),
    )

    bucket_models = {
        "dialogues": RawMessage,
        "analysis": StyleLearningReview,
        "features": ExpressionPattern,
        "history": LearningBatch,
    }

    try:
        for bucket, model in bucket_models.items():
            response = await client.delete(
                f"/api/style_learning/content_text/{bucket}/{ids[bucket]}"
            )
            assert response.status_code == 200
            payload = await response.get_json()
            assert payload["success"] is True

            async with session_factory() as session:
                assert await session.get(model, ids[bucket]) is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_learning_content_delete_rejects_invalid_or_missing_rows(client, monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    database_manager = SimpleNamespace(get_session=session_factory)
    monkeypatch.setattr(
        learning_module,
        "get_container",
        lambda: SimpleNamespace(database_manager=database_manager),
    )

    try:
        response = await client.delete("/api/style_learning/content_text/unknown/1")
        assert response.status_code == 400

        response = await client.delete("/api/style_learning/content_text/dialogues/999")
        assert response.status_code == 404
    finally:
        await engine.dispose()
