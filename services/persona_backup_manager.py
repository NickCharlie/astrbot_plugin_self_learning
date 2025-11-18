"""
人格备份管理器 - 管理人格数据的备份和恢复
"""
import json
import time
from typing import Dict, List, Optional, Any
from datetime import datetime

from astrbot.api import logger
from astrbot.api.star import Context

from ..config import PluginConfig
from ..exceptions import BackupError
from .database_manager import DatabaseManager


class PersonaBackupManager:
    """人格备份管理器"""
    
    def __init__(self, config: PluginConfig, context: Context, db_manager: DatabaseManager):
        self.config = config
        self.context = context
        self.db_manager = db_manager
        
        # 备份配置
        self.auto_backup_enabled = config.auto_backup_enabled
        self.backup_interval_hours = config.backup_interval_hours
        self.max_backups_per_group = config.max_backups_per_group
        
        logger.info("人格备份管理器初始化完成")

    async def create_backup_before_update(self, group_id: str, reason: str = "Auto backup before update") -> int:
        """在更新前创建备份"""
        try:
            # 获取当前人格设置
            current_persona = await self._get_current_persona_data()
            
            # 获取当前模仿对话列表
            imitation_dialogues = await self._get_current_imitation_dialogues()
            
            # 创建备份数据
            backup_data = {
                'backup_name': f"备份_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                'original_persona': current_persona,
                'imitation_dialogues': imitation_dialogues,
                'backup_reason': reason
            }
            
            # 保存到数据库
            backup_id = await self.db_manager.backup_persona(group_id, backup_data)
            
            # 清理旧备份
            await self._cleanup_old_backups(group_id)
            
            logger.info(f"人格备份创建成功，备份ID: {backup_id}")
            return backup_id
            
        except Exception as e:
            logger.error(f"创建人格备份失败: {e}")
            raise BackupError(f"创建人格备份失败: {str(e)}")

    async def _get_current_persona_data(self) -> Dict[str, Any]:
        """获取当前人格数据"""
        try:
            # 从AstrBot框架获取当前人格设置
            provider = self.context.get_using_provider()
            if provider and hasattr(provider, 'curr_personality'):
                personality = provider.curr_personality
                return {
                    'name': getattr(personality, 'name', '默认人格'),
                    'prompt': getattr(personality, 'prompt', ''),
                    'settings': getattr(personality, 'settings', {}),
                    'created_time': datetime.now().isoformat()
                }
            else:
                # 如果无法获取provider，尝试从context.persona_manager获取
                if hasattr(self.context, 'persona_manager') and self.context.persona_manager:
                    try:
                        default_persona = await self.context.persona_manager.get_default_persona_v3()
                        if default_persona:
                            return {
                                'name': default_persona.get('name', '默认人格'),
                                'prompt': default_persona.get('prompt', ''),
                                'settings': {},
                                'created_time': datetime.now().isoformat()
                            }
                    except Exception as e:
                        logger.warning(f"从persona_manager获取默认人格失败: {e}")

                # 如果都失败，返回默认值
                return {
                    'name': '默认人格',
                    'prompt': '',
                    'settings': {},
                    'created_time': datetime.now().isoformat()
                }
                
        except Exception as e:
            logger.error(f"获取当前人格数据失败: {e}")
            return {
                'name': '获取失败',
                'prompt': '',
                'settings': {},
                'error': str(e)
            }

    async def _get_current_imitation_dialogues(self) -> List[str]:
        """获取当前模仿对话列表"""
        try:
            # 这里需要根据AstrBot框架的具体API来获取
            # 目前使用简化实现
            provider = self.context.get_using_provider()
            if provider and hasattr(provider, 'mood_imitation_dialogs'):
                return list(provider.mood_imitation_dialogs)
            else:
                # 如果无法获取，返回空列表
                return []
                
        except Exception as e:
            logger.error(f"获取模仿对话列表失败: {e}")
            return []

    async def restore_backup(self, group_id: str, backup_id: int) -> bool:
        """恢复备份"""
        try:
            # 获取备份数据
            backup_data = await self.db_manager.restore_persona_backup(group_id, backup_id)
            
            if not backup_data:
                logger.warning(f"备份ID {backup_id} 不存在")
                return False
            
            # 在恢复前创建当前状态的备份
            await self.create_backup_before_update(group_id, f"Before restore backup {backup_id}")
            
            # 恢复人格设置
            persona_restored = await self._restore_persona_data(backup_data['original_persona'])
            
            # 恢复模仿对话
            dialogues_restored = await self._restore_imitation_dialogues(backup_data['imitation_dialogues'])
            
            success = persona_restored and dialogues_restored
            
            if success:
                logger.info(f"备份 {backup_id} 恢复成功")
            else:
                logger.warning(f"备份 {backup_id} 部分恢复失败")
            
            return success
            
        except Exception as e:
            logger.error(f"恢复备份失败: {e}")
            raise BackupError(f"恢复备份失败: {str(e)}")

    async def _restore_persona_data(self, persona_data: Dict[str, Any]) -> bool:
        """恢复人格数据"""
        try:
            # 使用新版框架API恢复人格数据
            if hasattr(self.context, 'persona_manager') and self.context.persona_manager:
                try:
                    persona_name = persona_data.get('name', '恢复的人格')
                    persona_prompt = persona_data.get('prompt', '')

                    # 通过PersonaManager更新当前人格
                    await self.context.persona_manager.update_persona(
                        persona_id=persona_name,
                        system_prompt=persona_prompt,
                        begin_dialogs=persona_data.get('begin_dialogs', []),
                        tools=persona_data.get('tools')
                    )

                    logger.info(f"人格数据恢复成功: {persona_name}")
                    return True
                except Exception as e:
                    logger.warning(f"使用PersonaManager恢复失败: {e}, 尝试旧方法")

            # 回退到旧方法（兼容性）
            provider = self.context.get_using_provider()
            if provider and hasattr(provider, 'curr_personality'):
                # Personality是TypedDict，使用字典方式
                if isinstance(provider.curr_personality, dict):
                    provider.curr_personality['name'] = persona_data.get('name', '恢复的人格')
                    provider.curr_personality['prompt'] = persona_data.get('prompt', '')
                else:
                    # 如果是对象，尝试属性设置
                    if hasattr(provider.curr_personality, 'name'):
                        provider.curr_personality.name = persona_data.get('name', '恢复的人格')
                    if hasattr(provider.curr_personality, 'prompt'):
                        provider.curr_personality.prompt = persona_data.get('prompt', '')

                logger.info("人格数据恢复成功（使用旧方法）")
                return True
            else:
                logger.warning("无法访问人格设置接口")
                return False

        except Exception as e:
            logger.error(f"恢复人格数据失败: {e}")
            return False

    async def _restore_imitation_dialogues(self, dialogues: List[str]) -> bool:
        """恢复模仿对话列表"""
        try:
            # 这里需要调用AstrBot框架的API来设置模仿对话
            # 目前使用简化实现
            provider = self.context.get_using_provider()
            if provider and hasattr(provider, 'mood_imitation_dialogs'):
                provider.mood_imitation_dialogs = dialogues
                logger.info(f"恢复了 {len(dialogues)} 条模仿对话")
                return True
            else:
                logger.warning("无法访问模仿对话接口")
                return False
                
        except Exception as e:
            logger.error(f"恢复模仿对话失败: {e}")
            return False

    async def _cleanup_old_backups(self, group_id: str):
        """清理旧备份"""
        try:
            # 获取备份列表
            backups = await self.db_manager.get_persona_backups(group_id, limit=100)
            
            if len(backups) > self.max_backups_per_group:
                # 删除多余的备份（保留最新的）
                excess_count = len(backups) - self.max_backups_per_group
                old_backups = backups[self.max_backups_per_group:]
                
                conn = await self.db_manager.get_group_connection(group_id)
                cursor = await conn.cursor()
                
                for backup in old_backups:
                    await cursor.execute('DELETE FROM persona_backups WHERE id = ?', (backup['id'],))
                
                await conn.commit()
                logger.info(f"清理了 {excess_count} 个旧备份")
                
        except Exception as e:
            logger.error(f"清理旧备份失败: {e}")

    async def get_backup_list(self, group_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取备份列表"""
        try:
            backups = await self.db_manager.get_persona_backups(group_id, limit)
            
            # 添加备份大小信息
            for backup in backups:
                backup['display_name'] = f"{backup['backup_name']} ({backup['created_at'][:16]})"
                backup['reason_short'] = backup['backup_reason'][:50] if backup['backup_reason'] else ''
            
            return backups
            
        except Exception as e:
            logger.error(f"获取备份列表失败: {e}")
            return []

    async def schedule_auto_backup(self, group_id: str):
        """计划自动备份"""
        if not self.auto_backup_enabled:
            return
        
        try:
            # 检查是否需要自动备份
            last_backup_time = await self._get_last_backup_time(group_id)
            current_time = time.time()
            
            if (current_time - last_backup_time) >= (self.backup_interval_hours * 3600):
                await self.create_backup_before_update(group_id, "Scheduled auto backup")
                logger.info(f"群 {group_id} 自动备份完成")
                
        except Exception as e:
            logger.error(f"自动备份失败: {e}")

    async def _get_last_backup_time(self, group_id: str) -> float:
        """获取最后备份时间"""
        try:
            backups = await self.db_manager.get_persona_backups(group_id, limit=1)
            if backups:
                # 解析时间字符串
                backup_time_str = backups[0]['created_at']
                backup_time = datetime.fromisoformat(backup_time_str.replace('Z', '+00:00'))
                return backup_time.timestamp()
            else:
                return 0.0  # 如果没有备份，返回0
                
        except Exception as e:
            logger.error(f"获取最后备份时间失败: {e}")
            return 0.0

    async def export_backup(self, group_id: str, backup_id: int) -> Optional[Dict[str, Any]]:
        """导出备份数据"""
        try:
            backup_data = await self.db_manager.restore_persona_backup(group_id, backup_id)
            
            if backup_data:
                # 添加导出元信息
                backup_data['export_time'] = datetime.now().isoformat()
                backup_data['group_id'] = group_id
                backup_data['backup_id'] = backup_id
                
                return backup_data
            
            return None
            
        except Exception as e:
            logger.error(f"导出备份失败: {e}")
            return None

    async def import_backup(self, group_id: str, backup_data: Dict[str, Any]) -> int:
        """导入备份数据"""
        try:
            # 验证备份数据格式
            if not self._validate_backup_data(backup_data):
                raise BackupError("备份数据格式无效")
            
            # 创建导入备份
            import_backup_data = {
                'backup_name': f"导入_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                'original_persona': backup_data['original_persona'],
                'imitation_dialogues': backup_data['imitation_dialogues'],
                'backup_reason': f"Imported from backup {backup_data.get('backup_id', 'unknown')}"
            }
            
            backup_id = await self.db_manager.backup_persona(group_id, import_backup_data)
            logger.info(f"备份数据导入成功，新备份ID: {backup_id}")
            
            return backup_id
            
        except Exception as e:
            logger.error(f"导入备份失败: {e}")
            raise BackupError(f"导入备份失败: {str(e)}")

    def _validate_backup_data(self, backup_data: Dict[str, Any]) -> bool:
        """验证备份数据格式"""
        required_fields = ['original_persona', 'imitation_dialogues']
        
        for field in required_fields:
            if field not in backup_data:
                logger.error(f"备份数据缺少必需字段: {field}")
                return False
        
        # 验证人格数据结构
        persona = backup_data['original_persona']
        if not isinstance(persona, dict):
            logger.error("人格数据格式错误")
            return False
        
        # 验证对话列表结构
        dialogues = backup_data['imitation_dialogues']
        if not isinstance(dialogues, list):
            logger.error("对话列表格式错误")
            return False
        
        return True

    async def get_backup_statistics(self, group_id: str) -> Dict[str, Any]:
        """获取备份统计信息"""
        try:
            backups = await self.db_manager.get_persona_backups(group_id, limit=100)
            
            if not backups:
                return {
                    'total_backups': 0,
                    'latest_backup': None,
                    'auto_backup_enabled': self.auto_backup_enabled
                }
            
            latest_backup = backups if backups else None
            auto_backup_count = len([b for b in backups if 'auto' in b['backup_reason'].lower()])
            
            return {
                'total_backups': len(backups),
                'auto_backup_count': auto_backup_count,
                'manual_backup_count': len(backups) - auto_backup_count,
                'latest_backup': latest_backup,
                'auto_backup_enabled': self.auto_backup_enabled,
                'backup_interval_hours': self.backup_interval_hours,
                'max_backups_per_group': self.max_backups_per_group
            }
            
        except Exception as e:
            logger.error(f"获取备份统计失败: {e}")
            return {}

    async def stop(self):
        """停止服务"""
        try:
            logger.info("人格备份管理服务已停止")
            return True
        except Exception as e:
            logger.error(f"停止人格备份管理服务失败: {e}")
            return False
