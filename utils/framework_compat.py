"""Framework API compatibility helpers."""

import inspect
from typing import Any


async def get_using_provider_compat(context: Any):
    """Resolve the current chat provider across AstrBot versions.

    AstrBot v4.27 deprecates the sync ``Context.get_using_provider()`` in
    favour of ``get_using_provider_async()`` (the sync version emits a
    runtime DeprecationWarning). Older versions only ship the sync one, so
    prefer the async accessor when it is a real coroutine function and fall
    back otherwise.

    Args:
        context: The plugin ``Context`` (or any compatible object).

    Returns:
        The active chat provider, or ``None`` when unavailable.
    """
    async_getter = getattr(context, "get_using_provider_async", None)
    if inspect.iscoroutinefunction(async_getter):
        return await async_getter()
    return context.get_using_provider()
