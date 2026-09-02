"""Quart → FastAPI 兼容层。

AstrBot core 自 v4.26.0 起迁移到 FastAPI/uvicorn，独立 WebUI 随之对齐：
应用实例是真正的 FastAPI（uvicorn 承载），但既有蓝图的处理器仍以
Quart 风格编写（模块级 ``request``/``session`` 代理、``jsonify(...) , status``
元组返回）。本模块提供这两者之间的桥：

- ``Blueprint``/``Quart``：把 ``@bp.route`` 注册翻译为 FastAPI 路由，
  并把 ``(body, status)`` 元组返回归一化为 Response；
- ``request``/``session``：基于 ContextVar 的请求级代理；
- ``jsonify``/``redirect``/``url_for``/``render_template``/``send_file``/
  ``Response``：与 Quart 同名的响应助手；
- ``Quart.test_client()``：包装 starlette TestClient，保持既有集成测试
  的 ``await client.get(...)`` / ``await response.get_json()`` 用法。

后续如需彻底去掉代理语义，可逐个蓝图把处理器改为显式 FastAPI 参数注入，
本模块只为过渡期保留。
"""

from __future__ import annotations

import inspect
import json
import base64
import os
import re
import secrets
from contextvars import ContextVar
from datetime import date, datetime, timedelta
from typing import Any, Callable, Optional
from urllib.parse import parse_qsl, quote

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from itsdangerous import TimestampSigner
from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.datastructures import MutableHeaders
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import (
    FileResponse,
    HTMLResponse,
    RedirectResponse,
    Response as StarletteResponse,
)
from starlette.testclient import TestClient

__all__ = [
    "Blueprint",
    "Quart",
    "Response",
    "current_app",
    "jsonify",
    "redirect",
    "render_template",
    "request",
    "send_file",
    "session",
    "url_for",
]


# ─────────────────────────────────────────────────────────────────────
# 请求上下文
# ─────────────────────────────────────────────────────────────────────

_current_request: ContextVar[Optional[StarletteRequest]] = ContextVar(
    "sl_webui_request", default=None
)
_current_blueprint: ContextVar[str] = ContextVar("sl_webui_blueprint", default="")
_current_app: ContextVar[Optional["Quart"]] = ContextVar(
    "sl_webui_app", default=None
)


class RequestContextMiddleware:
    """把 starlette Request 存入 ContextVar，供模块级 request/session 代理使用。"""

    def __init__(self, app, quart_app: "Quart"):
        self.app = app
        self.quart_app = quart_app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = StarletteRequest(scope, receive=receive)
        token_req = _current_request.set(request)
        token_app = _current_app.set(self.quart_app)
        try:
            await self.app(scope, receive, send)
        finally:
            _current_request.reset(token_req)
            _current_app.reset(token_app)


class _ResponseHeadersMiddleware:
    """响应头中间件：no-store 缓存策略 + 基础安全响应头（可分别开关）。"""

    SECURITY_HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "SAMEORIGIN",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    }

    def __init__(
        self,
        app,
        skip_static: bool = True,
        cache_headers: bool = True,
        security_headers: bool = True,
    ):
        self.app = app
        self.skip_static = skip_static
        self.cache_headers = cache_headers
        self.security_headers = security_headers

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                path = scope.get("path", "")
                if not (self.skip_static and path.startswith("/static/")):
                    headers = MutableHeaders(scope=message)
                    if self.cache_headers:
                        headers.setdefault("Cache-Control", "no-store")
                        headers.setdefault("Pragma", "no-cache")
                        headers.setdefault("Expires", "0")
                    if self.security_headers:
                        for key, value in self.SECURITY_HEADERS.items():
                            headers.setdefault(key, value)
            await send(message)

        await self.app(scope, receive, send_wrapper)


# ─────────────────────────────────────────────────────────────────────
# request / session 代理
# ─────────────────────────────────────────────────────────────────────


