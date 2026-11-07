"""运行监控蓝图：健康检查附带运行态（数据库降级标记）。

独立 WebUI 的 AI 巡检「数据库处于降级状态」读 ``/api/monitoring/health`` 的
``runtime``，与内嵌插件页 ``page/dashboard`` 的 ``monitoring.runtime`` 同源。
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PARENT = PACKAGE_ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from self_learning_EterU.webui.compat import Quart  # noqa: E402
import self_learning_EterU.webui.blueprints.monitoring as monitoring_module  # noqa: E402


class _Checker:
    def get_summary(self):
        return {"overall": "healthy", "checks": {"cpu": {"status": "healthy", "detail": {"cpu_percent": 3}}}}


def _client(monkeypatch, **container_fields):
    container = SimpleNamespace(health_checker=_Checker(), llm_adapter=None, **container_fields)
    monkeypatch.setattr(monitoring_module, "get_container", lambda: container)
    app = Quart(__name__)
    app.config["TESTING"] = True
    app.secret_key = "test-secret-key"
    app.register_blueprint(monitoring_module.monitoring_bp)
    return app.test_client()


@pytest.mark.asyncio
async def test_health_reports_database_degraded_runtime(monkeypatch):
    client = _client(monkeypatch, database_degraded=True, database_start_error="sqlite locked")

    response = await client.get("/api/monitoring/health")

    assert response.status_code == 200
    data = await response.get_json()
    assert data["overall"] == "healthy"
    assert data["checks"]["cpu"]["status"] == "healthy"
    assert data["runtime"] == {"database_degraded": True, "database_start_error": "sqlite locked"}


@pytest.mark.asyncio
async def test_health_runtime_defaults_when_container_lacks_flags(monkeypatch):
    client = _client(monkeypatch)

    data = await (await client.get("/api/monitoring/health")).get_json()

    assert data["runtime"] == {"database_degraded": False, "database_start_error": None}
