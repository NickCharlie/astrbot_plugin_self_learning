"""网络层访问守卫（local_guard）与 Hub loopback 限制的单元测试。"""

import sys
from pathlib import Path
from unittest.mock import patch

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from self_learning_EterU.webui.middleware import local_guard
from self_learning_EterU.webui.middleware.local_guard import (
    LocalAccessGuardMiddleware,
    _is_loopback_ip,
    _origin_matches_host,
    _reject_message,
)


def _scope(
    *,
    client=("127.0.0.1", 5000),
    host="127.0.0.1:7833",
    origin=None,
    path="/api/metrics",
):
    headers = [(b"host", host.encode("latin-1"))]
    if origin:
        headers.append((b"origin", origin.encode("latin-1")))
    return {
        "type": "http",
        "path": path,
        "headers": headers,
        "client": client,
    }


def _password(disabled=False):
    return patch.object(
        local_guard,
        "_password_enabled",
        return_value=not disabled,
    )


def test_is_loopback_ip_variants():
    assert _is_loopback_ip("127.0.0.1")
    assert _is_loopback_ip("127.8.8.8")
    assert _is_loopback_ip("::1")
    assert _is_loopback_ip("[::1]")
    assert _is_loopback_ip("::ffff:127.0.0.1")
    assert _is_loopback_ip("0:0:0:0:0:0:0:1")
    assert _is_loopback_ip("localhost")
    assert not _is_loopback_ip("192.168.1.5")
    assert not _is_loopback_ip("203.0.113.9")
    assert not _is_loopback_ip("")
    assert not _is_loopback_ip("example.com")
    # 以 127. 开头的攻击者域名不是 IP 字面量，不得放行（DNS 重绑定变体）
    assert not _is_loopback_ip("127.evil.com")
    assert not _is_loopback_ip("localhost.evil.com")


def test_origin_matches_host():
    assert _origin_matches_host("http://127.0.0.1:7833", "127.0.0.1:7833")
    assert _origin_matches_host("http://localhost:7833", "127.0.0.1:7833")
    assert _origin_matches_host("http://192.168.1.5:7833", "192.168.1.5:7833")
    assert not _origin_matches_host("http://evil.example:7833", "127.0.0.1:7833")
    assert not _origin_matches_host("http://127.0.0.1:9999", "127.0.0.1:7833")
    # 无端口（默认端口）双方均视为同源
    assert _origin_matches_host("https://panel.example.com", "panel.example.com")
    assert not _origin_matches_host("https://other.example.com", "panel.example.com")
    # 一方显式端口、另一方协议默认端口：不等即跨源
    assert not _origin_matches_host("https://panel.example.com", "panel.example.com:8443")
    assert _origin_matches_host("https://panel.example.com:443", "panel.example.com")


def test_rebinding_hostname_with_127_prefix_rejected():
    # Host 为 127.evil.com：socket 来自本机，但主机名不是本机 → 拦截
    with _password(disabled=True):
        message = _reject_message(_scope(host="127.evil.com:7833"))
    assert message and "DNS 重绑定" in message


def test_passwordless_rejects_lan_client():
    with _password(disabled=True):
        message = _reject_message(_scope(client=("192.168.1.7", 5000)))
    assert message and "免密模式仅允许本机访问" in message


def test_passwordless_rejects_non_loopback_host_header():
    # DNS 重绑定：socket 来自本机，但 Host 是攻击者域名
    with _password(disabled=True):
        message = _reject_message(_scope(host="evil.example:7833"))
    assert message and "DNS 重绑定" in message


def test_passwordless_allows_loopback():
    with _password(disabled=True):
        assert _reject_message(_scope()) is None
        assert _reject_message(_scope(host="localhost:7833")) is None


def test_password_mode_allows_lan_client():
    with _password():
        assert _reject_message(_scope(client=("192.168.1.7", 5000))) is None


def test_cross_origin_rejected_in_all_modes():
    # 免密模式：本机客户端发起的跨站请求 → 同源检查拦截
    with _password(disabled=True):
        message = _reject_message(_scope(origin="http://evil.example:7833"))
    assert message and "跨站" in message
    # 密码模式：局域网客户端发起的跨站请求 → 同源检查拦截
    with _password():
        message = _reject_message(
            _scope(origin="http://evil.example:7833", client=("192.168.1.7", 5000))
        )
    assert message and "跨站" in message


def test_same_origin_and_server_side_requests_pass():
    with _password():
        assert _reject_message(_scope(origin="http://127.0.0.1:7833")) is None
    # 服务器间调用不携带 Origin
    with _password(disabled=True):
        assert _reject_message(_scope()) is None


async def test_guard_middleware_returns_403_json():
    async def dummy_app(scope, receive, send):
        raise AssertionError("guard must short-circuit before app")

    seen = {}

    async def send(message):
        seen.setdefault("status", message.get("status"))
        seen.setdefault("body", b"")
        if message.get("body") is not None:
            seen["body"] = message["body"]

    with _password(disabled=True):
        await LocalAccessGuardMiddleware(dummy_app)(
            _scope(client=("203.0.113.5", 5000)),
            lambda *args: None,
            send,
        )
    assert seen["status"] == 403
    assert "免密模式仅允许本机访问" in seen["body"].decode("utf-8")


async def test_guard_middleware_passes_non_http_and_clean_requests():
    forwarded = []

    async def dummy_app(scope, receive, send):
        forwarded.append(scope["type"])

    with _password(disabled=True):
        await LocalAccessGuardMiddleware(dummy_app)(
            {"type": "lifespan"}, lambda *args: None, lambda *args: None
        )
        await LocalAccessGuardMiddleware(dummy_app)(
            _scope(), lambda *args: None, lambda *args: None
        )
    assert forwarded == ["lifespan", "http"]


def test_hub_api_rejects_remote_caller_without_api_auth():
    """enable_api_auth=False 时 Hub API 仅允许本机直连（socket 与 Host 均本机）。"""
    from types import SimpleNamespace
    from unittest.mock import patch as mock_patch

    from self_learning_EterU.webui.middleware import hub_aspects
    from self_learning_EterU.webui.middleware.hub_aspects import require_hub_api_key

    @require_hub_api_key
    async def handler():
        return "ok"

    container = SimpleNamespace(
        plugin_config=SimpleNamespace(enable_api_auth=False, api_key="")
    )

    async def call():
        return await handler()

    import asyncio

    cases = [
        # 局域网直连
        (SimpleNamespace(scope={"client": ("203.0.113.5", 5000)}, headers={"Host": "203.0.113.5:7833"}), 403),
        # 同机反代转发远程请求：socket 是 loopback，但 Host 是外部域名
        (SimpleNamespace(scope={"client": ("127.0.0.1", 5000)}, headers={"Host": "panel.example.com"}), 403),
        # 本机直连
        (SimpleNamespace(scope={"client": ("127.0.0.1", 5000)}, headers={"Host": "127.0.0.1:7833"}), 200),
    ]
    for fake_request, expected in cases:
        with mock_patch.object(hub_aspects, "get_container", lambda: container), \
                mock_patch.object(hub_aspects, "request", fake_request):
            result = asyncio.run(call())
        if expected == 403:
            assert isinstance(result, tuple) and result[1] == 403
        else:
            assert result == "ok"
