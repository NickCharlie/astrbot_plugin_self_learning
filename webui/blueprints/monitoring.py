"""Monitoring blueprint - Prometheus metrics, health checks, and profiling endpoints."""

import time
from quart import Blueprint, request, jsonify

from astrbot.api import logger
from ..dependencies import get_container
from ..middleware.auth import require_auth
from ..utils.response import success_response, error_response
from ...services.monitoring.metrics import REGISTRY, has_prometheus
from ...services.monitoring.health_checker import HealthChecker
from ...services.monitoring.profiler import ProfileSession

# Lazy import: generate_latest / CONTENT_TYPE_LATEST only available
# when prometheus_client is present.
_generate_latest = None
_CONTENT_TYPE_LATEST = "text/plain; charset=utf-8"
if has_prometheus():
    try:
        from prometheus_client import generate_latest as _generate_latest
        from prometheus_client import CONTENT_TYPE_LATEST as _CONTENT_TYPE_LATEST
    except Exception:
        pass

monitoring_bp = Blueprint("monitoring", __name__, url_prefix="/api/monitoring")

# Module-level profiler instance shared across requests.
_profiler = ProfileSession()


@monitoring_bp.route("/metrics", methods=["GET"])
@require_auth
async def prometheus_metrics():
    """Return metrics in Prometheus text exposition format.

    This endpoint can be scraped by a Prometheus server directly.
    """
    try:
        if _generate_latest is None:
            return error_response("prometheus_client 不可用", 503)
        data = _generate_latest(REGISTRY)
        return data, 200, {"Content-Type": _CONTENT_TYPE_LATEST}
    except Exception as e:
        logger.error(f"[Monitoring] Failed to generate metrics: {e}")
        return error_response(str(e), 500)


@monitoring_bp.route("/metrics/json", methods=["GET"])
@require_auth
async def metrics_json():
    """Return all metrics as JSON for WebUI dashboard consumption."""
    try:
        result = {}
        for metric in REGISTRY.collect():
            for sample in metric.samples:
                name = sample.name
                labels = sample.labels
                value = sample.value
                key = name
                if labels:
                    label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
                    key = f"{name}{{{label_str}}}"
                result[key] = value

        return jsonify({
            "metrics": result,
            "timestamp": time.time(),
        }), 200
    except Exception as e:
        logger.error(f"[Monitoring] Failed to serialize metrics: {e}")
        return error_response(str(e), 500)


@monitoring_bp.route("/health", methods=["GET"])
@require_auth
async def health_check():
    """Return health check results for all subsystems."""
    try:
        container = get_container()
        checker = getattr(container, "health_checker", None)
        if checker is None:
            checker = HealthChecker(
                service_registry=_get_service_registry(container),
                cache_manager=_get_cache_manager(),
                llm_adapter=container.llm_adapter,
            )

        summary = checker.get_summary()
        return jsonify(summary), 200
    except Exception as e:
        logger.error(f"[Monitoring] Health check failed: {e}")
        return error_response(str(e), 500)


@monitoring_bp.route("/functions", methods=["GET"])
@require_auth
async def function_metrics():
    """Return structured function-level metrics for the WebUI.

    Only populated when config.debug_mode is True and @monitored
    decorators have been triggered.  Results are sorted by average
    duration descending so the slowest functions appear first.
    """
    try:
        from ...services.monitoring.instrumentation import (
            is_debug_mode,
            _func_histograms,
            _func_counters,
            _func_error_counters,
        )

        functions = []
        for fqn, histogram in _func_histograms.items():
            calls = 0
            errors = 0
            duration_count = 0
            duration_sum = 0.0
            buckets = {}

            counter = _func_counters.get(fqn)
            if counter:
                for sample in counter.collect()[0].samples:
                    if sample.name.endswith("_total"):
                        calls = int(sample.value)

            error_counter = _func_error_counters.get(fqn)
            if error_counter:
                for sample in error_counter.collect()[0].samples:
                    if sample.name.endswith("_total"):
                        errors = int(sample.value)

            for sample in histogram.collect()[0].samples:
                if sample.name.endswith("_count"):
                    duration_count = int(sample.value)
                elif sample.name.endswith("_sum"):
                    duration_sum = sample.value
                elif sample.name.endswith("_bucket"):
                    le = sample.labels.get("le", "")
                    if le != "+Inf":
                        buckets[le] = int(sample.value)

            avg = duration_sum / duration_count if duration_count > 0 else 0.0
            error_rate = errors / calls if calls > 0 else 0.0

            functions.append({
                "name": fqn,
                "calls": calls,
                "errors": errors,
                "error_rate": round(error_rate, 4),
                "duration": {
                    "count": duration_count,
                    "sum": round(duration_sum, 4),
                    "avg": round(avg, 6),
                    "buckets": buckets,
                },
            })

        functions.sort(key=lambda f: f["duration"]["avg"], reverse=True)

        return jsonify({
            "debug_mode": is_debug_mode(),
            "functions": functions,
            "timestamp": time.time(),
        }), 200
    except Exception as e:
        logger.error(f"[Monitoring] Failed to get function metrics: {e}")
        return error_response(str(e), 500)


