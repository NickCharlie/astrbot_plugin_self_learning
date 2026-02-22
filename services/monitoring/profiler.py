"""On-demand profiling interface.

Provides wrappers around stdlib profiling tools (``cProfile``,
``tracemalloc``) and the optional ``yappi`` library for async-aware
profiling. Profiling is NOT always-on -- sessions are started and
stopped explicitly via API endpoints or commands.

Backend selection:
    - ``yappi``: Preferred for async code. Measures wall/CPU time per
      coroutine accurately. Written in C, ~2.5x overhead. Optional
      dependency; detected at runtime.
    - ``cProfile``: Stdlib fallback. Works well for synchronous code.
      ~1.5x overhead.
    - ``tracemalloc``: Stdlib. Tracks memory allocations by file/line.
      Low overhead, safe for short production sessions.
"""

import cProfile
import io
import pstats
import time
import tracemalloc
import uuid
from typing import Any, Dict, List, Optional

from astrbot.api import logger

# Optional yappi import.
try:
    import yappi
    _HAS_YAPPI = True
except ImportError:
    yappi = None  # type: ignore[assignment]
    _HAS_YAPPI = False


class ProfileSession:
    """Manages on-demand profiling sessions.

    Each session is identified by a UUID and tracks its start/stop state.
    Multiple sessions can run concurrently (memory and CPU profiling are
    independent).
    """

    def __init__(self) -> None:
        self._cpu_sessions: Dict[str, Dict[str, Any]] = {}
        self._memory_sessions: Dict[str, Dict[str, Any]] = {}

    # -- Discovery ----------------------------------------------------------

    def get_available_backends(self) -> List[str]:
        """Return the list of available profiling backends."""
        backends = ["cProfile", "tracemalloc"]
        if _HAS_YAPPI:
            backends.insert(0, "yappi")
        return backends

    # -- CPU profiling ------------------------------------------------------

    def start_cpu_profile(
        self,
        backend: Optional[str] = None,
        clock_type: str = "wall",
    ) -> str:
        """Start a CPU profiling session.

        Args:
            backend: ``"yappi"`` or ``"cProfile"``. Auto-selects if None.
            clock_type: ``"wall"`` or ``"cpu"`` (yappi only).

        Returns:
            Session ID string.
        """
        session_id = uuid.uuid4().hex[:12]

        if backend is None:
            backend = "yappi" if _HAS_YAPPI else "cProfile"

        if backend == "yappi" and _HAS_YAPPI:
            yappi.set_clock_type(clock_type)
            yappi.clear_stats()
            yappi.start()
            self._cpu_sessions[session_id] = {
                "backend": "yappi",
                "start_time": time.time(),
                "clock_type": clock_type,
            }
            logger.info(f"[Profiler] Started yappi session {session_id} (clock={clock_type})")
        else:
            profiler = cProfile.Profile()
            profiler.enable()
            self._cpu_sessions[session_id] = {
                "backend": "cProfile",
                "profiler": profiler,
                "start_time": time.time(),
            }
            logger.info(f"[Profiler] Started cProfile session {session_id}")

        return session_id

    def stop_cpu_profile(self, session_id: str, top_n: int = 30) -> Dict[str, Any]:
        """Stop a CPU profiling session and return sorted statistics.

        Args:
            session_id: Session ID from ``start_cpu_profile``.
            top_n: Number of top entries to include.

        Returns:
            Dict with backend, duration, and top function stats.
        """
        session = self._cpu_sessions.pop(session_id, None)
        if session is None:
            return {"error": f"Session {session_id} not found"}

        duration = time.time() - session["start_time"]
        backend = session["backend"]

        if backend == "yappi":
            yappi.stop()
            stats = yappi.get_func_stats()
            entries = []
            for stat in stats[:top_n]:
                entries.append({
                    "name": stat.full_name,
                    "ncall": stat.ncall,
                    "tsub": round(stat.tsub, 6),
                    "ttot": round(stat.ttot, 6),
                    "tavg": round(stat.tavg, 6),
                })
            yappi.clear_stats()
            logger.info(f"[Profiler] Stopped yappi session {session_id}, duration={duration:.1f}s")
            return {
                "session_id": session_id,
                "backend": "yappi",
                "clock_type": session.get("clock_type", "wall"),
                "duration_s": round(duration, 2),
                "top_functions": entries,
            }

        # cProfile
        profiler: cProfile.Profile = session["profiler"]
        profiler.disable()
        stream = io.StringIO()
        ps = pstats.Stats(profiler, stream=stream)
        ps.sort_stats("cumulative")
        ps.print_stats(top_n)
        text_output = stream.getvalue()

        entries = []
        for key, (cc, nc, tt, ct, callers) in list(ps.stats.items())[:top_n]:
            filename, lineno, func_name = key
            entries.append({
                "name": f"{filename}:{lineno}({func_name})",
                "ncall": nc,
                "tottime": round(tt, 6),
                "cumtime": round(ct, 6),
            })

        logger.info(f"[Profiler] Stopped cProfile session {session_id}, duration={duration:.1f}s")
        return {
            "session_id": session_id,
            "backend": "cProfile",
            "duration_s": round(duration, 2),
            "top_functions": entries,
            "text_output": text_output,
        }

    # -- Memory profiling ---------------------------------------------------

    def start_memory_trace(self, n_frames: int = 10) -> str:
        """Start a memory allocation trace using ``tracemalloc``.

        Args:
            n_frames: Number of stack frames to capture per allocation.

        Returns:
            Session ID string.
        """
        session_id = uuid.uuid4().hex[:12]

        if tracemalloc.is_tracing():
            tracemalloc.stop()

        tracemalloc.start(n_frames)
        self._memory_sessions[session_id] = {
            "start_time": time.time(),
            "n_frames": n_frames,
        }
        logger.info(f"[Profiler] Started tracemalloc session {session_id} (frames={n_frames})")
        return session_id

    def get_memory_snapshot(
        self,
        session_id: str,
        top_n: int = 20,
        group_by: str = "lineno",
    ) -> Dict[str, Any]:
        """Take a memory snapshot and return top allocations.

        Args:
            session_id: Session ID from ``start_memory_trace``.
            top_n: Number of top entries to include.
            group_by: ``"lineno"`` or ``"filename"``.

        Returns:
            Dict with duration, current/peak memory, and top allocations.
        """
        session = self._memory_sessions.get(session_id)
        if session is None:
            return {"error": f"Session {session_id} not found"}

        if not tracemalloc.is_tracing():
            return {"error": "tracemalloc is not active"}

        snapshot = tracemalloc.take_snapshot()
        stats = snapshot.statistics(group_by)

        entries = []
        for stat in stats[:top_n]:
            entries.append({
                "location": str(stat),
                "size_kb": round(stat.size / 1024, 2),
                "count": stat.count,
            })

        current, peak = tracemalloc.get_traced_memory()
        duration = time.time() - session["start_time"]

        return {
            "session_id": session_id,
            "duration_s": round(duration, 2),
            "current_kb": round(current / 1024, 2),
            "peak_kb": round(peak / 1024, 2),
            "top_allocations": entries,
        }

    def stop_memory_trace(self, session_id: str) -> Dict[str, Any]:
        """Stop a memory trace session.

        Args:
            session_id: Session ID from ``start_memory_trace``.

        Returns:
            Final snapshot data before stopping.
        """
        result = self.get_memory_snapshot(session_id)
        session = self._memory_sessions.pop(session_id, None)
        if session is not None and tracemalloc.is_tracing():
            tracemalloc.stop()
        logger.info(f"[Profiler] Stopped tracemalloc session {session_id}")
        return result

    # -- Cleanup ------------------------------------------------------------

    def cleanup_all(self) -> None:
        """Stop all active profiling sessions."""
        for sid in list(self._cpu_sessions.keys()):
            try:
                self.stop_cpu_profile(sid)
            except Exception:
                pass
        for sid in list(self._memory_sessions.keys()):
            try:
                self.stop_memory_trace(sid)
            except Exception:
                pass