class ArgsProxy:
    """Query string 代理，语义对齐 Werkzeug MultiDict.get(key, default, type)。"""

    def __init__(self, request: StarletteRequest):
        query_string = request.scope.get("query_string", b"")
        if isinstance(query_string, bytes):
            query_string = query_string.decode("latin-1")
        self._pairs = parse_qsl(query_string, keep_blank_values=True)

    def get(self, key: str, default: Any = None, type: Callable = None) -> Any:
        for item_key, item_value in self._pairs:
            if item_key != key:
                continue
            if type is None:
                return item_value
            try:
                return type(item_value)
            except (TypeError, ValueError):
                return default
        return default

    def getlist(self, key: str) -> list:
        return [value for item_key, value in self._pairs if item_key == key]

    def to_dict(self) -> dict:
        result: dict = {}
        for key, value in self._pairs:
            result.setdefault(key, value)
        return result

    def keys(self):
        return dict(self.to_dict()).keys()

    def __contains__(self, key: str) -> bool:
        return any(item_key == key for item_key, _ in self._pairs)


class SessionProxy:
    """Session 代理，后端为 SessionMiddleware 写入的 scope['session']。"""

    @property
    def _session(self) -> dict:
        request = _current_request.get()
        if request is None:
            raise RuntimeError("session 仅在请求上下文中可用")
        return request.scope.setdefault("session", {})

    def get(self, key: str, default: Any = None) -> Any:
        return self._session.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self._session[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._session[key] = value

    def __delitem__(self, key: str) -> None:
        del self._session[key]

    def __contains__(self, key: str) -> bool:
        return key in self._session

    def pop(self, key: str, *args) -> Any:
        return self._session.pop(key, *args)

    def setdefault(self, key: str, default: Any = None) -> Any:
        return self._session.setdefault(key, default)

    def clear(self) -> None:
        self._session.clear()

    @property
    def permanent(self) -> bool:
        # 会话有效期由 SessionMiddleware 的 max_age 统一控制。
        return False

    @permanent.setter
    def permanent(self, value: bool) -> None:
        return None


class RequestProxy:
    """模块级 ``request`` 代理（Quart 语义 → starlette Request）。"""

    @property
    def _request(self) -> StarletteRequest:
        request = _current_request.get()
        if request is None:
            raise RuntimeError("request 仅在请求上下文中可用")
        return request

    @property
    def args(self) -> ArgsProxy:
        return ArgsProxy(self._request)

    @property
    def method(self) -> str:
        return self._request.method

    @property
    def path(self) -> str:
        return self._request.url.path

    @property
    def url(self) -> str:
        return str(self._request.url)

    @property
    def url_root(self) -> str:
        return str(self._request.base_url)

    @property
    def headers(self):
        return self._request.headers

    @property
    def remote_addr(self):
        client = self._request.client
        return client.host if client else None

    @property
    def is_json(self) -> bool:
        content_type = self._request.headers.get("content-type", "")
        return content_type.split(";", 1)[0].strip() == "application/json"

    @property
    def client(self):
        return self._request.client

    async def get_json(self, silent: bool = False, force: bool = False):
        request = self._request
        body = await request.body()
        if not body:
            return None
        try:
            return json.loads(body)
        except (ValueError, UnicodeDecodeError):
            if silent:
                return None
            # from None 切断异常链，避免原始解析错误堆栈流向客户端
            from starlette.exceptions import HTTPException

            raise HTTPException(
                status_code=400, detail="Failed to decode JSON body"
            ) from None


class _CurrentAppProxy:
    """模块级 ``current_app`` 代理。"""

    @property
    def config(self) -> dict:
        app = _current_app.get()
        if app is None:
            raise RuntimeError("current_app 仅在请求上下文中可用")
        return app.config

    @property
    def secret_key(self):
        app = _current_app.get()
        return app.secret_key if app else None


request = RequestProxy()
session = SessionProxy()
current_app = _CurrentAppProxy()


# ─────────────────────────────────────────────────────────────────────
# 响应助手
# ─────────────────────────────────────────────────────────────────────


def _json_default(value: Any):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, set):
        return sorted(value, key=repr)
    return str(value)


class WebUIJSONResponse(JSONResponse):
    """JSONResponse：宽容序列化（datetime/NaN），非 ASCII 直接输出。"""

    def render(self, content: Any) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=True,
            default=_json_default,
            separators=(",", ":"),
        ).encode("utf-8")


def jsonify(data: Any, **kwargs) -> WebUIJSONResponse:
    return WebUIJSONResponse(data, **kwargs)


