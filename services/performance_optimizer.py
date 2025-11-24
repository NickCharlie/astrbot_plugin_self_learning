"""
并行化和异步优化服务 - 应用MaiBot的高性能架构

关键技术:
1. asyncio.gather 并行信息收集 (串行8s+ → 并行3.2s)
2. LLM判定缓存 (30秒TTL)
3. 非阻塞异步学习任务
4. 上下文哈希缓存
"""
import asyncio
import hashlib
import time
from typing import Dict, Any, Callable, Optional, List, Tuple
from functools import wraps
from astrbot.api import logger


class LLMResultCache:
    """
    LLM判定结果缓存

    MaiBot的关键优化: 30秒TTL缓存避免重复LLM调用
    缓存命中率可达60%+, 节省大量时间和API调用
    """

    def __init__(self, ttl: int = 30, max_size: int = 1000):
        """
        初始化LLM缓存

        Args:
            ttl: 缓存有效期(秒), 默认30秒
            max_size: 最大缓存条目数
        """
        self.cache: Dict[str, Tuple[Any, float]] = {}
        self.ttl = ttl
        self.max_size = max_size
        self.hits = 0
        self.misses = 0

    def _make_key(self, action_name: str, context: str) -> str:
        """
        生成缓存键

        Args:
            action_name: 操作名称
            context: 上下文内容

        Returns:
            缓存键
        """
        # 使用上下文的MD5哈希作为键的一部分
        context_hash = hashlib.md5(context.encode()).hexdigest()[:8]
        return f"{action_name}_{context_hash}"

    async def get_or_compute(
        self,
        action_name: str,
        context: str,
        compute_fn: Callable
    ) -> Any:
        """
        获取缓存值或计算新值

        Args:
            action_name: 操作名称
            context: 上下文内容
            compute_fn: 计算函数(异步)

        Returns:
            缓存或计算的结果
        """
        key = self._make_key(action_name, context)

        # 检查缓存
        if key in self.cache:
            result, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl:
                self.hits += 1
                logger.debug(f"缓存命中: {action_name}")
                return result

        # 计算新值
        self.misses += 1
        result = await compute_fn()
        self.cache[key] = (result, time.time())

        # 清理过期缓存
        self._cleanup()

        return result

    def get(self, action_name: str, context: str) -> Optional[Any]:
        """
        仅获取缓存值(不计算)

        Args:
            action_name: 操作名称
            context: 上下文内容

        Returns:
            缓存值或None
        """
        key = self._make_key(action_name, context)
        if key in self.cache:
            result, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl:
                return result
        return None

    def set(self, action_name: str, context: str, value: Any):
        """
        设置缓存值

        Args:
            action_name: 操作名称
            context: 上下文内容
            value: 要缓存的值
        """
        key = self._make_key(action_name, context)
        self.cache[key] = (value, time.time())
        self._cleanup()

    def _cleanup(self):
        """清理过期缓存"""
        now = time.time()
        expired_keys = [
            k for k, (_, ts) in self.cache.items()
            if now - ts > self.ttl
        ]
        for k in expired_keys:
            del self.cache[k]

        # 如果仍然超过最大大小,删除最旧的条目
        if len(self.cache) > self.max_size:
            sorted_items = sorted(
                self.cache.items(),
                key=lambda x: x[1][1]  # 按时间戳排序
            )
            # 删除最旧的20%
            to_remove = int(len(self.cache) * 0.2)
            for key, _ in sorted_items[:to_remove]:
                del self.cache[key]

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        total = self.hits + self.misses
        hit_rate = self.hits / total if total > 0 else 0
        return {
            'hits': self.hits,
            'misses': self.misses,
            'total': total,
            'hit_rate': f"{hit_rate:.1%}",
            'cache_size': len(self.cache)
        }

    def clear(self):
        """清空缓存"""
        self.cache.clear()
        self.hits = 0
        self.misses = 0


