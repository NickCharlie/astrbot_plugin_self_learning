"""
插件核心模块
"""

from .factory import ServiceFactory
from .patterns import ServiceRegistry, AsyncServiceBase, LearningContext, LearningContextBuilder, StrategyFactory
from .interfaces import (
    IMessageCollector, IMessageFilter, IStyleAnalyzer, ILearningStrategy,
    IQualityMonitor, IPersonaManager, IPersonaUpdater, IPersonaBackupManager,
    IDataStorage, IServiceFactory, IAsyncService,
    IMLAnalyzer, IIntelligentResponder, ServiceLifecycle, MessageData,
    AnalysisResult, LearningStrategyType, AnalysisType,
    ServiceError, StyleAnalysisError, ConfigurationError, DataStorageError, PersonaUpdateError
)

__all__ = [
    'ServiceFactory',
    'ServiceRegistry',
    'AsyncServiceBase',
    'LearningContext',
    'LearningContextBuilder',
    'StrategyFactory',
    'IMessageCollector',
    'IMessageFilter',
    'IStyleAnalyzer',
    'ILearningStrategy',
    'IQualityMonitor',
    'IPersonaManager',
    'IPersonaUpdater',
    'IPersonaBackupManager',
    'IDataStorage',
    'IServiceFactory',
    'IAsyncService',
    'IMLAnalyzer',
    'IIntelligentResponder',
    'ServiceLifecycle',
    'MessageData',
    'AnalysisResult',
    'LearningStrategyType',
    'AnalysisType',
    'ServiceError',
    'ConfigurationError',
    'DataStorageError',
    'PersonaUpdateError'
]
