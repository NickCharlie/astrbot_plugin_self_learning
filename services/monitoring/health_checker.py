"""Service health checker with configurable thresholds.

Evaluates system health from prometheus metric values and psutil system
checks. Results are cached with a short TTL to avoid per-request
overhead from psutil calls and metric aggregation.
"""

import time
from enum import Enum
from typing import Any, Dict, List, Optional

import psutil
from cachetools import TTLCache
from astrbot.api import logger

from ...core.patterns import ServiceRegistry
from ...core.interfaces import ServiceLifecycle


class HealthStatus(Enum):
    """Overall health status of a subsystem."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class HealthChecker:
    """Evaluates service health based on metrics and system state.

    Args:
        service_registry: ServiceRegistry for checking service statuses.
        cache_manager: CacheManager for reading hit rates.
        llm_adapter: FrameworkLLMAdapter for reading call statistics.
        thresholds: Optional override for default threshold values.
    """

    # Default thresholds. Can be overridden via constructor.
    DEFAULT_THRESHOLDS: Dict[str, Dict[str, float]] = {
        "llm_error_rate": {"healthy": 0.05, "degraded": 0.20},
        "llm_p95_latency_s": {"healthy": 5.0, "degraded": 10.0},
        "cache_hit_rate": {"healthy": 0.50, "degraded": 0.30},
        "cpu_percent": {"healthy": 70.0, "degraded": 90.0},
        "memory_percent": {"healthy": 70.0, "degraded": 85.0},
    }

    def __init__(
        self,
        service_registry: Optional[ServiceRegistry] = None,
        cache_manager: Optional[Any] = None,
        llm_adapter: Optional[Any] = None,
        thresholds: Optional[Dict[str, Dict[str, float]]] = None,
    ) -> None:
        self._service_registry = service_registry
        self._cache_manager = cache_manager
        self._llm_adapter = llm_adapter
        self._thresholds = dict(self.DEFAULT_THRESHOLDS)
        if thresholds:
            self._thresholds.update(thresholds)

        # Cache health check results for 30 seconds.
        self._cache: TTLCache = TTLCache(maxsize=1, ttl=30)

    # -- Public API ---------------------------------------------------------

    def check_all(self) -> Dict[str, Dict[str, Any]]:
        """Run all health checks and return per-subsystem results.

        Returns:
            Dict mapping check name to ``{"status": HealthStatus, "detail": ...}``.
        """
        cached = self._cache.get("health")
        if cached is not None:
            return cached

        results: Dict[str, Dict[str, Any]] = {}
        results["cpu"] = self._check_cpu()
        results["memory"] = self._check_memory()
        results["llm"] = self._check_llm()
        results["cache"] = self._check_cache()
        results["services"] = self._check_services()

        self._cache["health"] = results
        return results

    def get_summary(self) -> Dict[str, Any]:
        """Return an overall health summary including per-check breakdown.

        The overall status is the worst status among all checks.
        """
        checks = self.check_all()
        statuses = [c["status"] for c in checks.values()]

        if HealthStatus.UNHEALTHY in statuses:
            overall = HealthStatus.UNHEALTHY
        elif HealthStatus.DEGRADED in statuses:
            overall = HealthStatus.DEGRADED
        else:
            overall = HealthStatus.HEALTHY

        serialized = {}
        for name, check in checks.items():
            serialized[name] = {
                "status": check["status"].value,
                "detail": check.get("detail", {}),
            }

        return {
            "overall": overall.value,
            "checks": serialized,
            "timestamp": time.time(),
        }

    # -- Individual checks --------------------------------------------------

    def _check_cpu(self) -> Dict[str, Any]:
        """Check CPU usage via psutil."""
        try:
            cpu = psutil.cpu_percent(interval=0)
            t = self._thresholds["cpu_percent"]
            if cpu >= t["degraded"]:
                status = HealthStatus.UNHEALTHY
            elif cpu >= t["healthy"]:
                status = HealthStatus.DEGRADED
            else:
                status = HealthStatus.HEALTHY
            return {"status": status, "detail": {"cpu_percent": cpu}}
        except Exception as exc:
            logger.debug(f"[HealthChecker] CPU check error: {exc}")
            return {"status": HealthStatus.DEGRADED, "detail": {"error": str(exc)}}

    def _check_memory(self) -> Dict[str, Any]:
        """Check memory usage via psutil."""
        try:
            mem = psutil.virtual_memory()
            t = self._thresholds["memory_percent"]
            if mem.percent >= t["degraded"]:
                status = HealthStatus.UNHEALTHY
            elif mem.percent >= t["healthy"]:
                status = HealthStatus.DEGRADED
            else:
                status = HealthStatus.HEALTHY
            return {
                "status": status,
                "detail": {
                    "memory_percent": mem.percent,
                    "used_gb": round(mem.used / (1024 ** 3), 2),
                    "total_gb": round(mem.total / (1024 ** 3), 2),
                },
            }
        except Exception as exc:
            logger.debug(f"[HealthChecker] Memory check error: {exc}")
            return {"status": HealthStatus.DEGRADED, "detail": {"error": str(exc)}}

    def _check_llm(self) -> Dict[str, Any]:
        """Check LLM availability from adapter statistics."""
        if not self._llm_adapter or not hasattr(self._llm_adapter, "get_call_statistics"):
            return {"status": HealthStatus.HEALTHY, "detail": {"note": "no adapter"}}

        try:
            stats = self._llm_adapter.get_call_statistics()
            overall = stats.get("overall", {})
            total = overall.get("total_calls", 0)
            errors = overall.get("error_count", 0)
            avg_ms = overall.get("avg_response_time_ms", 0)

            if total == 0:
                return {"status": HealthStatus.HEALTHY, "detail": {"total_calls": 0}}

            error_rate = errors / total
            avg_s = avg_ms / 1000.0

            t_err = self._thresholds["llm_error_rate"]
            t_lat = self._thresholds["llm_p95_latency_s"]

            if error_rate >= t_err["degraded"] or avg_s >= t_lat["degraded"]:
                status = HealthStatus.UNHEALTHY
            elif error_rate >= t_err["healthy"] or avg_s >= t_lat["healthy"]:
                status = HealthStatus.DEGRADED
            else:
                status = HealthStatus.HEALTHY

            return {
                "status": status,
                "detail": {
                    "total_calls": total,
                    "error_rate": round(error_rate, 4),
                    "avg_latency_s": round(avg_s, 3),
                },
            }
        except Exception as exc:
            logger.debug(f"[HealthChecker] LLM check error: {exc}")
            return {"status": HealthStatus.DEGRADED, "detail": {"error": str(exc)}}

    def _check_cache(self) -> Dict[str, Any]:
        """Check cache hit rates from CacheManager."""
        if not self._cache_manager or not hasattr(self._cache_manager, "get_hit_rates"):
            return {"status": HealthStatus.HEALTHY, "detail": {"note": "no cache manager"}}

        try:
            rates = self._cache_manager.get_hit_rates()
            if not rates:
                return {"status": HealthStatus.HEALTHY, "detail": {"note": "no data"}}

            total_hits = sum(s.get("hits", 0) for s in rates.values())
            total_misses = sum(s.get("misses", 0) for s in rates.values())
            total = total_hits + total_misses

            if total == 0:
                return {"status": HealthStatus.HEALTHY, "detail": {"total_queries": 0}}

            hit_rate = total_hits / total
            t = self._thresholds["cache_hit_rate"]

            if hit_rate <= t["degraded"]:
                status = HealthStatus.UNHEALTHY
            elif hit_rate <= t["healthy"]:
                status = HealthStatus.DEGRADED
            else:
                status = HealthStatus.HEALTHY

            return {
                "status": status,
                "detail": {
                    "hit_rate": round(hit_rate, 4),
                    "total_hits": total_hits,
                    "total_misses": total_misses,
                },
            }
        except Exception as exc:
            logger.debug(f"[HealthChecker] Cache check error: {exc}")
            return {"status": HealthStatus.DEGRADED, "detail": {"error": str(exc)}}

    def _check_services(self) -> Dict[str, Any]:
        """Check all registered service statuses."""
        if not self._service_registry:
            return {"status": HealthStatus.HEALTHY, "detail": {"note": "no registry"}}

        try:
            statuses = self._service_registry.get_service_status()
            error_services: List[str] = []
            stopped_services: List[str] = []

            for name, status_str in statuses.items():
                if status_str == ServiceLifecycle.ERROR.value:
                    error_services.append(name)
                elif status_str == ServiceLifecycle.STOPPED.value:
                    stopped_services.append(name)

            if error_services:
                status = HealthStatus.UNHEALTHY
            elif stopped_services:
                status = HealthStatus.DEGRADED
            else:
                status = HealthStatus.HEALTHY

            return {
                "status": status,
                "detail": {
                    "total": len(statuses),
                    "error_services": error_services,
                    "stopped_services": stopped_services,
                },
            }
        except Exception as exc:
            logger.debug(f"[HealthChecker] Services check error: {exc}")
            return {"status": HealthStatus.DEGRADED, "detail": {"error": str(exc)}}
