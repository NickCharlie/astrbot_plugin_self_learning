"""Async-aware instrumentation helpers.

Provides thin wrappers around ``prometheus_async`` for timing async
functions and context-manager-style inline timing blocks. All helpers
default to the plugin's dedicated ``REGISTRY``.

The ``monitored`` decorator additionally provides function-level
performance tracking (latency histogram, call counter, error counter
keyed by fully-qualified function name) that is gated by a
``debug_mode`` flag -- zero overhead when monitoring is disabled.

Usage::

    from services.monitoring.instrumentation import timed, timer, count_errors, monitored

    # Always-on metric recording
    @timed(LLM_REQUEST_DURATION, labels={"provider_type": "filter", "model": "gpt-4"})
    async def call_llm(...):
        ...

    # Function-level monitoring (only active in debug_mode)
    @monitored
    async def process_message(self, ...):
        ...

    # Context-manager style
    async with timer(LLM_REQUEST_DURATION, labels={"provider_type": "refine", "model": "gpt-4"}):
        result = await slow_operation()
"""

import asyncio
import contextlib
import contextvars
import functools
import time
from typing import Any, Callable, Dict, Optional

try:
    from ...utils.logging_utils import TRACE_LEVEL, get_astrbot_logger
except ImportError:
    from utils.logging_utils import TRACE_LEVEL, get_astrbot_logger

from .metrics import REGISTRY, has_prometheus

# Re-import Counter / Histogram from our own metrics module (which provides
# stubs when prometheus_client is unavailable).
from .metrics import Counter, Histogram

# prometheus-async is an optional runtime dependency.  When missing the
# decorators fall back to a lightweight pure-Python implementation so
# that the module can still be imported and used without it.
try:
    from prometheus_async.aio import count_exceptions as _prom_count_exceptions
    from prometheus_async.aio import time as _prom_time

    _HAS_PROM_ASYNC = True
except ImportError:
    _HAS_PROM_ASYNC = False


def _resolve_metric(metric: Any, labels: Optional[Dict[str, str]] = None) -> Any:
    """Apply label values to a metric if labels are provided."""
    if labels:
        return metric.labels(**labels)
    return metric


# -- Decorator: @timed -----------------------------------------------------

def timed(
    histogram: Histogram,
    labels: Optional[Dict[str, str]] = None,
):
    """Decorator that records async function execution time to a Histogram.

    When ``prometheus-async`` is installed the decorator delegates to
    ``prometheus_async.aio.time`` for accurate async timing. Otherwise a
    lightweight fallback based on ``time.perf_counter`` is used.

    Args:
        histogram: A ``prometheus_client.Histogram`` instance.
        labels: Optional dict of label key-value pairs.
    """
    resolved = _resolve_metric(histogram, labels)

    def decorator(func):
        if _HAS_PROM_ASYNC:
            return _prom_time(resolved)(func)

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            finally:
                resolved.observe(time.perf_counter() - start)

        return wrapper

    return decorator


# -- Context manager: timer ------------------------------------------------

@contextlib.asynccontextmanager
async def timer(
    histogram: Histogram,
    labels: Optional[Dict[str, str]] = None,
):
    """Async context manager that records duration to a Histogram.

    Args:
        histogram: A ``prometheus_client.Histogram`` instance.
        labels: Optional dict of label key-value pairs.
    """
    resolved = _resolve_metric(histogram, labels)
    start = time.perf_counter()
    try:
        yield
    finally:
        resolved.observe(time.perf_counter() - start)


# -- Decorator: @count_errors ----------------------------------------------

def count_errors(
    counter: Counter,
    labels: Optional[Dict[str, str]] = None,
):
    """Decorator that increments a Counter when an exception is raised.

    When ``prometheus-async`` is installed the decorator delegates to
    ``prometheus_async.aio.count_exceptions``. Otherwise a lightweight
    fallback is used.

    Args:
        counter: A ``prometheus_client.Counter`` instance.
        labels: Optional dict of label key-value pairs.
    """
    resolved = _resolve_metric(counter, labels)

    def decorator(func):
        if _HAS_PROM_ASYNC:
            return _prom_count_exceptions(resolved)(func)

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception:
                resolved.inc()
                raise

        return wrapper

    return decorator


# -- Debug-mode gated function monitoring ------------------------------------

_debug_mode: bool = False
_trace_enabled: bool = False
_trace_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "self_learning_trace_id",
    default=None,
)
_trace_depth_var: contextvars.ContextVar[int] = contextvars.ContextVar(
    "self_learning_trace_depth",
    default=0,
)
_trace_seq_var: contextvars.ContextVar[int] = contextvars.ContextVar(
    "self_learning_trace_seq",
    default=0,
)
_trace_logger = get_astrbot_logger("monitoring.trace")


def set_debug_mode(enabled: bool) -> None:
    """Enable or disable function-level performance monitoring.

    When disabled (default), the ``@monitored`` decorator is a no-op and
    adds zero overhead.  Call this once during plugin initialisation with
    ``config.debug_mode``.
    """
    global _debug_mode
    _debug_mode = enabled
    _trace_logger.info("Function-level monitoring %s", "enabled" if enabled else "disabled")


def is_debug_mode() -> bool:
    """Return whether function-level monitoring is active."""
    return _debug_mode


def set_trace_enabled(enabled: bool) -> None:
    """Enable or disable function entry/exit trace logs."""
    global _trace_enabled
    _trace_enabled = bool(enabled)
    _trace_logger.setLevel(TRACE_LEVEL if _trace_enabled else 0)
    _trace_logger.info("Function-level trace logging %s", "enabled" if enabled else "disabled")


def is_trace_enabled() -> bool:
    """Return whether function trace logging is active."""
    return _trace_enabled


