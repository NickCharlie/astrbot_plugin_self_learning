"""
统一缓存管理器 - 使用 Cachetools
高性能、支持 TTL、LRU 等多种淘汰策略
"""
from typing import Any, Dict, Optional, Callable
from collections import defaultdict
from functools import wraps
import asyncio
from cachetools import TTLCache, LRUCache, Cache
from astrbot.api import logger


class CacheManager:
    """
    统一缓存管理器

    功能:
    1. 提供多种缓存策略 (TTL, LRU)
    2. 支持装饰器模式
    3. 统一的缓存接口
    4. 自动过期和淘汰
    """

    def __init__(self):
        """初始化缓存管理器"""
        # 不同用途的缓存实例
        # TTL 缓存 - 用于有明确过期时间的数据
        self.affection_cache = TTLCache(maxsize=2000, ttl=300) # 5分钟
        self.memory_cache = TTLCache(maxsize=1000, ttl=600) # 10分钟
        self.state_cache = TTLCache(maxsize=500, ttl=60) # 1分钟
        self.relation_cache = TTLCache(maxsize=1000, ttl=60) # 1分钟

        # LRU 缓存 - 用于需要保持热点数据的场景
        self.conversation_cache = LRUCache(maxsize=500)
        self.summary_cache = LRUCache(maxsize=200)

        # 通用缓存 - 使用LRU策略防止无界增长
        self.general_cache = LRUCache(maxsize=5000)

        # 缓存命中/未命中统计，用于监控和TTL调优
        self._hit_counts: Dict[str, int] = defaultdict(int)
        self._miss_counts: Dict[str, int] = defaultdict(int)

        logger.info("[缓存管理器] 初始化完成")

    def get(self, cache_name: str, key: str) -> Optional[Any]:
        """获取缓存值，同时记录命中/未命中统计

        Args:
            cache_name: 缓存名称 (affection/memory/state/relation等)
            key: 缓存键

        Returns:
            缓存值或 None
        """
        cache = self._get_cache(cache_name)
        if cache is None:
            return None

        result = cache.get(key)
        if result is not None:
            self._hit_counts[cache_name] += 1
        else:
            self._miss_counts[cache_name] += 1
        return result

    def set(self, cache_name: str, key: str, value: Any):
        """
        设置缓存值

        Args:
            cache_name: 缓存名称
            key: 缓存键
            value: 缓存值
        """
        cache = self._get_cache(cache_name)
        if cache is None:
            return

        cache[key] = value

    def delete(self, cache_name: str, key: str):
        """删除缓存值"""
        cache = self._get_cache(cache_name)
        if cache is None:
            return

        if key in cache:
            del cache[key]

    def clear(self, cache_name: str):
        """清空指定缓存"""
        cache = self._get_cache(cache_name)
        if cache is None:
            return

        cache.clear()
        logger.debug(f"[缓存管理器] 已清空缓存: {cache_name}")

    def clear_all(self):
        """清空所有缓存"""
        self.affection_cache.clear()
        self.memory_cache.clear()
        self.state_cache.clear()
        self.relation_cache.clear()
        self.conversation_cache.clear()
        self.summary_cache.clear()
        self.general_cache.clear()
        logger.info("[缓存管理器] 已清空所有缓存")

    def _get_cache(self, cache_name: str) -> Optional[Cache]:
        """获取缓存实例"""
        cache_map = {
            'affection': self.affection_cache,
            'memory': self.memory_cache,
            'state': self.state_cache,
            'relation': self.relation_cache,
            'conversation': self.conversation_cache,
            'summary': self.summary_cache,
            'general': self.general_cache,
        }
        cache = cache_map.get(cache_name)
        if cache is None:
            logger.warning(f"[缓存管理器] 未知的缓存名称: {cache_name}")
        return cache

    def get_stats(self, cache_name: str) -> dict:
        """
        获取缓存统计信息

        Returns:
            {'size': 当前大小, 'maxsize': 最大大小, 'currsize': 当前大小}
        """
        cache = self._get_cache(cache_name)
        if cache is None:
            return {}

        if hasattr(cache, 'maxsize'):
            return {
                'size': len(cache),
                'maxsize': cache.maxsize,
                'currsize': cache.currsize if hasattr(cache, 'currsize') else len(cache)
            }
        else:
            return {'size': len(cache)}

    def get_hit_rates(self) -> Dict[str, Dict[str, Any]]:
        """获取所有缓存的命中率统计

        Returns:
            以缓存名称为键的统计字典，包含hits、misses和hit_rate
        """
        stats = {}
        all_names = set(self._hit_counts.keys()) | set(self._miss_counts.keys())
        for name in all_names:
            hits = self._hit_counts.get(name, 0)
            misses = self._miss_counts.get(name, 0)
            total = hits + misses
            stats[name] = {
                'hits': hits,
                'misses': misses,
                'hit_rate': hits / total if total > 0 else 0.0,
            }
        return stats


# 装饰器

def cached(
    cache_name: str = 'general',
    key_func: Optional[Callable] = None,
    manager: Optional[CacheManager] = None
):
    """
    缓存装饰器 - 用于同步函数

    Args:
        cache_name: 缓存名称
        key_func: 生成缓存键的函数
        manager: 缓存管理器实例

    Examples:
        @cached(cache_name='affection', key_func=lambda g, u: f"{g}:{u}")
        def get_affection(group_id: str, user_id: str):
            return db.query(...)
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            if key_func:
                key = key_func(*args, **kwargs)
            else:
                key = f"{func.__name__}:{args}:{kwargs}"

            # 获取缓存管理器
            mgr = manager if manager else _global_cache_manager

            # 尝试从缓存获取
            cached_value = mgr.get(cache_name, key)
            if cached_value is not None:
                logger.debug(f"[缓存命中] {cache_name}:{key}")
                return cached_value

            # 调用原函数
            result = func(*args, **kwargs)

            # 写入缓存
            mgr.set(cache_name, key, result)

            return result
        return wrapper
    return decorator


def async_cached(
    cache_name: str = 'general',
    key_func: Optional[Callable] = None,
    manager: Optional[CacheManager] = None
):
    """
    异步缓存装饰器 - 用于异步函数

    Examples:
        @async_cached(cache_name='affection', key_func=lambda g, u: f"{g}:{u}")
        async def get_affection(group_id: str, user_id: str):
            return await db.query(...)
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 生成缓存键
            if key_func:
                key = key_func(*args, **kwargs)
            else:
                key = f"{func.__name__}:{args}:{kwargs}"

            # 获取缓存管理器
            mgr = manager if manager else _global_cache_manager

            # 尝试从缓存获取
            cached_value = mgr.get(cache_name, key)
            if cached_value is not None:
                logger.debug(f"[缓存命中] {cache_name}:{key}")
                return cached_value

            # 调用原函数
            result = await func(*args, **kwargs)

            # 写入缓存
            mgr.set(cache_name, key, result)

            return result
        return wrapper
    return decorator


# 全局单例

_global_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """
    获取全局缓存管理器单例

    Returns:
        CacheManager 实例
    """
    global _global_cache_manager

    if _global_cache_manager is None:
        _global_cache_manager = CacheManager()

    return _global_cache_manager