class ParallelTaskExecutor:
    """
    并行任务执行器

    MaiBot的关键优化: 使用asyncio.gather并行执行多个独立任务
    总耗时从串行的8秒+降低到并行的3-4秒
    """

    def __init__(self, timeout: float = 30.0):
        """
        初始化并行执行器

        Args:
            timeout: 单个任务的超时时间(秒)
        """
        self.timeout = timeout

    async def execute_parallel(
        self,
        tasks: Dict[str, Callable],
        return_exceptions: bool = True
    ) -> Dict[str, Any]:
        """
        并行执行多个任务

        Args:
            tasks: 任务字典 {任务名: 异步函数}
            return_exceptions: 是否返回异常而不是抛出

        Returns:
            结果字典 {任务名: 结果}
        """
        start_time = time.time()

        # 创建任务协程列表
        task_names = list(tasks.keys())
        task_coroutines = [
            asyncio.wait_for(task(), timeout=self.timeout)
            for task in tasks.values()
        ]

        # 并行执行
        results_list = await asyncio.gather(
            *task_coroutines,
            return_exceptions=return_exceptions
        )

        # 组装结果
        results = {}
        for name, result in zip(task_names, results_list):
            if isinstance(result, Exception):
                logger.warning(f"任务 {name} 执行失败: {result}")
                results[name] = None
            else:
                results[name] = result

        elapsed = time.time() - start_time
        logger.debug(f"并行执行 {len(tasks)} 个任务完成, 耗时: {elapsed:.2f}秒")

        return results

    async def execute_with_priority(
        self,
        high_priority_tasks: Dict[str, Callable],
        low_priority_tasks: Dict[str, Callable]
    ) -> Tuple[Dict[str, Any], asyncio.Task]:
        """
        执行带优先级的任务

        高优先级任务立即执行并等待结果
        低优先级任务在后台执行,不阻塞

        Args:
            high_priority_tasks: 高优先级任务字典
            low_priority_tasks: 低优先级任务字典

        Returns:
            (高优先级结果, 低优先级任务的Task对象)
        """
        # 立即执行高优先级任务
        high_results = await self.execute_parallel(high_priority_tasks)

        # 低优先级任务在后台执行
        async def run_low_priority():
            return await self.execute_parallel(low_priority_tasks)

        low_priority_task = asyncio.create_task(run_low_priority())

        return high_results, low_priority_task


class AsyncLearningScheduler:
    """
    异步学习任务调度器

    MaiBot的关键优化: 学习任务不阻塞主回复流程
    使用asyncio.create_task在后台执行学习
    """

    def __init__(self, max_concurrent: int = 5):
        """
        初始化学习调度器

        Args:
            max_concurrent: 最大并发学习任务数
        """
        self.max_concurrent = max_concurrent
        self.running_tasks: List[asyncio.Task] = []
        self.pending_tasks: List[Callable] = []
        self._lock = asyncio.Lock()

    async def schedule_learning(
        self,
        learning_fn: Callable,
        task_name: str = "learning"
    ) -> Optional[asyncio.Task]:
        """
        调度一个学习任务(非阻塞)

        Args:
            learning_fn: 学习函数(异步)
            task_name: 任务名称

        Returns:
            创建的Task对象或None(如果超过并发限制)
        """
        async with self._lock:
            # 清理已完成的任务
            self.running_tasks = [
                t for t in self.running_tasks
                if not t.done()
            ]

            # 检查是否可以启动新任务
            if len(self.running_tasks) >= self.max_concurrent:
                logger.debug(f"学习任务队列已满,延迟执行: {task_name}")
                self.pending_tasks.append(learning_fn)
                return None

            # 创建后台任务
            async def wrapped_task():
                try:
                    await learning_fn()
                    logger.debug(f"学习任务完成: {task_name}")
                except Exception as e:
                    logger.error(f"学习任务失败 {task_name}: {e}")
                finally:
                    # 尝试执行待处理的任务
                    await self._try_execute_pending()

            task = asyncio.create_task(wrapped_task())
            self.running_tasks.append(task)
            logger.debug(f"学习任务已调度: {task_name}")

            return task

    async def _try_execute_pending(self):
        """尝试执行待处理的任务"""
        async with self._lock:
            # 清理已完成的任务
            self.running_tasks = [
                t for t in self.running_tasks
                if not t.done()
            ]

            # 如果有空位且有待处理任务
            while (
                len(self.running_tasks) < self.max_concurrent
                and self.pending_tasks
            ):
                pending_fn = self.pending_tasks.pop(0)

                async def wrapped():
                    try:
                        await pending_fn()
                    except Exception as e:
                        logger.error(f"待处理学习任务失败: {e}")

                task = asyncio.create_task(wrapped())
                self.running_tasks.append(task)

    async def wait_all(self, timeout: float = 60.0) -> bool:
        """
        等待所有学习任务完成

        Args:
            timeout: 超时时间(秒)

        Returns:
            是否全部完成
        """
        if not self.running_tasks:
            return True

        try:
            await asyncio.wait_for(
                asyncio.gather(*self.running_tasks, return_exceptions=True),
                timeout=timeout
            )
            return True
        except asyncio.TimeoutError:
            logger.warning("等待学习任务超时")
            return False

    def get_status(self) -> Dict[str, Any]:
        """获取调度器状态"""
        return {
            'running_count': len([t for t in self.running_tasks if not t.done()]),
            'pending_count': len(self.pending_tasks),
            'max_concurrent': self.max_concurrent
        }


