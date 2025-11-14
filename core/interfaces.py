"""
插件核心接口定义 - 抽象接口和协议
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Protocol
from dataclasses import dataclass
from enum import Enum

from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import Context


class ServiceLifecycle(Enum):
    """服务生命周期状态"""
    CREATED = "created"
    INITIALIZING = "initializing"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class MessageData:
    """标准化消息数据结构"""
    sender_id: str
    sender_name: str
    message: str
    group_id: str
    timestamp: float
    platform: str
    message_id: Optional[str] = None
    reply_to: Optional[str] = None


@dataclass
class AnalysisResult:
    """分析结果基础结构"""
    success: bool
    confidence: float
    data: Dict[str, Any]
    timestamp: float = 0.0
    error: Optional[str] = None
    consistency_score: Optional[float] = None


@dataclass
class PersonaUpdateRecord:
    """需要人工审查的人格更新记录"""
    timestamp: float
    group_id: str
    update_type: str # 例如: "prompt_update", "style_attribute_update"
    original_content: str # 更新前的内容
    new_content: str # 更新后的内容
    reason: str # 需要审查的原因
    confidence_score: float = 0.5  # 置信度得分
    id: Optional[int] = None # 数据库ID
    status: str = "pending" # "pending", "approved", "rejected"
    reviewer_comment: Optional[str] = None
    review_time: Optional[float] = None


class IMessageCollector(ABC):
    """消息收集器接口"""
    
    @abstractmethod
    async def collect_message(self, message_data: MessageData) -> bool:
        """收集消息"""
        pass
    
    @abstractmethod
    async def get_unprocessed_messages(self, limit: int = 100) -> List[MessageData]:
        """获取未处理的消息"""
        pass
    
    @abstractmethod
    async def mark_messages_processed(self, message_ids: List[str]) -> bool:
        """标记消息为已处理"""
        pass
    
    @abstractmethod
    async def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        pass


class IMessageFilter(ABC):
    """消息过滤器接口"""
    
    @abstractmethod
    async def filter_message(self, message: str) -> AnalysisResult:
        """过滤消息"""
        pass
    
    @abstractmethod
    async def is_suitable_for_learning(self, message: str) -> bool:
        """判断消息是否适合学习"""
        pass


class IStyleAnalyzer(ABC):
    """风格分析器接口"""
    
    @abstractmethod
    async def analyze_conversation_style(self, group_id: str, messages: List[MessageData]) -> AnalysisResult:
        """分析对话风格"""
        pass
    
    @abstractmethod
    async def compare_styles(self, style1: Dict[str, Any], style2: Dict[str, Any]) -> float:
        """比较风格相似度"""
        pass
    
    @abstractmethod
    async def get_style_trends(self) -> Dict[str, Any]:
        """获取风格趋势分析"""
        pass


class ILearningStrategy(ABC):
    """学习策略接口"""
    
    @abstractmethod
    async def execute_learning_cycle(self, messages: List[MessageData]) -> AnalysisResult:
        """执行学习周期"""
        pass
    
    @abstractmethod
    async def should_learn(self, context: Dict[str, Any]) -> bool:
        """判断是否应该学习"""
        pass


class IQualityMonitor(ABC):
    """质量监控器接口"""
    
    @abstractmethod
    async def evaluate_learning_quality(self, before: Dict[str, Any], after: Dict[str, Any]) -> AnalysisResult:
        """评估学习质量"""
        pass
    
    @abstractmethod
    async def detect_quality_issues(self, data: Dict[str, Any]) -> List[str]:
        """检测质量问题"""
        pass


class IPersonaManager(ABC):
    """人格管理器接口 - 负责协调人格的更新、备份和恢复"""
    
    @abstractmethod
    async def update_persona(self, style_data: Dict[str, Any], messages: List[MessageData]) -> bool:
        """更新人格"""
        pass
    
    @abstractmethod
    async def backup_persona(self, reason: str) -> int:
        """备份人格"""
        pass
    
    @abstractmethod
    async def restore_persona(self, backup_id: int) -> bool:
        """恢复人格"""
        pass


class IPersonaUpdater(ABC):
    """人格更新器接口 - 负责执行具体的人格更新逻辑"""
    
    @abstractmethod
    async def update_persona_with_style(self, group_id: str, style_analysis: Dict[str, Any], filtered_messages: List[MessageData]) -> bool:
        """根据风格分析和筛选过的消息更新人格"""
        pass

    @abstractmethod
    async def record_persona_update_for_review(self, record: PersonaUpdateRecord) -> int:
        """记录需要人工审查的人格更新"""
        pass

    @abstractmethod
    async def get_pending_persona_updates(self) -> List[PersonaUpdateRecord]:
        """获取所有待审查的人格更新"""
        pass

    @abstractmethod
    async def review_persona_update(self, update_id: int, status: str, reviewer_comment: Optional[str] = None) -> bool:
        """审查人格更新"""
        pass


class IPersonaBackupManager(ABC):
    """人格备份管理器接口 - 负责人格的备份和恢复存储"""
    
    @abstractmethod
    async def create_backup_before_update(self, persona_id: str, reason: str) -> int:
        """在更新前创建人格备份"""
        pass
    
    @abstractmethod
    async def get_backup(self, backup_id: int) -> Optional[Dict[str, Any]]:
        """获取指定ID的人格备份"""
        pass
    
    @abstractmethod
    async def list_backups(self) -> List[Dict[str, Any]]:
        """列出所有可用的人格备份"""
        pass
    
    @abstractmethod
    async def delete_backup(self, backup_id: int) -> bool:
        """删除指定ID的人格备份"""
        pass


class IDataStorage(ABC):
    """数据存储接口"""
    
    @abstractmethod
    async def save_data(self, key: str, data: Any) -> bool:
        """保存数据"""
        pass
    
    @abstractmethod
    async def load_data(self, key: str) -> Optional[Any]:
        """加载数据"""
        pass
    
    @abstractmethod
    async def delete_data(self, key: str) -> bool:
        """删除数据"""
        pass


class IObserver(ABC):
    """观察者接口"""
    
    @abstractmethod
    async def on_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """处理事件"""
        pass


class IEventPublisher(ABC):
    """事件发布器接口"""
    
    @abstractmethod
    async def publish_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """发布事件"""
        pass
    
    @abstractmethod
    def subscribe(self, event_type: str, observer: IObserver) -> None:
        """订阅事件"""
        pass
    
    @abstractmethod
    def unsubscribe(self, event_type: str, observer: IObserver) -> None:
        """取消订阅"""
        pass


class IMessageRelationshipAnalyzer(ABC):
    """消息关系分析器接口"""
    
    @abstractmethod
    async def analyze_message_relationships(self, messages: List[Dict[str, Any]], group_id: str) -> List[Any]:
        """分析消息之间的关系"""
        pass
    
    @abstractmethod
    async def get_conversation_pairs(self, relationships: List[Any]) -> List[tuple]:
        """从关系中提取对话对"""
        pass
    
    @abstractmethod
    async def analyze_conversation_quality(self, relationships: List[Any]) -> Dict[str, Any]:
        """分析对话质量"""
        pass


class IServiceFactory(ABC):
    """服务工厂接口"""
    
    @abstractmethod
    def create_message_collector(self) -> IMessageCollector:
        """创建消息收集器"""
        pass
    
    @abstractmethod
    def create_style_analyzer(self) -> IStyleAnalyzer:
        """创建风格分析器"""
        pass
    
    @abstractmethod
    def create_learning_strategy(self, strategy_type: str) -> ILearningStrategy:
        """创建学习策略"""
        pass
    
    @abstractmethod
    def create_quality_monitor(self) -> IQualityMonitor:
        """创建质量监控器"""
        pass
    
    @abstractmethod
    def create_persona_updater(self) -> IPersonaUpdater:
        """创建人格更新器"""
        pass
    
    @abstractmethod
    def create_message_relationship_analyzer(self) -> IMessageRelationshipAnalyzer:
        """创建消息关系分析器"""
        pass
    
    def get_persona_updater(self) -> Optional[IPersonaUpdater]:
        """获取已创建的人格更新器实例，如果不存在则创建（默认实现）"""
        return self.create_persona_updater()


class IAsyncService(ABC):
    """异步服务基础接口"""
    
    @property
    @abstractmethod
    def status(self) -> ServiceLifecycle:
        """服务状态"""
        pass
    
    @abstractmethod
    async def start(self) -> bool:
        """启动服务"""
        pass
    
    @abstractmethod
    async def stop(self) -> bool:
        """停止服务"""
        pass
    
    @abstractmethod
    async def restart(self) -> bool:
        """重启服务"""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """健康检查"""
        pass


class IConfigurable(Protocol):
    """可配置接口协议"""
    
    def update_config(self, config: Dict[str, Any]) -> bool:
        """更新配置"""
        ...
    
    def get_config(self) -> Dict[str, Any]:
        """获取配置"""
        ...


class IMetricsProvider(Protocol):
    """指标提供者协议"""
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取指标"""
        ...
    
    def reset_metrics(self) -> None:
        """重置指标"""
        ...


