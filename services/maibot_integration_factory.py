"""
MaiBot功能集成工厂 - 提供统一的外部接口
简化MaiBot增强功能的使用和集成
"""
from typing import Optional, Dict, Any, List
from astrbot.api import logger

from ..core.interfaces import MessageData
from ..config import PluginConfig
from .database_manager import DatabaseManager
from .maibot_enhanced_learning_manager import MaiBotEnhancedLearningManager
from .expression_pattern_learner import ExpressionPatternLearner
from .knowledge_graph_manager import KnowledgeGraphManager
from .time_decay_manager import TimeDecayManager


class MaiBotIntegrationFactory:
    """
    MaiBot功能集成工厂
    提供简化的API接口，隐藏内部复杂性
    采用单例模式确保全局一致性
    """

    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, config: PluginConfig = None, db_manager: DatabaseManager = None, context=None, llm_adapter=None):
        if self._initialized:
            return

        self.config = config
        self.db_manager = db_manager

        # 获取主管理器实例
        self.enhanced_manager = MaiBotEnhancedLearningManager.get_instance()

        # 初始化子管理器（如果还没有初始化）
        if config and db_manager:
            self.enhanced_manager.__init__(config, db_manager)

            # 确保子管理器也被正确初始化，传递所有必要参数
            ExpressionPatternLearner.get_instance(
                config=config,
                db_manager=db_manager,
                context=context,
                llm_adapter=llm_adapter
            )

            # 使用管理器工厂创建记忆管理器（根据配置选择实现）
            use_enhanced = getattr(config, 'use_enhanced_managers', False)
            if use_enhanced:
                logger.info("📦 [MaiBot工厂] 使用增强型记忆管理器")
                from .manager_factory import get_manager_factory
                manager_factory = get_manager_factory(config)
                self.memory_manager = manager_factory.create_memory_manager(
                    db_manager,
                    llm_adapter,
                    self.enhanced_manager.time_decay_manager
                )
            else:
                logger.info("📦 [MaiBot工厂] 使用原始记忆管理器")
                from .memory_graph_manager import MemoryGraphManager
                self.memory_manager = MemoryGraphManager.get_instance()
                self.memory_manager.__init__(config, db_manager,
                                           self.enhanced_manager.llm_adapter,
                                           self.enhanced_manager.time_decay_manager)

            KnowledgeGraphManager.get_instance().__init__(config, db_manager,
                                                         self.enhanced_manager.llm_adapter)

        self._initialized = True
    
    @classmethod
    def get_instance(cls) -> 'MaiBotIntegrationFactory':
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    async def start_all_services(self) -> bool:
        """启动所有MaiBot增强服务"""
        try:
            return await self.enhanced_manager.start()
        except Exception as e:
            logger.error(f"启动MaiBot服务失败: {e}")
            return False
    
    async def stop_all_services(self) -> bool:
        """停止所有MaiBot增强服务"""
        try:
            return await self.enhanced_manager.stop()
        except Exception as e:
            logger.error(f"停止MaiBot服务失败: {e}")
            return False
    
    async def process_message(self, message: MessageData, group_id: str) -> Dict[str, bool]:
        """
        处理消息 - 统一入口
        
        Args:
            message: 消息数据
            group_id: 群组ID
            
        Returns:
            处理结果
        """
        try:
            return await self.enhanced_manager.process_message(message, group_id)
        except Exception as e:
            logger.error(f"处理消息失败: {e}")
            return {}
    
    async def force_learning(self, group_id: str) -> Dict[str, Any]:
        """
        强制触发学习
        
        Args:
            group_id: 群组ID
            
        Returns:
            学习结果
        """
        try:
            return await self.enhanced_manager.force_learning_for_group(group_id)
        except Exception as e:
            logger.error(f"强制学习失败: {e}")
            return {'error': str(e)}
    
    async def get_learning_status(self, group_id: str) -> Dict[str, Any]:
        """
        获取学习状态
        
        Args:
            group_id: 群组ID
            
        Returns:
            学习状态信息
        """
        try:
            return await self.enhanced_manager.get_learning_status(group_id)
        except Exception as e:
            logger.error(f"获取学习状态失败: {e}")
            return {'error': str(e)}
    
    async def get_enhanced_context(self, query: str, group_id: str) -> Dict[str, Any]:
        """
        获取增强的上下文信息
        
        Args:
            query: 查询内容
            group_id: 群组ID
            
        Returns:
            增强的上下文信息
        """
        try:
            return await self.enhanced_manager.get_enhanced_context_for_response(query, group_id)
        except Exception as e:
            logger.error(f"获取增强上下文失败: {e}")
            return {}
    
    async def get_expression_patterns(self, group_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取表达模式
        
        Args:
            group_id: 群组ID
            limit: 返回数量限制
            
        Returns:
            表达模式列表
        """
        try:
            learner = ExpressionPatternLearner.get_instance()
            patterns = await learner.get_expression_patterns(group_id, limit)
            return [p.to_dict() for p in patterns]
        except Exception as e:
            logger.error(f"获取表达模式失败: {e}")
            return []
    
    async def query_knowledge_graph(self, query: str, group_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        查询知识图谱
        
        Args:
            query: 查询内容
            group_id: 群组ID
            limit: 返回数量限制
            
        Returns:
            查询结果
        """
        try:
            kg_manager = KnowledgeGraphManager.get_instance()
            return await kg_manager.query_knowledge_graph(query, group_id, limit)
        except Exception as e:
            logger.error(f"查询知识图谱失败: {e}")
            return []
    
    async def get_related_memories(self, query: str, group_id: str, limit: int = 5) -> List[str]:
        """
        获取相关记忆

        Args:
            query: 查询内容
            group_id: 群组ID
            limit: 返回数量限制

        Returns:
            相关记忆列表
        """
        try:
            # 使用实例属性而非单例
            if hasattr(self, 'memory_manager'):
                return await self.memory_manager.get_related_memories(query, group_id, limit)
            else:
                # 降级方案
                from .memory_graph_manager import MemoryGraphManager
                memory_manager = MemoryGraphManager.get_instance()
                return await memory_manager.get_related_memories(query, group_id, limit)
        except Exception as e:
            logger.error(f"获取相关记忆失败: {e}")
            return []
    
    async def answer_with_knowledge_graph(self, question: str, group_id: str) -> str:
        """
        使用知识图谱回答问题
        
        Args:
            question: 问题
            group_id: 群组ID
            
        Returns:
            回答内容
        """
        try:
            kg_manager = KnowledgeGraphManager.get_instance()
            return await kg_manager.answer_question_with_knowledge_graph(question, group_id)
        except Exception as e:
            logger.error(f"知识图谱回答问题失败: {e}")
            return "我不知道"
    
    async def get_all_statistics(self, group_id: str) -> Dict[str, Any]:
        """
        获取所有模块的统计信息
        
        Args:
            group_id: 群组ID
            
        Returns:
            统计信息汇总
        """
        try:
            stats = {
                'group_id': group_id,
                'expression_patterns': {},
                'memory_graph': {},
                'knowledge_graph': {},
                'time_decay': {}
            }
            
            # 表达模式统计
            learner = ExpressionPatternLearner.get_instance()
            patterns = await learner.get_expression_patterns(group_id, limit=5)
            stats['expression_patterns'] = {
                'count': len(patterns),
                'top_patterns': [
                    {'situation': p.situation, 'expression': p.expression, 'weight': p.weight}
                    for p in patterns
                ]
            }
            
            # 记忆图统计
            if hasattr(self, 'memory_manager'):
                stats['memory_graph'] = await self.memory_manager.get_memory_graph_statistics(group_id)
            else:
                # 降级方案
                from .memory_graph_manager import MemoryGraphManager
                memory_manager = MemoryGraphManager.get_instance()
                stats['memory_graph'] = await memory_manager.get_memory_graph_statistics(group_id)
            
            # 知识图谱统计
            kg_manager = KnowledgeGraphManager.get_instance()
            stats['knowledge_graph'] = await kg_manager.get_knowledge_graph_statistics(group_id)
            
            # 时间衰减统计
            if self.enhanced_manager.time_decay_manager:
                stats['time_decay'] = await self.enhanced_manager.time_decay_manager.get_decay_statistics(group_id)
            
            return stats
            
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {'error': str(e)}
    
    def format_enhanced_prompt(self, base_prompt: str, context: Dict[str, Any]) -> str:
        """
        格式化增强的prompt
        
        Args:
            base_prompt: 基础prompt
            context: 增强上下文
            
        Returns:
            格式化后的prompt
        """
        try:
            # 使用MaiBot风格的prompt格式
            enhanced_prompt = base_prompt
            
            # 添加表达模式
            if context.get('expression_patterns'):
                enhanced_prompt = enhanced_prompt.replace(
                    '{expression_patterns_block}',
                    context['expression_patterns']
                )
            
            # 添加记忆上下文
            if context.get('related_memories'):
                memory_text = "\n".join(context['related_memories'][:3])  # 限制数量
                enhanced_prompt = enhanced_prompt.replace(
                    '{memory_context}',
                    f"相关记忆：\n{memory_text}" if memory_text else ""
                )
            
            # 添加知识图谱上下文
            if context.get('knowledge_graph_context'):
                enhanced_prompt = enhanced_prompt.replace(
                    '{knowledge_context}',
                    f"相关知识：{context['knowledge_graph_context']}"
                )
            
            # 清理未替换的占位符
            enhanced_prompt = enhanced_prompt.replace('{expression_patterns_block}', '')
            enhanced_prompt = enhanced_prompt.replace('{memory_context}', '')
            enhanced_prompt = enhanced_prompt.replace('{knowledge_context}', '')
            
            return enhanced_prompt
            
        except Exception as e:
            logger.error(f"格式化增强prompt失败: {e}")
            return base_prompt


# 便捷的全局访问函数
def get_maibot_factory() -> MaiBotIntegrationFactory:
    """获取MaiBot集成工厂实例"""
    return MaiBotIntegrationFactory.get_instance()


# 快捷API函数
async def process_message_with_maibot(message: MessageData, group_id: str) -> Dict[str, bool]:
    """快捷处理消息"""
    factory = get_maibot_factory()
    return await factory.process_message(message, group_id)


async def get_maibot_enhanced_context(query: str, group_id: str) -> Dict[str, Any]:
    """快捷获取增强上下文"""
    factory = get_maibot_factory()
    return await factory.get_enhanced_context(query, group_id)


async def force_maibot_learning(group_id: str) -> Dict[str, Any]:
    """快捷强制学习"""
    factory = get_maibot_factory()
    return await factory.force_learning(group_id)


async def get_maibot_statistics(group_id: str) -> Dict[str, Any]:
    """快捷获取统计信息"""
    factory = get_maibot_factory()
    return await factory.get_all_statistics(group_id)