class PerformanceOptimizer:
    """
    性能优化器 - 整合所有优化功能

    提供:
    1. 并行信息收集
    2. LLM结果缓存
    3. 异步学习调度
    """

    def __init__(self, cache_ttl: int = 30):
        """初始化性能优化器"""
        self.cache = LLMResultCache(ttl=cache_ttl)
        self.executor = ParallelTaskExecutor()
        self.scheduler = AsyncLearningScheduler()

    async def collect_reply_context(
        self,
        tasks: Dict[str, Callable]
    ) -> Dict[str, Any]:
        """
        并行收集回复所需的上下文信息

        这是MaiBot高速回复的核心: 将原本串行的8秒+操作
        通过并行执行降低到3-4秒

        Args:
            tasks: 上下文收集任务字典

        Returns:
            收集到的上下文信息
        """
        return await self.executor.execute_parallel(tasks)

    async def cached_llm_call(
        self,
        action: str,
        context: str,
        llm_fn: Callable
    ) -> Any:
        """
        带缓存的LLM调用

        Args:
            action: 操作名称
            context: 上下文(用于生成缓存键)
            llm_fn: LLM调用函数

        Returns:
            LLM调用结果
        """
        return await self.cache.get_or_compute(action, context, llm_fn)

    async def schedule_background_learning(
        self,
        learning_fn: Callable,
        name: str = "learning"
    ):
        """
        调度后台学习任务(非阻塞)

        Args:
            learning_fn: 学习函数
            name: 任务名称
        """
        await self.scheduler.schedule_learning(learning_fn, name)

    def get_performance_stats(self) -> Dict[str, Any]:
        """获取性能统计"""
        return {
            'cache': self.cache.get_stats(),
            'scheduler': self.scheduler.get_status()
        }


# 全局性能优化器实例
_performance_optimizer: Optional[PerformanceOptimizer] = None


def get_performance_optimizer() -> PerformanceOptimizer:
    """获取全局性能优化器实例"""
    global _performance_optimizer
    if _performance_optimizer is None:
        _performance_optimizer = PerformanceOptimizer()
    return _performance_optimizer


# 装饰器: 自动缓存LLM调用结果
def cached_llm_result(action_name: str, context_key: str = None):
    """
    装饰器: 自动缓存LLM调用结果

    Args:
        action_name: 操作名称
        context_key: 用于缓存键的参数名(默认使用第一个参数)
    """
    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            optimizer = get_performance_optimizer()

            # 获取上下文
            if context_key and context_key in kwargs:
                context = str(kwargs[context_key])
            elif args:
                context = str(args[0])
            else:
                context = ""

            return await optimizer.cached_llm_call(
                action_name,
                context[:100],  # 只使用前100字符
                lambda: fn(*args, **kwargs)
            )
        return wrapper
    return decorator


# 装饰器: 非阻塞后台执行
def background_task(name: str = "background"):
    """
    装饰器: 将任务转为后台非阻塞执行

    Args:
        name: 任务名称
    """
    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            optimizer = get_performance_optimizer()
            await optimizer.schedule_background_learning(
                lambda: fn(*args, **kwargs),
                name
            )
        return wrapper
    return decorator
