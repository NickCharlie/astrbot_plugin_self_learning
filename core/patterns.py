
import abc
from typing import Dict, List, Optional, Any, Type
from dataclasses import dataclass, field
from datetime import datetime

from astrbot.api import logger # 导入 logger

from .interfaces import (
    IServiceFactory, ILearningStrategy,
    IAsyncService, ServiceLifecycle, LearningStrategyType,
    MessageData, AnalysisResult, IMessageCollector, IStyleAnalyzer,
    IQualityMonitor, IPersonaManager, ServiceError
)


class SingletonABCMeta(abc.ABCMeta):
    """结合单例和ABC的元类"""
    _instances = {}
    
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


class AsyncServiceBase(IAsyncService):
    """异步服务基类"""
    
    def __init__(self, name: str):
        self.name = name
        self._status = ServiceLifecycle.CREATED
        self._logger = logger
    
    @property
    def status(self) -> ServiceLifecycle:
        return self._status
    
    async def _change_status(self, new_status: ServiceLifecycle):
        """改变服务状态"""
        old_status = self._status
        self._status = new_status
        self._logger.info(f"服务状态变更: {old_status.value} -> {new_status.value}")
    
    async def start(self) -> bool:
        """启动服务"""
        try:
            if self._status == ServiceLifecycle.RUNNING:
                return True
            
            await self._change_status(ServiceLifecycle.INITIALIZING)
            success = await self._do_start()
            
            if success:
                await self._change_status(ServiceLifecycle.RUNNING)
                self._logger.info("服务启动成功")
            else:
                await self._change_status(ServiceLifecycle.ERROR)
                self._logger.error("服务启动失败")
            
            return success
            
        except Exception as e:
            await self._change_status(ServiceLifecycle.ERROR)
            self._logger.error(f"服务启动异常: {e}")
            return False
    
    async def stop(self) -> bool:
        """停止服务"""
        try:
            if self._status == ServiceLifecycle.STOPPED:
                return True
            
            await self._change_status(ServiceLifecycle.STOPPING)
            success = await self._do_stop()
            
            if success:
                await self._change_status(ServiceLifecycle.STOPPED)
                self._logger.info("服务停止成功")
            else:
                await self._change_status(ServiceLifecycle.ERROR)
                self._logger.error("服务停止失败")
            
            return success
            
        except Exception as e:
            await self._change_status(ServiceLifecycle.ERROR)
            self._logger.error(f"服务停止异常: {e}")
            return False
    
    async def restart(self) -> bool:
        """重启服务"""
        self._logger.info("重启服务")
        return await self.stop() and await self.start()
    
    async def is_running(self) -> bool:
        """检查服务是否正在运行"""
        return self._status == ServiceLifecycle.RUNNING
    
    async def health_check(self) -> bool:
        """健康检查"""
        return self._status == ServiceLifecycle.RUNNING
    
    async def _do_start(self) -> bool:
        """子类实现具体启动逻辑"""
        return True
    
    async def _do_stop(self) -> bool:
        """子类实现具体停止逻辑"""
        return True


@dataclass
class LearningContext:
    """学习上下文 - 建造者模式数据"""
    messages: List[MessageData] = field(default_factory=list)
    strategy_type: LearningStrategyType = LearningStrategyType.PROGRESSIVE
    quality_threshold: float = 0.7
    max_iterations: int = 3
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


class LearningContextBuilder:
    """学习上下文建造者"""
    
    def __init__(self):
        self._context = LearningContext()
    
    def with_messages(self, messages: List[MessageData]) -> 'LearningContextBuilder':
        """设置消息"""
        self._context.messages = messages
        return self
    
    def with_strategy(self, strategy: LearningStrategyType) -> 'LearningContextBuilder':
        """设置学习策略"""
        self._context.strategy_type = strategy
        return self
    
    def with_quality_threshold(self, threshold: float) -> 'LearningContextBuilder':
        """设置质量阈值"""
        self._context.quality_threshold = threshold
        return self
    
    def with_max_iterations(self, iterations: int) -> 'LearningContextBuilder':
        """设置最大迭代次数"""
        self._context.max_iterations = iterations
        return self
    
    def with_metadata(self, key: str, value: Any) -> 'LearningContextBuilder':
        """添加元数据"""
        self._context.metadata[key] = value
        return self
    
    def build(self) -> LearningContext:
        """构建学习上下文"""
        return self._context


