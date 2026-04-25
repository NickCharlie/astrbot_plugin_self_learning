"""
全局 LLM 请求限流器 — Token Bucket + 并发控制 + 429 指数退避/抖动重试

设计目标：
1. 所有 LLM 调用在发送前必须通过 ``wait_for_token()`` 获取令牌
2. 支持令牌桶（控制 RPM）与并发上限（控制同时飞行请求数）
3. 429 重试使用统一 ``backoff_delay()`` 实现指数退避 + 全抖动
4. 学习系统的批量任务通过 ``acquire_concurrency_slot()`` 排队执行
"""
import asyncio
import random
import time
from typing import Optional

from astrbot.api import logger


class RateLimiter:
    """全局 LLM 请求限流器（单例）

    结合令牌桶（控制每分钟请求数）和异步信号量（控制并发请求数）。

    Args:
        max_requests_per_minute: 每分钟最大请求数。0 表示不限制。
        max_concurrent_requests: 最大并发请求数。0 表示不限制。
        retry_max_attempts: 429 后最大重试次数。
        retry_base_delay: 指数退避基数（秒）。
        retry_max_delay: 最大退避延迟（秒）。
        retry_jitter: 是否启用全抖动（Full Jitter）。
    """

    def __init__(
        self,
        max_requests_per_minute: int = 60,
        max_concurrent_requests: int = 3,
        retry_max_attempts: int = 4,
        retry_base_delay: float = 2.0,
        retry_max_delay: float = 60.0,
        retry_jitter: bool = True,
    ) -> None:
        # Token bucket state
        self.max_rpm = max_requests_per_minute
        self._tokens: float = float(max_requests_per_minute)
        self._last_refill: float = time.monotonic()
        self._bucket_lock = asyncio.Lock()

        # Concurrency semaphore
        self._concurrency_sem: Optional[asyncio.Semaphore] = None
        if max_concurrent_requests > 0:
            self._concurrency_sem = asyncio.Semaphore(max_concurrent_requests)
            self._max_concurrent = max_concurrent_requests
        else:
            self._max_concurrent = 0

        # Retry config
        self.retry_max_attempts = retry_max_attempts
        self.retry_base_delay = retry_base_delay
        self.retry_max_delay = retry_max_delay
        self.retry_jitter = retry_jitter

        # Stats
        self.total_acquisitions: int = 0
        self.total_retries: int = 0
        self.total_429s: int = 0

        logger.info(
            f"[RateLimiter] 初始化: RPM={max_requests_per_minute}, "
            f"MaxConcurrent={max_concurrent_requests}, "
            f"Retry(max={retry_max_attempts}, base={retry_base_delay}s, "
            f"max={retry_max_delay}s, jitter={retry_jitter})"
        )

    # -- Public API ---------------------------------------------------------

    async def wait_for_token(self) -> None:
        """等待直到获得一个令牌。

        使用令牌桶算法：以 ``max_rpm / 60`` 的速率补充令牌。
        如果 ``max_rpm <= 0`` 则直接返回（不限制）。
        """
        if self.max_rpm <= 0:
            return

        while True:
            async with self._bucket_lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    self.total_acquisitions += 1
                    return
            # 令牌不足，等待补充周期后重试
            await asyncio.sleep(60.0 / self.max_rpm)

    async def acquire_concurrency_slot(self) -> None:
        """获取并发槽位（如果配置了并发上限）。

        调用方应在 LLM 请求完成后调用 ``release_concurrency_slot()``。
        """
        if self._concurrency_sem is not None:
            await self._concurrency_sem.acquire()

    def release_concurrency_slot(self) -> None:
        """释放并发槽位。"""
        if self._concurrency_sem is not None:
            self._concurrency_sem.release()

    def backoff_delay(self, attempt: int, server_retry_after: Optional[float] = None) -> float:
        """计算 429 后的退避延迟（秒），并实际 sleep。

        优先级：
        1. 如果服务器返回 ``Retry-After`` 头，优先使用该值 + 小抖动
        2. 否则使用指数退避 + 全抖动::

            delay = min(base_delay * 2^attempt, max_delay)
            delay = random.uniform(0, delay)  # Full Jitter

        Args:
            attempt: 当前重试次数（从 0 开始）。
            server_retry_after: 服务器返回的 Retry-After 秒数（如有）。

        Returns:
            实际 sleep 的秒数。
        """
        if server_retry_after is not None and server_retry_after > 0:
            # 尊重服务器建议 + 0~1s 抖动避免同时对齐
            delay = server_retry_after + random.uniform(0, 1.0)
        else:
            exponential = self.retry_base_delay * (2 ** attempt)
            capped = min(exponential, self.retry_max_delay)
            if self.retry_jitter:
                delay = random.uniform(0, capped)  # Full Jitter
            else:
                delay = capped

        logger.info(
            f"[RateLimiter] 429 退避: attempt={attempt + 1}, "
            f"delay={delay:.2f}s"
        )
        self.total_429s += 1
        self.total_retries += 1
        time.sleep(0)  # yield to event loop (no-op, keeps sync signature)
        return delay

    async def backoff_delay_async(
        self, attempt: int, server_retry_after: Optional[float] = None
    ) -> None:
        """异步版本的 ``backoff_delay``，会自动 await sleep。"""
        delay = self.backoff_delay(attempt, server_retry_after)
        await asyncio.sleep(delay)

    def update_config(
        self,
        max_requests_per_minute: Optional[int] = None,
        max_concurrent_requests: Optional[int] = None,
    ) -> None:
        """运行时更新限流配置。"""
        if max_requests_per_minute is not None:
            self.max_rpm = max_requests_per_minute
            if max_requests_per_minute > 0:
                self._tokens = min(self._tokens, float(max_requests_per_minute))

        if max_concurrent_requests is not None:
            if max_concurrent_requests > 0:
                self._concurrency_sem = asyncio.Semaphore(max_concurrent_requests)
                self._max_concurrent = max_concurrent_requests
            else:
                self._concurrency_sem = None
                self._max_concurrent = 0

    def get_stats(self) -> dict:
        """返回限流统计。"""
        return {
            "total_acquisitions": self.total_acquisitions,
            "total_retries": self.total_retries,
            "total_429s": self.total_429s,
            "current_tokens": round(self._tokens, 2),
            "max_concurrent": self._max_concurrent,
        }

    # -- Internal -----------------------------------------------------------

    def _refill(self) -> None:
        """补充令牌（必须在 ``_bucket_lock`` 内调用）。"""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._last_refill = now
        refill_amount = elapsed * (self.max_rpm / 60.0)
        self._tokens = min(self._tokens + refill_amount, float(self.max_rpm))


# -- 全局单例 ---------------------------------------------------------------

_global_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """获取全局限流器单例。"""
    global _global_rate_limiter
    if _global_rate_limiter is None:
        _global_rate_limiter = RateLimiter()
    return _global_rate_limiter


def init_rate_limiter(
    max_requests_per_minute: int = 60,
    max_concurrent_requests: int = 3,
    retry_max_attempts: int = 4,
    retry_base_delay: float = 2.0,
    retry_max_delay: float = 60.0,
    retry_jitter: bool = True,
) -> RateLimiter:
    """初始化全局限流器（应在插件启动时调用一次）。"""
    global _global_rate_limiter
    _global_rate_limiter = RateLimiter(
        max_requests_per_minute=max_requests_per_minute,
        max_concurrent_requests=max_concurrent_requests,
        retry_max_attempts=retry_max_attempts,
        retry_base_delay=retry_base_delay,
        retry_max_delay=retry_max_delay,
        retry_jitter=retry_jitter,
    )
    return _global_rate_limiter
