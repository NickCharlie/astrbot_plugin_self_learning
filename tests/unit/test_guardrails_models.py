"""
Unit tests for Guardrails Pydantic validation models

Tests the Pydantic model definitions used for structured LLM output:
- PsychologicalStateTransition validation
- GoalAnalysisResult validation
- ConversationIntentAnalysis defaults and validation
- RelationChange and SocialRelationAnalysis validation
- Field range constraints (ge, le, min_length, max_length)
"""
import pytest
from pydantic import ValidationError

from utils.guardrails_manager import (
    PsychologicalStateTransition,
    GoalAnalysisResult,
    ConversationIntentAnalysis,
    RelationChange,
    SocialRelationAnalysis,
)


@pytest.mark.unit
@pytest.mark.utils
class TestPsychologicalStateTransition:
    """Test PsychologicalStateTransition Pydantic model."""

    def test_valid_creation(self):
        """Test creating a valid state transition."""
        state = PsychologicalStateTransition(
            new_state="愉悦",
            confidence=0.85,
            reason="Positive conversation detected",
        )

        assert state.new_state == "愉悦"
        assert state.confidence == 0.85
        assert state.reason == "Positive conversation detected"

    def test_default_values(self):
        """Test default confidence and reason values."""
        state = PsychologicalStateTransition(new_state="平静")

        assert state.confidence == 0.8
        assert state.reason == ""

    def test_state_name_too_long(self):
        """Test state name longer than 20 chars is rejected."""
        with pytest.raises(ValidationError):
            PsychologicalStateTransition(new_state="a" * 21)

    def test_empty_state_name(self):
        """Test empty state name is rejected."""
        with pytest.raises(ValidationError):
            PsychologicalStateTransition(new_state="")

    def test_confidence_below_zero(self):
        """Test confidence below 0.0 is rejected."""
        with pytest.raises(ValidationError):
            PsychologicalStateTransition(new_state="测试", confidence=-0.1)

    def test_confidence_above_one(self):
        """Test confidence above 1.0 is rejected."""
        with pytest.raises(ValidationError):
            PsychologicalStateTransition(new_state="测试", confidence=1.1)

    def test_confidence_boundary_values(self):
        """Test confidence at exact boundaries (0.0 and 1.0)."""
        s_low = PsychologicalStateTransition(new_state="低", confidence=0.0)
        s_high = PsychologicalStateTransition(new_state="高", confidence=1.0)

        assert s_low.confidence == 0.0
        assert s_high.confidence == 1.0

    def test_state_name_whitespace_stripped(self):
        """Test state name with whitespace is stripped."""
        state = PsychologicalStateTransition(new_state="  愉悦  ")
        assert state.new_state == "愉悦"


@pytest.mark.unit
@pytest.mark.utils
class TestGoalAnalysisResult:
    """Test GoalAnalysisResult Pydantic model."""

    def test_valid_creation(self):
        """Test creating a valid goal analysis result."""
        result = GoalAnalysisResult(
            goal_type="emotional_support",
            topic="工作压力",
            confidence=0.85,
            reasoning="User seems stressed",
        )

        assert result.goal_type == "emotional_support"
        assert result.topic == "工作压力"
        assert result.confidence == 0.85

    def test_default_values(self):
        """Test default values for optional fields."""
        result = GoalAnalysisResult(
            goal_type="casual_chat",
            topic="日常",
        )

        assert result.confidence == 0.7
        assert result.reasoning == ""

    def test_goal_type_too_long(self):
        """Test goal_type exceeding 50 chars is rejected."""
        with pytest.raises(ValidationError):
            GoalAnalysisResult(
                goal_type="a" * 51,
                topic="test",
            )

    def test_topic_too_long(self):
        """Test topic exceeding 100 chars is rejected."""
        with pytest.raises(ValidationError):
            GoalAnalysisResult(
                goal_type="test",
                topic="a" * 101,
            )

    def test_empty_goal_type(self):
        """Test empty goal_type is rejected."""
        with pytest.raises(ValidationError):
            GoalAnalysisResult(goal_type="", topic="test")

    def test_empty_topic(self):
        """Test empty topic is rejected."""
        with pytest.raises(ValidationError):
            GoalAnalysisResult(goal_type="test", topic="")


