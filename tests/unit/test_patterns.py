"""
Unit tests for core design patterns module

Tests the design pattern implementations:
- AsyncServiceBase lifecycle management
- LearningContextBuilder (builder pattern)
- StrategyFactory (factory + strategy patterns)
- ServiceRegistry (singleton + registry pattern)
- ProgressiveLearningStrategy execution
- BatchLearningStrategy execution
"""
import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime

from core.interfaces import (
    ServiceLifecycle,
    LearningStrategyType,
    MessageData,
)
from core.patterns import (
    AsyncServiceBase,
    LearningContext,
    LearningContextBuilder,
    ProgressiveLearningStrategy,
    BatchLearningStrategy,
    StrategyFactory,
    ServiceRegistry,
    SingletonABCMeta,
)


@pytest.mark.unit
@pytest.mark.core
class TestAsyncServiceBase:
    """Test AsyncServiceBase lifecycle management."""

    def _create_service(self, name: str = "test_service") -> AsyncServiceBase:
        """Helper to create a concrete service instance."""
        return AsyncServiceBase(name)

    def test_initial_status_is_created(self):
        """Test service starts in CREATED state."""
        service = self._create_service()
        assert service.status == ServiceLifecycle.CREATED

    @pytest.mark.asyncio
    async def test_start_transitions_to_running(self):
        """Test starting service transitions to RUNNING."""
        service = self._create_service()

        result = await service.start()

        assert result is True
        assert service.status == ServiceLifecycle.RUNNING

    @pytest.mark.asyncio
    async def test_start_already_running(self):
        """Test starting already running service returns True."""
        service = self._create_service()
        await service.start()

        result = await service.start()

        assert result is True
        assert service.status == ServiceLifecycle.RUNNING

    @pytest.mark.asyncio
    async def test_stop_transitions_to_stopped(self):
        """Test stopping service transitions to STOPPED."""
        service = self._create_service()
        await service.start()

        result = await service.stop()

        assert result is True
        assert service.status == ServiceLifecycle.STOPPED

    @pytest.mark.asyncio
    async def test_stop_already_stopped(self):
        """Test stopping already stopped service returns True."""
        service = self._create_service()
        await service.start()
        await service.stop()

        result = await service.stop()

        assert result is True
        assert service.status == ServiceLifecycle.STOPPED

    @pytest.mark.asyncio
    async def test_restart(self):
        """Test restarting service."""
        service = self._create_service()
        await service.start()

        result = await service.restart()

        assert result is True
        assert service.status == ServiceLifecycle.RUNNING

    @pytest.mark.asyncio
    async def test_is_running(self):
        """Test is_running check."""
        service = self._create_service()

        assert await service.is_running() is False

        await service.start()
        assert await service.is_running() is True

        await service.stop()
        assert await service.is_running() is False

    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test health check reflects running state."""
        service = self._create_service()

        assert await service.health_check() is False

        await service.start()
        assert await service.health_check() is True

    @pytest.mark.asyncio
    async def test_start_failure_transitions_to_error(self):
        """Test service transitions to ERROR on start failure."""
        service = self._create_service()
        service._do_start = AsyncMock(side_effect=RuntimeError("init failed"))

        result = await service.start()

        assert result is False
        assert service.status == ServiceLifecycle.ERROR

    @pytest.mark.asyncio
    async def test_stop_failure_transitions_to_error(self):
        """Test service transitions to ERROR on stop failure."""
        service = self._create_service()
        await service.start()
        service._do_stop = AsyncMock(side_effect=RuntimeError("cleanup failed"))

        result = await service.stop()

        assert result is False
        assert service.status == ServiceLifecycle.ERROR


@pytest.mark.unit
@pytest.mark.core
class TestLearningContextBuilder:
    """Test LearningContextBuilder (builder pattern)."""

    def test_build_default_context(self):
        """Test building context with default values."""
        context = LearningContextBuilder().build()

        assert isinstance(context, LearningContext)
        assert context.messages == []
        assert context.strategy_type == LearningStrategyType.PROGRESSIVE
        assert context.quality_threshold == 0.7
        assert context.max_iterations == 3
        assert context.metadata == {}

    def test_builder_chain(self):
        """Test fluent builder chaining."""
        messages = [
            MessageData(
                sender_id="u1", sender_name="Alice",
                message="Hello", group_id="g1",
                timestamp=1.0, platform="qq",
            )
        ]

        context = (
            LearningContextBuilder()
            .with_messages(messages)
            .with_strategy(LearningStrategyType.BATCH)
            .with_quality_threshold(0.9)
            .with_max_iterations(5)
            .with_metadata("source", "test")
            .build()
        )

        assert len(context.messages) == 1
        assert context.strategy_type == LearningStrategyType.BATCH
        assert context.quality_threshold == 0.9
        assert context.max_iterations == 5
        assert context.metadata["source"] == "test"


@pytest.mark.unit
@pytest.mark.core
class TestStrategyFactory:
    """Test StrategyFactory (factory + strategy patterns)."""

    def test_create_progressive_strategy(self):
        """Test creating progressive learning strategy."""
        config = {"batch_size": 25, "min_messages": 10}
        strategy = StrategyFactory.create_strategy(
            LearningStrategyType.PROGRESSIVE, config
        )

        assert isinstance(strategy, ProgressiveLearningStrategy)
        assert strategy.config == config

    def test_create_batch_strategy(self):
        """Test creating batch learning strategy."""
        config = {"batch_size": 100}
        strategy = StrategyFactory.create_strategy(
            LearningStrategyType.BATCH, config
        )

        assert isinstance(strategy, BatchLearningStrategy)

    def test_create_unsupported_strategy_raises(self):
        """Test creating unsupported strategy raises ValueError."""
        with pytest.raises(ValueError, match="不支持的策略类型"):
            StrategyFactory.create_strategy(
                LearningStrategyType.REALTIME, {}
            )

    def test_register_custom_strategy(self):
        """Test registering a custom strategy type."""

        class CustomStrategy:
            def __init__(self, config):
                self.config = config

        StrategyFactory.register_strategy(
            LearningStrategyType.REALTIME, CustomStrategy
        )
        strategy = StrategyFactory.create_strategy(
            LearningStrategyType.REALTIME, {"custom": True}
        )

        assert isinstance(strategy, CustomStrategy)

        # Cleanup: remove custom strategy to avoid test pollution
        del StrategyFactory._strategies[LearningStrategyType.REALTIME]


@pytest.mark.unit
@pytest.mark.core
class TestProgressiveLearningStrategy:
    """Test ProgressiveLearningStrategy execution logic."""

    def _make_messages(self, count: int):
        """Helper to create test messages."""
        return [
            MessageData(
                sender_id=f"u{i}", sender_name=f"User{i}",
                message=f"Message {i}", group_id="g1",
                timestamp=float(i), platform="qq",
            )
            for i in range(count)
        ]

    @pytest.mark.asyncio
    async def test_execute_learning_cycle_success(self):
        """Test progressive learning cycle executes successfully."""
        strategy = ProgressiveLearningStrategy({"batch_size": 10})
        messages = self._make_messages(25)

        result = await strategy.execute_learning_cycle(messages)

        assert result.success is True
        assert result.confidence > 0
        assert result.data["total_processed"] == 25
        assert result.data["batch_count"] == 3

    @pytest.mark.asyncio
    async def test_execute_learning_cycle_empty_messages(self):
        """Test progressive learning cycle with empty messages."""
        strategy = ProgressiveLearningStrategy({"batch_size": 10})

        result = await strategy.execute_learning_cycle([])

        assert result.success is True
        assert result.data["total_processed"] == 0

    @pytest.mark.asyncio
    async def test_should_learn_sufficient_messages(self):
        """Test should_learn returns True when conditions are met."""
        strategy = ProgressiveLearningStrategy({
            "min_messages": 5,
            "min_interval_hours": 0,
        })
        context = {
            "message_count": 10,
            "last_learning_time": 0,
        }

        result = await strategy.should_learn(context)
        assert result is True

    @pytest.mark.asyncio
    async def test_should_learn_insufficient_messages(self):
        """Test should_learn returns False with insufficient messages."""
        strategy = ProgressiveLearningStrategy({
            "min_messages": 20,
            "min_interval_hours": 0,
        })
        context = {
            "message_count": 5,
            "last_learning_time": 0,
        }

        result = await strategy.should_learn(context)
        assert result is False


@pytest.mark.unit
@pytest.mark.core
class TestBatchLearningStrategy:
    """Test BatchLearningStrategy execution logic."""

    def _make_messages(self, count: int):
        """Helper to create test messages."""
        return [
            MessageData(
                sender_id=f"u{i}", sender_name=f"User{i}",
                message=f"Message {i}", group_id="g1",
                timestamp=float(i), platform="qq",
            )
            for i in range(count)
        ]

    @pytest.mark.asyncio
    async def test_execute_learning_cycle_success(self):
        """Test batch learning cycle executes successfully."""
        strategy = BatchLearningStrategy({"batch_size": 100})
        messages = self._make_messages(50)

        result = await strategy.execute_learning_cycle(messages)

        assert result.success is True
        assert result.confidence > 0
        assert result.data["processed_count"] == 50

    @pytest.mark.asyncio
    async def test_should_learn_above_threshold(self):
        """Test should_learn returns True when batch threshold is met."""
        strategy = BatchLearningStrategy({"batch_size": 20})
        context = {"message_count": 25}

        result = await strategy.should_learn(context)
        assert result is True

    @pytest.mark.asyncio
    async def test_should_learn_below_threshold(self):
        """Test should_learn returns False below batch threshold."""
        strategy = BatchLearningStrategy({"batch_size": 100})
        context = {"message_count": 50}

        result = await strategy.should_learn(context)
        assert result is False


@pytest.mark.unit
@pytest.mark.core
class TestServiceRegistry:
    """Test ServiceRegistry (singleton + registry pattern)."""

    def _create_fresh_registry(self) -> ServiceRegistry:
        """Create a fresh registry by clearing singleton cache."""
        # Clear singleton instance to avoid test pollution
        SingletonABCMeta._instances.pop(ServiceRegistry, None)
        return ServiceRegistry(service_stop_timeout=2)

    def test_register_service(self):
        """Test registering a service."""
        registry = self._create_fresh_registry()
        service = AsyncServiceBase("test_svc")

        registry.register_service("test_svc", service)

        assert registry.get_service("test_svc") is service

    def test_get_nonexistent_service(self):
        """Test getting a nonexistent service returns None."""
        registry = self._create_fresh_registry()

        assert registry.get_service("nonexistent") is None

    def test_unregister_service(self):
        """Test unregistering a service."""
        registry = self._create_fresh_registry()
        service = AsyncServiceBase("test_svc")
        registry.register_service("test_svc", service)

        result = registry.unregister_service("test_svc")

        assert result is True
        assert registry.get_service("test_svc") is None

    def test_unregister_nonexistent_service(self):
        """Test unregistering a nonexistent service returns False."""
        registry = self._create_fresh_registry()

        result = registry.unregister_service("nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_start_all_services(self):
        """Test starting all registered services."""
        registry = self._create_fresh_registry()
        svc1 = AsyncServiceBase("svc1")
        svc2 = AsyncServiceBase("svc2")
        registry.register_service("svc1", svc1)
        registry.register_service("svc2", svc2)

        result = await registry.start_all_services()

        assert result is True
        assert svc1.status == ServiceLifecycle.RUNNING
        assert svc2.status == ServiceLifecycle.RUNNING

    @pytest.mark.asyncio
    async def test_stop_all_services(self):
        """Test stopping all registered services."""
        registry = self._create_fresh_registry()
        svc1 = AsyncServiceBase("svc1")
        svc2 = AsyncServiceBase("svc2")
        registry.register_service("svc1", svc1)
        registry.register_service("svc2", svc2)
        await registry.start_all_services()

        result = await registry.stop_all_services()

        assert result is True
        assert svc1.status == ServiceLifecycle.STOPPED
        assert svc2.status == ServiceLifecycle.STOPPED

    def test_get_service_status(self):
        """Test getting status of all registered services."""
        registry = self._create_fresh_registry()
        svc = AsyncServiceBase("svc1")
        registry.register_service("svc1", svc)

        status = registry.get_service_status()

        assert "svc1" in status
        assert status["svc1"] == "created"