class Response(StarletteResponse):
    """Response 兼容 Quart 的 ``mimetype`` 参数。"""

    def __init__(
        self,
        content: Any = None,
        status_code: int = 200,
        headers: Optional[dict] = None,
        mimetype: Optional[str] = None,
        content_type: Optional[str] = None,
        media_type: Optional[str] = None,
    ) -> None:
        super().__init__(
            content=content,
            status_code=status_code,
            headers=headers,
            media_type=mimetype or content_type or media_type,
        )


def redirect(location: str, code: int = 302) -> RedirectResponse:
    return RedirectResponse(url=location, status_code=code)


# ─────────────────────────────────────────────────────────────────────
# 路由转换
# ─────────────────────────────────────────────────────────────────────

_RULE_PARAM = re.compile(r"<([^>]+)>")


def _convert_rule(rule: str) -> tuple:
    """把 Quart 规则 ``<int:name>`` 转成 FastAPI ``{name}``，返回 (path, 转换器表)。"""
    converters: dict = {}

    def _replace(match: "re.Match") -> str:
        inner = match.group(1)
        converter, _, name = inner.partition(":")
        if not name:
            name, converter = converter, "string"
        converters[name] = int if converter == "int" else str
        return "{" + name + "}"

    return _RULE_PARAM.sub(_replace, rule), converters


def _normalize_result(result: Any):
    """归一化 Quart 风格的 ``(body, status)`` 元组返回。"""
    if isinstance(result, tuple) and len(result) == 2:
        body, status = result
        if isinstance(status, int) or (
            isinstance(status, str) and status.isdigit()
        ):
            status = int(status)
            if isinstance(body, StarletteResponse):
                body.status_code = status
                return body
            return WebUIJSONResponse(body, status_code=status)
    return result


class _RouteRegistry:
    """Blueprint/Quart 共用的路由登记表。"""

    def __init__(self, url_prefix: str = ""):
        self.url_prefix = (url_prefix or "").rstrip("/")
        self._routes: list = []

    def route(self, rule: str, methods: Optional[list] = None, **options):
        def decorator(handler: Callable) -> Callable:
            self._routes.append(
                (rule, list(methods or ("GET",)), handler, options)
            )
            return handler

        return decorator

    def apply_to(self, app: FastAPI, bp_name: str) -> None:
        for rule, methods, handler, options in self._routes:
            path, converters = _convert_rule(rule)
            full_path = self.url_prefix + path
            endpoint = _make_endpoint(bp_name, handler, converters)
            app.add_api_route(
                full_path,
                endpoint,
                methods=methods,
                name=f"{bp_name}.{handler.__name__}",
                include_in_schema=bool(options.get("include_in_schema", True)),
            )
            _endpoint_paths[f"{bp_name}.{handler.__name__}"] = full_path


_endpoint_paths: dict = {}
_blueprints: dict = {}
_blueprint_template_folders: dict = {}
_default_template_folder: Optional[str] = None
_jinja_envs: dict = {}


def _make_endpoint(bp_name: str, handler: Callable, converters: dict) -> Callable:
    signature = inspect.signature(handler)
    accepted = {
        name
        for name, param in signature.parameters.items()
        if param.kind
        in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
        and name != "self"
    }

    async def endpoint():
        _current_blueprint.set(bp_name)
        starlette_request = _current_request.get()
        kwargs: dict = {}
        for name, converter in converters.items():
            if name not in accepted:
                continue
            raw = starlette_request.path_params.get(name)
            try:
                kwargs[name] = converter(raw)
            except (TypeError, ValueError):
                return _normalize_result(
                    (jsonify({"success": False, "message": "资源不存在"}), 404)
                )
        result = handler(**kwargs)
        if inspect.iscoroutine(result):
            result = await result
        response = _normalize_result(result)
        blueprint = _blueprints.get(bp_name)
        if blueprint is not None:
            for hook in blueprint._after_request_fns:
                hook_result = hook(response)
                if inspect.iscoroutine(hook_result):
                    hook_result = await hook_result
                response = hook_result
        return response

    endpoint.__name__ = handler.__name__
    return endpoint


class Blueprint:
    """Quart Blueprint 兼容包装（内部转为 FastAPI 路由注册）。"""

    def __init__(
        self,
        name: str,
        import_name: str,
        url_prefix: str = None,
        template_folder: str = None,
        static_folder: str = None,
        **kwargs,
    ):
        self.name = name
        self.import_name = import_name
        self.url_prefix = url_prefix or ""
        self.template_folder = template_folder
        self.registry = _RouteRegistry(self.url_prefix)
        self._after_request_fns: list = []
        _blueprints[name] = self
        _blueprint_template_folders[name] = template_folder

    def route(self, rule: str, methods: Optional[list] = None, **options):
        return self.registry.route(rule, methods, **options)

    def after_request(self, fn: Callable) -> Callable:
        self._after_request_fns.append(fn)
        return fn


