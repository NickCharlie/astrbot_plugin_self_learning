"""黑话联网释义补充 — 复用 AstrBot 联网搜索配置，为低提及词条补充释义。

针对的空缺场景（黑话学习流程缺口）：

* 词条提及次数低于首个推断阈值（3 次）时，三步推断永远不会触发，
  ``meaning`` 永远为 NULL；
* 三步推断在上下文不足时返回 ``no_info``，含义同样留空。

本模块读取 AstrBot 主配置 ``provider_settings`` 中的联网搜索密钥（与
AstrBot 内置 web search 使用同一套配置，无需重复填写 key），调用搜索
API 获取公开网页释义线索，再由筛选模型归纳成简明释义，交由挖掘器写回
词条（``is_complete`` 保持 False，后续推断可继续修正）。
"""

import asyncio
import time
from typing import Any, Dict, List, Optional

import aiohttp

from astrbot.api import logger

from ...core.framework_llm_adapter import FrameworkLLMAdapter
from ...utils.json_utils import safe_parse_llm_json


# AstrBot provider_settings 中的搜索密钥配置名（与内置 web search 一致）。
_PROVIDER_KEY_SETTINGS = {
    "tavily": ("websearch_tavily_key", "list"),
    "bocha": ("websearch_bocha_key", "list"),
    "exa": ("websearch_exa_key", "list"),
    "baidu": ("websearch_baidu_app_builder_key", "str"),
}

# auto 模式下的探测顺序：先跟随 AstrBot websearch_provider，再按此顺序兜底。
_PROVIDER_FALLBACK_ORDER = ("tavily", "bocha", "exa", "baidu")

_SEARCH_TIMEOUT_SECONDS = 10.0


def _provider_keys(provider_settings: Dict[str, Any], provider: str) -> List[str]:
    """Return the configured API keys for *provider* (may be empty)."""
    entry = _PROVIDER_KEY_SETTINGS.get(provider)
    if not entry:
        return []
    setting_name, kind = entry
    value = provider_settings.get(setting_name)
    if kind == "list":
        if isinstance(value, str):
            return [value] if value.strip() else []
        if isinstance(value, (list, tuple)):
            return [str(item).strip() for item in value if str(item).strip()]
        return []
    text = str(value).strip() if value else ""
    return [text] if text else []


