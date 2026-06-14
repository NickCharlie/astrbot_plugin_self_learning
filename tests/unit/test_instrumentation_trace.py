import io
import logging

import pytest

from self_learning_EterU.services.monitoring.instrumentation import (
    is_trace_enabled,
    monitored,
    reset_trace_context,
    set_debug_mode,
    set_trace_enabled,
)
from self_learning_EterU.utils.logging_utils import TRACE_LEVEL, get_astrbot_logger


@pytest.mark.asyncio
async def test_monitored_emits_trace_logs_without_debug_mode():
    set_debug_mode(False)
    set_trace_enabled(True)
    reset_trace_context()
    logger = get_astrbot_logger("monitoring.trace")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger.addHandler(handler)
    original_propagate = logger.propagate

    @monitored
    async def sample_call():
        return "ok"

    try:
        logger.propagate = False
        assert await sample_call() == "ok"
    finally:
        logger.removeHandler(handler)
        logger.propagate = original_propagate
        set_trace_enabled(False)
        reset_trace_context()

    output = stream.getvalue()
    assert is_trace_enabled() is False
    assert "TRACE" in output
    assert "> " in output and "sample_call" in output
    assert "< " in output and "sample_call" in output