class ProgressiveLearningStrategy(ILearningStrategy):
    """渐进式学习策略"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._logger = logger
    
    async def execute_learning_cycle(self, messages: List[MessageData]) -> AnalysisResult:
        """执行渐进式学习"""
        self._logger.info(f"开始渐进式学习，消息数量: {len(messages)}")
        
        try:
            # 分批处理消息
            batch_size = self.config.get('batch_size', 50)
            results = []
            
            for i in range(0, len(messages), batch_size):
                batch = messages[i:i + batch_size]
                batch_result = await self._process_batch(batch)
                results.append(batch_result)
                
                # 小延迟避免过载
                # await asyncio.sleep(0.1) # 移除不必要的 sleep
            
            # 合并结果
            merged_result = self._merge_results(results)
            
            return AnalysisResult(
                success=True,
                confidence=merged_result.get('confidence', 0.8),
                data=merged_result,
                timestamp=datetime.now().timestamp()
            )
            
        except Exception as e:
            self._logger.error(f"渐进式学习失败: {e}")
            return AnalysisResult(
                success=False,
                confidence=0.0,
                data={},
                error=str(e),
                timestamp=datetime.now().timestamp()
            )
    
    async def should_learn(self, context: Dict[str, Any]) -> bool:
        """判断是否应该学习"""
        message_count = context.get('message_count', 0)
        last_learning_time = context.get('last_learning_time', 0)
        current_time = datetime.now().timestamp()
        
        # 检查消息数量和时间间隔
        min_messages = self.config.get('min_messages', 10)
        min_interval = self.config.get('min_interval_hours', 1) * 3600
        
        return (message_count >= min_messages and 
                current_time - last_learning_time >= min_interval)
    
    async def _process_batch(self, batch: List[MessageData]) -> Dict[str, Any]:
        """处理消息批次"""
        # 简化实现，实际应该调用具体的分析服务
        return {
            'processed_count': len(batch),
            'quality_score': 0.8,
            'confidence': 0.75
        }
    
    def _merge_results(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """合并批次结果"""
        total_processed = sum(r.get('processed_count', 0) for r in results)
        avg_confidence = sum(r.get('confidence', 0) for r in results) / max(len(results), 1)
        
        return {
            'total_processed': total_processed,
            'confidence': avg_confidence,
            'batch_count': len(results)
        }


class BatchLearningStrategy(ILearningStrategy):
    """批量学习策略"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._logger = logger
    
    async def execute_learning_cycle(self, messages: List[MessageData]) -> AnalysisResult:
        """执行批量学习"""
        self._logger.info(f"开始批量学习，消息数量: {len(messages)}")
        
        try:
            # 一次性处理所有消息
            result = await self._process_all_messages(messages)
            
            return AnalysisResult(
                success=True,
                confidence=result.get('confidence', 0.8),
                data=result,
                timestamp=datetime.now().timestamp()
            )
            
        except Exception as e:
            self._logger.error(f"批量学习失败: {e}")
            return AnalysisResult(
                success=False,
                confidence=0.0,
                data={},
                error=str(e),
                timestamp=datetime.now().timestamp()
            )
    
    async def should_learn(self, context: Dict[str, Any]) -> bool:
        """判断是否应该学习"""
        message_count = context.get('message_count', 0)
        batch_size = self.config.get('batch_size', 100)
        
        return message_count >= batch_size
    
    async def _process_all_messages(self, messages: List[MessageData]) -> Dict[str, Any]:
        """处理所有消息"""
        return {
            'processed_count': len(messages),
            'confidence': 0.85,
            'processing_time': datetime.now().timestamp()
        }


