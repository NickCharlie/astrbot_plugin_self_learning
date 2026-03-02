"""
Unit tests for TieredLearningTrigger

Tests the two-tier learning trigger mechanism:
- Tier 1 registration and execution (per-message, concurrent)
- Tier 2 registration and gated execution (batch, cooldown/threshold)
- Error isolation between Tier 1 operations
- BatchTriggerPolicy configuration
- force_tier2 fast-path triggering
- Per-group state tracking and statistics
"""
import asyncio
import time
import pytest
from unittest.mock import AsyncMock, patch

from core.interfaces import MessageData
from services.quality.tiered_learning_trigger import (
    TieredLearningTrigger,
    BatchTriggerPolicy,
    TriggerResult,
    _GroupTriggerState,
)


def _make_message(text: str = "test message", group_id: str = "g1") -> MessageData:
    """Helper to create a test MessageData instance."""
    return MessageData(
        sender_id="user1",
        sender_name="TestUser",
        message=text,
        group_id=group_id,
        timestamp=time.time(),
        platform="test",
    )


@pytest.mark.unit
@pytest.mark.quality
class TestTieredLearningTriggerRegistration:
    """Test callback registration for both tiers."""

    def test_register_tier1_success(self):
        """Test registering a valid Tier 1 async callback."""
        trigger = TieredLearningTrigger()

        async def callback(msg, gid):
            pass

        trigger.register_tier1("test_op", callback)
        assert "test_op" in trigger._tier1_ops

    def test_register_tier1_none_callback_ignored(self):
        """Test registering None callback is silently ignored."""
        trigger = TieredLearningTrigger()
        trigger.register_tier1("test_op", None)
        assert "test_op" not in trigger._tier1_ops

    def test_register_tier1_sync_callback_raises(self):
        """Test registering a sync callback raises TypeError."""
        trigger = TieredLearningTrigger()

        def sync_callback(msg, gid):
            pass

        with pytest.raises(TypeError, match="must be an async function"):
            trigger.register_tier1("bad_op", sync_callback)

    def test_register_tier2_success(self):
        """Test registering a valid Tier 2 async callback."""
        trigger = TieredLearningTrigger()

        async def callback(gid):
            pass

        trigger.register_tier2("batch_op", callback)
        assert "batch_op" in trigger._tier2_ops

    def test_register_tier2_with_custom_policy(self):
        """Test registering Tier 2 with custom policy."""
        trigger = TieredLearningTrigger()
        policy = BatchTriggerPolicy(message_threshold=50, cooldown_seconds=300.0)

        async def callback(gid):
            pass

        trigger.register_tier2("batch_op", callback, policy=policy)

        stored_callback, stored_policy = trigger._tier2_ops["batch_op"]
        assert stored_policy.message_threshold == 50
        assert stored_policy.cooldown_seconds == 300.0

    def test_register_tier2_default_policy(self):
        """Test registering Tier 2 uses default policy when none specified."""
        trigger = TieredLearningTrigger()

        async def callback(gid):
            pass

        trigger.register_tier2("batch_op", callback)

        _, stored_policy = trigger._tier2_ops["batch_op"]
        assert stored_policy.message_threshold == 15
        assert stored_policy.cooldown_seconds == 120.0

    def test_register_tier2_sync_callback_raises(self):
        """Test registering a sync Tier 2 callback raises TypeError."""
        trigger = TieredLearningTrigger()

        def sync_callback(gid):
            pass

        with pytest.raises(TypeError, match="must be an async function"):
            trigger.register_tier2("bad_op", sync_callback)