class ILearningSession(ABC):
    """学习会话接口"""
    
    @abstractmethod
    async def start_session(self, context: Dict[str, Any]) -> str:
        """开始学习会话"""
        pass
    
    @abstractmethod
    async def add_message(self, session_id: str, message: MessageData) -> bool:
        """添加消息到会话"""
        pass
    
    @abstractmethod
    async def complete_session(self, session_id: str) -> AnalysisResult:
        """完成学习会话"""
        pass
    
    @abstractmethod
    async def abort_session(self, session_id: str) -> bool:
        """中止学习会话"""
        pass


class IMLAnalyzer(ABC):
    """机器学习分析器接口"""
    
    @abstractmethod
    async def analyze_user_behavior(self, user_id: str, messages: List[MessageData]) -> AnalysisResult:
        """分析用户行为"""
        pass
    
    @abstractmethod
    async def cluster_messages(self, messages: List[MessageData]) -> AnalysisResult:
        """消息聚类"""
        pass
    
    @abstractmethod
    async def predict_response_quality(self, message: str, response: str) -> float:
        """预测回复质量"""
        pass


class IIntelligentResponder(ABC):
    """智能回复器接口"""
    
    @abstractmethod
    async def should_respond(self, event: AstrMessageEvent) -> bool:
        """判断是否应该回复"""
        pass
    
    @abstractmethod
    async def generate_response(self, event: AstrMessageEvent) -> Optional[str]:
        """生成回复"""
        pass
    
    @abstractmethod
    async def send_response(self, event: AstrMessageEvent) -> bool:
        """发送回复"""
        pass


