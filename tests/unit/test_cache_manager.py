"""
Unit tests for CacheManager

Tests the unified cache management system:
- Cache get/set/delete/clear operations
- Named cache isolation (affection, memory, state, etc.)
- Hit rate statistics tracking
- Cache stats reporting
- Global singleton management
- Unknown cache name handling
"""
import pytest
from unittest.mock import patch

from utils.cache_manager import CacheManager, get_cache_manager, cached, async_cached


@pytest.mark.unit
@pytest.mark.utils
class TestCacheManagerOperations:
    """Test basic CacheManager CRUD operations."""

    def test_set_and_get(self):
        """Test setting and getting a cache value."""
        mgr = CacheManager()
        mgr.set("general", "key1", "value1")

        result = mgr.get("general", "key1")
        assert result == "value1"

    def test_get_nonexistent_key(self):
        """Test getting a nonexistent key returns None."""
        mgr = CacheManager()

        result = mgr.get("general", "nonexistent")
        assert result is None

    def test_delete_existing_key(self):
        """Test deleting an existing cache entry."""
        mgr = CacheManager()
        mgr.set("general", "key1", "value1")

        mgr.delete("general", "key1")

        assert mgr.get("general", "key1") is None

    def test_delete_nonexistent_key(self):
        """Test deleting a nonexistent key does not raise."""
        mgr = CacheManager()
        mgr.delete("general", "nonexistent")  # Should not raise

    def test_clear_specific_cache(self):
        """Test clearing a specific named cache."""
        mgr = CacheManager()
        mgr.set("affection", "k1", "v1")
        mgr.set("affection", "k2", "v2")

        mgr.clear("affection")

        assert mgr.get("affection", "k1") is None
        assert mgr.get("affection", "k2") is None

    def test_clear_all_caches(self):
        """Test clearing all caches at once."""
        mgr = CacheManager()
        mgr.set("affection", "k1", "v1")
        mgr.set("memory", "k2", "v2")
        mgr.set("general", "k3", "v3")

        mgr.clear_all()

        assert mgr.get("affection", "k1") is None
        assert mgr.get("memory", "k2") is None
        assert mgr.get("general", "k3") is None


@pytest.mark.unit
@pytest.mark.utils
class TestCacheManagerIsolation:
    """Test cache name isolation between different caches."""

    def test_different_caches_are_isolated(self):
        """Test same key in different caches are independent."""
        mgr = CacheManager()
        mgr.set("affection", "shared_key", "affection_value")
        mgr.set("memory", "shared_key", "memory_value")

        assert mgr.get("affection", "shared_key") == "affection_value"
        assert mgr.get("memory", "shared_key") == "memory_value"

    @pytest.mark.parametrize("cache_name", [
        "affection", "memory", "state", "relation",
        "context", "embedding_query",
        "conversation", "summary", "general",
    ])
    def test_all_named_caches_accessible(self, cache_name):
        """Test all named caches are accessible."""
        mgr = CacheManager()
        mgr.set(cache_name, "test_key", "test_value")

        result = mgr.get(cache_name, "test_key")
        assert result == "test_value"

    def test_unknown_cache_name_returns_none(self):
        """Test accessing an unknown cache name returns None."""
        mgr = CacheManager()

        result = mgr.get("unknown_cache", "key1")
        assert result is None

    def test_set_to_unknown_cache_does_not_raise(self):
        """Test setting to an unknown cache does not raise."""
        mgr = CacheManager()
        mgr.set("unknown_cache", "key1", "value1")  # Should not raise


@pytest.mark.unit
@pytest.mark.utils
class TestCacheManagerStats:
    """Test cache statistics and hit rate tracking."""

    def test_hit_rate_empty(self):
        """Test hit rates with no operations."""
        mgr = CacheManager()

        stats = mgr.get_hit_rates()
        assert stats == {}

    def test_hit_rate_tracking(self):
        """Test hit/miss tracking across operations."""
        mgr = CacheManager()
        mgr.set("general", "key1", "value1")

        # Hit
        mgr.get("general", "key1")
        # Miss
        mgr.get("general", "nonexistent")

        stats = mgr.get_hit_rates()
        assert "general" in stats
        assert stats["general"]["hits"] == 1
        assert stats["general"]["misses"] == 1
        assert stats["general"]["hit_rate"] == 0.5

    def test_get_stats_for_cache(self):
        """Test getting stats for a specific cache."""
        mgr = CacheManager()
        mgr.set("affection", "k1", "v1")

        stats = mgr.get_stats("affection")

        assert "size" in stats
        assert "maxsize" in stats
        assert stats["size"] == 1

    def test_get_stats_unknown_cache(self):
        """Test getting stats for unknown cache returns empty dict."""
        mgr = CacheManager()

        stats = mgr.get_stats("unknown")
        assert stats == {}


@pytest.mark.unit
@pytest.mark.utils
class TestCachedDecorator:
    """Test the synchronous cached decorator."""

    def test_cached_decorator_caches_result(self):
        """Test cached decorator returns cached result on second call."""
        mgr = CacheManager()
        call_count = 0

        @cached(cache_name="general", key_func=lambda x: f"key_{x}", manager=mgr)
        def expensive_func(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        result1 = expensive_func(5)
        result2 = expensive_func(5)

        assert result1 == 10
        assert result2 == 10
        assert call_count == 1  # Only called once

    def test_cached_decorator_different_keys(self):
        """Test cached decorator uses correct keys for different inputs."""
        mgr = CacheManager()

        @cached(cache_name="general", key_func=lambda x: f"key_{x}", manager=mgr)
        def add_one(x):
            return x + 1

        assert add_one(1) == 2
        assert add_one(2) == 3


@pytest.mark.unit
@pytest.mark.utils
class TestAsyncCachedDecorator:
    """Test the asynchronous cached decorator."""

    @pytest.mark.asyncio
    async def test_async_cached_decorator(self):
        """Test async cached decorator caches result."""
        mgr = CacheManager()
        call_count = 0

        @async_cached(
            cache_name="general",
            key_func=lambda x: f"async_key_{x}",
            manager=mgr,
        )
        async def async_expensive_func(x):
            nonlocal call_count
            call_count += 1
            return x * 3

        result1 = await async_expensive_func(7)
        result2 = await async_expensive_func(7)

        assert result1 == 21
        assert result2 == 21
        assert call_count == 1


@pytest.mark.unit
@pytest.mark.utils
class TestGlobalCacheManager:
    """Test global singleton cache manager."""

    def test_get_cache_manager_returns_instance(self):
        """Test get_cache_manager returns a CacheManager instance."""
        # Reset global to ensure clean state
        import utils.cache_manager as module
        module._global_cache_manager = None

        mgr = get_cache_manager()

        assert isinstance(mgr, CacheManager)

    def test_get_cache_manager_returns_same_instance(self):
        """Test get_cache_manager always returns the same singleton."""
        import utils.cache_manager as module
        module._global_cache_manager = None

        mgr1 = get_cache_manager()
        mgr2 = get_cache_manager()

        assert mgr1 is mgr2