@pytest.mark.unit
@pytest.mark.quality
class TestTier1Execution:
    """Test Tier 1 per-message execution."""

    @pytest.mark.asyncio
    async def test_tier1_executes_for_every_message(self):
        """Test Tier 1 callbacks execute for every incoming message."""
        trigger = TieredLearningTrigger()
        call_count = 0

        async def tier1_callback(msg, gid):
            nonlocal call_count
            call_count += 1

        trigger.register_tier1("counter", tier1_callback)

        for _ in range(5):
            await trigger.process_message(_make_message(), "g1")

        assert call_count == 5

    @pytest.mark.asyncio
    async def test_tier1_concurrent_execution(self):
        """Test multiple Tier 1 callbacks run concurrently."""
        trigger = TieredLearningTrigger()
        execution_order = []

        async def op_a(msg, gid):
            execution_order.append("a")

        async def op_b(msg, gid):
            execution_order.append("b")

        trigger.register_tier1("op_a", op_a)
        trigger.register_tier1("op_b", op_b)

        await trigger.process_message(_make_message(), "g1")

        assert "a" in execution_order
        assert "b" in execution_order

    @pytest.mark.asyncio
    async def test_tier1_error_isolation(self):
        """Test one Tier 1 failure does not affect others."""
        trigger = TieredLearningTrigger()
        healthy_called = False

        async def failing_op(msg, gid):
            raise RuntimeError("Tier 1 failure")

        async def healthy_op(msg, gid):
            nonlocal healthy_called
            healthy_called = True

        trigger.register_tier1("failing", failing_op)
        trigger.register_tier1("healthy", healthy_op)

        result = await trigger.process_message(_make_message(), "g1")

        assert healthy_called is True
        assert result.tier1_details["failing"] is False
        assert result.tier1_details["healthy"] is True
        assert result.tier1_ok is False

    @pytest.mark.asyncio
    async def test_tier1_all_success(self):
        """Test tier1_ok is True when all operations succeed."""
        trigger = TieredLearningTrigger()

        async def ok_op(msg, gid):
            pass

        trigger.register_tier1("op1", ok_op)
        trigger.register_tier1("op2", ok_op)

        result = await trigger.process_message(_make_message(), "g1")

        assert result.tier1_ok is True
        assert all(result.tier1_details.values())


@pytest.mark.unit
@pytest.mark.quality
class TestTier2Execution:
    """Test Tier 2 batch execution with gating."""

    @pytest.mark.asyncio
    async def test_tier2_triggers_on_message_threshold(self):
        """Test Tier 2 fires when message count reaches threshold."""
        trigger = TieredLearningTrigger()
        tier2_called = False

        async def tier1_noop(msg, gid):
            pass

        async def tier2_callback(gid):
            nonlocal tier2_called
            tier2_called = True

        trigger.register_tier1("noop", tier1_noop)
        trigger.register_tier2(
            "batch", tier2_callback,
            policy=BatchTriggerPolicy(message_threshold=3, cooldown_seconds=9999),
        )

        for _ in range(3):
            result = await trigger.process_message(_make_message(), "g1")

        assert tier2_called is True

    @pytest.mark.asyncio
    async def test_tier2_does_not_trigger_below_threshold(self):
        """Test Tier 2 does not fire below message threshold."""
        trigger = TieredLearningTrigger()
        tier2_called = False

        async def tier1_noop(msg, gid):
            pass

        async def tier2_callback(gid):
            nonlocal tier2_called
            tier2_called = True

        trigger.register_tier1("noop", tier1_noop)
        trigger.register_tier2(
            "batch", tier2_callback,
            policy=BatchTriggerPolicy(message_threshold=100, cooldown_seconds=9999),
        )

        # Process only 2 messages
        for _ in range(2):
            await trigger.process_message(_make_message(), "g1")

        assert tier2_called is False

    @pytest.mark.asyncio
    async def test_tier2_triggers_on_cooldown_expiry(self):
        """Test Tier 2 fires when cooldown expires even below threshold."""
        trigger = TieredLearningTrigger()
        tier2_called = False

        async def tier1_noop(msg, gid):
            pass

        async def tier2_callback(gid):
            nonlocal tier2_called
            tier2_called = True

        trigger.register_tier1("noop", tier1_noop)
        trigger.register_tier2(
            "batch", tier2_callback,
            policy=BatchTriggerPolicy(message_threshold=9999, cooldown_seconds=0.0),
        )

        # First message initializes state; cooldown=0 means always ready
        # But _get_state initializes last_op_times to now, so the first
        # process_message won't trigger. We need to manually adjust.
        state = trigger._get_state("g1")
        state.last_op_times["batch"] = 0.0  # Long ago

        result = await trigger.process_message(_make_message(), "g1")

        assert tier2_called is True
        assert result.tier2_triggered is True

    @pytest.mark.asyncio
    async def test_tier2_resets_counter_after_trigger(self):
        """Test message counter resets after Tier 2 trigger."""
        trigger = TieredLearningTrigger()

        async def tier1_noop(msg, gid):
            pass

        async def tier2_callback(gid):
            pass

        trigger.register_tier1("noop", tier1_noop)
        trigger.register_tier2(
            "batch", tier2_callback,
            policy=BatchTriggerPolicy(message_threshold=2, cooldown_seconds=9999),
        )

        await trigger.process_message(_make_message(), "g1")
        await trigger.process_message(_make_message(), "g1")

        state = trigger._states["g1"]
        assert state.message_count == 0  # Reset after trigger

    @pytest.mark.asyncio
    async def test_tier2_error_handling(self):
        """Test Tier 2 failure is captured in result."""
        trigger = TieredLearningTrigger()

        async def tier1_noop(msg, gid):
            pass

        async def failing_tier2(gid):
            raise RuntimeError("Batch failure")

        trigger.register_tier1("noop", tier1_noop)
        trigger.register_tier2(
            "batch", failing_tier2,
            policy=BatchTriggerPolicy(message_threshold=1, cooldown_seconds=9999),
        )

        result = await trigger.process_message(_make_message(), "g1")

        assert result.tier2_triggered is True
        assert result.tier2_details["batch"] is False


