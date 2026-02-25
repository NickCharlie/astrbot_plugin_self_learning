"""
Unit tests for core interfaces module

Tests the core data classes, enums, and interface definitions:
- MessageData dataclass construction and defaults
- AnalysisResult dataclass construction and defaults
- PersonaUpdateRecord dataclass construction and defaults
- ServiceLifecycle enum values
- LearningStrategyType enum values
- AnalysisType enum values
"""
import pytest
from unittest.mock import MagicMock

from core.interfaces import (
    ServiceLifecycle,
    MessageData,
    AnalysisResult,
    PersonaUpdateRecord,
    LearningStrategyType,
    AnalysisType,
)


@pytest.mark.unit
@pytest.mark.core
class TestMessageData:
    """Test MessageData dataclass."""

    def test_required_fields(self):
        """Test creating MessageData with all required fields."""
        msg = MessageData(
            sender_id="user_001",
            sender_name="Alice",
            message="Hello world",
            group_id="group_001",
            timestamp=1700000000.0,
            platform="qq",
        )

        assert msg.sender_id == "user_001"
        assert msg.sender_name == "Alice"
        assert msg.message == "Hello world"
        assert msg.group_id == "group_001"
        assert msg.timestamp == 1700000000.0
        assert msg.platform == "qq"

    def test_optional_fields_default_none(self):
        """Test optional fields default to None."""
        msg = MessageData(
            sender_id="user_001",
            sender_name="Alice",
            message="Hello",
            group_id="group_001",
            timestamp=1700000000.0,
            platform="qq",
        )

        assert msg.message_id is None
        assert msg.reply_to is None

    def test_optional_fields_set_explicitly(self):
        """Test optional fields can be set explicitly."""
        msg = MessageData(
            sender_id="user_001",
            sender_name="Alice",
            message="Hello",
            group_id="group_001",
            timestamp=1700000000.0,
            platform="qq",
            message_id="msg_123",
            reply_to="msg_100",
        )

        assert msg.message_id == "msg_123"
        assert msg.reply_to == "msg_100"


@pytest.mark.unit
@pytest.mark.core
class TestAnalysisResult:
    """Test AnalysisResult dataclass."""

    def test_required_fields(self):
        """Test creating AnalysisResult with required fields."""
        result = AnalysisResult(
            success=True,
            confidence=0.85,
            data={"key": "value"},
        )

        assert result.success is True
        assert result.confidence == 0.85
        assert result.data == {"key": "value"}

    def test_default_values(self):
        """Test AnalysisResult default values."""
        result = AnalysisResult(
            success=True,
            confidence=0.9,
            data={},
        )

        assert result.timestamp == 0.0
        assert result.error is None
        assert result.consistency_score is None

    def test_with_error(self):
        """Test AnalysisResult with error information."""
        result = AnalysisResult(
            success=False,
            confidence=0.0,
            data={},
            error="Analysis failed due to insufficient data",
        )

        assert result.success is False
        assert result.error == "Analysis failed due to insufficient data"

    def test_with_consistency_score(self):
        """Test AnalysisResult with consistency score."""
        result = AnalysisResult(
            success=True,
            confidence=0.8,
            data={"metrics": [1, 2, 3]},
            consistency_score=0.75,
        )

        assert result.consistency_score == 0.75


@pytest.mark.unit
@pytest.mark.core
class TestPersonaUpdateRecord:
    """Test PersonaUpdateRecord dataclass."""

    def test_required_fields(self):
        """Test creating PersonaUpdateRecord with required fields."""
        record = PersonaUpdateRecord(
            timestamp=1700000000.0,
            group_id="group_001",
            update_type="prompt_update",
            original_content="Original prompt",
            new_content="New prompt",
            reason="Style analysis update",
        )

        assert record.timestamp == 1700000000.0
        assert record.group_id == "group_001"
        assert record.update_type == "prompt_update"
        assert record.original_content == "Original prompt"
        assert record.new_content == "New prompt"
        assert record.reason == "Style analysis update"

    def test_default_values(self):
        """Test PersonaUpdateRecord default values."""
        record = PersonaUpdateRecord(
            timestamp=0.0,
            group_id="g1",
            update_type="test",
            original_content="",
            new_content="",
            reason="",
        )

        assert record.confidence_score == 0.5
        assert record.id is None
        assert record.status == "pending"
        assert record.reviewer_comment is None
        assert record.review_time is None

    def test_approved_record(self):
        """Test PersonaUpdateRecord with approved status."""
        record = PersonaUpdateRecord(
            timestamp=1700000000.0,
            group_id="g1",
            update_type="prompt_update",
            original_content="old",
            new_content="new",
            reason="update",
            id=42,
            status="approved",
            reviewer_comment="Looks good",
            review_time=1700001000.0,
        )

        assert record.id == 42
        assert record.status == "approved"
        assert record.reviewer_comment == "Looks good"
        assert record.review_time == 1700001000.0


@pytest.mark.unit
@pytest.mark.core
class TestServiceLifecycleEnum:
    """Test ServiceLifecycle enum."""

    def test_all_states_exist(self):
        """Test all expected lifecycle states exist."""
        assert ServiceLifecycle.CREATED.value == "created"
        assert ServiceLifecycle.INITIALIZING.value == "initializing"
        assert ServiceLifecycle.RUNNING.value == "running"
        assert ServiceLifecycle.STOPPING.value == "stopping"
        assert ServiceLifecycle.STOPPED.value == "stopped"
        assert ServiceLifecycle.ERROR.value == "error"

    def test_enum_count(self):
        """Test the total number of lifecycle states."""
        assert len(ServiceLifecycle) == 6


@pytest.mark.unit
@pytest.mark.core
class TestLearningStrategyTypeEnum:
    """Test LearningStrategyType enum."""

    def test_all_strategies_exist(self):
        """Test all expected strategy types exist."""
        assert LearningStrategyType.PROGRESSIVE.value == "progressive"
        assert LearningStrategyType.BATCH.value == "batch"
        assert LearningStrategyType.REALTIME.value == "realtime"
        assert LearningStrategyType.HYBRID.value == "hybrid"

    def test_enum_count(self):
        """Test the total number of strategy types."""
        assert len(LearningStrategyType) == 4


@pytest.mark.unit
@pytest.mark.core
class TestAnalysisTypeEnum:
    """Test AnalysisType enum."""

    def test_all_types_exist(self):
        """Test all expected analysis types exist."""
        assert AnalysisType.STYLE.value == "style"
        assert AnalysisType.SENTIMENT.value == "sentiment"
        assert AnalysisType.TOPIC.value == "topic"
        assert AnalysisType.BEHAVIOR.value == "behavior"
        assert AnalysisType.QUALITY.value == "quality"

    def test_enum_count(self):
        """Test the total number of analysis types."""
        assert len(AnalysisType) == 5
