"""黑话联网释义补充（jargon_websearch_enabled）回归测试"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from self_learning_EterU.models.jargon import Jargon
from self_learning_EterU.services.jargon.jargon_miner import JargonMiner
from self_learning_EterU.services.jargon.web_search_definition import (
    JargonWebDefinitionService,
    WebSearchClient,
    build_web_definition_service,
)


# ---------------------------------------------------------------------------
# WebSearchClient：provider 解析与搜索路由
# ---------------------------------------------------------------------------


def _settings(**overrides):
    settings = {
        "websearch_provider": "",
        "websearch_tavily_key": [],
        "websearch_bocha_key": [],
        "websearch_exa_key": [],
        "websearch_baidu_app_builder_key": "",
    }
    settings.update(overrides)
    return settings


def test_client_resolves_preferred_provider():
    client = WebSearchClient(
        lambda: _settings(
            websearch_provider="bocha", websearch_bocha_key=["k1"]
        ),
        preferred_provider="bocha",
    )
    assert client.available() is True


def test_client_falls_back_to_first_configured_provider():
    client = WebSearchClient(
        lambda: _settings(websearch_exa_key=["k1"]),
        preferred_provider="",
    )
    assert client.available() is True
    assert client._resolve_provider() == "exa"


def test_client_unavailable_without_keys():
    client = WebSearchClient(lambda: _settings(), preferred_provider="")
    assert client.available() is False
    assert client._resolve_provider() is None


def test_from_astrbot_config_handles_none():
    assert WebSearchClient.from_astrbot_config(None) is None


@pytest.mark.asyncio
async def test_search_routes_to_bocha_and_parses_results():
    client = WebSearchClient(
        lambda: _settings(websearch_bocha_key=["k1"]),
        preferred_provider="",
    )
    captured = {}

    async def fake_fetch(method, url, headers, payload=None, params=None):
        captured["url"] = url
        captured["payload"] = payload
        return {
            "data": {
                "webPages": {
                    "value": [
                        {
                            "name": "标题",
                            "url": "https://example.com",
                            "snippet": "释义片段",
                        }
                    ]
                }
            }
        }

    client._fetch_json = fake_fetch

    results = await client.search("xx 网络用语 意思", max_results=5)

    assert "bochaai.com" in captured["url"]
    assert captured["payload"]["query"] == "xx 网络用语 意思"
    assert results == [
        {
            "title": "标题",
            "url": "https://example.com",
            "snippet": "释义片段",
        }
    ]


@pytest.mark.asyncio
async def test_search_returns_empty_on_provider_error():
    client = WebSearchClient(
        lambda: _settings(websearch_tavily_key=["k1"]),
        preferred_provider="",
    )

    async def failing_fetch(*args, **kwargs):
        raise RuntimeError("boom")

    client._fetch_json = failing_fetch

    assert await client.search("任意查询") == []


# ---------------------------------------------------------------------------
# JargonWebDefinitionService：搜索 + 归纳释义
# ---------------------------------------------------------------------------


def _make_service(search_results, llm_response, **kwargs):
    web_client = WebSearchClient(
        lambda: _settings(websearch_tavily_key=["k1"]),
        preferred_provider="",
    )
    web_client.search = AsyncMock(return_value=search_results)
    llm = SimpleNamespace(
        generate_response=AsyncMock(return_value=llm_response)
    )
    service = JargonWebDefinitionService(llm, web_client, **kwargs)
    return service, web_client.search, llm.generate_response


@pytest.mark.asyncio
async def test_supplement_returns_meaning_with_source_marker():
    service, search_mock, llm_mock = _make_service(
        search_results=[{"title": "t", "url": "u", "snippet": "s"}],
        llm_response='{"found": true, "meaning": "指非常厉害的人"}',
    )

    meaning = await service.supplement("yyds", ["他太yyds了"])

    assert meaning is not None
    assert "指非常厉害的人" in meaning
    assert "联网检索" in meaning
    search_mock.assert_awaited_once()
    prompt = llm_mock.await_args.args[0]
    assert "yyds" in prompt
    assert "他太yyds了" in prompt


@pytest.mark.asyncio
async def test_supplement_returns_none_when_not_found():
    service, _, _ = _make_service(
        search_results=[{"title": "t", "url": "u", "snippet": "无关内容"}],
        llm_response='{"found": false, "meaning": ""}',
    )

    assert await service.supplement("某词", []) is None


@pytest.mark.asyncio
async def test_supplement_returns_none_without_search_results():
    service, _, llm_mock = _make_service(
        search_results=[], llm_response='{"found": true, "meaning": "x"}'
    )

    assert await service.supplement("某词", []) is None
    llm_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_supplement_noop_when_provider_unavailable():
    web_client = WebSearchClient(lambda: _settings(), preferred_provider="")
    service = JargonWebDefinitionService(
        SimpleNamespace(generate_response=AsyncMock()), web_client
    )

    assert await service.supplement("某词", []) is None


def test_build_service_disabled_by_config():
    assert (
        build_web_definition_service(
            llm_adapter=object(),
            astrbot_config=SimpleNamespace(
                get=lambda key, default=None: {}
            ),
            plugin_config=SimpleNamespace(jargon_websearch_enabled=False),
        )
        is None
    )


def test_build_service_none_without_astrbot_config():
    assert (
        build_web_definition_service(
            llm_adapter=object(),
            astrbot_config=None,
            plugin_config=SimpleNamespace(jargon_websearch_enabled=True),
        )
        is None
    )


# ---------------------------------------------------------------------------
# JargonMiner：两处释义空缺点接入联网补充
# ---------------------------------------------------------------------------


def _make_miner(service):
    db = SimpleNamespace(
        get_jargon=AsyncMock(return_value=None),
        update_jargon=AsyncMock(return_value=True),
    )
    miner = JargonMiner(
        "group-a",
        llm_adapter=object(),
        db_manager=db,
        config=SimpleNamespace(),
        web_definition_service=service,
    )
    return miner, db


def _jargon(content="yyds", count=3, meaning=None):
    return Jargon(
        content=content,
        raw_content='["上下文一"]',
        meaning=meaning,
        is_jargon=None,
        count=count,
        chat_id="group-a",
    )


def _service_returning(meaning):
    return SimpleNamespace(supplement=AsyncMock(return_value=meaning))


@pytest.mark.asyncio
async def test_no_info_branch_triggers_web_supplement():
    service = _service_returning("网络流行语：厉害")
    miner, db = _make_miner(service)
    miner.inference_engine = SimpleNamespace(
        infer_meaning=AsyncMock(return_value={"no_info": True})
    )
    jargon = _jargon(count=3)

    await miner.infer_and_update(jargon)

    service.supplement.assert_awaited_once_with("yyds", ["上下文一"])
    updated = db.update_jargon.await_args.args[0]
    assert updated["is_jargon"] is True
    assert "网络流行语" in updated["meaning"]
    assert updated["is_complete"] is False


@pytest.mark.asyncio
async def test_no_info_without_web_result_leaves_meaning_empty():
    service = _service_returning(None)
    miner, db = _make_miner(service)
    miner.inference_engine = SimpleNamespace(
        infer_meaning=AsyncMock(return_value={"no_info": True})
    )
    jargon = _jargon(count=3)

    await miner.infer_and_update(jargon)

    service.supplement.assert_awaited_once()
    updated = db.update_jargon.await_args.args[0]
    assert updated["meaning"] is None
    assert updated["is_jargon"] is None


@pytest.mark.asyncio
async def test_supplement_skipped_when_meaning_exists():
    service = _service_returning("不应被调用")
    miner, _ = _make_miner(service)
    jargon = _jargon(count=3, meaning="已有含义")

    assert await miner._supplement_via_web(jargon) is False
    service.supplement.assert_not_awaited()


@pytest.mark.asyncio
async def test_supplement_does_not_override_concurrent_update():
    service = _service_returning("联网释义")
    miner, db = _make_miner(service)
    # 模拟补充期间数据库已被并发写入含义
    db.get_jargon = AsyncMock(
        return_value={"meaning": "并发写入的含义", "is_complete": False}
    )
    jargon = _jargon(count=3)

    assert await miner._supplement_via_web(jargon) is False
    db.update_jargon.assert_not_awaited()


@pytest.mark.asyncio
async def test_rare_term_sweep_limited_and_sorted_by_count():
    supplement_calls = []

    async def record_supplement(term, raw_content_list=None):
        supplement_calls.append(term)
        return "联网释义"

    service = SimpleNamespace(supplement=AsyncMock(side_effect=record_supplement))
    miner, _ = _make_miner(service)
    rare_terms = [
        _jargon(content="词一", count=1),
        _jargon(content="词二", count=2),
        _jargon(content="词三", count=2),
    ]

    await miner._sweep_rare_terms_via_web(rare_terms)

    assert supplement_calls == ["词三", "词二"] or supplement_calls == [
        "词二",
        "词三",
    ]
    assert len(supplement_calls) == miner.WEB_SUPPLEMENT_BATCH_LIMIT


@pytest.mark.asyncio
async def test_rare_term_sweep_skips_terms_with_meaning():
    service = _service_returning("联网释义")
    miner, _ = _make_miner(service)
    has_meaning = _jargon(content="已有释义词", count=2, meaning="已有")
    no_meaning = _jargon(content="无释义词", count=1)

    await miner._sweep_rare_terms_via_web([has_meaning, no_meaning])

    assert service.supplement.await_count == 1
    assert service.supplement.await_args.args[0] == "无释义词"


def test_miner_without_service_defaults_to_none():
    miner = JargonMiner(
        "group-a",
        llm_adapter=object(),
        db_manager=SimpleNamespace(),
        config=SimpleNamespace(),
    )
    assert miner.web_definition_service is None