@pytest.mark.unit
@pytest.mark.quality
class TestForceTier2:
    """Test force_tier2 fast-path triggering."""

    @pytest.mark.asyncio
    async def test_force_tier2_success(self):
        """Test force triggering a registered Tier 2 operation."""
        trigger = TieredLearningTrigger()
        called_with_group = None

        async def tier2_callback(gid):
            nonlocal called_with_group
            called_with_group = gid

        trigger.register_tier2("batch", tier2_callback)

        result = await trigger.force_tier2("batch", "g1")

        assert result is True
        assert called_with_group == "g1"

    @pytest.mark.asyncio
    async def test_force_tier2_unregistered_operation(self):
        """Test forcing an unregistered operation returns False."""
        trigger = TieredLearningTrigger()

        result = await trigger.force_tier2("nonexistent", "g1")
        assert result is False

    @pytest.mark.asyncio
    async def test_force_tier2_failure(self):
        """Test force_tier2 returns False on callback failure."""
        trigger = TieredLearningTrigger()

        async def failing_callback(gid):
            raise RuntimeError("force failure")

        trigger.register_tier2("batch", failing_callback)

        result = await trigger.force_tier2("batch", "g1")
        assert result is False


@pytest.mark.unit
@pytest.mark.quality
class TestGroupStats:
    """Test per-group statistics."""

    def test_stats_for_unknown_group(self):
        """Test stats for unknown group returns inactive."""
        trigger = TieredLearningTrigger()

        stats = trigger.get_group_stats("unknown_group")
        assert stats == {"active": False}

    @pytest.mark.asyncio
    async def test_stats_after_processing(self):
        """Test stats reflect processing state."""
        trigger = TieredLearningTrigger()

        async def tier1_noop(msg, gid):
            pass

        trigger.register_tier1("noop", tier1_noop)

        await trigger.process_message(_make_message(), "g1")
        await trigger.process_message(_make_message(), "g1")

        stats = trigger.get_group_stats("g1")
        assert stats["active"] is True
        assert stats["total_processed"] == 2
        assert stats["message_count"] == 2  # No Tier 2 to reset

    @pytest.mark.asyncio
    async def test_stats_consecutive_tier1_errors(self):
        """Test consecutive Tier 1 error tracking."""
        trigger = TieredLearningTrigger()

        async def failing_op(msg, gid):
            raise RuntimeError("fail")

        trigger.register_tier1("failing", failing_op)

        await trigger.process_message(_make_message(), "g1")
        await trigger.process_message(_make_message(), "g1")

        stats = trigger.get_group_stats("g1")
        assert stats["consecutive_tier1_errors"] == 2


@pytest.mark.unit
@pytest.mark.quality
class TestBatchTriggerPolicy:
    """Test BatchTriggerPolicy dataclass."""

    def test_default_values(self):
        """Test default policy values."""
        policy = BatchTriggerPolicy()
        assert policy.message_threshold == 15
        assert policy.cooldown_seconds == 120.0

    def test_custom_values(self):
        """Test custom policy values."""
        policy = BatchTriggerPolicy(message_threshold=50, cooldown_seconds=600.0)
        assert policy.message_threshold == 50
        assert policy.cooldown_seconds == 600.0

    def test_policy_is_frozen(self):
        """Test policy dataclass is immutable."""
        policy = BatchTriggerPolicy()
        with pytest.raises(AttributeError):
            policy.message_threshold = 99
