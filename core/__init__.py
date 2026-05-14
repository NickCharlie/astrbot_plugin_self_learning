"""Plugin core module.

Core exports are loaded lazily so importing a focused submodule does not pull in
the full service factory and its runtime-only dependencies.
"""

_FACTORY_EXPORTS = {"ServiceFactory"}
_PATTERN_EXPORTS = {
    "ServiceRegistry",
    "AsyncServiceBase",
    "LearningContext",
    "LearningContextBuilder",
    "StrategyFactory",
}
_INTERFACE_EXPORTS = {
    "IMessageCollector",
    "IMessageFilter",
    "IStyleAnalyzer",
    "ILearningStrategy",
    "IQualityMonitor",
    "IPersonaManager",
    "IPersonaUpdater",
    "IPersonaBackupManager",
    "IDataStorage",
    "IServiceFactory",
    "IAsyncService",
    "IMLAnalyzer",
    "IIntelligentResponder",
    "ServiceLifecycle",
    "MessageData",
    "AnalysisResult",
    "LearningStrategyType",
    "AnalysisType",
    "ServiceError",
    "StyleAnalysisError",
    "ConfigurationError",
    "DataStorageError",
    "PersonaUpdateError",
}

__all__ = sorted(_FACTORY_EXPORTS | _PATTERN_EXPORTS | _INTERFACE_EXPORTS)


def __getattr__(name):
    if name in _FACTORY_EXPORTS:
        from .factory import ServiceFactory
        return ServiceFactory

    if name in _PATTERN_EXPORTS:
        from . import patterns
        return getattr(patterns, name)

    if name in _INTERFACE_EXPORTS:
        from . import interfaces
        return getattr(interfaces, name)

    raise AttributeError(f"module 'core' has no attribute {name!r}")