class WebSearchClient:
    """Minimal multi-provider web search client.

    Reads the same ``provider_settings`` keys as AstrBot's built-in web
    search, so users who already configured a search provider get jargon
    web definitions with zero extra setup. ``available()`` re-reads the
    settings on every call so keys added at runtime are picked up.
    """

    def __init__(self, provider_settings_getter, preferred_provider: str = "") -> None:
        self._get_settings = provider_settings_getter
        self._preferred = (preferred_provider or "").strip().lower()

    @classmethod
    def from_astrbot_config(cls, astrbot_config: Any) -> Optional["WebSearchClient"]:
        """Build a client from the AstrBot main config; None if unavailable."""
        if astrbot_config is None:
            return None
        try:
            provider_settings = astrbot_config.get("provider_settings", {}) or {}
            preferred = str(
                provider_settings.get("websearch_provider", "") or ""
            )
        except Exception:
            return None

        def _get_settings() -> Dict[str, Any]:
            try:
                return astrbot_config.get("provider_settings", {}) or {}
            except Exception:
                return {}

        return cls(_get_settings, preferred_provider=preferred)

    def _resolve_provider(self) -> Optional[str]:
        settings = self._get_settings()
        if self._preferred in _PROVIDER_KEY_SETTINGS and _provider_keys(
            settings, self._preferred
        ):
            return self._preferred
        for provider in _PROVIDER_FALLBACK_ORDER:
            if _provider_keys(settings, provider):
                return provider
        return None

    def available(self) -> bool:
        return self._resolve_provider() is not None

    async def search(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        """Search the web; returns [{title, url, snippet}] (possibly empty)."""
        provider = self._resolve_provider()
        if not provider:
            return []
        settings = self._get_settings()
        try:
            if provider == "tavily":
                return await self._search_tavily(settings, query, max_results)
            if provider == "bocha":
                return await self._search_bocha(settings, query, max_results)
            if provider == "exa":
                return await self._search_exa(settings, query, max_results)
            if provider == "baidu":
                return await self._search_baidu(settings, query, max_results)
        except asyncio.TimeoutError:
            logger.debug(f"[黑话联网释义] 搜索超时: {provider}")
        except Exception as exc:
            logger.debug(f"[黑话联网释义] 搜索失败 ({provider}): {exc}")
        return []

    async def _fetch_json(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        payload: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        timeout = aiohttp.ClientTimeout(total=_SEARCH_TIMEOUT_SECONDS)
        async with aiohttp.ClientSession(trust_env=True, timeout=timeout) as session:
            async with session.request(
                method,
                url,
                json=payload,
                params=params,
                headers=headers,
            ) as response:
                if response.status != 200:
                    reason = await response.text()
                    raise RuntimeError(
                        f"search provider returned {response.status}: {reason[:120]}"
                    )
                return await response.json()

    @staticmethod
    def _first_key(settings: Dict[str, Any], provider: str) -> str:
        keys = _provider_keys(settings, provider)
        return keys[0] if keys else ""

    async def _search_tavily(
        self, settings: Dict[str, Any], query: str, max_results: int
    ) -> List[Dict[str, str]]:
        data = await self._fetch_json(
            "POST",
            "https://api.tavily.com/search",
            headers={
                "Authorization": f"Bearer {self._first_key(settings, 'tavily')}",
                "Content-Type": "application/json",
            },
            payload={"query": query, "max_results": max_results},
        )
        return [
            {
                "title": str(item.get("title") or ""),
                "url": str(item.get("url") or ""),
                "snippet": str(item.get("content") or ""),
            }
            for item in data.get("results", [])
        ]

    async def _search_bocha(
        self, settings: Dict[str, Any], query: str, max_results: int
    ) -> List[Dict[str, str]]:
        data = await self._fetch_json(
            "POST",
            "https://api.bochaai.com/v1/web-search",
            headers={
                "Authorization": f"Bearer {self._first_key(settings, 'bocha')}",
                "Content-Type": "application/json",
                "Accept-Encoding": "gzip, deflate",
            },
            payload={"query": query, "count": max_results},
        )
        rows = (
            data.get("data", {}).get("webPages", {}).get("value", [])
            if isinstance(data.get("data"), dict)
            else []
        )
        return [
            {
                "title": str(item.get("name") or ""),
                "url": str(item.get("url") or ""),
                "snippet": str(item.get("snippet") or ""),
            }
            for item in rows
        ]

    async def _search_exa(
        self, settings: Dict[str, Any], query: str, max_results: int
    ) -> List[Dict[str, str]]:
        data = await self._fetch_json(
            "POST",
            "https://api.exa.ai/search",
            headers={
                "x-api-key": self._first_key(settings, "exa"),
                "Content-Type": "application/json",
            },
            payload={
                "query": query,
                "numResults": max_results,
                "contents": {"text": {"maxCharacters": 400}},
            },
        )
        return [
            {
                "title": str(item.get("title") or ""),
                "url": str(item.get("url") or ""),
                "snippet": str(
                    item.get("text")
                    or (item.get("highlights") or [""])[0]
                    or item.get("summary")
                    or ""
                ),
            }
            for item in data.get("results", [])
        ]

    async def _search_baidu(
        self, settings: Dict[str, Any], query: str, max_results: int
    ) -> List[Dict[str, str]]:
        api_key = self._first_key(settings, "baidu")
        data = await self._fetch_json(
            "POST",
            "https://qianfan.baidubce.com/v2/ai_search/web_search",
            headers={
                "Authorization": f"Bearer {api_key}",
                "X-Appbuilder-Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            payload={
                "messages": [{"role": "user", "content": query[:72]}],
                "search_source": "baidu_search_v2",
                "resource_type_filter": [{"type": "web", "top_k": max_results}],
            },
        )
        return [
            {
                "title": str(item.get("title") or ""),
                "url": str(item.get("url") or ""),
                "snippet": str(item.get("content") or ""),
            }
            for item in data.get("references", [])
        ]


_DEFINITION_PROMPT = """**待解释词条**
{term}

**联网检索到的公开资料（标题与摘要）**
{search_context}

**该词条在本群聊中出现过的上下文（供参考，可能很少）**
{group_context}

请基于以上公开资料归纳这个词条作为网络用语/黑话/特定圈子用语时的含义。
要求：
- 优先参考公开资料中与"网络用语/俚语/缩写"相关的解释，并结合群内上下文
- 如果资料与词条明显无关，或无法给出可信解释，将 found 设为 false
- 释义控制在 120 字以内，说明含义与典型使用场景

以 JSON 格式输出：
{{
  "found": true/false,
  "meaning": "简明释义"
}}"""


class JargonWebDefinitionService:
    """搜索 + 归纳的黑话释义补充服务（带全局限速，避免批量触发时打爆配额）。"""

    def __init__(
        self,
        llm_adapter: FrameworkLLMAdapter,
        web_client: WebSearchClient,
        min_interval_seconds: float = 10.0,
        definition_timeout_seconds: float = 30.0,
    ) -> None:
        self.llm = llm_adapter
        self.web_client = web_client
        self.min_interval_seconds = min_interval_seconds
        self.definition_timeout_seconds = definition_timeout_seconds
        self._lock = asyncio.Lock()
        self._last_call_ts = 0.0

    async def supplement(
        self,
        term: str,
        raw_content_list: Optional[List[str]] = None,
    ) -> Optional[str]:
        """Search the web for *term* and return a concise definition, or None.

        None means "no supplement available" (feature off, no provider,
        no usable results, or model could not confirm a definition) —
        callers should leave the term untouched in that case.
        """
        term = str(term or "").strip()
        if not term or not self.web_client.available():
            return None

        async with self._lock:
            now = time.monotonic()
            wait = self.min_interval_seconds - (now - self._last_call_ts)
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                return await self._supplement_unlocked(term, raw_content_list or [])
            finally:
                self._last_call_ts = time.monotonic()

    async def _supplement_unlocked(
        self, term: str, raw_content_list: List[str]
    ) -> Optional[str]:
        query = f"{term} 网络用语 黑话 意思"
        results = await self.web_client.search(query, max_results=5)
        if not results:
            logger.debug(f"[黑话联网释义] {term}: 无检索结果")
            return None

        search_lines = []
        for index, item in enumerate(results, 1):
            snippet = item.get("snippet", "").strip()[:300]
            if not snippet:
                continue
            search_lines.append(f"{index}. {item.get('title', '')}: {snippet}")
        if not search_lines:
            return None

        context_lines = [str(text).strip()[:120] for text in raw_content_list[:3]]
        prompt = _DEFINITION_PROMPT.format(
            term=term,
            search_context="\n".join(search_lines),
            group_context="\n".join(context_lines) or "（无）",
        )

        try:
            response = await asyncio.wait_for(
                self.llm.generate_response(prompt, temperature=0.2),
                timeout=self.definition_timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.debug(f"[黑话联网释义] {term}: 归纳释义超时")
            return None
        if not response:
            return None

        parsed = safe_parse_llm_json(response.strip())
        if not isinstance(parsed, dict):
            return None
        if not parsed.get("found"):
            return None
        meaning = parsed.get("meaning")
        meaning = str(meaning).strip() if meaning else ""
        if not meaning:
            return None

        logger.info(f"[黑话联网释义] {term}: 已通过联网检索补充释义")
        return f"{meaning}\n（释义来自联网检索，供理解参考）"


def build_web_definition_service(
    llm_adapter: FrameworkLLMAdapter,
    astrbot_config: Any,
    plugin_config: Any,
) -> Optional[JargonWebDefinitionService]:
    """Wire the supplement service from configs; None when disabled."""
    if not bool(getattr(plugin_config, "jargon_websearch_enabled", True)):
        return None
    client = WebSearchClient.from_astrbot_config(astrbot_config)
    if client is None:
        return None
    return JargonWebDefinitionService(llm_adapter, client)
