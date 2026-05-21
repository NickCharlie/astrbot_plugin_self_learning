"""Unit tests for message target filtering defaults."""
import sys
from pathlib import Path

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from self_learning_EterU.core.factory import QQFilter


@pytest.mark.unit
def test_blank_target_rows_collect_all_non_blacklisted_messages():
    qq_filter = QQFilter(["", "   "], blacklist=["group_blocked"])

    assert qq_filter.should_collect_message("user-a", "group-a") is True
    assert qq_filter.should_collect_message("user-a", "blocked") is False


@pytest.mark.unit
def test_full_learning_marker_collects_all_non_blacklisted_messages():
    qq_filter = QQFilter(["all", "user-only"], blacklist=["blocked-user"])

    assert qq_filter.should_collect_message("other-user", "group-a") is True
    assert qq_filter.should_collect_message("blocked-user", "group-a") is False


@pytest.mark.unit
def test_non_empty_target_list_remains_whitelist():
    qq_filter = QQFilter(["target-user", "group_target"], blacklist=[])

    assert qq_filter.should_collect_message("target-user", "group-a") is True
    assert qq_filter.should_collect_message("other-user", "target") is True
    assert qq_filter.should_collect_message("other-user", "group-a") is False
