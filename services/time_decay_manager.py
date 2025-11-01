"""
时间衰减管理器 - 实现MaiBot的时间衰减机制
为现有学习系统添加时间衰减功能，保持学习内容的时效性
"""
import time
import math
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from dataclasses import dataclass

from astrbot.api import logger

from ..core.interfaces import ServiceLifecycle
from ..config import PluginConfig
from ..exceptions import TimeDecayError
from .database_manager import DatabaseManager


@dataclass
class DecayConfig:
    """衰减配置"""
    decay_days: int = 15  # MaiBot的15天衰减周期
    decay_min: float = 0.01  # 最小衰减值
    decay_table: str = ""  # 衰减表名
    weight_column: str = "weight"  # 权重列名
    time_column: str = "last_active_time"  # 时间列名
    id_column: str = "id"  # ID列名


class TimeDecayManager:
    """
    时间衰减管理器 - 完全基于MaiBot的衰减机制设计
    为各种学习数据提供统一的时间衰减管理
    """
    
    def __init__(self, config: PluginConfig, db_manager: DatabaseManager):
        self.config = config
        self.db_manager = db_manager
        self._status = ServiceLifecycle.CREATED
        
        # 预定义的衰减配置
        self.decay_configs = {
            'style_features': DecayConfig(
                decay_days=15,
                decay_table='style_features',
                weight_column='confidence',
                time_column='updated_at'
            ),
            'persona_updates': DecayConfig(
                decay_days=30,  # 人格更新衰减周期更长
                decay_table='persona_updates',
                weight_column='confidence',
                time_column='timestamp'
            ),
            'learning_batches': DecayConfig(
                decay_days=7,  # 学习批次衰减更快
                decay_table='learning_batches',
                weight_column='quality_score',
                time_column='created_at'
            ),
            'affection_records': DecayConfig(
                decay_days=20,
                decay_table='affection_records',
                weight_column='strength',
                time_column='timestamp'
            )
        }
    
    async def start(self) -> bool:
        """启动服务"""
        self._status = ServiceLifecycle.RUNNING
        logger.info("TimeDecayManager服务已启动")
        return True
    
    async def stop(self) -> bool:
        """停止服务"""
        self._status = ServiceLifecycle.STOPPED
        logger.info("TimeDecayManager服务已停止")
        return True
    
    def calculate_decay_factor(self, time_diff_days: float, decay_days: int = 15) -> float:
        """
        计算衰减因子 - 完全采用MaiBot的衰减算法
        
        Args:
            time_diff_days: 时间差（天）
            decay_days: 衰减周期天数
            
        Returns:
            衰减因子
        """
        if time_diff_days <= 0:
            return 0.0  # 刚激活的不衰减
        
        if time_diff_days >= decay_days:
            return 0.01  # 长时间未活跃的大幅衰减
        
        # 使用二次函数插值：在0-decay_days天之间从0衰减到0.01
        a = 0.01 / (decay_days ** 2)
        decay = a * (time_diff_days ** 2)
        
        return min(0.01, decay)
    
    async def apply_decay_to_table(self, decay_config: DecayConfig, group_id: Optional[str] = None) -> Tuple[int, int]:
        """
        对指定表应用时间衰减
        
        Args:
            decay_config: 衰减配置
            group_id: 可选的群组ID筛选
            
        Returns:
            (更新数量, 删除数量)
        """
        try:
            current_time = time.time()
            updated_count = 0
            deleted_count = 0
            
            with self.db_manager.get_connection() as conn:
                # 构建查询语句
                base_query = f'SELECT {decay_config.id_column}, {decay_config.weight_column}, {decay_config.time_column} FROM {decay_config.decay_table}'
                
                if group_id:
                    query = f'{base_query} WHERE group_id = ?'
                    cursor = conn.execute(query, (group_id,))
                else:
                    cursor = conn.execute(base_query)
                
                records = cursor.fetchall()
                
                for record_id, weight, last_active_time in records:
                    # 计算时间差（天）
                    time_diff_days = (current_time - last_active_time) / (24 * 3600)
                    
                    # 计算衰减值
                    decay_value = self.calculate_decay_factor(time_diff_days, decay_config.decay_days)
                    new_weight = max(decay_config.decay_min, weight - decay_value)
                    
                    if new_weight <= decay_config.decay_min:
                        # 删除权重过低的记录
                        delete_query = f'DELETE FROM {decay_config.decay_table} WHERE {decay_config.id_column} = ?'
                        conn.execute(delete_query, (record_id,))
                        deleted_count += 1
                    else:
                        # 更新权重
                        update_query = f'UPDATE {decay_config.decay_table} SET {decay_config.weight_column} = ? WHERE {decay_config.id_column} = ?'
                        conn.execute(update_query, (new_weight, record_id))
                        updated_count += 1
                
                conn.commit()
                
                if updated_count > 0 or deleted_count > 0:
                    table_name = decay_config.decay_table
                    group_info = f" (群组: {group_id})" if group_id else ""
                    logger.info(f"表 {table_name}{group_info} 时间衰减完成：更新了 {updated_count} 个，删除了 {deleted_count} 个记录")
                
                return updated_count, deleted_count
                
        except Exception as e:
            logger.error(f"对表 {decay_config.decay_table} 应用时间衰减失败: {e}")
            raise TimeDecayError(f"时间衰减失败: {e}")
    
    async def apply_decay_to_all_tables(self, group_id: Optional[str] = None) -> Dict[str, Tuple[int, int]]:
        """
        对所有配置的表应用时间衰减
        
        Args:
            group_id: 可选的群组ID筛选
            
        Returns:
            每个表的(更新数量, 删除数量)结果
        """
        results = {}
        
        for table_name, decay_config in self.decay_configs.items():
            try:
                # 检查表是否存在
                if await self._table_exists(decay_config.decay_table):
                    updated, deleted = await self.apply_decay_to_table(decay_config, group_id)
                    results[table_name] = (updated, deleted)
                else:
                    logger.debug(f"表 {decay_config.decay_table} 不存在，跳过衰减")
                    results[table_name] = (0, 0)
            except Exception as e:
                logger.error(f"对表 {table_name} 应用衰减失败: {e}")
                results[table_name] = (0, 0)
        
        return results
    
    async def _table_exists(self, table_name: str) -> bool:
        """检查表是否存在"""
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table_name,)
                )
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"检查表 {table_name} 是否存在失败: {e}")
            return False
    
    async def add_decay_config(self, name: str, config: DecayConfig):
        """添加新的衰减配置"""
        self.decay_configs[name] = config
        logger.info(f"添加衰减配置: {name}")
    
    async def get_decay_statistics(self, group_id: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """
        获取衰减统计信息
        
        Args:
            group_id: 可选的群组ID筛选
            
        Returns:
            各表的衰减统计信息
        """
        statistics = {}
        current_time = time.time()
        
        for table_name, decay_config in self.decay_configs.items():
            try:
                if not await self._table_exists(decay_config.decay_table):
                    continue
                
                with self.db_manager.get_connection() as conn:
                    # 构建查询语句
                    base_query = f'''
                        SELECT 
                            COUNT(*) as total_count,
                            AVG({decay_config.weight_column}) as avg_weight,
                            MIN({decay_config.time_column}) as oldest_time,
                            MAX({decay_config.time_column}) as newest_time
                        FROM {decay_config.decay_table}
                    '''
                    
                    if group_id:
                        query = f'{base_query} WHERE group_id = ?'
                        cursor = conn.execute(query, (group_id,))
                    else:
                        cursor = conn.execute(base_query)
                    
                    result = cursor.fetchone()
                    
                    if result and result[0] > 0:
                        total_count, avg_weight, oldest_time, newest_time = result
                        
                        # 计算老化程度
                        oldest_days = (current_time - oldest_time) / (24 * 3600) if oldest_time else 0
                        newest_days = (current_time - newest_time) / (24 * 3600) if newest_time else 0
                        
                        statistics[table_name] = {
                            'total_count': total_count,
                            'avg_weight': round(avg_weight, 3) if avg_weight else 0,
                            'oldest_days': round(oldest_days, 1),
                            'newest_days': round(newest_days, 1),
                            'decay_config': {
                                'decay_days': decay_config.decay_days,
                                'decay_min': decay_config.decay_min
                            }
                        }
                    else:
                        statistics[table_name] = {
                            'total_count': 0,
                            'avg_weight': 0,
                            'oldest_days': 0,
                            'newest_days': 0,
                            'decay_config': {
                                'decay_days': decay_config.decay_days,
                                'decay_min': decay_config.decay_min
                            }
                        }
                        
            except Exception as e:
                logger.error(f"获取表 {table_name} 衰减统计失败: {e}")
                statistics[table_name] = {'error': str(e)}
        
        return statistics
    
    async def schedule_decay_maintenance(self, interval_hours: int = 24):
        """
        定期衰减维护任务
        
        Args:
            interval_hours: 维护间隔小时数
        """
        logger.info(f"启动定期衰减维护，间隔: {interval_hours}小时")
        
        while self._status == ServiceLifecycle.RUNNING:
            try:
                # 执行全局衰减
                results = await self.apply_decay_to_all_tables()
                
                # 记录衰减结果
                total_updated = sum(r[0] for r in results.values())
                total_deleted = sum(r[1] for r in results.values())
                
                if total_updated > 0 or total_deleted > 0:
                    logger.info(f"定期衰减维护完成，总计更新: {total_updated}，删除: {total_deleted}")
                
                # 等待下次维护
                await asyncio.sleep(interval_hours * 3600)
                
            except Exception as e:
                logger.error(f"定期衰减维护失败: {e}")
                await asyncio.sleep(3600)  # 错误后等待1小时再重试


# 衰减工具函数
def add_time_decay_to_existing_tables():
    """
    为现有表添加时间衰减支持的工具函数
    修改现有表结构，添加必要的时间和权重列
    """
    
    # 表结构修改SQL
    table_modifications = {
        'learning_batches': [
            'ALTER TABLE learning_batches ADD COLUMN weight REAL DEFAULT 1.0',
            'ALTER TABLE learning_batches ADD COLUMN last_active_time REAL DEFAULT 0'
        ],
        'style_features': [
            'ALTER TABLE style_features ADD COLUMN last_active_time REAL DEFAULT 0'
        ],
        'persona_updates': [
            'ALTER TABLE persona_updates ADD COLUMN weight REAL DEFAULT 1.0',
            'ALTER TABLE persona_updates ADD COLUMN last_active_time REAL DEFAULT 0'
        ]
    }
    
    return table_modifications


# 使用示例函数
async def integrate_time_decay_to_existing_services(decay_manager: TimeDecayManager):
    """
    将时间衰减机制集成到现有服务的示例
    """
    
    # 1. 在学习服务中集成衰减
    async def enhanced_learning_with_decay(learning_service, group_id: str):
        """带衰减的增强学习"""
        # 执行正常学习
        learning_result = await learning_service.process_learning(group_id)
        
        # 应用时间衰减
        if learning_result:
            await decay_manager.apply_decay_to_table(
                decay_manager.decay_configs['learning_batches'], 
                group_id
            )
        
        return learning_result
    
    # 2. 在人格更新中集成衰减
    async def enhanced_persona_update_with_decay(persona_service, group_id: str):
        """带衰减的人格更新"""
        # 执行人格更新
        update_result = await persona_service.update_persona(group_id)
        
        # 应用衰减
        if update_result:
            await decay_manager.apply_decay_to_table(
                decay_manager.decay_configs['persona_updates'],
                group_id
            )
        
        return update_result
    
    return enhanced_learning_with_decay, enhanced_persona_update_with_decay