@pytest.mark.unit
@pytest.mark.utils
class TestConversationIntentAnalysis:
    """Test ConversationIntentAnalysis Pydantic model."""

    def test_default_values(self):
        """Test all default values are correctly set."""
        intent = ConversationIntentAnalysis()

        assert intent.goal_switch_needed is False
        assert intent.new_goal_type is None
        assert intent.new_topic is None
        assert intent.topic_completed is False
        assert intent.stage_completed is False
        assert intent.stage_adjustment_needed is False
        assert intent.suggested_stage is None
        assert intent.completion_signals == 0
        assert intent.user_engagement == 0.5
        assert intent.reasoning == ""

    def test_custom_values(self):
        """Test setting custom values."""
        intent = ConversationIntentAnalysis(
            goal_switch_needed=True,
            new_goal_type="knowledge_sharing",
            user_engagement=0.9,
            completion_signals=3,
        )

        assert intent.goal_switch_needed is True
        assert intent.new_goal_type == "knowledge_sharing"
        assert intent.user_engagement == 0.9
        assert intent.completion_signals == 3

    def test_engagement_below_zero(self):
        """Test user_engagement below 0.0 is rejected."""
        with pytest.raises(ValidationError):
            ConversationIntentAnalysis(user_engagement=-0.1)

    def test_engagement_above_one(self):
        """Test user_engagement above 1.0 is rejected."""
        with pytest.raises(ValidationError):
            ConversationIntentAnalysis(user_engagement=1.1)

    def test_negative_completion_signals(self):
        """Test negative completion_signals is rejected."""
        with pytest.raises(ValidationError):
            ConversationIntentAnalysis(completion_signals=-1)


@pytest.mark.unit
@pytest.mark.utils
class TestRelationChange:
    """Test RelationChange Pydantic model."""

    def test_valid_creation(self):
        """Test creating a valid relation change."""
        change = RelationChange(
            relation_type="挚友",
            value_delta=0.1,
            reason="Shared positive experience",
        )

        assert change.relation_type == "挚友"
        assert change.value_delta == 0.1

    def test_relation_type_too_long(self):
        """Test relation_type exceeding 30 chars is rejected."""
        with pytest.raises(ValidationError):
            RelationChange(
                relation_type="a" * 31,
                value_delta=0.1,
            )

    def test_value_delta_below_negative_one(self):
        """Test value_delta below -1.0 is rejected."""
        with pytest.raises(ValidationError):
            RelationChange(relation_type="test", value_delta=-1.1)

    def test_value_delta_above_one(self):
        """Test value_delta above 1.0 is rejected."""
        with pytest.raises(ValidationError):
            RelationChange(relation_type="test", value_delta=1.1)

    def test_boundary_values(self):
        """Test boundary values for value_delta."""
        low = RelationChange(relation_type="低", value_delta=-1.0)
        high = RelationChange(relation_type="高", value_delta=1.0)

        assert low.value_delta == -1.0
        assert high.value_delta == 1.0


@pytest.mark.unit
@pytest.mark.utils
class TestSocialRelationAnalysis:
    """Test SocialRelationAnalysis Pydantic model."""

    def test_valid_creation(self):
        """Test creating a valid social relation analysis."""
        analysis = SocialRelationAnalysis(
            relations=[
                RelationChange(relation_type="友情", value_delta=0.05),
                RelationChange(relation_type="信任", value_delta=0.02),
            ],
            overall_sentiment="positive",
        )

        assert len(analysis.relations) == 2
        assert analysis.overall_sentiment == "positive"

    def test_empty_relations(self):
        """Test empty relations list is valid."""
        analysis = SocialRelationAnalysis(relations=[])
        assert len(analysis.relations) == 0

    def test_default_sentiment(self):
        """Test default overall_sentiment is neutral."""
        analysis = SocialRelationAnalysis(relations=[])
        assert analysis.overall_sentiment == "neutral"

    def test_max_five_relations(self):
        """Test relations are capped at 5."""
        relations = [
            RelationChange(relation_type=f"type_{i}", value_delta=0.01)
            for i in range(7)
        ]
        analysis = SocialRelationAnalysis(relations=relations)
        assert len(analysis.relations) == 5