class StrategyFactory:
    """策略工厂"""
    
    _strategies: Dict[LearningStrategyType, Type[ILearningStrategy]] = {
        LearningStrategyType.PROGRESSIVE: ProgressiveLearningStrategy,
        LearningStrategyType.BATCH: BatchLearningStrategy,
        # 可以添加更多策略
    }
    
    @classmethod
    def create_strategy(cls, strategy_type: LearningStrategyType, config: Dict[str, Any]) -> ILearningStrategy:
        """创建学习策略"""
        if strategy_type not in cls._strategies:
            raise ValueError(f"不支持的策略类型: {strategy_type}")
        
        strategy_class = cls._strategies[strategy_type]
        return strategy_class(config)
    
    @classmethod
    def register_strategy(cls, strategy_type: LearningStrategyType, strategy_class: Type[ILearningStrategy]):
        """注册新的策略类型"""
        cls._strategies[strategy_type] = strategy_class


class ServiceRegistry(metaclass=SingletonABCMeta):
    """服务注册表 - 管理所有服务实例"""
    
    def __init__(self):
        self._services: Dict[str, IAsyncService] = {}
        self._logger = logger
    
    def register_service(self, name: str, service: IAsyncService):
        """注册服务"""
        self._services[name] = service
        self._logger.info(f"注册服务: {name}")
    
    def get_service(self, name: str) -> Optional[IAsyncService]:
        """获取服务"""
        return self._services.get(name)
    
    def unregister_service(self, name: str) -> bool:
        """注销服务"""
        if name in self._services:
            del self._services[name]
            self._logger.info(f"注销服务: {name}")
            return True
        return False
    
    async def start_all_services(self) -> bool:
        """启动所有服务"""
        self._logger.info("启动所有服务")
        results = []
        
        for name, service in self._services.items():
            try:
                result = await service.start()
                results.append(result)
                if not result:
                    self._logger.error(f"服务 {name} 启动失败")
            except Exception as e:
                self._logger.error(f"启动服务 {name} 异常: {e}")
                results.append(False)
        
        return all(results)
    
    _SERVICE_STOP_TIMEOUT = 5  # 每个服务停止的超时秒数

    async def stop_all_services(self) -> bool:
        """停止所有服务（每个服务带超时，避免卡死）"""
        import asyncio

        self._logger.info("停止所有服务")
        results = []

        for name, service in self._services.items():
            try:
                if hasattr(service, 'stop') and callable(getattr(service, 'stop')):
                    result = await asyncio.wait_for(
                        service.stop(),
                        timeout=self._SERVICE_STOP_TIMEOUT,
                    )
                    results.append(result)
                    if not result:
                        self._logger.error(f"服务 {name} 停止失败")
                    else:
                        self._logger.info(f"服务 {name} 已停止")
                else:
                    self._logger.warning(f"服务 {name} 没有stop方法，跳过停止")
                    results.append(True)
            except asyncio.TimeoutError:
                self._logger.warning(
                    f"服务 {name} 停止超时 ({self._SERVICE_STOP_TIMEOUT}s)，跳过"
                )
                results.append(False)
            except Exception as e:
                self._logger.error(f"停止服务 {name} 异常: {e}")
                results.append(False)

        return all(results)
    
    def get_service_status(self) -> Dict[str, str]:
        """获取所有服务状态"""
        result = {}
        for name, service in self._services.items():
            status = getattr(service, 'status', None)
            if status is not None:
                result[name] = status.value if hasattr(status, 'value') else str(status)
            else:
                # 没有 status 属性的服务，通过 _started 推断状态
                started = getattr(service, '_started', False)
                result[name] = ServiceLifecycle.RUNNING.value if started else ServiceLifecycle.CREATED.value
        return result


