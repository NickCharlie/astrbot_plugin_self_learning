import pytest

from config import PluginConfig
from models.orm.affection import AffectionInteraction, UserAffection
from models.orm.conversation_goal import ConversationGoal
from models.orm.expression import ExpressionGenerationResult, ExpressionPattern
from models.orm.exemplar import Exemplar
from models.orm.jargon import Jargon, JargonUsageFrequency
from models.orm.knowledge_graph import KGEntity, KGParagraphHash, KGRelation
from models.orm.learning import (
    InteractionRecord,
    LearningBatch,
    PersonaLearningReview,
)
from models.orm.memory import Memory, MemoryEmbedding, MemorySummary
from models.orm.psychological import (
    PersonaAttributeWeight,
    PersonaBackup,
    PersonaDiversityScore,
    PersonaEvolutionSnapshot,
)
from services.database.sqlalchemy_database_manager import SQLAlchemyDatabaseManager


@pytest.mark.asyncio
async def test_clear_all_plugin_data_removes_learning_persistence(tmp_path):
    manager = SQLAlchemyDatabaseManager(
        PluginConfig(data_dir=str(tmp_path), db_type="sqlite", enable_web_interface=False)
    )

    try:
        assert await manager.start() is True

        async with manager.get_session() as session:
            now = 1_700_000_000

            memory = Memory(
                group_id="group-a",
                user_id="user-a",
                content="remembered fact",
                importance=5,
                created_at=now,
                last_accessed=now,
            )
            session.add(memory)
            await session.flush()
            session.add_all(
                [
                    MemoryEmbedding(
                        memory_id=memory.id,
                        embedding_model="test",
                        embedding_data="[]",
                        created_at=now,
                    ),
                    MemorySummary(
                        group_id="group-a",
                        user_id="user-a",
                        summary_type="daily",
                        summary_content="summary",
                        created_at=now,
                        updated_at=now,
                    ),
                    KGEntity(
                        name="Alice",
                        entity_type="person",
                        appear_count=1,
                        last_active_time=float(now),
                        group_id="group-a",
                    ),
                    KGRelation(
                        subject="Alice",
                        predicate="likes",
                        object="Tea",
                        confidence=1.0,
                        created_time=float(now),
                        group_id="group-a",
                    ),
                    KGParagraphHash(
                        hash_value="a" * 64,
                        group_id="group-a",
                        created_time=float(now),
                    ),
                    PersonaLearningReview(
                        timestamp=float(now),
                        group_id="group-a",
                        update_type="progressive_persona_learning",
                        status="pending",
                    ),
                    PersonaBackup(
                        group_id="group-a",
                        backup_name="before-learning",
                        timestamp=float(now),
                    ),
                    PersonaEvolutionSnapshot(
                        group_id="group-a",
                        persona_id="default",
                        snapshot_data="{}",
                        version=1,
                        snapshot_timestamp=float(now),
                    ),
                    PersonaAttributeWeight(
                        group_id="group-a",
                        persona_id="default",
                        attribute_name="tone",
                        weight=0.5,
                        updated_at=float(now),
                    ),
                    PersonaDiversityScore(
                        group_id="group-a",
                        persona_id="default",
                        diversity_dimension="style",
                        score=0.5,
                        calculated_at=float(now),
                    ),
                    LearningBatch(
                        batch_name="batch-a",
                        group_id="group-a",
                        start_time=float(now),
                    ),
                    InteractionRecord(
                        group_id="group-a",
                        user_id="user-a",
                        interaction_type="message",
                        timestamp=now,
                    ),
                    Exemplar(
                        content="high quality style sample",
                        sender_id="user-a",
                        group_id="group-a",
                    ),
                    ConversationGoal(
                        session_id="session-a",
                        user_id="user-a",
                        group_id="group-a",
                        final_goal={"type": "support"},
                        current_stage={"index": 1},
                        planned_stages=["listen"],
                        metrics={"rounds": 1},
                        created_at=now,
                        last_updated=now,
                    ),
                ]
            )

            pattern = ExpressionPattern(
                group_id="group-a",
                situation="greeting",
                expression="hello there",
                weight=1.0,
                last_active_time=float(now),
                create_time=float(now),
            )
            session.add(pattern)
            await session.flush()
            session.add(
                ExpressionGenerationResult(
                    group_id="group-a",
                    pattern_id=pattern.id,
                    generated_text="hello there",
                    generated_at=float(now),
                )
            )

            jargon = Jargon(
                content="暗号",
                chat_id="group-a",
                is_jargon=True,
                created_at=now,
                updated_at=now,
            )
            affection = UserAffection(
                group_id="group-a",
                user_id="user-a",
                created_at=now,
                updated_at=now,
            )
            session.add_all([jargon, affection])
            await session.flush()
            session.add_all(
                [
                    JargonUsageFrequency(
                        jargon_id=jargon.id,
                        group_id="group-a",
                        last_used_at=float(now),
                    ),
                    AffectionInteraction(
                        user_affection_id=affection.id,
                        interaction_type="message",
                        affection_delta=1,
                        timestamp=now,
                    ),
                ]
            )
            await session.commit()

        before = await manager.get_data_statistics()
        assert before["memory"] == 3
        assert before["knowledge_graph"] == 3
        assert before["persona_reviews"] == 5
        assert before["style_learning"] == 3
        assert before["jargon"] == 2
        assert before["learning_history"] == 2
        assert before["runtime_state"] == 3

        result = await manager.clear_all_plugin_data()

        assert result["success"] is True
        assert result["details"]["memory"]["deleted"] == 3
        assert result["details"]["knowledge_graph"]["deleted"] == 3
        assert result["details"]["runtime_state"]["deleted"] == 3
        assert all(value == 0 for value in (await manager.get_data_statistics()).values())
    finally:
        await manager.stop()
