"""
Tiered learning trigger mechanism.

Replaces the legacy fixed-threshold trigger system with a two-tier
architecture that separates lightweight per-message operations (Tier 1)
from LLM-heavy batch operations (Tier 2).

Tier 1 (per message, sub-millisecond to sub-second each):
    * Statistical jargon filter update (in-memory counters)
    * Message buffer append for deferred ingestion (no I/O)
    * Exemplar candidate screening (embedding + DB insert)

Tier 2 (batch, LLM-gated, cooldown-protected):
    * Knowledge graph ingestion via LightRAG (batched LLM entity extraction)
    * Memory ingestion via Mem0 (batched LLM fact extraction)
    * Jargon meaning inference on top statistical candidates
    * Social sentiment batch analysis
    * Expression pattern learning

Design notes:
    - Each Tier 1 operation is executed with individual error isolation
      so one failure cannot block the others.
    - Tier 2 triggers are gated by *configurable* message-count
      thresholds **and** wall-clock cooldowns; either condition can be
      satisfied independently to handle both high-traffic and low-traffic
      groups.
    - An optional event-driven fast-path lets Tier 2 fire early when the
      statistical filter detects a strong new-term signal.
    - All state is per-group; no cross-group interference.
    - Thread-safe for single-event-loop asyncio usage.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple

from astrbot.api import logger

from ...core.interfaces import MessageData


# Type aliases

# Internal alias: once registered, a callback is always a real callable.
_AsyncCallable = Callable[..., Coroutine[Any, Any, Any]]

# Public-facing alias: accepts None from callers to allow conditional wiring.
_OptionalAsyncCallback = Optional[_AsyncCallable]


# Per-group trigger state

@dataclass
class _GroupTriggerState:
    """Mutable per-group state tracked by the trigger."""

    # Counters
    message_count: int = 0
    total_processed: int = 0

    # Per-operation last-execution timestamps (keyed by operation name).
    last_op_times: Dict[str, float] = field(default_factory=dict)

    # Accumulated interactions for social sentiment batch.
    pending_interactions: List[Dict[str, str]] = field(default_factory=list)

    # Consecutive Tier 1 failure count for observability.
    consecutive_tier1_errors: int = 0


# Tier 2 trigger policy

@dataclass(frozen=True)
class BatchTriggerPolicy:
    """Configurable policy for gating Tier 2 batch operations.

    A Tier 2 operation is triggered when **either** the message-count
    threshold **or** the maximum time interval is reached, whichever
    comes first. This ensures both high-traffic groups (hit count
    quickly) and low-traffic groups (hit time limit) get timely
    processing.
    """

    message_threshold: int = 15
    cooldown_seconds: float = 120.0


# Result container

@dataclass
class TriggerResult:
    """Outcome of a ``process_message`` invocation."""

    tier1_ok: bool = True
    tier1_details: Dict[str, bool] = field(default_factory=dict)
    tier2_triggered: bool = False
    tier2_details: Dict[str, bool] = field(default_factory=dict)


# Main class

class TieredLearningTrigger:
    """Orchestrates tiered learning operations for incoming messages.

    Usage::

        trigger = TieredLearningTrigger()
        trigger.register_tier1("memory", memory_manager.add_memory_from_message)
        trigger.register_tier2("jargon", jargon_batch_callback, policy)
        result = await trigger.process_message(message, group_id)
    """

    def __init__(self) -> None:
        # Per-group mutable state.
        self._states: Dict[str, _GroupTriggerState] = {}

        # Registered operations.
        # Tier 1: name -> async callable(message, group_id)
        self._tier1_ops: Dict[str, _AsyncCallable] = {}
        # Tier 2: name -> (async callable(group_id), policy)
        self._tier2_ops: Dict[str, Tuple[_AsyncCallable, BatchTriggerPolicy]] = {}

    # Registration

    def register_tier1(
        self,
        name: str,
        callback: _OptionalAsyncCallback,
    ) -> None:
        """Register a per-message Tier 1 operation.

        The callback signature must be::

            async def callback(message: MessageData, group_id: str) -> None

        Callbacks are executed concurrently for every incoming message.
        Errors in one callback do not affect others.
        """
        if callback is None:
            return
        if not asyncio.iscoroutinefunction(callback):
            raise TypeError(
                f"Tier 1 callback '{name}' must be an async function, "
                f"got {type(callback)!r}"
            )
        self._tier1_ops[name] = callback
        logger.debug(f"[TieredTrigger] Registered Tier 1 op: {name}")

    def register_tier2(
        self,
        name: str,
        callback: _OptionalAsyncCallback,
        policy: Optional[BatchTriggerPolicy] = None,
    ) -> None:
        """Register a batch Tier 2 operation.

        The callback signature must be::

            async def callback(group_id: str) -> None

        The operation fires when the group's message count exceeds
        ``policy.message_threshold`` **or** ``policy.cooldown_seconds``
        have elapsed since the last execution, whichever comes first.
        """
        if callback is None:
            return
        if not asyncio.iscoroutinefunction(callback):
            raise TypeError(
                f"Tier 2 callback '{name}' must be an async function, "
                f"got {type(callback)!r}"
            )
        self._tier2_ops[name] = (
            callback,
            policy or BatchTriggerPolicy(),
        )
        logger.debug(f"[TieredTrigger] Registered Tier 2 op: {name}")

    # Main entry point

    async def process_message(
        self,
        message: MessageData,
        group_id: str,
    ) -> TriggerResult:
        """Process an incoming message through all registered tiers.

        Returns a :class:`TriggerResult` summarising what was executed.
        """
        state = self._get_state(group_id)
        result = TriggerResult()

        # ---- Tier 1: always execute (concurrent, error-isolated) ----
        result.tier1_details = await self._execute_tier1(
            message, group_id, state
        )
        # tier1_ok is True only when at least one op ran and all succeeded.
        result.tier1_ok = (
            bool(result.tier1_details)
            and all(result.tier1_details.values())
        )

        # Update counters.
        state.message_count += 1
        state.total_processed += 1

        # ---- Tier 2: check each registered batch operation ----
        # Each operation has its own counter/cooldown gate. When any
        # operation fires, the shared message counter resets so that
        # all Tier 2 ops start their count window fresh. The time-based
        # fallback ensures low-traffic groups still trigger eventually.
        now = time.time()
        for name, (callback, policy) in self._tier2_ops.items():
            last_time = state.last_op_times.get(name, 0.0)
            count_ok = state.message_count >= policy.message_threshold
            time_ok = (now - last_time) >= policy.cooldown_seconds

            if count_ok or time_ok:
                ok = await self._execute_tier2_op(
                    name, callback, group_id, state
                )
                result.tier2_details[name] = ok
                result.tier2_triggered = True

        if result.tier2_triggered:
            state.message_count = 0

        return result

    # Event-driven fast-path

    async def force_tier2(
        self,
        name: str,
        group_id: str,
    ) -> bool:
        """Force-trigger a specific Tier 2 operation outside the normal
        schedule (e.g. when the statistical filter detects a strong
        new-term signal).

        Returns ``True`` if the operation executed successfully.
        """
        if name not in self._tier2_ops:
            return False

        state = self._get_state(group_id)
        callback, _ = self._tier2_ops[name]
        return await self._execute_tier2_op(name, callback, group_id, state)

    # Inspection / statistics

    def get_group_stats(self, group_id: str) -> Dict[str, Any]:
        """Return trigger statistics for a group."""
        state = self._states.get(group_id)
        if not state:
            return {"active": False}

        return {
            "active": True,
            "message_count": state.message_count,
            "total_processed": state.total_processed,
            "last_op_times": dict(state.last_op_times),
            "pending_interactions": len(state.pending_interactions),
            "consecutive_tier1_errors": state.consecutive_tier1_errors,
        }

    # Internals

    def _get_state(self, group_id: str) -> _GroupTriggerState:
        if group_id not in self._states:
            # Initialise last_op_times to "now" so that Tier 2 operations
            # do not fire on the very first message of a new group.
            state = _GroupTriggerState()
            now = time.time()
            for name in self._tier2_ops:
                state.last_op_times[name] = now
            self._states[group_id] = state
        return self._states[group_id]

    async def _execute_tier1(
        self,
        message: MessageData,
        group_id: str,
        state: _GroupTriggerState,
    ) -> Dict[str, bool]:
        """Run all Tier 1 operations concurrently with error isolation."""
        if not self._tier1_ops:
            return {}

        names = list(self._tier1_ops.keys())
        callbacks = list(self._tier1_ops.values())

        async def _safe_run(op_name: str, cb: _AsyncCallable) -> bool:
            try:
                await cb(message, group_id)
                return True
            except Exception as exc:
                logger.debug(
                    f"[TieredTrigger] Tier 1 op '{op_name}' failed: {exc}"
                )
                return False

        results = await asyncio.gather(
            *(_safe_run(n, c) for n, c in zip(names, callbacks)),
            return_exceptions=False,
        )

        details = dict(zip(names, results))

        # Track consecutive failures for observability.
        if not all(results):
            state.consecutive_tier1_errors += 1
        else:
            state.consecutive_tier1_errors = 0

        return details

    async def _execute_tier2_op(
        self,
        name: str,
        callback: _AsyncCallable,
        group_id: str,
        state: _GroupTriggerState,
    ) -> bool:
        """Execute a single Tier 2 operation with error handling."""
        try:
            await callback(group_id)
            state.last_op_times[name] = time.time()
            logger.debug(
                f"[TieredTrigger] Tier 2 op '{name}' completed for "
                f"group {group_id}"
            )
            return True
        except Exception as exc:
            logger.warning(
                f"[TieredTrigger] Tier 2 op '{name}' failed for "
                f"group {group_id}: {exc}"
            )
            return False
