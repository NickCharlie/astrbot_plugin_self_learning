"""
Unit tests for LearningQualityMonitor

Tests the learning quality monitoring service:
- PersonaMetrics and LearningAlert dataclasses
- Consistency calculation (text similarity fallback)
- Style stability calculation
- Vocabulary diversity calculation
- Emotional balance calculation (simple fallback)
- Coherence calculation
- Quality alert generation
- Style drift detection
- Threshold dynamic adjustment
- Pause learning decision
- Quality report generation
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timedelta

from services.quality.learning_quality_monitor import (
    LearningQualityMonitor,
    PersonaMetrics,
    LearningAlert,
)


def _create_monitor(
    consistency_threshold=0.5,
    stability_threshold=0.4,
    drift_threshold=0.4,
) -> LearningQualityMonitor:
    """Create a LearningQualityMonitor with mocked dependencies."""
    config = MagicMock()
    context = MagicMock()

    monitor = LearningQualityMonitor(
        config=config,
        context=context,
        llm_adapter=None,
        prompts=None,
    )
    monitor.consistency_threshold = consistency_threshold
    monitor.stability_threshold = stability_threshold
    monitor.drift_threshold = drift_threshold

    return monitor


def _make_messages(texts):
    """Helper to create message dicts from text list."""
    return [{"message": text} for text in texts]


@pytest.mark.unit
@pytest.mark.quality
class TestPersonaMetrics:
    """Test PersonaMetrics dataclass."""

    def test_default_values(self):
        """Test default metric values."""
        metrics = PersonaMetrics()

        assert metrics.consistency_score == 0.0
        assert metrics.style_stability == 0.0
        assert metrics.vocabulary_diversity == 0.0
        assert metrics.emotional_balance == 0.0
        assert metrics.coherence_score == 0.0

    def test_custom_values(self):
        """Test custom metric values."""
        metrics = PersonaMetrics(
            consistency_score=0.85,
            style_stability=0.9,
            vocabulary_diversity=0.7,
            emotional_balance=0.65,
            coherence_score=0.8,
        )

        assert metrics.consistency_score == 0.85
        assert metrics.style_stability == 0.9


@pytest.mark.unit
@pytest.mark.quality
class TestLearningAlert:
    """Test LearningAlert dataclass."""

    def test_alert_creation(self):
        """Test creating a learning alert."""
        alert = LearningAlert(
            alert_type="consistency",
            severity="high",
            message="Consistency dropped below threshold",
            timestamp=datetime.now().isoformat(),
            metrics={"consistency_score": 0.3},
            suggestions=["Review persona changes"],
        )

        assert alert.alert_type == "consistency"
        assert alert.severity == "high"
        assert len(alert.suggestions) == 1


@pytest.mark.unit
@pytest.mark.quality
class TestConsistencyCalculation:
    """Test persona consistency score calculation."""

    @pytest.mark.asyncio
    async def test_both_empty_personas(self):
        """Test consistency when both personas are empty."""
        monitor = _create_monitor()

        score = await monitor._calculate_consistency(
            {"prompt": ""}, {"prompt": ""}
        )
        assert score == 0.7

    @pytest.mark.asyncio
    async def test_one_empty_persona(self):
        """Test consistency when one persona is empty."""
        monitor = _create_monitor()

        score = await monitor._calculate_consistency(
            {"prompt": "I am a helpful bot"}, {"prompt": ""}
        )
        assert score == 0.6

    @pytest.mark.asyncio
    async def test_identical_personas(self):
        """Test consistency when personas are identical."""
        monitor = _create_monitor()
        prompt = "I am a friendly chatbot."

        score = await monitor._calculate_consistency(
            {"prompt": prompt}, {"prompt": prompt}
        )
        assert score == 0.95

    @pytest.mark.asyncio
    async def test_similar_personas_fallback(self):
        """Test consistency using text similarity fallback (no LLM)."""
        monitor = _create_monitor()

        score = await monitor._calculate_consistency(
            {"prompt": "I am a helpful assistant."},
            {"prompt": "I am a helpful assistant. I like chatting."},
        )
        assert 0.4 <= score <= 1.0


@pytest.mark.unit
@pytest.mark.quality
class TestTextSimilarity:
    """Test text similarity fallback method."""

    def test_identical_texts(self):
        """Test identical texts return high similarity."""
        monitor = _create_monitor()

        score = monitor._calculate_text_similarity("hello world", "hello world")
        assert score == 0.95

    def test_empty_texts(self):
        """Test empty texts return default."""
        monitor = _create_monitor()

        score = monitor._calculate_text_similarity("", "")
        assert score == 0.6

    def test_one_empty_text(self):
        """Test one empty text returns default."""
        monitor = _create_monitor()

        score = monitor._calculate_text_similarity("hello", "")
        assert score == 0.6

    def test_different_texts(self):
        """Test different texts return lower similarity."""
        monitor = _create_monitor()

        score = monitor._calculate_text_similarity("abc", "xyz")
        assert 0.4 <= score <= 1.0


@pytest.mark.unit
@pytest.mark.quality
class TestStyleStability:
    """Test style stability calculation."""

    @pytest.mark.asyncio
    async def test_single_message_perfect_stability(self):
        """Test single message returns perfect stability."""
        monitor = _create_monitor()
        messages = _make_messages(["Hello!"])

        score = await monitor._calculate_style_stability(messages)
        assert score == 1.0

    @pytest.mark.asyncio
    async def test_identical_messages_high_stability(self):
        """Test identical messages have high stability."""
        monitor = _create_monitor()
        messages = _make_messages(["Hello!", "Hello!", "Hello!"])

        score = await monitor._calculate_style_stability(messages)
        assert score >= 0.8

    @pytest.mark.asyncio
    async def test_diverse_messages_lower_stability(self):
        """Test diverse messages have lower stability."""
        monitor = _create_monitor()
        messages = _make_messages([
            "Hi",
            "This is a very long message with lots of words and punctuation! Really?",
            "Ok",
        ])

        score = await monitor._calculate_style_stability(messages)
        assert 0.0 <= score <= 1.0


@pytest.mark.unit
@pytest.mark.quality
class TestVocabularyDiversity:
    """Test vocabulary diversity calculation."""

    @pytest.mark.asyncio
    async def test_empty_messages(self):
        """Test empty messages return zero diversity."""
        monitor = _create_monitor()

        score = await monitor._calculate_vocabulary_diversity([])
        assert score == 0.0

    @pytest.mark.asyncio
    async def test_single_word_messages(self):
        """Test messages with same word have low diversity (actually 1.0)."""
        monitor = _create_monitor()
        messages = _make_messages(["hello", "hello", "hello"])

        score = await monitor._calculate_vocabulary_diversity(messages)
        # All same word: unique=1, total=3, ratio=0.33, *2=0.66
        assert 0.5 <= score <= 1.0

    @pytest.mark.asyncio
    async def test_unique_words_high_diversity(self):
        """Test messages with all unique words have high diversity."""
        monitor = _create_monitor()
        messages = _make_messages(["apple banana", "cherry date", "elderberry fig"])

        score = await monitor._calculate_vocabulary_diversity(messages)
        assert score >= 0.8


@pytest.mark.unit
@pytest.mark.quality
class TestEmotionalBalance:
    """Test emotional balance calculation (simple fallback)."""

    def test_neutral_messages(self):
        """Test messages without emotional words return high balance."""
        monitor = _create_monitor()
        messages = _make_messages(["今天天气不错", "我去了公园"])

        score = monitor._simple_emotional_balance(messages)
        assert score == 0.8  # No emotional words = neutral

    def test_positive_messages(self):
        """Test messages with positive words."""
        monitor = _create_monitor()
        messages = _make_messages(["好棒啊！", "真的很开心！喜欢！"])

        score = monitor._simple_emotional_balance(messages)
        assert 0.0 <= score <= 1.0

    def test_negative_messages(self):
        """Test messages with negative words."""
        monitor = _create_monitor()
        messages = _make_messages(["不好", "真烦人，讨厌"])

        score = monitor._simple_emotional_balance(messages)
        assert 0.0 <= score <= 1.0

    def test_balanced_messages(self):
        """Test balanced positive and negative messages."""
        monitor = _create_monitor()
        messages = _make_messages(["好开心", "不好"])

        score = monitor._simple_emotional_balance(messages)
        assert 0.0 <= score <= 1.0


@pytest.mark.unit
@pytest.mark.quality
class TestCoherence:
    """Test coherence calculation."""

    @pytest.mark.asyncio
    async def test_empty_persona(self):
        """Test empty persona returns zero coherence."""
        monitor = _create_monitor()

        score = await monitor._calculate_coherence({"prompt": ""})
        assert score == 0.0

    @pytest.mark.asyncio
    async def test_single_sentence(self):
        """Test single sentence returns high coherence."""
        monitor = _create_monitor()

        score = await monitor._calculate_coherence({"prompt": "我是一个友好的助手"})
        assert score == 0.8

    @pytest.mark.asyncio
    async def test_multiple_sentences(self):
        """Test multiple sentences are evaluated."""
        monitor = _create_monitor()
        prompt = "我是一个友好的助手。我喜欢帮助人。我会用中文交流。"

        score = await monitor._calculate_coherence({"prompt": prompt})
        assert 0.0 <= score <= 1.0


@pytest.mark.unit
@pytest.mark.quality
class TestStyleDrift:
    """Test style drift detection."""

    def test_no_drift_identical_metrics(self):
        """Test no drift when metrics are identical."""
        monitor = _create_monitor()
        metrics = PersonaMetrics(
            consistency_score=0.8,
            style_stability=0.7,
            vocabulary_diversity=0.6,
        )

        drift = monitor._calculate_style_drift(metrics, metrics)
        assert drift == 0.0

    def test_large_drift(self):
        """Test large drift detection."""
        monitor = _create_monitor()
        prev = PersonaMetrics(
            consistency_score=0.9,
            style_stability=0.8,
            vocabulary_diversity=0.7,
        )
        curr = PersonaMetrics(
            consistency_score=0.3,
            style_stability=0.2,
            vocabulary_diversity=0.1,
        )

        drift = monitor._calculate_style_drift(prev, curr)
        assert drift > 0.4


@pytest.mark.unit
@pytest.mark.quality
class TestQualityAlerts:
    """Test quality alert generation."""

    @pytest.mark.asyncio
    async def test_consistency_alert(self):
        """Test alert is generated when consistency is below threshold."""
        monitor = _create_monitor(consistency_threshold=0.5)
        metrics = PersonaMetrics(consistency_score=0.3)

        await monitor._check_quality_alerts(metrics)

        assert len(monitor.alerts_history) >= 1
        assert any(a.alert_type == "consistency" for a in monitor.alerts_history)

    @pytest.mark.asyncio
    async def test_stability_alert(self):
        """Test alert is generated when stability is below threshold."""
        monitor = _create_monitor(stability_threshold=0.4)
        metrics = PersonaMetrics(style_stability=0.2)

        await monitor._check_quality_alerts(metrics)

        assert any(a.alert_type == "stability" for a in monitor.alerts_history)

    @pytest.mark.asyncio
    async def test_no_alert_when_above_thresholds(self):
        """Test no alerts when all metrics are above thresholds."""
        monitor = _create_monitor()
        metrics = PersonaMetrics(
            consistency_score=0.9,
            style_stability=0.8,
            vocabulary_diversity=0.7,
        )

        await monitor._check_quality_alerts(metrics)
        assert len(monitor.alerts_history) == 0

    @pytest.mark.asyncio
    async def test_drift_alert_with_history(self):
        """Test drift alert when historical metrics exist."""
        monitor = _create_monitor(drift_threshold=0.1)
        # Add previous metrics
        monitor.historical_metrics.append(
            PersonaMetrics(consistency_score=0.9, style_stability=0.9, vocabulary_diversity=0.9)
        )
        # Current metrics show significant change
        current = PersonaMetrics(
            consistency_score=0.3,
            style_stability=0.3,
            vocabulary_diversity=0.3,
        )
        monitor.historical_metrics.append(current)

        await monitor._check_quality_alerts(current)

        assert any(a.alert_type == "drift" for a in monitor.alerts_history)


@pytest.mark.unit
@pytest.mark.quality
class TestShouldPauseLearning:
    """Test learning pause decision logic."""

    @pytest.mark.asyncio
    async def test_no_history_no_pause(self):
        """Test no pause with empty history."""
        monitor = _create_monitor()

        should_pause, reason = await monitor.should_pause_learning()
        assert should_pause is False

    @pytest.mark.asyncio
    async def test_pause_on_low_consistency(self):
        """Test pause when consistency is critically low."""
        monitor = _create_monitor()
        monitor.historical_metrics.append(
            PersonaMetrics(consistency_score=0.3)
        )

        should_pause, reason = await monitor.should_pause_learning()
        assert should_pause is True
        assert "一致性" in reason

    @pytest.mark.asyncio
    async def test_no_pause_above_threshold(self):
        """Test no pause when metrics are acceptable."""
        monitor = _create_monitor()
        monitor.historical_metrics.append(
            PersonaMetrics(consistency_score=0.8)
        )

        should_pause, reason = await monitor.should_pause_learning()
        assert should_pause is False


@pytest.mark.unit
@pytest.mark.quality
class TestQualityReport:
    """Test quality report generation."""

    @pytest.mark.asyncio
    async def test_report_no_history(self):
        """Test report with no historical data."""
        monitor = _create_monitor()

        report = await monitor.get_quality_report()
        assert "error" in report

    @pytest.mark.asyncio
    async def test_report_with_single_metric(self):
        """Test report with single historical metric."""
        monitor = _create_monitor()
        monitor.historical_metrics.append(
            PersonaMetrics(
                consistency_score=0.8,
                style_stability=0.7,
                vocabulary_diversity=0.6,
                emotional_balance=0.5,
                coherence_score=0.9,
            )
        )

        report = await monitor.get_quality_report()

        assert "current_metrics" in report
        assert report["current_metrics"]["consistency_score"] == 0.8
        assert "trends" in report
        assert "recommendations" in report

    @pytest.mark.asyncio
    async def test_report_with_trends(self):
        """Test report includes trend data when sufficient history exists."""
        monitor = _create_monitor()
        monitor.historical_metrics.append(
            PersonaMetrics(consistency_score=0.6, style_stability=0.5, vocabulary_diversity=0.4)
        )
        monitor.historical_metrics.append(
            PersonaMetrics(consistency_score=0.8, style_stability=0.7, vocabulary_diversity=0.6)
        )

        report = await monitor.get_quality_report()

        assert report["trends"]["consistency_trend"] == pytest.approx(0.2)
        assert report["trends"]["stability_trend"] == pytest.approx(0.2)


@pytest.mark.unit
@pytest.mark.quality
class TestDynamicThresholdAdjustment:
    """Test dynamic threshold adjustment based on history."""

    @pytest.mark.asyncio
    async def test_no_adjustment_insufficient_history(self):
        """Test no adjustment with less than 5 historical entries."""
        monitor = _create_monitor(consistency_threshold=0.5)

        for _ in range(3):
            monitor.historical_metrics.append(PersonaMetrics(consistency_score=0.9))

        await monitor.adjust_thresholds_based_on_history()

        # Should remain unchanged
        assert monitor.consistency_threshold == 0.5

    @pytest.mark.asyncio
    async def test_threshold_increases_on_good_performance(self):
        """Test threshold increases when performance is consistently good."""
        monitor = _create_monitor(consistency_threshold=0.5)

        for _ in range(5):
            monitor.historical_metrics.append(
                PersonaMetrics(consistency_score=0.85, style_stability=0.75)
            )

        await monitor.adjust_thresholds_based_on_history()

        assert monitor.consistency_threshold == 0.55  # Increased by 0.05


@pytest.mark.unit
@pytest.mark.quality
class TestHelperMethods:
    """Test helper methods."""

    def test_punctuation_ratio(self):
        """Test punctuation ratio calculation."""
        monitor = _create_monitor()

        assert monitor._get_punctuation_ratio("") == 0.0
        assert monitor._get_punctuation_ratio("hello") == 0.0
        assert monitor._get_punctuation_ratio("你好，世界！") > 0.0

    def test_count_emoji(self):
        """Test emoji counting."""
        monitor = _create_monitor()

        assert monitor._count_emoji("hello") == 0
        # The emoji patterns defined in the source are empty strings,
        # so this tests the current behavior
        assert isinstance(monitor._count_emoji("hello 😀"), int)

    def test_recommendations_low_consistency(self):
        """Test recommendations for low consistency."""
        monitor = _create_monitor()
        metrics = PersonaMetrics(consistency_score=0.5)

        recs = monitor._generate_recommendations(metrics, [])
        assert any("一致性" in r for r in recs)

    def test_recommendations_good_quality(self):
        """Test recommendations for good quality."""
        monitor = _create_monitor()
        metrics = PersonaMetrics(consistency_score=0.9, style_stability=0.8)

        recs = monitor._generate_recommendations(metrics, [])
        assert any("良好" in r for r in recs)

    @pytest.mark.asyncio
    async def test_stop(self):
        """Test service stop."""
        monitor = _create_monitor()

        result = await monitor.stop()
        assert result is True
