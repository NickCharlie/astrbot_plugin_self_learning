"""
自学习插件异常定义
"""


class SelfLearningError(Exception):
    """自学习插件基础异常类"""
    pass


class ConfigurationError(SelfLearningError):
    """配置错误异常"""
    pass


class MessageCollectionError(SelfLearningError):
    """消息收集异常"""
    pass


class StyleAnalysisError(SelfLearningError):
    """风格分析异常"""
    pass


class PersonaUpdateError(SelfLearningError):
    """人格更新异常"""
    pass


class ModelAccessError(SelfLearningError):
    """模型访问异常"""
    pass


class DataStorageError(SelfLearningError):
    """数据存储异常"""
    pass


class LearningSchedulerError(SelfLearningError):
    """学习调度异常"""
    pass


class LearningError(SelfLearningError):
    """学习相关异常"""
    pass


class ServiceError(SelfLearningError):
    """服务相关异常"""
    pass


class ResponseError(SelfLearningError):
    """响应相关异常"""
    pass


class BackupError(SelfLearningError):
    """备份相关异常"""
    pass


class ExpressionLearningError(SelfLearningError):
    """表达模式学习异常"""
    pass


class MemoryGraphError(SelfLearningError):
    """记忆图系统异常"""
    pass


class TimeDecayError(SelfLearningError):
    """时间衰减异常"""
    pass


class MessageAnalysisError(SelfLearningError):
    """消息分析异常"""
    pass


class KnowledgeGraphError(SelfLearningError):
    """知识图谱异常"""
    pass
