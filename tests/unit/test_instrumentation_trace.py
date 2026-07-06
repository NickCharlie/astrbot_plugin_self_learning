import io
import importlib

import pytest

from self_learning_EterU.services.monitoring.instrumentation import (
    is_trace_enabled,
    monitored,
    reset_trace_context,
    set_debug_mode,
    set_trace_enabled,
)
from self_learning_EterU.utils.logging_utils import TRACE_LEVEL, get_astrbot_logger

_logging = importlib.import_module("logging")


@pytest.mark.asyncio
async def test_monitored_emits_trace_logs_without_debug_mode():
    set_debug_mode(False)
    set_trace_enabled(True)
    reset_trace_context()
    test_logger = get_astrbot_logger("monitoring.trace")
    stream = io.StringIO()
    handler = _logging.StreamHandler(stream)
    handler.setFormatter(_logging.Formatter("%(levelname)s %(message)s"))
    test_logger.addHandler(handler)
    original_propagate = test_logger.propagate

    @monitored
    async def sample_call():
        return "ok"

    try:
        test_logger.propagate = False
        assert await sample_call() == "ok"
    finally:
        test_logger.removeHandler(handler)
        test_logger.propagate = original_propagate
        set_trace_enabled(False)
        reset_trace_context()

    output = stream.getvalue()
    assert is_trace_enabled() is False
    assert "TRACE" in output
    assert "> " in output and "sample_call" in output
    assert "< " in output and "sample_call" in output
