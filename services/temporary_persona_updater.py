"""
临时人格更新器 - 实现安全的临时人格学习和更新
"""
import os
import json
import time
import asyncio
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta

from astrbot.api import logger
from astrbot.api.star import Context

from ..config import PluginConfig

from ..core.interfaces import IPersonaUpdater, IPersonaBackupManager

from ..services.database_manager import DatabaseManager
from ..services.persona_manager_updater import PersonaManagerUpdater

from ..statics.temp_persona_messages import TemporaryPersonaMessages

from ..statics.prompts import MULTIDIMENSIONAL_ANALYZER_FILTER_MESSAGE_PROMPT

from ..exceptions import SelfLearningError


class TemporaryPersonaUpdater:
    """
    临时人格更新器
    功能：
    1. 严格的人格备份管理（人格名_时间.txt格式）
    2. 临时人格应用和过期管理
    3. 基于新特征和对话的临时学习
    4. 安全的恢复机制
    """
    
    def __init__(self, 
                 config: PluginConfig, 
                 context: Context,
                 persona_updater: IPersonaUpdater,
                 backup_manager: IPersonaBackupManager,
                 db_manager: DatabaseManager):
        self.config = config
        self.context = context
        self.persona_updater = persona_updater
        self.backup_manager = backup_manager
        # llm_client 参数保持为了兼容性，但不使用
        self.db_manager = db_manager
        
        # 临时人格存储
        self.active_temp_personas: Dict[str, Dict] = {}  # group_id -> temp_persona_info
        self.expiry_tasks: Dict[str, asyncio.Task] = {}  # group_id -> expiry_task
        
        # 备份目录设置
        self.backup_base_dir = os.path.join(config.data_dir, "persona_backups")
        self._ensure_backup_directory()
        
        # 人格更新文件路径
        self.persona_updates_file = os.path.join(config.data_dir, "persona_updates.txt")
        
        # 初始化PersonaManager更新器
        self.persona_manager_updater = PersonaManagerUpdater(config, context)
        
        logger.info("临时人格更新器初始化完成")

    async def _get_framework_persona(self, group_id: str = None) -> Optional[Dict[str, Any]]:
        """
        获取框架当前人格的辅助方法 - 兼容新旧框架API
        返回: Personality的字典表示
        """
        try:
            # 优先使用新版PersonaManager
            if hasattr(self.context, 'persona_manager') and self.context.persona_manager:
                persona = await self.context.persona_manager.get_default_persona_v3(group_id)
                if persona:
                    return dict(persona) if isinstance(persona, dict) else persona

            # 回退到旧方法（兼容性）
            provider = self.context.get_using_provider()
            if provider and hasattr(provider, 'curr_personality') and provider.curr_personality:
                return dict(provider.curr_personality) if isinstance(provider.curr_personality, dict) else provider.curr_personality

            return None
        except Exception as e:
            logger.warning(f"获取框架人格失败: {e}")
            return None

    async def _update_framework_persona(self, persona_id: str, system_prompt: str, begin_dialogs: List[str] = None, tools: List[str] = None) -> bool:
        """
        更新框架人格的辅助方法 - 兼容新旧框架API
        """
        try:
            # 优先使用新版PersonaManager
            if hasattr(self.context, 'persona_manager') and self.context.persona_manager:
                await self.context.persona_manager.update_persona(
                    persona_id=persona_id,
                    system_prompt=system_prompt,
                    begin_dialogs=begin_dialogs,
                    tools=tools
                )
                return True

            # 回退到旧方法（兼容性）- 直接修改provider.curr_personality
            provider = self.context.get_using_provider()
            if provider and hasattr(provider, 'curr_personality'):
                if isinstance(provider.curr_personality, dict):
                    provider.curr_personality['prompt'] = system_prompt
                    if begin_dialogs is not None:
                        provider.curr_personality['begin_dialogs'] = begin_dialogs
                else:
                    if hasattr(provider.curr_personality, 'prompt'):
                        provider.curr_personality.prompt = system_prompt
                    if begin_dialogs is not None and hasattr(provider.curr_personality, 'begin_dialogs'):
                        provider.curr_personality.begin_dialogs = begin_dialogs
                return True

            return False
        except Exception as e:
            logger.error(f"更新框架人格失败: {e}")
            return False

    def _ensure_backup_directory(self):
        """确保备份目录存在"""
        try:
            os.makedirs(self.backup_base_dir, exist_ok=True)
        except Exception as e:
            logger.error(TemporaryPersonaMessages.ERROR_BACKUP_DIRECTORY_CREATE.format(error=e))
            raise SelfLearningError(f"创建备份目录失败: {e}")
    
    async def create_strict_persona_backup(self, group_id: str, reason: str = "临时更新前备份") -> str:
        """
        创建严格的人格备份（人格名_时间.txt格式）
        """
        try:
            # 获取当前人格信息
            current_persona = await self.persona_updater.get_current_persona(group_id)
            if not current_persona:
                raise SelfLearningError(TemporaryPersonaMessages.ERROR_NO_ORIGINAL_PERSONA)
            
            # 生成备份文件名：人格名_时间
            persona_name = current_persona.get('name', '默认人格').replace(' ', '_')
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_filename = f"{persona_name}_{timestamp}.txt"
            
            # 创建群组备份目录
            group_backup_dir = os.path.join(self.backup_base_dir, f"group_{group_id}")
            os.makedirs(group_backup_dir, exist_ok=True)
            
            backup_file_path = os.path.join(group_backup_dir, backup_filename)
            
            # 准备备份数据
            backup_data = {
                "backup_info": {
                    "persona_name": current_persona.get('name', '默认人格'),
                    "backup_time": datetime.now().isoformat(),
                    "backup_reason": reason,
                    "group_id": group_id
                },
                "persona_data": {
                    "name": current_persona.get('name', ''),
                    "prompt": current_persona.get('prompt', ''),
                    "settings": current_persona.get('settings', {}),
                    "mood_imitation_dialogs": current_persona.get('mood_imitation_dialogs', []),
                    "style_attributes": current_persona.get('style_attributes', {})
                },
                "metadata": {
                    "backup_version": "1.0",
                    "plugin_version": "1.0.0"
                }
            }
            
            # 写入备份文件（txt格式，JSON内容）
            with open(backup_file_path, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, ensure_ascii=False, indent=2)
            
            # 同时在数据库中记录备份
            await self.backup_manager.create_backup_before_update(group_id, reason)
            
            logger.info(TemporaryPersonaMessages.LOG_BACKUP_CREATED.format(
                group_id=group_id,
                backup_name=backup_filename
            ))
            
            return backup_file_path
            
        except Exception as e:
            logger.error(TemporaryPersonaMessages.BACKUP_FAILED.format(error=e))
            raise SelfLearningError(f"创建人格备份失败: {e}")
    
    async def apply_temporary_persona_update(self, 
                                           group_id: str, 
                                           new_features: List[str],
                                           example_dialogs: List[str],
                                           duration_minutes: int = 60) -> bool:
        """
        应用临时人格更新
        
        Args:
            group_id: 群组ID
            new_features: 新的特征字符串列表
            example_dialogs: 需要模仿的对话列表（注意：这些应该是从真实消息提取的特征，不是虚假对话）
            duration_minutes: 临时人格持续时间（分钟）
        
        Returns:
            bool: 是否应用成功
        """
        try:
            # 验证example_dialogs不包含虚假对话
            validated_dialogs = await self._validate_dialog_authenticity(example_dialogs)
            
            # 检查是否已有活动的临时人格
            if group_id in self.active_temp_personas:
                raise SelfLearningError(TemporaryPersonaMessages.ERROR_TEMP_PERSONA_CONFLICT)
            
            # 创建严格备份
            backup_path = await self.create_strict_persona_backup(group_id, "临时人格更新前备份")
            
            # 获取当前人格
            original_persona = await self.persona_updater.get_current_persona(group_id)
            
            # 创建临时增强人格（使用验证后的对话）
            temp_persona = await self._create_enhanced_persona(
                original_persona, new_features, validated_dialogs
            )
            
            # 应用临时人格到系统
            success = await self._apply_persona_to_system(group_id, temp_persona)
            if not success:
                raise SelfLearningError("应用临时人格到系统失败")
            
            # 记录临时人格信息
            expiry_time = time.time() + (duration_minutes * 60)
            temp_persona_info = {
                'original_persona': original_persona,
                'temp_persona': temp_persona,
                'backup_path': backup_path,
                'start_time': time.time(),
                'expiry_time': expiry_time,
                'duration_minutes': duration_minutes,
                'new_features': new_features,
                'example_dialogs': example_dialogs
            }
            
            self.active_temp_personas[group_id] = temp_persona_info
            
            # 设置过期任务
            expiry_task = asyncio.create_task(
                self._schedule_temp_persona_expiry(group_id, duration_minutes * 60)
            )
            self.expiry_tasks[group_id] = expiry_task
            
            logger.info(TemporaryPersonaMessages.LOG_TEMP_PERSONA_STARTED.format(
                group_id=group_id,
                persona_name=temp_persona.get('name', '临时人格')
            ))
            
            return True
            
        except Exception as e:
            logger.error(TemporaryPersonaMessages.TEMP_PERSONA_CREATE_FAILED.format(error=e))
            return False
    
    async def _create_enhanced_persona(self, 
                                     original_persona: Dict[str, Any],
                                     new_features: List[str],
                                     example_dialogs: List[str]) -> Dict[str, Any]:
        """
        基于原始人格创建增强的临时人格
        """
        # 复制原始人格
        enhanced_persona = original_persona.copy()
        
        # 增强prompt
        original_prompt = original_persona.get('prompt', '')
        feature_enhancement = self._build_feature_enhancement(new_features)
        
        enhanced_prompt = f'{original_prompt}\n\n【临时特征增强】\n{feature_enhancement}\n\n【参考对话风格】\n请参考以下对话风格进行回应：'
        
        # 添加对话示例
        if example_dialogs:
            dialog_examples = ['\n\".join([f\"- {dialog}' for dialog in example_dialogs[:5]]  # 限制数量
            enhanced_prompt += f'{dialog_examples}'
        
        enhanced_persona.update({
            'name': f"{original_persona.get('name', '默认人格')}_临时增强",
            'prompt': enhanced_prompt,
            'mood_imitation_dialogs': (
                original_persona.get('mood_imitation_dialogs', []) + example_dialogs
            )[-20:],  # 保留最新20条
            'temp_features': new_features,
            'temp_created_at': datetime.now().isoformat()
            })
        
        return enhanced_persona
    
    def _build_feature_enhancement(self, features: List[str]) -> str:
        """构建特征增强文本"""
        if not features:
            return '"\"'
        
        enhancement_parts = []
        for i, feature in enumerate(features, 1):
            enhancement_parts.append(f"{i}. {feature}")
        
        return "\n".join(enhancement_parts)
    
    async def _apply_persona_to_system(self, group_id: str, persona: Dict[str, Any]) -> bool:
        """将人格应用到系统中 - 通过增强system prompt而不是替换整个人格"""
        try:
            logger.info(f"尝试将增量人格更新应用到群组 {group_id} 的系统中")
            logger.info(f"增强人格名称: {persona.get('name', '未知')}")
            
            # 获取provider并更新prompt
            provider = self.context.get_using_provider()
            if not provider:
                logger.warning("无法获取provider")
                return False
            
            # 检查是否有当前人格
            if not hasattr(provider, 'curr_personality'):
                logger.error("Provider没有curr_personality属性")
                return False
            
            if not provider.curr_personality:
                logger.warning("当前没有设置人格，将创建新的人格")
                # 创建基础人格
                provider.curr_personality = {
                    'name': persona.get('name', '默认人格'),
                    'prompt': persona.get('prompt', ''),
                    'begin_dialogs': [],
                    'mood_imitation_dialogs': []
                }
                logger.info(f"创建了新的基础人格并应用增量更新")
                return True
            
            # 获取原有的基础prompt
            original_prompt = provider.curr_personality.get('prompt', '')
            logger.info(f"原有prompt长度: {len(original_prompt)}")
            
            # 从增强的persona中提取增量更新部分
            enhanced_prompt = persona.get('prompt', '')
            
            # 查找增量更新标记
            update_marker = "【增量更新 -"
            if update_marker in enhanced_prompt:
                # 提取增量更新部分
                update_start = enhanced_prompt.find(update_marker)
                if update_start != -1:
                    incremental_update = enhanced_prompt[update_start:]
                    logger.info(f"提取到增量更新内容: {incremental_update[:100]}...")
                    
                    # 检查原有prompt是否已包含此更新
                    if incremental_update not in original_prompt:
                        # 将增量更新附加到原有prompt后面
                        updated_prompt = original_prompt + incremental_update
                        provider.curr_personality['prompt'] = updated_prompt
                        
                        logger.info(f"成功将增量更新附加到system prompt")
                        logger.info(f"更新后prompt长度: {len(updated_prompt)}")
                        
                        return True
                    else:
                        logger.info("增量更新已存在于当前prompt中，跳过重复更新")
                        return True
                else:
                    logger.warning("未找到增量更新标记的开始位置")
            else:
                # 如果没有找到增量更新标记，直接使用整个增强的prompt
                logger.info("未找到增量更新标记，使用整个增强的prompt")
                provider.curr_personality['prompt'] = enhanced_prompt
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"应用人格到系统失败: {e}")
            return False
    
    async def _schedule_temp_persona_expiry(self, group_id: str, duration_seconds: float):
        """调度临时人格过期"""
        try:
            await asyncio.sleep(duration_seconds)
            await self.remove_temporary_persona(group_id, reason="自动过期")
        except asyncio.CancelledError:
            logger.info(f"临时人格过期任务被取消: {group_id}")
        except Exception as e:
            logger.error(f"临时人格过期处理失败: {e}")
    
    async def remove_temporary_persona(self, group_id: str, reason: str = "手动移除") -> bool:
        """
        移除临时人格，恢复原始人格
        """
        try:
            if group_id not in self.active_temp_personas:
                return False
            
            temp_info = self.active_temp_personas[group_id]
            original_persona = temp_info['original_persona']
            
            # 恢复原始人格
            success = await self._apply_persona_to_system(group_id, original_persona)
            
            if success:
                # 清理临时人格记录
                del self.active_temp_personas[group_id]
                
                # 取消过期任务
                if group_id in self.expiry_tasks:
                    self.expiry_tasks[group_id].cancel()
                    del self.expiry_tasks[group_id]
                
                logger.info(TemporaryPersonaMessages.LOG_TEMP_PERSONA_EXPIRED.format(
                    group_id=group_id,
                    persona_name=temp_info['temp_persona'].get('name', '临时人格')
                ))
                
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"移除临时人格失败: {e}")
            return False
    
    async def get_temporary_persona_status(self, group_id: str) -> Optional[Dict[str, Any]]:
        """获取临时人格状态"""
        if group_id not in self.active_temp_personas:
            return None
        
        temp_info = self.active_temp_personas[group_id]
        current_time = time.time()
        
        return {
            'active': True,
            'persona_name': temp_info['temp_persona'].get('name', ''),
            'start_time': temp_info['start_time'],
            'expiry_time': temp_info['expiry_time'],
            'remaining_seconds': max(0, temp_info['expiry_time'] - current_time),
            'duration_minutes': temp_info['duration_minutes'],
            'features_count': len(temp_info['new_features']),
            'dialogs_count': len(temp_info['example_dialogs']),
            'backup_path': temp_info['backup_path']
        }
    
    async def extend_temporary_persona(self, group_id: str, additional_minutes: int) -> bool:
        """延长临时人格持续时间"""
        try:
            if group_id not in self.active_temp_personas:
                return False
            
            temp_info = self.active_temp_personas[group_id]
            
            # 更新过期时间
            additional_seconds = additional_minutes * 60
            temp_info['expiry_time'] += additional_seconds
            temp_info['duration_minutes'] += additional_minutes
            
            # 取消旧的过期任务
            if group_id in self.expiry_tasks:
                self.expiry_tasks[group_id].cancel()
            
            # 创建新的过期任务
            remaining_seconds = temp_info['expiry_time'] - time.time()
            expiry_task = asyncio.create_task(
                self._schedule_temp_persona_expiry(group_id, remaining_seconds)
            )
            self.expiry_tasks[group_id] = expiry_task
            
            logger.info(f"临时人格时间已延长 {additional_minutes} 分钟，群组: {group_id}")
            return True
            
        except Exception as e:
            logger.error(f"延长临时人格失败: {e}")
            return False
    
    async def list_persona_backups(self, group_id: str) -> List[Dict[str, Any]]:
        """列出指定群组的人格备份文件"""
        try:
            group_backup_dir = os.path.join(self.backup_base_dir, f"group_{group_id}")
            if not os.path.exists(group_backup_dir):
                return []
            
            backups = []
            for filename in os.listdir(group_backup_dir):
                if filename.endswith('.txt'):
                    file_path = os.path.join(group_backup_dir, filename)
                    try:
                        # 读取备份文件信息
                        with open(file_path, 'r', encoding='utf-8') as f:
                            backup_data = json.load(f)
                        
                        backup_info = {
                            'filename': filename,
                            'file_path': file_path,
                            'persona_name': backup_data.get('backup_info', {}).get('persona_name', ''),
                            'backup_time': backup_data.get('backup_info', {}).get('backup_time', ''),
                            'backup_reason': backup_data.get('backup_info', {}).get('backup_reason', ''),
                            'file_size': os.path.getsize(file_path)
                        }
                        backups.append(backup_info)
                    except Exception as e:
                        logger.warning(f"读取备份文件失败 {filename}: {e}")
            
            # 按时间排序（最新的在前）
            backups.sort(key=lambda x: x['backup_time'], reverse=True)
            return backups
            
        except Exception as e:
            logger.error(f"列出人格备份失败: {e}")
            return []
    
    async def restore_from_backup_file(self, group_id: str, backup_file_path: str) -> bool:
        """从备份文件恢复人格"""
        try:
            if not os.path.exists(backup_file_path):
                raise SelfLearningError(f"备份文件不存在: {backup_file_path}")
            
            # 读取备份数据
            with open(backup_file_path, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)
            
            persona_data = backup_data.get('persona_data', {})
            if not persona_data:
                raise SelfLearningError("备份文件中没有有效的人格数据")
            
            # 在恢复前创建当前状态备份
            await self.create_strict_persona_backup(group_id, f"恢复前备份_{datetime.now().strftime('%H%M%S')}")
            
            # 移除临时人格（如果存在）
            if group_id in self.active_temp_personas:
                await self.remove_temporary_persona(group_id, "恢复备份前移除")
            
            # 应用备份的人格
            success = await self._apply_persona_to_system(group_id, persona_data)
            
            if success:
                backup_name = backup_data.get('backup_info', {}).get('persona_name', '备份人格')
                logger.info(TemporaryPersonaMessages.BACKUP_RESTORE_SUCCESS.format(backup_name=backup_name))
            
            return success
            
        except Exception as e:
            logger.error(TemporaryPersonaMessages.BACKUP_RESTORE_FAILED.format(error=e))
            return False
    
    async def read_and_apply_persona_updates(self, group_id: str) -> bool:
        """
        读取persona_updates.txt文件并应用增量人格更新
        
        Args:
            group_id: 群组ID
            
        Returns:
            bool: 是否成功应用更新
        """
        try:
            logger.info(f"开始为群组 {group_id} 读取并应用人格更新")
            
            # 检查文件是否存在
            if not os.path.exists(self.persona_updates_file):
                logger.warning(f"人格更新文件不存在: {self.persona_updates_file}")
                return False
            
            logger.info(f"人格更新文件存在: {self.persona_updates_file}")
            
            # 读取更新内容
            updates = await self._read_persona_updates()
            if not updates:
                logger.warning("没有找到有效的人格更新内容")
                return False
            
            logger.info(f"找到 {len(updates)} 个有效更新")
            
            # 创建备份
            backup_path = await self.create_strict_persona_backup(group_id, "增量更新前备份")
            logger.info(f"备份已创建: {backup_path}")
            
            # 获取当前人格
            current_persona = await self.persona_updater.get_current_persona(group_id)
            if not current_persona:
                logger.error("无法获取当前人格信息")
                return False
            
            logger.info(f"获取到当前人格: {current_persona.get('name', '未知')}")
            
            # 应用增量更新
            updated_persona = await self._apply_incremental_updates(current_persona, updates)
            logger.info(f"增量更新已应用到人格: {updated_persona.get('name', '未知')}")
            
            # 应用到系统
            success = await self._apply_persona_to_system(group_id, updated_persona)
            
            if success:
                # 清空更新文件，准备下次更新
                await self._clear_persona_updates_file()
                logger.info(f"成功应用 {len(updates)} 项人格增量更新到群组 {group_id}")
                return True
            else:
                logger.error("应用人格更新到系统失败")
                return False
                
        except Exception as e:
            logger.error(f"读取并应用人格更新失败: {e}")
            return False
    
    async def _read_persona_updates(self) -> List[str]:
        """读取人格更新文件"""
        try:
            updates = []
            logger.info(f"开始读取人格更新文件: {self.persona_updates_file}")
            
            with open(self.persona_updates_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            logger.info(f"读取到 {len(lines)} 行内容")
            
            for i, line in enumerate(lines, 1):
                line = line.strip()
                logger.debug(f"处理第{i}行: '{line}'")
                
                # 跳过空行和注释行
                if line and not line.startswith('#'):
                    # 处理不同类型的更新
                    if line.startswith('+') or line.startswith('~'):
                        updates.append(line)
                        logger.info(f"找到有效更新 (第{i}行): {line}")
            
            logger.info(f"总共找到 {len(updates)} 个有效更新")
            for idx, update in enumerate(updates, 1):
                logger.info(f"更新{idx}: {update}")
            
            return updates
            
        except Exception as e:
            logger.error(f"读取人格更新文件失败: {e}")
            return []
    
    async def _apply_incremental_updates(self, current_persona: Dict[str, Any], updates: List[str]) -> Dict[str, Any]:
        """应用增量更新到当前人格"""
        try:
            updated_persona = current_persona.copy()
            current_prompt = updated_persona.get('prompt', '')
            
            # 去除重复的更新内容
            unique_updates = list(dict.fromkeys(updates))  # 保持顺序的去重
            logger.info(f"原始更新数量: {len(updates)}, 去重后: {len(unique_updates)}")
            
            # 构建增量更新文本
            update_sections = []
            
            # 分类处理更新
            additions = []
            modifications = []
            
            for update in unique_updates:
                if update.startswith('+'):
                    additions.append(update[1:].strip())
                elif update.startswith('~'):
                    modifications.append(update[1:].strip())
            
            # 构建更新文本
            if additions:
                update_sections.append(f"【新增特征】\n" + "\n".join([f"• {add}" for add in additions]))
            
            if modifications:
                update_sections.append(f"【行为调整】\n" + "\n".join([f"• {mod}" for mod in modifications]))
            
            # 将更新附加到现有prompt
            if update_sections:
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
                update_text = f"\n\n【增量更新 - {timestamp}】\n" + "\n\n".join(update_sections)
                updated_persona['prompt'] = current_prompt + update_text
                
                # 更新人格名称以反映更新
                original_name = updated_persona.get('name', '默认人格')
                updated_persona['name'] = f"{original_name}_增量更新_{timestamp.replace(':', '').replace('-', '').replace(' ', '_')}"
            
            return updated_persona
            
        except Exception as e:
            logger.error(f"应用增量更新失败: {e}")
            return current_persona
    
    async def _clear_persona_updates_file(self):
        """清空人格更新文件，准备下次更新"""
        try:
            # 保留文件头部说明，清空更新内容
            header_content = """# 增量人格更新文件
                # 本文件用于存储增量的人格文本更新
                # 每次执行时会读取此文件的新内容并应用到当前人格

                # 格式：每行一条增量更新，支持以下格式：
                # 1. 直接添加特征：+ 特征描述
                # 2. 修改行为：~ 行为描述
                # 3. 注释行：# 开头的行会被忽略

                # 示例：
                # + 更加幽默风趣，喜欢使用轻松的语调
                # ~ 回复时更加亲切，经常使用感叹号
                # + 对新技术话题表现出浓厚兴趣

                # 以下是待应用的增量更新：
                """
            with open(self.persona_updates_file, 'w', encoding='utf-8') as f:
                f.write(header_content)
                
            logger.info("人格更新文件已清空，等待下次更新")
            
        except Exception as e:
            logger.error(f"清空人格更新文件失败: {e}")

    async def clear_persona_updates_file(self):
        """公开的清空人格更新文件方法"""
        await self._clear_persona_updates_file()

    async def apply_mood_based_persona_update(self, group_id: str, mood_type: str, mood_description: str) -> bool:
        """
        基于情绪状态应用增量人格更新 - 支持PersonaManager和文件两种方式
        
        Args:
            group_id: 群组ID
            mood_type: 情绪类型
            mood_description: 情绪描述
            
        Returns:
            bool: 是否应用成功
        """
        try:
            logger.info(f"开始应用基于情绪的增量更新: {mood_type} -> {mood_description}")
            
            # 1. 创建基于情绪的增量更新内容
            mood_update = f"~ 当前情绪状态: {mood_description}，请根据此情绪调整回复的语气和风格"
            
            # 2. 根据配置选择更新方式
            if self.config.use_persona_manager_updates and self.persona_manager_updater.is_available():
                # 使用PersonaManager更新
                logger.info("使用PersonaManager方式应用情绪更新")
                
                # 先创建备份（如果启用）
                if self.config.persona_update_backup_enabled:
                    await self._create_mood_backup_persona(group_id, mood_type)
                
                # 应用增量更新
                success = await self.persona_manager_updater.apply_incremental_update(group_id, mood_update)
                
                if success:
                    logger.info(f"PersonaManager情绪更新应用成功: {mood_type}")
                    return True
                else:
                    logger.warning("PersonaManager更新失败，回退到文件+系统prompt方式")
            
            # 传统的文件+系统prompt方式（回退或配置选择）
            logger.info("使用传统文件+系统prompt方式应用情绪更新")
            
            # 写入到persona_updates.txt文件（为了持久化和后续批量更新）
            await self._append_to_persona_updates_file(mood_update)
            logger.info(f"情绪更新已写入文件: {mood_update}")
            
            # 立即应用到当前系统的 system prompt
            success = await self._apply_mood_update_to_system_prompt(group_id, mood_description)
            
            if success:
                logger.info(f"情绪状态增量更新应用成功: {mood_type} -> {mood_description}")
                return True
            else:
                logger.warning(f"情绪状态增量更新应用失败，但文件写入成功")
                return False
            
        except Exception as e:
            logger.error(f"应用情绪状态更新失败: {e}")
            return False

    async def _apply_mood_update_to_system_prompt(self, group_id: str, mood_description: str) -> bool:
        """
        直接将情绪更新应用到系统的 system prompt
        
        Args:
            group_id: 群组ID
            mood_description: 情绪描述
            
        Returns:
            bool: 是否应用成功
        """
        try:
            # 获取provider
            provider = self.context.get_using_provider()
            if not provider:
                logger.warning("无法获取provider，无法直接更新system prompt")
                return False
            
            # 检查是否有当前人格
            if not hasattr(provider, 'curr_personality'):
                logger.warning("Provider没有curr_personality属性")
                return False
                
            if not provider.curr_personality:
                logger.warning("当前没有设置人格，无法直接更新")
                return False
            
            # 获取当前的prompt
            current_prompt = provider.curr_personality.get('prompt', '')
            
            # 彻底清理所有重复的历史内容
            cleaned_prompt = self._clean_duplicate_content(current_prompt)
            
            # 构建情绪更新文本
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
            mood_update_text = f"\n\n【当前情绪状态 - {timestamp}】\n• 情绪描述: {mood_description}\n• 请根据此情绪调整回复的语气和风格，保持语言与心情对应"
            
            # 添加新的情绪状态更新
            updated_prompt = cleaned_prompt + mood_update_text
            provider.curr_personality['prompt'] = updated_prompt
            
            logger.info(f"成功将情绪状态直接更新到system prompt")
            logger.info(f"情绪描述: {mood_description}")
            logger.info(f"更新后prompt长度: {len(updated_prompt)}")
            
            return True
            
        except Exception as e:
            logger.error(f"直接更新system prompt失败: {e}")
            return False
    
    def _clean_duplicate_content(self, content: str) -> str:
        """
        彻底清理重复的历史内容
        
        Args:
            content: 原始内容
            
        Returns:
            str: 清理后的内容
        """
        try:
            if not content:
                return content
            
            # 清理标记列表
            markers_to_clean = [
                "【增量更新 -",
                "【当前情绪状态 -", 
                "【当前社交关系状态 -",
                "【当前用户档案 -",
                "【当前学习洞察 -",
                "【当前上下文状态 -",
                "【行为调整】"
            ]
            
            lines = content.split('\n')
            cleaned_lines = []
            skip_until_next_section = False
            
            for line in lines:
                line_stripped = line.strip()
                
                # 检查是否是需要清理的标记开始
                is_marker_line = any(marker in line for marker in markers_to_clean)
                
                if is_marker_line:
                    # 跳过这个标记及其内容，直到下一个【或内容结束
                    skip_until_next_section = True
                    continue
                
                # 如果在跳过模式中，检查是否遇到新的【标记（不在清理列表中）
                if skip_until_next_section:
                    if line.startswith('【') and not any(marker in line for marker in markers_to_clean):
                        # 遇到新的标记，停止跳过
                        skip_until_next_section = False
                        cleaned_lines.append(line)
                    elif not line.startswith('【') and not line.startswith('•') and line_stripped:
                        # 遇到非标记、非列表项的内容，停止跳过
                        skip_until_next_section = False
                        cleaned_lines.append(line)
                    # 否则继续跳过
                else:
                    cleaned_lines.append(line)
            
            # 清理多余的空行
            result_lines = []
            prev_empty = False
            
            for line in cleaned_lines:
                if line.strip() == '':
                    if not prev_empty:
                        result_lines.append(line)
                    prev_empty = True
                else:
                    result_lines.append(line)
                    prev_empty = False
            
            # 移除末尾的空行
            while result_lines and result_lines[-1].strip() == '':
                result_lines.pop()
            
            cleaned_content = '\n'.join(result_lines)
            
            logger.info(f"清理前内容长度: {len(content)}, 清理后内容长度: {len(cleaned_content)}")
            
            return cleaned_content
            
        except Exception as e:
            logger.error(f"清理重复内容失败: {e}")
            return content

    async def apply_expression_style_learning(self, group_id: str, expression_patterns: List[Dict[str, Any]]) -> bool:
        """应用表达风格学习结果到人格"""
        try:
            if not expression_patterns:
                logger.debug(f"群组 {group_id} 没有新的表达风格模式需要应用")
                return False
            
            # 构建表达风格描述
            style_descriptions = []
            for pattern in expression_patterns[:5]:  # 只取前5个最重要的
                situation = pattern.get('situation', '').strip()
                expression = pattern.get('expression', '').strip()
                weight = pattern.get('weight', 1.0)
                
                if situation and expression:
                    style_descriptions.append(f"当{situation}时，倾向于使用\"{expression}\"这样的表达方式")
            
            if not style_descriptions:
                return False
            
            # 生成更新内容
            update_content = f"""
【表达风格特征】
基于最近学习到的表达模式，在对话中体现以下语言风格特点：
{chr(10).join(f'• {desc}' for desc in style_descriptions)}

这些表达方式应该自然地融入到你的回复中，而不是刻意模仿。
"""
            
            # 应用到当前人格
            if self.config.use_persona_manager_updates:
                # 使用PersonaManager方式
                persona_manager_updater = self.factory_manager.get_service_factory().create_persona_manager_updater()
                if persona_manager_updater and persona_manager_updater.is_available():
                    success = await persona_manager_updater.apply_incremental_update(group_id, update_content.strip())
                    if success:
                        logger.info(f"群组 {group_id} 表达风格学习通过PersonaManager成功应用")
                        return True
                else:
                    logger.warning("PersonaManager不可用，回退到传统文件方式")
            
            # 传统文件方式
            await self._append_to_persona_updates_file(update_content.strip())
            logger.info(f"群组 {group_id} 表达风格学习已添加到更新文件，包含 {len(style_descriptions)} 个表达模式")
            return True
            
        except Exception as e:
            logger.error(f"应用表达风格学习失败 for group {group_id}: {e}")
            return False

    async def apply_temporary_style_update(self, group_id: str, style_content: str) -> bool:
        """临时应用风格更新到当前prompt（不修改人格文件）"""
        try:
            # 直接更新到当前使用的prompt中
            provider = self.context.get_using_provider()

            # 检查provider是否存在以及是否有curr_personality属性
            if not provider:
                logger.warning("无法获取当前provider，临时风格更新失败")
                return False

            if not hasattr(provider, 'curr_personality') or not provider.curr_personality:
                logger.warning("Provider没有curr_personality属性或为空，临时风格更新失败")
                return False

            current_prompt = provider.curr_personality.get('prompt', '') if isinstance(provider.curr_personality, dict) else (provider.curr_personality.prompt if hasattr(provider.curr_personality, 'prompt') else '')
            
            # 检查是否已经有临时风格特征，如果有则替换
            lines = current_prompt.split('\n')
            filtered_lines = []
            in_temp_style_section = False
            
            for line in lines:
                if '【临时表达风格特征】' in line:
                    in_temp_style_section = True
                    continue
                elif in_temp_style_section and line.startswith('【') and '临时表达风格特征' not in line:
                    # 遇到新的【标记，结束临时风格部分
                    in_temp_style_section = False
                    filtered_lines.append(line)
                elif not in_temp_style_section:
                    filtered_lines.append(line)
            
            # 在prompt末尾添加新的临时风格特征
            updated_prompt = '\n'.join(filtered_lines).strip() + '\n\n' + style_content

            # 应用到当前人格（兼容dict和对象两种形式）
            if isinstance(provider.curr_personality, dict):
                provider.curr_personality['prompt'] = updated_prompt
            elif hasattr(provider.curr_personality, 'prompt'):
                provider.curr_personality.prompt = updated_prompt
            else:
                logger.warning("无法更新prompt，curr_personality格式不支持")
                return False

            logger.info(f"群组 {group_id} 临时风格更新已应用到当前prompt")
            return True
            
        except Exception as e:
            logger.error(f"临时风格更新失败 for group {group_id}: {e}")
            return False

    async def _append_to_persona_updates_file(self, update_content: str):
        """向人格更新文件追加内容（带去重逻辑）"""
        try:
            logger.info(f"准备向文件追加内容: {self.persona_updates_file}")
            logger.info(f"更新内容: {update_content}")
            
            # 检查文件是否存在，如果不存在先创建
            if not os.path.exists(self.persona_updates_file):
                logger.warning(f"人格更新文件不存在，将创建新文件: {self.persona_updates_file}")
                # 创建文件头部
                header_content = """# 增量人格更新文件
                    # 本文件用于存储增量的人格文本更新
                    # 每次执行时会读取此文件的新内容并应用到当前人格

                    # 格式：每行一条增量更新，支持以下格式：
                    # 1. 直接添加特征：+ 特征描述
                    # 2. 修改行为：~ 行为描述
                    # 3. 注释行：# 开头的行会被忽略

                    # 示例：
                    # + 更加幽默风趣，喜欢使用轻松的语调
                    # ~ 回复时更加亲切，经常使用感叹号
                    # + 对新技术话题表现出浓厚兴趣

                    # 以下是待应用的增量更新：
                    """
                with open(self.persona_updates_file, 'w', encoding='utf-8') as f:
                    f.write(header_content)
                logger.info(f"已创建人格更新文件: {self.persona_updates_file}")
            
            # 读取现有内容进行去重检查
            existing_content = ""
            try:
                with open(self.persona_updates_file, 'r', encoding='utf-8') as f:
                    existing_content = f.read()
            except Exception as e:
                logger.warning(f"读取现有文件内容失败: {e}")
                
            # 检查是否已存在相同的情绪状态更新
            if "当前情绪状态:" in update_content:
                # 移除旧的情绪状态更新
                lines = existing_content.split('\n')
                filtered_lines = []
                
                for line in lines:
                    # 跳过包含"当前情绪状态:"的行
                    if "当前情绪状态:" not in line:
                        filtered_lines.append(line)
                
                # 重写文件（不包含旧的情绪状态）
                with open(self.persona_updates_file, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(filtered_lines))
                    
                logger.info("已移除文件中旧的情绪状态更新")
            else:
                # 对于非情绪状态的更新，检查是否已存在相同内容
                if update_content in existing_content:
                    logger.info(f"内容已存在于文件中，跳过重复追加: {update_content}")
                    return
            
            # 追加新的更新内容
            with open(self.persona_updates_file, 'a', encoding='utf-8') as f:
                f.write(f"\n{update_content}")
            
            logger.info(f"已成功向人格更新文件追加内容: {update_content}")
            
            # 验证写入是否成功
            with open(self.persona_updates_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if update_content in content:
                    logger.info("写入验证成功，内容已确认存在于文件中")
                else:
                    logger.error("写入验证失败，内容不存在于文件中")
                    
        except Exception as e:
            logger.error(f"追加到人格更新文件失败: {e}")
            raise

    async def cleanup_temp_personas(self):
        """清理所有临时人格（用于插件卸载）"""
        for group_id in list(self.active_temp_personas.keys()):
            await self.remove_temporary_persona(group_id, "插件清理")
        
        # 取消所有过期任务
        for task in self.expiry_tasks.values():
            task.cancel()
        self.expiry_tasks.clear()

    async def _apply_social_relationship_update_to_system_prompt(self, group_id: str, relationship_info: dict) -> bool:
        """
        直接将社交关系更新应用到系统的 system prompt
        
        Args:
            group_id: 群组ID
            relationship_info: 社交关系信息 (包含用户关系、群体氛围等)
            
        Returns:
            bool: 是否应用成功
        """
        try:
            provider = self.context.get_using_provider()
            if not provider or not hasattr(provider, 'curr_personality') or not provider.curr_personality:
                logger.warning("无法获取provider或当前人格，无法直接更新system prompt")
                return False
            
            current_prompt = provider.curr_personality.get('prompt', '')
            cleaned_prompt = self._clean_duplicate_content(current_prompt)
            
            # 构建社交关系更新文本
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
            relationship_text = f"\n\n【当前社交关系状态 - {timestamp}】\n"
            
            if 'user_relationships' in relationship_info:
                relationship_text += "• 用户关系: " + relationship_info['user_relationships'] + "\n"
            if 'group_atmosphere' in relationship_info:
                relationship_text += "• 群体氛围: " + relationship_info['group_atmosphere'] + "\n"
            if 'interaction_style' in relationship_info:
                relationship_text += "• 互动风格: " + relationship_info['interaction_style'] + "\n"
                
            relationship_text += "• 请根据当前社交关系状态调整回复方式和互动风格"
            
            updated_prompt = cleaned_prompt + relationship_text
            provider.curr_personality['prompt'] = updated_prompt
            
            logger.info(f"成功将社交关系状态直接更新到system prompt")
            logger.info(f"关系信息: {relationship_info}")
            
            return True
            
        except Exception as e:
            logger.error(f"直接更新社交关系到system prompt失败: {e}")
            return False

    async def _apply_user_profile_update_to_system_prompt(self, group_id: str, profile_info: dict) -> bool:
        """
        直接将用户档案更新应用到系统的 system prompt
        
        Args:
            group_id: 群组ID
            profile_info: 用户档案信息 (包含用户偏好、兴趣等)
            
        Returns:
            bool: 是否应用成功
        """
        try:
            provider = self.context.get_using_provider()
            if not provider or not hasattr(provider, 'curr_personality') or not provider.curr_personality:
                logger.warning("无法获取provider或当前人格，无法直接更新system prompt")
                return False
            
            current_prompt = provider.curr_personality.get('prompt', '')
            cleaned_prompt = self._clean_duplicate_content(current_prompt)
            
            # 构建用户档案更新文本
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
            profile_text = f"\n\n【当前用户档案 - {timestamp}】\n"
            
            if 'preferences' in profile_info:
                profile_text += "• 用户偏好: " + profile_info['preferences'] + "\n"
            if 'interests' in profile_info:
                profile_text += "• 兴趣爱好: " + profile_info['interests'] + "\n"
            if 'communication_style' in profile_info:
                profile_text += "• 沟通风格: " + profile_info['communication_style'] + "\n"
            if 'personality_traits' in profile_info:
                profile_text += "• 性格特征: " + profile_info['personality_traits'] + "\n"
                
            profile_text += "• 请根据用户档案信息调整回复内容和方式以更好地适应用户"
            
            updated_prompt = cleaned_prompt + profile_text
            provider.curr_personality['prompt'] = updated_prompt
            
            logger.info(f"成功将用户档案直接更新到system prompt")
            logger.info(f"档案信息: {profile_info}")
            
            return True
            
        except Exception as e:
            logger.error(f"直接更新用户档案到system prompt失败: {e}")
            return False

    async def _apply_learning_insights_update_to_system_prompt(self, group_id: str, insights_info: dict) -> bool:
        """
        直接将学习洞察更新应用到系统的 system prompt
        
        Args:
            group_id: 群组ID
            insights_info: 学习洞察信息 (包含交互模式、改进建议等)
            
        Returns:
            bool: 是否应用成功
        """
        try:
            provider = self.context.get_using_provider()
            if not provider or not hasattr(provider, 'curr_personality') or not provider.curr_personality:
                logger.warning("无法获取provider或当前人格，无法直接更新system prompt")
                return False
            
            current_prompt = provider.curr_personality.get('prompt', '')
            cleaned_prompt = self._clean_duplicate_content(current_prompt)
            
            # 构建学习洞察更新文本
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
            insights_text = f"\n\n【当前学习洞察 - {timestamp}】\n"
            
            if 'interaction_patterns' in insights_info:
                insights_text += "• 交互模式: " + insights_info['interaction_patterns'] + "\n"
            if 'improvement_suggestions' in insights_info:
                insights_text += "• 改进建议: " + insights_info['improvement_suggestions'] + "\n"
            if 'effective_strategies' in insights_info:
                insights_text += "• 有效策略: " + insights_info['effective_strategies'] + "\n"
            if 'learning_focus' in insights_info:
                insights_text += "• 学习重点: " + insights_info['learning_focus'] + "\n"
                
            insights_text += "• 请根据学习洞察调整回复策略和改进交互质量"
            
            updated_prompt = cleaned_prompt + insights_text
            provider.curr_personality['prompt'] = updated_prompt
            
            logger.info(f"成功将学习洞察直接更新到system prompt")
            logger.info(f"洞察信息: {insights_info}")
            
            return True
            
        except Exception as e:
            logger.error(f"直接更新学习洞察到system prompt失败: {e}")
            return False

    async def _apply_context_awareness_update_to_system_prompt(self, group_id: str, context_info: dict) -> bool:
        """
        直接将上下文感知更新应用到系统的 system prompt
        
        Args:
            group_id: 群组ID
            context_info: 上下文感知信息 (包含当前话题、对话状态等)
            
        Returns:
            bool: 是否应用成功
        """
        try:
            provider = self.context.get_using_provider()
            if not provider or not hasattr(provider, 'curr_personality') or not provider.curr_personality:
                logger.warning("无法获取provider或当前人格，无法直接更新system prompt")
                return False
            
            current_prompt = provider.curr_personality.get('prompt', '')
            cleaned_prompt = self._clean_duplicate_content(current_prompt)
            
            # 构建上下文感知更新文本
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
            context_text = f"\n\n【当前上下文状态 - {timestamp}】\n"
            
            if 'current_topic' in context_info:
                context_text += "• 当前话题: " + context_info['current_topic'] + "\n"
            if 'conversation_state' in context_info:
                context_text += "• 对话状态: " + context_info['conversation_state'] + "\n"
            if 'recent_focus' in context_info:
                context_text += "• 近期关注: " + context_info['recent_focus'] + "\n"
            if 'dialogue_flow' in context_info:
                context_text += "• 对话流向: " + context_info['dialogue_flow'] + "\n"
                
            context_text += "• 请根据当前上下文状态保持话题连贯性并提供相关回复"
            
            updated_prompt = cleaned_prompt + context_text
            provider.curr_personality['prompt'] = updated_prompt
            
            logger.info(f"成功将上下文感知直接更新到system prompt")
            logger.info(f"上下文信息: {context_info}")
            
            return True
            
        except Exception as e:
            logger.error(f"直接更新上下文感知到system prompt失败: {e}")
            return False

    async def apply_comprehensive_update_to_system_prompt(self, group_id: str, update_data: dict) -> bool:
        """
        综合应用多种类型的增量更新到 system prompt
        
        Args:
            group_id: 群组ID
            update_data: 包含各种更新类型的数据字典
            
        Returns:
            bool: 是否应用成功
        """
        try:
            success_count = 0
            total_updates = 0
            
            # 应用情绪更新
            if 'mood' in update_data:
                total_updates += 1
                if await self._apply_mood_update_to_system_prompt(group_id, update_data['mood']):
                    success_count += 1
            
            # 应用社交关系更新
            if 'social_relationship' in update_data:
                total_updates += 1
                if await self._apply_social_relationship_update_to_system_prompt(group_id, update_data['social_relationship']):
                    success_count += 1
            
            # 应用用户档案更新
            if 'user_profile' in update_data:
                total_updates += 1
                if await self._apply_user_profile_update_to_system_prompt(group_id, update_data['user_profile']):
                    success_count += 1
            
            # 应用学习洞察更新
            if 'learning_insights' in update_data:
                total_updates += 1
                if await self._apply_learning_insights_update_to_system_prompt(group_id, update_data['learning_insights']):
                    success_count += 1
            
            # 应用上下文感知更新
            if 'context_awareness' in update_data:
                total_updates += 1
                if await self._apply_context_awareness_update_to_system_prompt(group_id, update_data['context_awareness']):
                    success_count += 1
            
            logger.info(f"综合更新完成: {success_count}/{total_updates} 项更新成功应用")
            return success_count > 0
            
        except Exception as e:
            logger.error(f"综合应用增量更新失败: {e}")
            return False

    async def _create_mood_backup_persona(self, group_id: str, mood_type: str) -> bool:
        """为情绪更新创建备份persona"""
        try:
            # 获取当前人格信息
            provider = self.context.get_using_provider()
            if not provider or not hasattr(provider, 'curr_personality') or not provider.curr_personality:
                logger.warning("无法获取当前人格信息，跳过情绪备份")
                return False
            
            current_persona = provider.curr_personality
            
            # 提取原人格信息
            if hasattr(current_persona, 'prompt'):
                original_prompt = current_persona.prompt
                original_name = getattr(current_persona, 'name', '默认人格')
            elif isinstance(current_persona, dict):
                original_prompt = current_persona.get('prompt', '')
                original_name = current_persona.get('name', '默认人格')
            else:
                logger.warning("无法解析当前人格数据")
                return False
            
            # 生成情绪备份persona名称：原人格名_年月日时间_情绪备份_情绪类型
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            backup_persona_id = f"{original_name}_{timestamp}_情绪备份_{mood_type}"
            
            # 创建备份persona
            persona_manager = self.persona_manager_updater.persona_manager
            if persona_manager:
                backup_persona = await persona_manager.create_persona(
                    persona_id=backup_persona_id,
                    system_prompt=original_prompt,
                    begin_dialogs=getattr(current_persona, 'begin_dialogs', []) if hasattr(current_persona, 'begin_dialogs') else current_persona.get('begin_dialogs', []),
                    tools=getattr(current_persona, 'tools', None) if hasattr(current_persona, 'tools') else current_persona.get('tools')
                )
                
                if backup_persona:
                    logger.info(f"成功创建情绪备份persona: {backup_persona_id}")
                    return True
                else:
                    logger.error("创建情绪备份persona失败")
                    return False
            else:
                logger.error("PersonaManager不可用，无法创建情绪备份")
                return False
                
        except Exception as e:
            logger.error(f"创建情绪备份persona失败: {e}")
            return False

    async def _validate_dialog_authenticity(self, dialogs: List[str]) -> List[str]:
        """验证对话数据的真实性，过滤虚假对话"""
        validated_dialogs = []
        
        # 定义虚假对话的特征模式
        fake_patterns = [
            r'A:\s*你最近干.*呢.*\?',  # "A: 你最近干啥呢？"模式
            r'B:\s*',                 # "B: "开头的模式
            r'用户\d+:\s*',           # "用户01: "模式
            r'.*:\s*你最近.*',        # 任何包含"你最近"的对话格式
            r'开场对话列表',          # 示例文本
            r'情绪模拟对话列表',       # 示例文本
        ]
        
        import re
        for dialog in dialogs:
            is_fake = False
            for pattern in fake_patterns:
                if re.search(pattern, dialog, re.IGNORECASE):
                    logger.warning(f"检测到可能的虚假对话，已过滤: {dialog}")
                    is_fake = True
                    break
            
            if not is_fake and len(dialog.strip()) > 3:  # 只保留有效的真实对话
                validated_dialogs.append(dialog)
        
        logger.info(f"对话验证完成: 原始{len(dialogs)}条，验证后{len(validated_dialogs)}条")
        return validated_dialogs

    async def stop(self):
        """停止服务"""
        try:
            await self.cleanup_temp_personas()
            logger.info("临时人格更新服务已停止")
            return True
        except Exception as e:
            logger.error(f"停止临时人格更新服务失败: {e}")
            return False