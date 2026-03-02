"""
Unit tests for custom exception hierarchy

Tests the exception class inheritance chain and instantiation:
- Base exception class
- All derived exception types
- Exception message propagation
- isinstance checks for polymorphic handling
"""
import pytest

from exceptions import (
    SelfLearningError,
    ConfigurationError,
    MessageCollectionError,
    StyleAnalysisError,
    PersonaUpdateError,
    ModelAccessError,
    DataStorageError,
    LearningSchedulerError,
    LearningError,
    ServiceError,
    ResponseError,
    BackupError,
    ExpressionLearningError,
    MemoryGraphError,
    TimeDecayError,
    MessageAnalysisError,
    KnowledgeGraphError,
)


@pytest.mark.unit
class TestExceptionHierarchy:
    """Test exception class hierarchy and inheritance."""

    def test_base_exception_is_exception(self):
        """Test SelfLearningError is a proper Exception subclass."""
        assert issubclass(SelfLearningError, Exception)

    @pytest.mark.parametrize("exc_class", [
        ConfigurationError,
        MessageCollectionError,
        StyleAnalysisError,
        PersonaUpdateError,
        ModelAccessError,
        DataStorageError,
        LearningSchedulerError,
        LearningError,
        ServiceError,
        ResponseError,
        BackupError,
        ExpressionLearningError,
        MemoryGraphError,
        TimeDecayError,
        MessageAnalysisError,
        KnowledgeGraphError,
    ])
    def test_subclass_inherits_from_base(self, exc_class):
        """Test all custom exceptions inherit from SelfLearningError."""
        assert issubclass(exc_class, SelfLearningError)

    @pytest.mark.parametrize("exc_class", [
        ConfigurationError,
        MessageCollectionError,
        StyleAnalysisError,
        PersonaUpdateError,
        ModelAccessError,
        DataStorageError,
        LearningSchedulerError,
        LearningError,
        ServiceError,
        ResponseError,
        BackupError,
        ExpressionLearningError,
        MemoryGraphError,
        TimeDecayError,
        MessageAnalysisError,
        KnowledgeGraphError,
    ])
    def test_exception_instantiation(self, exc_class):
        """Test all exception classes can be instantiated with a message."""
        msg = f"Test error message for {exc_class.__name__}"
        exc = exc_class(msg)

        assert str(exc) == msg

    def test_catch_specific_exception(self):
        """Test catching a specific exception type."""
        with pytest.raises(ConfigurationError):
            raise ConfigurationError("invalid config")

    def test_catch_base_exception_for_derived(self):
        """Test catching base exception catches derived types."""
        with pytest.raises(SelfLearningError):
            raise DataStorageError("storage failure")

    def test_exception_with_no_message(self):
        """Test exception can be raised without a message."""
        exc = SelfLearningError()
        assert str(exc) == ""

    def test_exception_chain(self):
        """Test exception chaining with __cause__."""
        original = ValueError("original cause")
        try:
            raise ConfigurationError("config error") from original
        except ConfigurationError as e:
            assert e.__cause__ is original
            assert str(e.__cause__) == "original cause"