# ─────────────────────────────────────────────────────────────────────
# url_for / render_template / send_file
# ─────────────────────────────────────────────────────────────────────


def url_for(endpoint: str, **values) -> str:
    path = _endpoint_paths.get(endpoint)
    if path is None:
        raise KeyError(f"未知 endpoint: {endpoint}")
    for name, value in values.items():
        path = path.replace("{" + name + "}", quote(str(value), safe=""))
    return path


def _get_jinja_env(folder: str) -> Environment:
    env = _jinja_envs.get(folder)
    if env is None:
        env = Environment(
            loader=FileSystemLoader(folder),
            autoescape=select_autoescape(enabled_extensions=("html", "htm", "xml")),
        )
        _jinja_envs[folder] = env
    return env


async def render_template(template_name: str, **context) -> HTMLResponse:
    folder = _blueprint_template_folders.get(_current_blueprint.get("")) or _default_template_folder
    if not folder or not os.path.isdir(folder):
        raise RuntimeError(f"模板目录不可用: {folder}")
    env = _get_jinja_env(folder)
    template = env.get_template(template_name)
    context.setdefault("request", _current_request.get())
    html = template.render(**context)
    return HTMLResponse(html)


async def send_file(path: str, **kwargs) -> FileResponse:
    filename = kwargs.get("download_name") or kwargs.get("attachment_filename")
    if kwargs.get("as_attachment"):
        headers = {"Content-Disposition": f"attachment; filename={os.path.basename(path)}"}
        return FileResponse(path, headers=headers)
    return FileResponse(path, filename=filename)


# ─────────────────────────────────────────────────────────────────────
# Quart 应用工厂（内部为 FastAPI）
# ─────────────────────────────────────────────────────────────────────


class Quart:
    """兼容入口：接口形似 Quart，实际构建 FastAPI 应用（与 AstrBot core 对齐）。"""

    def __init__(
        self,
        import_name: str,
        static_folder: str = None,
        static_url_path: str = "/static",
        template_folder: str = None,
        **kwargs,
    ):
        self.name = import_name
        self.config: dict = {}
        self.secret_key: Optional[str] = None
        self.template_folder = template_folder
        self._static_folder = static_folder
        self._static_url_path = static_url_path
        self._registry = _RouteRegistry("")
        self._finalized = False
        self._effective_secret: str = ""
        self.fastapi_app = FastAPI(
            title="Self Learning WebUI",
            docs_url=None,
            redoc_url=None,
            openapi_url=None,
        )
        global _default_template_folder
        _default_template_folder = template_folder
        self.fastapi_app.add_middleware(
            RequestContextMiddleware, quart_app=self
        )

    def route(self, rule: str, methods: Optional[list] = None, **options):
        return self._registry.route(rule, methods, **options)

    def register_blueprint(self, blueprint: Blueprint, **options) -> None:
        prefix_override = options.get("url_prefix")
        if prefix_override is not None:
            blueprint.registry.url_prefix = prefix_override.rstrip("/")
        blueprint.registry.apply_to(self.fastapi_app, blueprint.name)

    def errorhandler(self, status_or_exc):
        return self.fastapi_app.exception_handler(status_or_exc)

    def _finalize(self) -> None:
        """注册路由与中间件；在首次 test_client/serve 前调用。"""
        if self._finalized:
            return
        self._finalized = True

        self._registry.apply_to(self.fastapi_app, "app")
        self._effective_secret = self.secret_key or secrets.token_hex(32)

        if self._static_folder and os.path.isdir(self._static_folder):
            self.fastapi_app.mount(
                self._static_url_path or "/static",
                StaticFiles(directory=self._static_folder),
                name="static",
            )

        self.fastapi_app.add_middleware(
            SessionMiddleware,
            secret_key=self._effective_secret,
            session_cookie="session",
            max_age=int(
                self.config.get("PERMANENT_SESSION_LIFETIME", timedelta(days=7)).total_seconds()
            )
            if isinstance(self.config.get("PERMANENT_SESSION_LIFETIME"), timedelta)
            else 7 * 24 * 3600,
            same_site=self.config.get("SESSION_COOKIE_SAMESITE", "lax"),
            https_only=False,
        )

    def test_client(self) -> "CompatTestClient":
        self._finalize()
        return CompatTestClient(
            TestClient(self.fastapi_app, raise_server_exceptions=False),
            secret_key=self._effective_secret,
        )

    def get_asgi_app(self) -> FastAPI:
        """返回底层 FastAPI 应用（uvicorn 承载），完成中间件装配。"""
        self._finalize()
        return self.fastapi_app


