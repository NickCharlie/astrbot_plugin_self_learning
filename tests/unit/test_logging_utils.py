import io
import importlib

from utils.logging_utils import TRACE_LEVEL, get_astrbot_logger, normalize_log_level

_logging = importlib.import_module("logging")


def test_child_logger_records_include_astrbot_formatter_fields():
    test_logger = get_astrbot_logger("self_learning.config")
    stream = io.StringIO()
    handler = _logging.StreamHandler(stream)
    handler.setFormatter(
        _logging.Formatter(
            "%(plugin_tag)s %(short_levelname)s %(astrbot_version_tag)s "
            "%(source_file)s:%(source_line)d %(message)s"
        )
    )
    test_logger.addHandler(handler)
    original_propagate = test_logger.propagate

    try:
        test_logger.propagate = False
        test_logger.info("config loaded")
    finally:
        test_logger.removeHandler(handler)
        test_logger.propagate = original_propagate

    output = stream.getvalue()
    assert "[Plug]" in output
    assert "INFO" in output
    assert "config loaded" in output


def test_trace_log_level_is_supported():
    test_logger = get_astrbot_logger("self_learning.trace_test")
    stream = io.StringIO()
    handler = _logging.StreamHandler(stream)
    handler.setFormatter(_logging.Formatter("%(levelname)s %(is_trace)s %(message)s"))
    test_logger.addHandler(handler)
    original_level = test_logger.level
    original_propagate = test_logger.propagate

    try:
        test_logger.propagate = False
        test_logger.setLevel(TRACE_LEVEL)
        test_logger.trace("trace message")
    finally:
        test_logger.removeHandler(handler)
        test_logger.setLevel(original_level)
        test_logger.propagate = original_propagate

    output = stream.getvalue()
    assert normalize_log_level("trace") == "trace"
    assert "TRACE True trace message" in output
