import io
import logging

from utils.logging_utils import get_astrbot_logger


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
