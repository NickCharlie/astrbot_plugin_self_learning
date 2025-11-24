"""
MaiBot式表达模式学习器 - 实现场景-表达映射的细粒度学习
基于MaiBot的expression_learner.py思路，实现场景化的语言风格学习
"""
import time
import json
import random
import sqlite3
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from dataclasses import dataclass, asdict

from astrbot.api import logger

from ..core.interfaces import MessageData, ServiceLifecycle
from ..core.framework_llm_adapter import FrameworkLLMAdapter
from ..config import PluginConfig
from ..exceptions import ExpressionLearningError, ModelAccessError
from ..utils.json_utils import safe_parse_llm_json
from .database_manager import DatabaseManager


@dataclass
class ExpressionPattern:
    """表达模式数据结构"""
    situation: str          # 场景描述，如"对某件事表示十分惊叹"
    expression: str         # 表达方式，如"我嘞个xxxx"
    weight: float          # 权重（使用频率）
    last_active_time: float  # 最后活跃时间
    create_time: float     # 创建时间
    group_id: str          # 所属群组ID
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExpressionPattern':
        return cls(**data)


class ExpressionPatternLearner:
    """
    MaiBot式表达模式学习器
    实现场景-表达映射的细粒度学习，完全参考MaiBot的设计思路
    采用单例模式确保全局唯一实例
    """
    
    # MaiBot的配置参数
    MAX_EXPRESSION_COUNT = 300  # 最大表达式数量
    DECAY_DAYS = 15  # 15天衰减周期
    DECAY_MIN = 0.01  # 最小衰减值
    MIN_MESSAGES_FOR_LEARNING = 25  # 触发学习所需的最少消息数
    MIN_LEARNING_INTERVAL = 300  # 最短学习时间间隔（秒）
    
    _instance = None
    _initialized = False
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, config: PluginConfig = None, db_manager: DatabaseManager = None, context=None, llm_adapter=None):
        # 防止重复初始化
        if self._initialized:
            return
            
        self.config = config
        self.db_manager = db_manager
        
        # 优先使用传入的llm_adapter，否则尝试创建新的
        if llm_adapter:
            self.llm_adapter = llm_adapter
        elif context:
            # 使用正确的context创建FrameworkLLMAdapter
            self.llm_adapter = FrameworkLLMAdapter(context)
            if config:
                self.llm_adapter.initialize_providers(config)
        elif config:
            # 旧的方式，可能会有问题
            self.llm_adapter = FrameworkLLMAdapter(config)
        else:
            self.llm_adapter = None
        
        self._status = ServiceLifecycle.CREATED
        
        # 维护每个群组的上次学习时间
        self.last_learning_times: Dict[str, float] = {}
        
        # 初始化数据库表
        if self.db_manager:
            self._init_expression_patterns_table()
            
        self._initialized = True
    
    @classmethod
    def get_instance(cls, config: PluginConfig = None, db_manager: DatabaseManager = None, context=None, llm_adapter=None) -> 'ExpressionPatternLearner':
        """获取单例实例，支持延迟初始化"""
        if cls._instance is None:
            cls._instance = cls(config, db_manager, context, llm_adapter)
        elif not cls._initialized or (cls._instance.llm_adapter is None and (context or llm_adapter)):
            # 如果实例存在但未正确初始化，或者现在有更好的初始化参数，重新初始化
            logger.info("重新初始化ExpressionPatternLearner单例，提供更好的参数")
            cls._initialized = False
            cls._instance.__init__(config, db_manager, context, llm_adapter)
        return cls._instance
    
    def _init_expression_patterns_table(self):
        """初始化表达模式数据库表"""
        try:
            with self.db_manager.get_connection() as conn:
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS expression_patterns (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        situation TEXT NOT NULL,
                        expression TEXT NOT NULL,
                        weight REAL NOT NULL DEFAULT 1.0,
                        last_active_time REAL NOT NULL,
                        create_time REAL NOT NULL,
                        group_id TEXT NOT NULL,
                        UNIQUE(situation, expression, group_id)
                    )
                ''')
                conn.commit()
                logger.info("表达模式数据库表初始化完成")
        except Exception as e:
            logger.error(f"初始化表达模式数据库表失败: {e}")
            raise ExpressionLearningError(f"数据库初始化失败: {e}")
    
    async def start(self) -> bool:
        """启动服务"""
        self._status = ServiceLifecycle.RUNNING
        logger.info("ExpressionPatternLearner服务已启动")
        return True
    
    async def stop(self) -> bool:
        """停止服务"""
        self._status = ServiceLifecycle.STOPPED
        logger.info("ExpressionPatternLearner服务已停止")
        return True
    
    def should_trigger_learning(self, group_id: str, recent_messages: List[MessageData]) -> bool:
        """
        检查是否应该触发学习 - 只检查消息数量（已移除时间间隔限制）

        Args:
            group_id: 群组ID
            recent_messages: 最近的消息列表

        Returns:
            bool: 是否应该触发学习
        """
        # 检查消息数量（至少5条消息）
        if len(recent_messages) < 5:
            logger.debug(f"群组 {group_id} 消息数量不足: {len(recent_messages)} < 5")
            return False

        return True
    
    async def trigger_learning_for_group(self, group_id: str, recent_messages: List[MessageData]) -> bool:
        """
        为指定群组触发表达模式学习
        
        Args:
            group_id: 群组ID
            recent_messages: 最近的消息列表
            
        Returns:
            bool: 是否成功学习到新模式
        """
        if not self.should_trigger_learning(group_id, recent_messages):
            return False
        
        try:
            logger.info(f"为群组 {group_id} 触发表达模式学习，消息数量: {len(recent_messages)}")
            
            # 学习表达模式
            learned_patterns = await self.learn_expression_patterns(recent_messages, group_id)
            
            if learned_patterns:
                # 保存到数据库
                await self._save_expression_patterns(learned_patterns, group_id)
                
                # 应用时间衰减
                await self._apply_time_decay(group_id)
                
                # 限制最大数量
                await self._limit_max_expressions(group_id)
                
                # 更新学习时间
                self.last_learning_times[group_id] = time.time()
                
                logger.info(f"群组 {group_id} 表达模式学习完成，学到 {len(learned_patterns)} 个新模式")
                return True
            else:
                logger.warning(f"群组 {group_id} 表达模式学习未获得有效结果")
                return False
                
        except Exception as e:
            logger.error(f"群组 {group_id} 表达模式学习失败: {e}")
            return False
    
    async def learn_expression_patterns(self, messages: List[MessageData], group_id: str) -> List[ExpressionPattern]:
        """
        学习表达模式 - 使用MaiBot的prompt设计
        
        Args:
            messages: 消息列表
            group_id: 群组ID
            
        Returns:
            学习到的表达模式列表
        """
        try:
            # 构建聊天上下文
            chat_context = self._build_anonymous_chat_context(messages)
            
            # 使用MaiBot的表达学习prompt
            prompt = f"""
{chat_context}

请从上面这段群聊中概括除了人名为"SELF"之外的人的语言风格
1. 只考虑文字，不要考虑表情包和图片
2. 不要涉及具体的人名，但是可以涉及具体名词  
3. 思考有没有特殊的梗，一并总结成语言风格
4. 例子仅供参考，请严格根据群聊内容总结!!!

注意：总结成如下格式的规律，总结的内容要详细，但具有概括性：
例如：当"AAAAA"时，可以"BBBBB", AAAAA代表某个具体的场景，不超过20个字。BBBBB代表对应的语言风格，特定句式或表达方式，不超过20个字。

例如：
当"对某件事表示十分惊叹"时，使用"我嘞个xxxx"
当"表示讽刺的赞同，不讲道理"时，使用"对对对"
当"想说明某个具体的事实观点，但懒得明说"时，使用"懂的都懂"
当"涉及游戏相关时，夸赞，略带戏谑意味"时，使用"这么强！"

请注意：不要总结你自己（SELF）的发言，尽量保证总结内容的逻辑性
现在请你概括
"""
            
            logger.debug(f"表达模式学习prompt: {prompt}")
            
            # 调用LLM生成回复 - 使用通用的generate_response方法
            if self.llm_adapter and hasattr(self.llm_adapter, 'generate_response'):
                try:
                    response = await self.llm_adapter.generate_response(
                        prompt, 
                        temperature=0.3,  # 使用MaiBot的temperature设置
                        model_type="refine"  # 使用精炼模型
                    )
                    
                    # 检查response是否有效
                    if not response:
                        logger.warning(f"LLM生成的response为空或None，可能是模型调用失败，尝试使用简化算法")
                        # 使用简化的规则生成基本表达模式
                        response = self._generate_fallback_expression_patterns(messages)
                    
                except Exception as llm_error:
                    logger.warning(f"LLM调用异常: {llm_error}，使用简化算法生成表达模式")
                    response = self._generate_fallback_expression_patterns(messages)
            else:
                logger.warning("LLM适配器未正确配置或缺少generate_response方法，使用简化算法")
                response = self._generate_fallback_expression_patterns(messages)
            
            logger.debug(f"表达模式学习response: {response}")
            
            # 解析响应
            patterns = self._parse_expression_response(response, group_id)
            
            return patterns
            
        except Exception as e:
            logger.error(f"学习表达模式失败: {e}")
            raise ExpressionLearningError(f"表达模式学习失败: {e}")
    
    def _build_anonymous_chat_context(self, messages: List[MessageData]) -> str:
        """
        构建匿名化的聊天上下文 - 参考MaiBot的build_anonymous_messages
        """
        context_lines = []
        
        for msg in messages:
            # 获取发送者信息 - 处理字典和对象两种情况
            if hasattr(msg, 'sender_id'):
                # 如果是对象
                is_bot = msg.sender_id == "bot"
                sender = msg.sender_name or msg.sender_id or 'Unknown'
                content = msg.message.strip() if msg.message else ''
                timestamp = msg.timestamp
            else:
                # 如果是字典
                is_bot = msg.get('sender_id') == "bot"
                sender = msg.get('sender_name') or msg.get('sender_id') or 'Unknown'
                content = msg.get('message', '').strip()
                timestamp = msg.get('timestamp', time.time())
            
            # 只保留文本内容，过滤掉图片、表情包等
            if content and not content.startswith('[') and not content.startswith('http'):
                timestamp_str = datetime.fromtimestamp(timestamp).strftime("%H:%M")
                context_lines.append(f"{timestamp_str} {sender}: {content}")
        
        return '\n'.join(context_lines)
    
    def _generate_fallback_expression_patterns(self, messages: List[MessageData]) -> str:
        """
        当LLM不可用时的降级方案：使用简单规则生成基本表达模式
        
        Args:
            messages: 消息列表
            
        Returns:
            str: JSON格式的表达模式字符串
        """
        try:
            patterns = []
            
            # 分析消息特征
            for msg in messages[:10]:  # 只分析前10条消息
                content = msg.message.strip()
                if len(content) < 5:
                    continue
                
                # 基于简单规则创建表达模式
                pattern_data = {}
                
                # 检测感叹类型
                if '！' in content or '!' in content:
                    if '太' in content or '好' in content or '棒' in content:
                        pattern_data = {
                            "situation": "对某件事表示惊喜或赞赏",
                            "expression": content[:15] + ('...' if len(content) > 15 else ''),
                            "weight": 0.7,
                            "context": "积极情感表达"
                        }
                    elif '什么' in content or '怎么' in content:
                        pattern_data = {
                            "situation": "对某事感到意外或疑问",
                            "expression": content[:15] + ('...' if len(content) > 15 else ''),
                            "weight": 0.6,
                            "context": "疑问情感表达"
                        }
                
                # 检测疑问类型
                elif '？' in content or '?' in content:
                    pattern_data = {
                        "situation": "询问或疑问",
                        "expression": content[:20] + ('...' if len(content) > 20 else ''),
                        "weight": 0.5,
                        "context": "疑问表达"
                    }
                
                # 检测口语化表达
                elif any(word in content for word in ['哈哈', '呵呵', '嗯嗯', '啊啊', '哦哦']):
                    pattern_data = {
                        "situation": "轻松愉快的对话",
                        "expression": content[:12] + ('...' if len(content) > 12 else ''),
                        "weight": 0.4,
                        "context": "口语化表达"
                    }
                
                # 检测表情符号
                elif any(emoji in content for emoji in ['😊', '😄', '😢', '😂', '🤔', '👍', '❤️']):
                    pattern_data = {
                        "situation": "表达情感状态",
                        "expression": content[:10] + ('...' if len(content) > 10 else ''),
                        "weight": 0.6,
                        "context": "表情符号表达"
                    }
                
                if pattern_data:
                    patterns.append(pattern_data)
            
            # 如果没有找到任何模式，创建一个默认模式
            if not patterns:
                patterns.append({
                    "situation": "日常对话",
                    "expression": "正常交流",
                    "weight": 0.3,
                    "context": "基本对话模式"
                })
            
            # 返回JSON格式
            return json.dumps({"patterns": patterns[:5]}, ensure_ascii=False, indent=2)
            
        except Exception as e:
            logger.error(f"降级表达模式生成失败: {e}")
            # 返回最简单的默认响应
            default_patterns = {
                "patterns": [
                    {
                        "situation": "日常对话",
                        "expression": "自然交流",
                        "weight": 0.3,
                        "context": "默认对话模式"
                    }
                ]
            }
            return json.dumps(default_patterns, ensure_ascii=False)
    
    def _parse_expression_response(self, response: str, group_id: str) -> List[ExpressionPattern]:
        """
        解析LLM返回的表达模式 - 完全参考MaiBot的解析逻辑
        
        Args:
            response: LLM响应
            group_id: 群组ID
            
        Returns:
            解析出的表达模式列表
        """
        patterns = []
        current_time = time.time()
        
        # 检查response是否为None或空字符串
        if not response:
            logger.warning(f"LLM返回的response为空或None，无法解析表达模式")
            return patterns
        
        for line in response.splitlines():
            line = line.strip()
            if not line:
                continue
                
            # 查找"当"和下一个引号
            idx_when = line.find('当"')
            if idx_when == -1:
                continue
                
            idx_quote1 = idx_when + 1
            idx_quote2 = line.find('"', idx_quote1 + 1)
            if idx_quote2 == -1:
                continue
                
            situation = line[idx_quote1 + 1:idx_quote2]
            
            # 查找"使用"或"时，使用"
            idx_use = line.find('使用"', idx_quote2)
            if idx_use == -1:
                continue
                
            idx_quote3 = idx_use + 2
            idx_quote4 = line.find('"', idx_quote3 + 1)
            if idx_quote4 == -1:
                continue
                
            expression = line[idx_quote3 + 1:idx_quote4]
            
            if situation and expression:
                pattern = ExpressionPattern(
                    situation=situation,
                    expression=expression,
                    weight=1.0,
                    last_active_time=current_time,
                    create_time=current_time,
                    group_id=group_id
                )
                patterns.append(pattern)
                
        return patterns
    
    async def _save_expression_patterns(self, patterns: List[ExpressionPattern], group_id: str):
        """保存表达模式到数据库（异步版本）"""
        try:
            async with self.db_manager.get_db_connection() as conn:
                cursor = await conn.cursor()

                for pattern in patterns:
                    # 查找是否已存在相似模式
                    await cursor.execute(
                        'SELECT id, weight FROM expression_patterns WHERE situation = ? AND expression = ? AND group_id = ?',
                        (pattern.situation, pattern.expression, group_id)
                    )
                    existing = await cursor.fetchone()

                    if existing:
                        # 更新现有模式，权重增加，50%概率替换内容（参考MaiBot）
                        new_weight = existing[1] + 1.0
                        if random.random() < 0.5:
                            await cursor.execute(
                                'UPDATE expression_patterns SET weight = ?, last_active_time = ?, situation = ?, expression = ? WHERE id = ?',
                                (new_weight, pattern.last_active_time, pattern.situation, pattern.expression, existing[0])
                            )
                        else:
                            await cursor.execute(
                                'UPDATE expression_patterns SET weight = ?, last_active_time = ? WHERE id = ?',
                                (new_weight, pattern.last_active_time, existing[0])
                            )
                    else:
                        # 插入新模式
                        await cursor.execute(
                            'INSERT INTO expression_patterns (situation, expression, weight, last_active_time, create_time, group_id) VALUES (?, ?, ?, ?, ?, ?)',
                            (pattern.situation, pattern.expression, pattern.weight, pattern.last_active_time, pattern.create_time, pattern.group_id)
                        )

                await conn.commit()
                logger.info(f"✅ 保存了 {len(patterns)} 个表达模式到数据库（群组: {group_id}）")

        except Exception as e:
            logger.error(f"保存表达模式失败: {e}", exc_info=True)
            raise ExpressionLearningError(f"保存表达模式失败: {e}")
    
    async def _apply_time_decay(self, group_id: str):
        """
        应用时间衰减 - 完全参考MaiBot的衰减机制（异步版本）
        """
        try:
            current_time = time.time()
            updated_count = 0
            deleted_count = 0

            async with self.db_manager.get_db_connection() as conn:
                cursor = await conn.cursor()

                # 获取所有该群组的表达模式
                await cursor.execute(
                    'SELECT id, weight, last_active_time FROM expression_patterns WHERE group_id = ?',
                    (group_id,)
                )
                patterns = await cursor.fetchall()

                for pattern_id, weight, last_active_time in patterns:
                    # 计算时间差（天）
                    time_diff_days = (current_time - last_active_time) / (24 * 3600)

                    # 计算衰减值
                    decay_value = self._calculate_decay_factor(time_diff_days)
                    new_weight = max(self.DECAY_MIN, weight - decay_value)

                    if new_weight <= self.DECAY_MIN:
                        # 删除权重过低的模式
                        await cursor.execute('DELETE FROM expression_patterns WHERE id = ?', (pattern_id,))
                        deleted_count += 1
                    else:
                        # 更新权重
                        await cursor.execute('UPDATE expression_patterns SET weight = ? WHERE id = ?', (new_weight, pattern_id))
                        updated_count += 1

                await conn.commit()

                if updated_count > 0 or deleted_count > 0:
                    logger.info(f"群组 {group_id} 时间衰减完成：更新了 {updated_count} 个，删除了 {deleted_count} 个表达模式")

        except Exception as e:
            logger.error(f"应用时间衰减失败: {e}", exc_info=True)
    
    def _calculate_decay_factor(self, time_diff_days: float) -> float:
        """
        计算衰减因子 - 完全参考MaiBot的衰减算法
        当时间差为0天时，衰减值为0（最近活跃的不衰减）
        当时间差为15天或更长时，衰减值为0.01（高衰减）
        使用二次函数进行曲线插值
        """
        if time_diff_days <= 0:
            return 0.0  # 刚激活的表达式不衰减
        
        if time_diff_days >= self.DECAY_DAYS:
            return 0.01  # 长时间未活跃的表达式大幅衰减
        
        # 使用二次函数插值：在0-15天之间从0衰减到0.01
        a = 0.01 / (self.DECAY_DAYS ** 2)
        decay = a * (time_diff_days ** 2)
        
        return min(0.01, decay)
    
    async def _limit_max_expressions(self, group_id: str):
        """限制最大表达模式数量（异步版本）"""
        try:
            async with self.db_manager.get_db_connection() as conn:
                cursor = await conn.cursor()

                # 统计当前数量
                await cursor.execute('SELECT COUNT(*) FROM expression_patterns WHERE group_id = ?', (group_id,))
                row = await cursor.fetchone()
                count = row[0] if row else 0

                if count > self.MAX_EXPRESSION_COUNT:
                    # 删除权重最小的多余模式
                    # MySQL 不支持 DELETE ... WHERE id IN (SELECT ... LIMIT)
                    # 改用 JOIN 方式
                    excess_count = count - self.MAX_EXPRESSION_COUNT

                    # 先查询要删除的 ID
                    await cursor.execute(
                        'SELECT id FROM expression_patterns WHERE group_id = ? ORDER BY weight ASC LIMIT ?',
                        (group_id, excess_count)
                    )
                    rows = await cursor.fetchall()
                    ids_to_delete = [row[0] for row in rows]

                    if ids_to_delete:
                        # 批量删除
                        placeholders = ','.join(['?' for _ in ids_to_delete])
                        await cursor.execute(
                            f'DELETE FROM expression_patterns WHERE id IN ({placeholders})',
                            tuple(ids_to_delete)
                        )
                        await conn.commit()
                        logger.info(f"群组 {group_id} 删除了 {len(ids_to_delete)} 个权重最小的表达模式")

        except Exception as e:
            logger.error(f"限制表达模式数量失败: {e}", exc_info=True)
    
    async def get_expression_patterns(self, group_id: str, limit: int = 10) -> List[ExpressionPattern]:
        """获取群组的表达模式（异步版本）"""
        try:
            async with self.db_manager.get_db_connection() as conn:
                cursor = await conn.cursor()

                await cursor.execute(
                    'SELECT situation, expression, weight, last_active_time, create_time, group_id FROM expression_patterns WHERE group_id = ? ORDER BY weight DESC LIMIT ?',
                    (group_id, limit)
                )

                rows = await cursor.fetchall()
                patterns = []
                for row in rows:
                    pattern = ExpressionPattern(
                        situation=row[0],
                        expression=row[1],
                        weight=row[2],
                        last_active_time=row[3],
                        create_time=row[4],
                        group_id=row[5]
                    )
                    patterns.append(pattern)

                return patterns

        except Exception as e:
            logger.error(f"获取表达模式失败: {e}", exc_info=True)
            return []
    
    async def format_expression_patterns_for_prompt(self, group_id: str, limit: int = 5) -> str:
        """
        格式化表达模式用于prompt
        
        Returns:
            格式化的表达模式字符串，用于插入到对话prompt中
        """
        patterns = await self.get_expression_patterns(group_id, limit)
        
        if not patterns:
            return ""
        
        lines = ["学到的表达习惯："]
        for pattern in patterns:
            lines.append(f"- 当{pattern.situation}时，可以{pattern.expression}")
        
        return "\n".join(lines)