class IPersonaManagerUpdater(ABC):
    """PersonaManager增量更新接口"""
    
    @abstractmethod
    async def apply_incremental_update(self, group_id: str, update_content: str) -> bool:
        """应用增量更新到PersonaManager中的persona"""
        pass
    
    @abstractmethod
    async def create_incremental_persona(self, base_persona_id: str, group_id: str, increments: List[str]) -> str:
        """基于基础persona创建增量更新的新persona"""
        pass
    
    @abstractmethod
    async def get_or_create_group_persona(self, group_id: str, base_persona_id: str = None) -> str:
        """获取或创建群组专用persona"""
        pass
    
    @abstractmethod
    async def merge_incremental_updates(self, persona_id: str, new_content: str) -> bool:
        """将新的增量内容合并到现有persona的末尾"""
        pass
    
    @abstractmethod
    async def cleanup_old_personas(self, group_id: str, keep_count: int = 5) -> bool:
        """清理旧的增量persona，只保留最新的几个"""
        pass



# 策略枚举
class LearningStrategyType(Enum):
    """学习策略类型"""
    PROGRESSIVE = "progressive"
    BATCH = "batch"
    REALTIME = "realtime"
    HYBRID = "hybrid"


class AnalysisType(Enum):
    """分析类型"""
    STYLE = "style"
    SENTIMENT = "sentiment"
    TOPIC = "topic"
    BEHAVIOR = "behavior"
    QUALITY = "quality"


class EventType(Enum):
    """事件类型"""
    MESSAGE_COLLECTED = "message_collected"
    MESSAGE_FILTERED = "message_filtered"
    STYLE_ANALYZED = "style_analyzed"
    PERSONA_UPDATED = "persona_updated"
    LEARNING_COMPLETED = "learning_completed"
    QUALITY_ISSUE_DETECTED = "quality_issue_detected"
    SERVICE_STATUS_CHANGED = "service_status_changed"


# 异常类型 (从 exceptions.py 导入，避免重复定义)
from ..exceptions import SelfLearningError, ConfigurationError, DataStorageError, MessageCollectionError, StyleAnalysisError, PersonaUpdateError, ModelAccessError, LearningSchedulerError, ServiceError
