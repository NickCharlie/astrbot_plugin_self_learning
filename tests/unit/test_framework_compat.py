"""AstrBot v4.29 plugin Pages→Views 改名的路由前缀门控测试。"""

import sys
import types
from pathlib import Path
from unittest.mock import patch

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from self_learning_EterU.utils import framework_compat


def _with_astrbot_version(version: str):
    fake = types.ModuleType("astrbot")
    fake.__version__ = version
    return patch.dict(sys.modules, {"astrbot": fake})


def test_prefix_uses_plugin_view_on_4_29_plus():
    with _with_astrbot_version("4.29.0"):
        assert framework_compat.plugin_page_hash_prefix() == "#/plugin-view"
    with _with_astrbot_version("4.30.1"):
        assert framework_compat.plugin_page_hash_prefix() == "#/plugin-view"


def test_prefix_keeps_legacy_route_before_4_29():
    with _with_astrbot_version("4.28.5"):
        assert framework_compat.plugin_page_hash_prefix() == "#/plugin-page"
    with _with_astrbot_version("4.14.0"):
        assert framework_compat.plugin_page_hash_prefix() == "#/plugin-page"


def test_prefix_falls_back_when_version_unparsable():
    with _with_astrbot_version("not-a-version"):
        assert framework_compat.plugin_page_hash_prefix() == "#/plugin-page"


def test_prefix_handles_prerelease_suffixes():
    # 预发布后缀不影响路由/目录是否存在：4.29.0rc1 已带 plugin-view 路由
    with _with_astrbot_version("4.29.0rc1"):
        assert framework_compat.plugin_page_hash_prefix() == "#/plugin-view"
        assert framework_compat.plugin_view_dir_names() == ("views", "pages")
    with _with_astrbot_version("4.28.9rc1"):
        assert framework_compat.plugin_page_hash_prefix() == "#/plugin-page"
        assert framework_compat.plugin_view_dir_names() == ("pages",)


def test_url_encodes_segments_and_uses_prefix():
    with _with_astrbot_version("4.29.0"):
        url = framework_compat.plugin_page_hash_url("astrbot_plugin_livingmemory", "dashboard")
        assert url == "#/plugin-view/astrbot_plugin_livingmemory/dashboard"
    with _with_astrbot_version("4.14.0"):
        url = framework_compat.plugin_page_hash_url("astrbot_plugin_livingmemory", "dashboard")
        assert url == "#/plugin-page/astrbot_plugin_livingmemory/dashboard"


def test_url_quotes_special_characters():
    with patch.object(
        framework_compat, "plugin_page_hash_prefix", return_value="#/plugin-view"
    ):
        url = framework_compat.plugin_page_hash_url("plugin with space", "page/1")
        assert url == "#/plugin-view/plugin%20with%20space/page%2F1"


def test_view_dir_names_follow_astrbot_version():
    with _with_astrbot_version("4.29.0"):
        assert framework_compat.plugin_view_dir_names() == ("views", "pages")
    with _with_astrbot_version("4.28.5"):
        assert framework_compat.plugin_view_dir_names() == ("pages",)
    with _with_astrbot_version("not-a-version"):
        assert framework_compat.plugin_view_dir_names() == ("pages",)