@monitoring_bp.route("/profile/backends", methods=["GET"])
@require_auth
async def profile_backends():
    """Return the list of available profiling backends."""
    try:
        backends = _profiler.get_available_backends()
        return jsonify({"backends": backends}), 200
    except Exception as e:
        return error_response(str(e), 500)


@monitoring_bp.route("/profile/start", methods=["POST"])
@require_auth
async def start_profile():
    """Start an on-demand profiling session.

    Request body (JSON, all optional):
        - type: ``"cpu"`` (default) or ``"memory"``
        - backend: ``"yappi"`` or ``"cProfile"`` (CPU only, auto if omitted)
        - clock_type: ``"wall"`` or ``"cpu"`` (yappi only)
        - n_frames: int (memory only, default 10)
    """
    try:
        data = await request.get_json(silent=True) or {}
        profile_type = data.get("type", "cpu")

        if profile_type == "cpu":
            backend = data.get("backend")
            clock_type = data.get("clock_type", "wall")
            session_id = _profiler.start_cpu_profile(
                backend=backend, clock_type=clock_type,
            )
        elif profile_type == "memory":
            n_frames = data.get("n_frames", 10)
            session_id = _profiler.start_memory_trace(n_frames=n_frames)
        else:
            return error_response(f"Unknown profile type: {profile_type}", 400)

        return jsonify({
            "session_id": session_id,
            "type": profile_type,
            "status": "started",
        }), 200
    except Exception as e:
        logger.error(f"[Monitoring] Failed to start profile: {e}")
        return error_response(str(e), 500)


@monitoring_bp.route("/profile/<session_id>", methods=["GET"])
@require_auth
async def get_profile(session_id: str):
    """Get profiling session results.

    Query params:
        - top_n: Number of top entries (default 30)
        - type: ``"cpu"`` or ``"memory"`` (default ``"cpu"``)
    """
    try:
        profile_type = request.args.get("type", "cpu")
        top_n = int(request.args.get("top_n", "30"))

        if profile_type == "cpu":
            result = _profiler.stop_cpu_profile(session_id, top_n=top_n)
        elif profile_type == "memory":
            result = _profiler.get_memory_snapshot(session_id, top_n=top_n)
        else:
            return error_response(f"Unknown profile type: {profile_type}", 400)

        return jsonify(result), 200
    except Exception as e:
        logger.error(f"[Monitoring] Failed to get profile: {e}")
        return error_response(str(e), 500)


@monitoring_bp.route("/profile/<session_id>", methods=["DELETE"])
@require_auth
async def stop_profile(session_id: str):
    """Stop and cleanup a profiling session."""
    try:
        profile_type = request.args.get("type", "cpu")

        if profile_type == "cpu":
            result = _profiler.stop_cpu_profile(session_id)
        elif profile_type == "memory":
            result = _profiler.stop_memory_trace(session_id)
        else:
            return error_response(f"Unknown profile type: {profile_type}", 400)

        return jsonify(result), 200
    except Exception as e:
        logger.error(f"[Monitoring] Failed to stop profile: {e}")
        return error_response(str(e), 500)


def _get_service_registry(container):
    """Safely retrieve ServiceRegistry from the factory manager."""
    try:
        if container.factory_manager:
            sf = container.factory_manager.get_service_factory()
            return sf.get_service_registry()
    except Exception:
        pass
    return None


def _get_cache_manager():
    """Safely retrieve the global CacheManager singleton."""
    try:
        from ...utils.cache_manager import get_cache_manager
        return get_cache_manager()
    except Exception:
        return None
