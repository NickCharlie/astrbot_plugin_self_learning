"""Ring-buffer performance tracker for LLM hook timing.

Collects per-request timing samples and maintains rolling-average
statistics. Designed to be referenced by the WebUI ServiceContainer
as ``perf_collector``.
"""

import time
from collections import deque
from typing import Any, Dict, List


class PerfTracker:
    """Collects LLM hook timing data in a fixed-size ring buffer.

    Usage::

        tracker = PerfTracker(maxlen=200)
        tracker.record({"total_ms": 123, "social_ctx_ms": 45, ...})
        data = tracker.get_perf_data(recent_limit=50)
    """

    _TIMING_KEYS = (
        "total_ms",
        "social_ctx_ms",
        "v2_ctx_ms",
        "diversity_ms",
        "jargon_ms",
    )

    def __init__(self, maxlen: int = 200) -> None:
        self._samples: deque = deque(maxlen=maxlen)
        self._stats: Dict[str, Any] = {
            "total_requests": 0,
            "avg_total_ms": 0,
            "avg_social_ctx_ms": 0,
            "avg_v2_ctx_ms": 0,
            "avg_diversity_ms": 0,
            "avg_jargon_ms": 0,
            "max_total_ms": 0,
            "last_updated": 0,
        }

    def record(self, sample: Dict[str, Any]) -> None:
        """Append a timing sample and update rolling statistics."""
        self._samples.append(sample)
        self._update_stats(sample)

    def get_perf_data(self, recent_limit: int = 50) -> Dict[str, Any]:
        """Return aggregated stats plus the most recent samples."""
        samples: List[Dict[str, Any]] = list(self._samples)[-recent_limit:]
        stats = {
            k: round(v, 1) if isinstance(v, float) else v
            for k, v in self._stats.items()
        }
        stats["recent_samples"] = samples
        return stats

    def _update_stats(self, sample: Dict[str, Any]) -> None:
        """Update rolling averages using Welford's online algorithm."""
        s = self._stats
        n = s["total_requests"] + 1
        for key in self._TIMING_KEYS:
            avg_key = f"avg_{key}"
            s[avg_key] = s[avg_key] + (sample.get(key, 0) - s[avg_key]) / n
        if sample.get("total_ms", 0) > s["max_total_ms"]:
            s["max_total_ms"] = sample["total_ms"]
        s["total_requests"] = n
        s["last_updated"] = time.time()
