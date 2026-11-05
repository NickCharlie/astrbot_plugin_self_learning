"""Persona-side expression extraction must retain original conversation boundaries."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from self_learning_EterU.services.core_learning.progressive_learning import (
    ProgressiveLearningService,
)
from self_learning_EterU.services.learning.conversation_samples import extract_human_dialog_pairs
from self_learning_EterU.services.learning.persona_learning import PersonaLearningModule
from self_learning_EterU.services.persona import persona_updater as persona_updater_module
from self_learning_EterU.services.persona.persona_manager import PersonaManagerService
from self_learning_EterU.services.persona.persona_updater import PersonaUpdater


@pytest.mark.unit
@pytest.mark.asyncio
async def test_progressive_secondary_expression_source_keeps_filtered_review_analysis(monkeypatch):
    timeline = [
        {"sender_id": sender, "message": text, "timestamp": timestamp, "group_id": "group-a"}
        for sender, text, timestamp in (
            ("alice", "The question before the command", 100),
            ("bob", "/help", 101),
            ("carol", "Unrelated text after the command", 102),
            ("alice", "A later actual question", 1000),
            ("bob", "The later actual response", 1001),
        )
    ]
    filtered = [timeline[0], *timeline[2:]]
    captured_pairs = []

    async def learn_expressions(group_id, messages, *, persona_id):
        assert persona_id == "persona-a"
        captured_pairs.extend(extract_human_dialog_pairs(messages, group_id))
        return True

    current_persona = {"persona_id": "persona-a", "prompt": "Original persona"}
    monkeypatch.setattr(
        persona_updater_module, "resolve_target_persona",
        AsyncMock(return_value=current_persona),
    )
    config = SimpleNamespace(target_blacklist=[], auto_backup_enabled=False)
    context = SimpleNamespace(persona_manager=object())
    updater = PersonaUpdater.__new__(PersonaUpdater)
    updater.config = config
    updater.context = context
    updater._logger = Mock()
    updater.format_persona_update_report = AsyncMock(return_value="Candidate report")
    updater.expression_learner = SimpleNamespace(
        trigger_learning_for_group=AsyncMock(side_effect=learn_expressions),
    )
    updater.memory_graph_manager = SimpleNamespace(add_memory_from_message=AsyncMock())
    updater.knowledge_graph_manager = None
    persona_manager = PersonaManagerService(config, context, updater, None)
    persona_manager.update_persona = AsyncMock(wraps=persona_manager.update_persona)
    persona_learning = PersonaLearningModule(
        config=config,
        context=context,
        db_manager=None,
        persona_manager=persona_manager,
        multidimensional_analyzer=None,
        prompts=None,
        resolve_umo=lambda group_id: group_id,
        json_serializer=str,
    )
    persona_learning.create_persona_review = AsyncMock(return_value=1)
    service = ProgressiveLearningService.__new__(ProgressiveLearningService)
    service.config = config
    service.persona_learning = persona_learning
    service._group_sessions = {}
    service._save_style_learning_record = AsyncMock()

    await service._apply_learning_updates(
        "group-a", {}, filtered,
        current_persona=current_persona,
        updated_persona={"persona_id": "persona-a", "prompt": "Updated persona"},
        source_messages=timeline,
    )

    assert persona_manager.update_persona.await_args.args[2] is filtered
    assert persona_manager.update_persona.await_args.kwargs["expression_messages"] is timeline
    assert persona_learning.create_persona_review.await_args.args[2] is filtered
    assert updater.expression_learner.trigger_learning_for_group.await_args.args[1] is timeline
    assert [
        call.args[0] for call in updater.memory_graph_manager.add_memory_from_message.await_args_list
    ] == filtered
    assert [(pair["situation"], pair["expression"]) for pair in captured_pairs] == [
        ("A later actual question", "The later actual response"),
    ]
