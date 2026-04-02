"""Text utilities for database storage safety."""

# MySQL TEXT column upper limit is 65,535 bytes.
# Use a safe margin to account for multi-byte UTF-8 characters.
_MAX_TEXT_BYTES = 60000
_TRUNCATION_MARKER = "...[truncated]"


def truncate_for_db(text: str, max_bytes: int = _MAX_TEXT_BYTES) -> str:
    """Truncate text to fit within MySQL TEXT column byte limit.

    Performs byte-level truncation to safely handle multi-byte UTF-8
    characters (e.g. CJK characters that use 3-4 bytes each). If the
    encoded text exceeds ``max_bytes``, it is truncated and a marker
    is appended.

    Args:
        text: The text to truncate.
        max_bytes: Maximum allowed byte length. Defaults to 60000.

    Returns:
        The original text if within limits, otherwise a truncated
        version with a ``...[truncated]`` suffix.
    """
    if not text:
        return text
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    marker = _TRUNCATION_MARKER.encode("utf-8")
    truncated = encoded[: max_bytes - len(marker)]
    return truncated.decode("utf-8", errors="ignore") + _TRUNCATION_MARKER