def reset_trace_context() -> None:
    """Clear the current async context trace id and nesting depth."""
    _trace_id_var.set(None)
    _trace_depth_var.set(0)
    _trace_seq_var.set(0)


def _next_trace_id() -> str:
    sequence = _trace_seq_var.get() + 1
    _trace_seq_var.set(sequence)
    return f"{int(time.time() * 1000):x}-{sequence:x}"


def _start_trace_call(fqn: str) -> tuple[float, contextvars.Token, contextvars.Token, str, int]:
    trace_id = _trace_id_var.get()
    if trace_id is None:
        trace_id = _next_trace_id()
        trace_token = _trace_id_var.set(trace_id)
    else:
        trace_token = _trace_id_var.set(trace_id)

    depth = _trace_depth_var.get()
    depth_token = _trace_depth_var.set(depth + 1)
    _trace_logger.trace(
        "[trace:%s] %s> %s",
        trace_id,
        "  " * depth,
        fqn,
    )
    return time.perf_counter(), trace_token, depth_token, trace_id, depth


def _finish_trace_call(
    fqn: str,
    start: float,
    trace_token: contextvars.Token,
    depth_token: contextvars.Token,
    trace_id: str,
    depth: int,
    *,
    exc: Optional[BaseException] = None,
) -> None:
    elapsed_ms = (time.perf_counter() - start) * 1000
    if exc is None:
        _trace_logger.trace(
            "[trace:%s] %s< %s %.2fms",
            trace_id,
            "  " * depth,
            fqn,
            elapsed_ms,
        )
    else:
        _trace_logger.trace(
            "[trace:%s] %s! %s %.2fms error=%s",
            trace_id,
            "  " * depth,
            fqn,
            elapsed_ms,
            exc.__class__.__name__,
        )
    _trace_depth_var.reset(depth_token)
    _trace_id_var.reset(trace_token)


# Lazy per-function metric caches keyed by fully-qualified function name.
_func_histograms: Dict[str, Histogram] = {}
_func_counters: Dict[str, "Counter"] = {}
_func_error_counters: Dict[str, "Counter"] = {}


def _func_fqn(func: Callable) -> str:
    """Return the fully-qualified name of *func*."""
    module = getattr(func, "__module__", None) or ""
    qualname = getattr(func, "__qualname__", None) or func.__name__
    return f"{module}.{qualname}"


def _get_func_histogram(name: str) -> Histogram:
    if name not in _func_histograms:
        safe_name = name.replace(".", "_").replace("<", "").replace(">", "")
        _func_histograms[name] = Histogram(
            f"func_{safe_name}_duration_seconds",
            f"Latency of {name}",
            registry=REGISTRY,
        )
    return _func_histograms[name]


def _get_func_counter(name: str) -> "Counter":
    if name not in _func_counters:
        safe_name = name.replace(".", "_").replace("<", "").replace(">", "")
        _func_counters[name] = Counter(
            f"func_{safe_name}_calls_total",
            f"Call count of {name}",
            registry=REGISTRY,
        )
    return _func_counters[name]


def _get_func_error_counter(name: str) -> "Counter":
    if name not in _func_error_counters:
        safe_name = name.replace(".", "_").replace("<", "").replace(">", "")
        _func_error_counters[name] = Counter(
            f"func_{safe_name}_errors_total",
            f"Error count of {name}",
            registry=REGISTRY,
        )
    return _func_error_counters[name]


def monitored(func: Callable) -> Callable:
    """Decorator for function-level performance monitoring.

    Records latency (histogram), call count (counter), and error count
    (counter) for the decorated function.  All three metrics are keyed by
    the function's fully-qualified name.

    **Zero overhead when disabled**: when ``debug_mode`` is ``False``
    (the default), the original function is called directly without any
    timing or counting logic.

    Supports both sync and async functions.

    Usage::

        @monitored
        async def some_important_function(self, ...):
            ...

        @monitored
        def sync_helper(...):
            ...
    """
    fqn = _func_fqn(func)

    if asyncio.iscoroutinefunction(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            if not _debug_mode and not _trace_enabled:
                return await func(*args, **kwargs)

            histogram = counter = error_counter = None
            if _debug_mode:
                histogram = _get_func_histogram(fqn)
                counter = _get_func_counter(fqn)
                error_counter = _get_func_error_counter(fqn)

                counter.inc()
            start = time.perf_counter()
            trace_state = None
            if _trace_enabled:
                trace_state = _start_trace_call(fqn)
            try:
                return await func(*args, **kwargs)
            except Exception as exc:
                if error_counter is not None:
                    error_counter.inc()
                if trace_state is not None:
                    _finish_trace_call(fqn, *trace_state, exc=exc)
                    trace_state = None
                raise
            finally:
                if histogram is not None:
                    histogram.observe(time.perf_counter() - start)
                if trace_state is not None:
                    _finish_trace_call(fqn, *trace_state)

        return async_wrapper

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        if not _debug_mode and not _trace_enabled:
            return func(*args, **kwargs)

        histogram = counter = error_counter = None
        if _debug_mode:
            histogram = _get_func_histogram(fqn)
            counter = _get_func_counter(fqn)
            error_counter = _get_func_error_counter(fqn)

            counter.inc()
        start = time.perf_counter()
        trace_state = None
        if _trace_enabled:
            trace_state = _start_trace_call(fqn)
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            if error_counter is not None:
                error_counter.inc()
            if trace_state is not None:
                _finish_trace_call(fqn, *trace_state, exc=exc)
                trace_state = None
            raise
        finally:
            if histogram is not None:
                histogram.observe(time.perf_counter() - start)
            if trace_state is not None:
                _finish_trace_call(fqn, *trace_state)

    return sync_wrapper
