import io
import logging

from utils.logging_utils import TRACE_LEVEL, get_astrbot_logger, normalize_log_level


def test_child_logger_records_include_astrbot_formatter_fields():
    logger = get_astrbot_logger("self_learning.config")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(
        logging.Formatter(
            "%(plugin_tag)s %(short_levelname)s %(astrbot_version_tag)s "
            "%(source_file)s:%(source_line)d %(message)s"
        )
    )
    logger.addHandler(handler)
    original_propagate = logger.propagate

    try:
        logger.propagate = False
        logger.info("config loaded")
    finally:
        logger.removeHandler(handler)
        logger.propagate = original_propagate

    output = stream.getvalue()
    assert "[Plug]" in output
    assert "INFO" in output
    assert "config loaded" in output


def test_trace_log_level_is_supported():
    logger = get_astrbot_logger("self_learning.trace_test")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s %(is_trace)s %(message)s"))
    logger.addHandler(handler)
    original_level = logger.level
    original_propagate = logger.propagate

    try:
        logger.propagate = False
        logger.setLevel(TRACE_LEVEL)
        logger.trace("trace message")
    finally:
        logger.removeHandler(handler)
        logger.setLevel(original_level)
        logger.propagate = original_propagate

    output = stream.getvalue()
    assert normalize_log_level("trace") == "trace"
    assert "TRACE True trace message" in output