class CompatTestResponse:
    """starlette/httpx 响应的 Quart 风格包装。"""

    def __init__(self, inner):
        self._inner = inner

    @property
    def status_code(self) -> int:
        return self._inner.status_code

    @property
    def headers(self):
        return self._inner.headers

    @property
    def text(self) -> str:
        return self._inner.text

    @property
    def content(self) -> bytes:
        return self._inner.content

    def json(self) -> Any:
        return self._inner.json()

    async def get_json(self, silent: bool = False) -> Any:
        if silent:
            try:
                return self.json()
            except ValueError:
                return None
        return self.json()

    async def get_data(self, as_text: bool = False):
        return self._inner.text if as_text else self._inner.content


class CompatTestClient:
    """Quart 异步 test_client 语义的 TestClient 包装。

    Quart 默认不跟随重定向，与 httpx 默认行为相反，这里统一注入
    ``follow_redirects=False`` 以保持既有测试断言的语义。
    """

    def __init__(self, inner: TestClient, secret_key: str = ""):
        self._inner = inner
        self._app_secret_key = secret_key

    @staticmethod
    def _kwargs(kwargs: dict) -> dict:
        kwargs.setdefault("follow_redirects", False)
        return kwargs

    async def get(self, url: str, **kwargs) -> CompatTestResponse:
        return CompatTestResponse(self._inner.get(url, **self._kwargs(kwargs)))

    async def post(self, url: str, **kwargs) -> CompatTestResponse:
        return CompatTestResponse(self._inner.post(url, **self._kwargs(kwargs)))

    async def put(self, url: str, **kwargs) -> CompatTestResponse:
        return CompatTestResponse(self._inner.put(url, **self._kwargs(kwargs)))

    async def patch(self, url: str, **kwargs) -> CompatTestResponse:
        return CompatTestResponse(self._inner.patch(url, **self._kwargs(kwargs)))

    async def delete(self, url: str, **kwargs) -> CompatTestResponse:
        return CompatTestResponse(self._inner.delete(url, **self._kwargs(kwargs)))

    async def options(self, url: str, **kwargs) -> CompatTestResponse:
        return CompatTestResponse(self._inner.options(url, **self._kwargs(kwargs)))

    def session_transaction(self) -> "_SessionTransaction":
        """Quart 风格的会话事务：退出时把改动写回签名 session cookie。"""
        return _SessionTransaction(
            self._inner.cookies,
            secret_key=self._app_secret_key,
        )

    async def __aenter__(self) -> "CompatTestClient":
        return self

    async def __aexit__(self, *exc_info) -> None:
        return None


class _SessionTransaction:
    """直接生成与 starlette SessionMiddleware 同格式的签名会话 cookie。

    SessionMiddleware 使用裸 ``TimestampSigner(secret)`` 签名
    ``b64(json(session))``，这里保持同一编码以便端点正常解码。
    """

    def __init__(self, cookie_jar, secret_key: str):
        self._jar = cookie_jar
        self._secret_key = secret_key
        self._data: dict = {}

    async def __aenter__(self) -> dict:
        existing = None
        try:
            existing = self._jar.get("session")
        except Exception:
            existing = None
        if existing:
            try:
                signer = TimestampSigner(str(self._secret_key))
                raw = signer.unsign(existing.encode("utf-8"), max_age=14 * 24 * 3600)
                self._data = json.loads(base64.b64decode(raw))
            except Exception:
                self._data = {}
        return self._data

    async def __aexit__(self, *exc_info) -> None:
        payload = base64.b64encode(json.dumps(self._data).encode("utf-8"))
        value = TimestampSigner(str(self._secret_key)).sign(payload).decode("utf-8")
        self._jar.set("session", value, domain="testserver")
