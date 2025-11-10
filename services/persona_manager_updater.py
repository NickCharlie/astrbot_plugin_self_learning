"""
PersonaManager增量更新服务
基于AstrBot框架的PersonaManager实现增量人格更新功能
"""
import time
import json
from typing import Dict, List, Optional, Any
from datetime import datetime

from astrbot.api import logger
from astrbot.api.star import Context

from ..core.interfaces import IPersonaManagerUpdater
from ..config import PluginConfig
from ..exceptions import SelfLearningError


class PersonaManagerUpdater(IPersonaManagerUpdater):
    """
    基于PersonaManager的增量更新服务
    
    功能：
    1. 直接通过PersonaManager创建和管理群组专用persona
    2. 实现增量内容的智能合并
    3. 自动清理历史版本
    4. 支持无缝回退到基础persona
    """
    
    def __init__(self, config: PluginConfig, context: Context):
        self.config = config
        self.context = context
        
        # 获取AstrBot的PersonaManager
        self.persona_manager = None
        self._init_persona_manager()
        
        # 群组到persona的映射关系
        self.group_persona_mapping: Dict[str, str] = {}
        
        # 增量更新历史记录
        self.update_history: Dict[str, List[Dict]] = {}  # group_id -> [update_record]
        
        logger.info("PersonaManager增量更新服务初始化完成")
    
    def _init_persona_manager(self):
        """初始化PersonaManager"""
        try:
            # 从context获取PersonaManager实例
            if hasattr(self.context, 'persona_manager') and self.context.persona_manager:
                self.persona_manager = self.context.persona_manager
                logger.info("成功获取AstrBot PersonaManager实例")
            else:
                logger.warning("无法获取PersonaManager实例，将回退到文件更新模式")
                self.persona_manager = None
        except Exception as e:
            logger.error(f"初始化PersonaManager失败: {e}")
            self.persona_manager = None
    
    async def apply_incremental_update(self, group_id: str, update_content: str) -> bool:
        """应用增量更新到PersonaManager中的persona"""
        try:
            if not self.persona_manager:
                logger.warning("PersonaManager不可用，跳过增量更新")
                return False
            
            logger.info(f"为群组 {group_id} 应用增量更新: {update_content[:50]}...")
            
            # 获取或创建群组专用persona
            persona_id = await self.get_or_create_group_persona(group_id)
            if not persona_id:
                logger.error(f"无法获取群组 {group_id} 的persona")
                return False
            
            # 应用增量更新
            success = await self.merge_incremental_updates(persona_id, update_content)
            
            if success:
                # 记录更新历史
                self._record_update_history(group_id, update_content, persona_id)
                logger.info(f"群组 {group_id} 增量更新应用成功")
                return True
            else:
                logger.error(f"群组 {group_id} 增量更新应用失败")
                return False
                
        except Exception as e:
            logger.error(f"应用增量更新失败: {e}")
            return False
    
    async def create_incremental_persona(self, base_persona_id: str, group_id: str, increments: List[str]) -> str:
        """基于基础persona创建增量更新的新persona"""
        try:
            if not self.persona_manager:
                raise SelfLearningError("PersonaManager不可用")
            
            # 获取基础persona
            base_persona = await self.persona_manager.get_persona(base_persona_id)
            if not base_persona:
                logger.warning(f"基础persona {base_persona_id} 不存在，使用默认persona")
                base_persona = await self.persona_manager.get_default_persona_v3()
            
            # 生成新的persona ID
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            new_persona_id = f"group_{group_id}_incremental_{timestamp}"
            
            # 构建增量更新的system_prompt
            base_prompt = base_persona.system_prompt if hasattr(base_persona, 'system_prompt') else base_persona.get('prompt', '')
            
            # 格式化增量内容
            incremental_content = self._format_incremental_content(increments)
            
            # 合并prompt
            new_prompt = f"{base_prompt}\n\n【增量更新 - {datetime.now().strftime('%Y-%m-%d %H:%M')}】\n{incremental_content}"
            
            # 创建新的persona
            new_persona = await self.persona_manager.create_persona(
                persona_id=new_persona_id,
                system_prompt=new_prompt,
                begin_dialogs=base_persona.begin_dialogs if hasattr(base_persona, 'begin_dialogs') else base_persona.get('begin_dialogs', []),
                tools=base_persona.tools if hasattr(base_persona, 'tools') else base_persona.get('tools')
            )
            
            if new_persona:
                # 更新映射关系
                self.group_persona_mapping[group_id] = new_persona_id
                logger.info(f"成功为群组 {group_id} 创建增量persona: {new_persona_id}")
                return new_persona_id
            else:
                logger.error(f"创建增量persona失败")
                return ""
                
        except Exception as e:
            logger.error(f"创建增量persona失败: {e}")
            return ""
    
    async def get_or_create_group_persona(self, group_id: str, base_persona_id: str = None) -> str:
        """获取或创建群组专用persona"""
        try:
            if not self.persona_manager:
                return ""
            
            # 检查是否已有群组专用persona
            if group_id in self.group_persona_mapping:
                persona_id = self.group_persona_mapping[group_id]
                # 验证persona是否仍然存在
                try:
                    existing_persona = await self.persona_manager.get_persona(persona_id)
                    if existing_persona:
                        logger.info(f"使用现有群组persona: {persona_id}")
                        return persona_id
                except:
                    # persona不存在，清理映射
                    del self.group_persona_mapping[group_id]
            
            # 创建新的群组persona
            if not base_persona_id:
                # 使用默认persona作为基础
                base_persona_id = "default"
            
            # 生成群组专用persona ID
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            group_persona_id = f"group_{group_id}_{timestamp}"
            
            # 获取基础persona
            try:
                base_persona = await self.persona_manager.get_persona(base_persona_id)
            except:
                # 如果指定的基础persona不存在，使用默认
                base_persona = await self.persona_manager.get_default_persona_v3()
            
            if not base_persona:
                logger.error("无法获取基础persona")
                return ""
            
            # 复制基础persona创建群组专用版本
            base_prompt = base_persona.system_prompt if hasattr(base_persona, 'system_prompt') else base_persona.get('prompt', '')
            
            # 添加群组标识到prompt
            group_prompt = f"{base_prompt}\n\n【群组专用版本 - 群组ID: {group_id}】\n创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            new_persona = await self.persona_manager.create_persona(
                persona_id=group_persona_id,
                system_prompt=group_prompt,
                begin_dialogs=base_persona.begin_dialogs if hasattr(base_persona, 'begin_dialogs') else base_persona.get('begin_dialogs', []),
                tools=base_persona.tools if hasattr(base_persona, 'tools') else base_persona.get('tools')
            )
            
            if new_persona:
                self.group_persona_mapping[group_id] = group_persona_id
                logger.info(f"成功为群组 {group_id} 创建专用persona: {group_persona_id}")
                return group_persona_id
            else:
                logger.error(f"创建群组专用persona失败")
                return ""
                
        except Exception as e:
            logger.error(f"获取或创建群组persona失败: {e}")
            return ""
    
    async def merge_incremental_updates(self, persona_id: str, new_content: str) -> bool:
        """将新的增量内容合并到现有persona的末尾"""
        try:
            if not self.persona_manager:
                return False
            
            # 获取现有persona
            existing_persona = await self.persona_manager.get_persona(persona_id)
            if not existing_persona:
                logger.error(f"Persona {persona_id} 不存在")
                return False
            
            # 获取现有prompt
            current_prompt = existing_persona.system_prompt if hasattr(existing_persona, 'system_prompt') else existing_persona.get('prompt', '')
            
            # 清理重复内容
            cleaned_prompt = self._clean_duplicate_content(current_prompt)
            
            # 格式化新的增量内容
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            formatted_content = f"\n\n【增量更新 - {timestamp}】\n{new_content}"
            
            # 合并内容
            updated_prompt = cleaned_prompt + formatted_content
            
            # 更新persona
            updated_persona = await self.persona_manager.update_persona(
                persona_id=persona_id,
                system_prompt=updated_prompt,
                begin_dialogs=existing_persona.begin_dialogs if hasattr(existing_persona, 'begin_dialogs') else existing_persona.get('begin_dialogs'),
                tools=existing_persona.tools if hasattr(existing_persona, 'tools') else existing_persona.get('tools')
            )
            
            if updated_persona:
                logger.info(f"成功更新persona {persona_id} 的增量内容")
                return True
            else:
                logger.error(f"更新persona {persona_id} 失败")
                return False
                
        except Exception as e:
            logger.error(f"合并增量更新失败: {e}")
            return False
    
    async def cleanup_old_personas(self, group_id: str, keep_count: int = 5) -> bool:
        """清理旧的增量persona，只保留最新的几个"""
        try:
            if not self.persona_manager:
                return False
            
            # 获取所有群组相关的persona
            all_personas = await self.persona_manager.get_all_personas()
            group_personas = [
                p for p in all_personas 
                if p.persona_id.startswith(f"group_{group_id}_")
            ]
            
            if len(group_personas) <= keep_count:
                logger.info(f"群组 {group_id} 的persona数量({len(group_personas)})未超过限制({keep_count})，无需清理")
                return True
            
            # 按创建时间排序，删除最旧的
            group_personas.sort(key=lambda p: p.created_at)
            personas_to_delete = group_personas[:-keep_count]
            
            deleted_count = 0
            for persona in personas_to_delete:
                try:
                    await self.persona_manager.delete_persona(persona.persona_id)
                    deleted_count += 1
                    logger.info(f"删除旧persona: {persona.persona_id}")
                    
                    # 清理映射关系
                    if self.group_persona_mapping.get(group_id) == persona.persona_id:
                        del self.group_persona_mapping[group_id]
                        
                except Exception as e:
                    logger.warning(f"删除persona {persona.persona_id} 失败: {e}")
            
            logger.info(f"群组 {group_id} 清理完成，删除了 {deleted_count} 个旧persona")
            return True
            
        except Exception as e:
            logger.error(f"清理旧persona失败: {e}")
            return False
    
    def _format_incremental_content(self, increments: List[str]) -> str:
        """格式化增量内容"""
        if not increments:
            return ""
        
        formatted_lines = []
        additions = []
        modifications = []
        
        for increment in increments:
            increment = increment.strip()
            if increment.startswith('+'):
                additions.append(f"• {increment[1:].strip()}")
            elif increment.startswith('~'):
                modifications.append(f"• {increment[1:].strip()}")
            else:
                # 默认作为添加项
                additions.append(f"• {increment}")
        
        if additions:
            formatted_lines.append("【新增特征】")
            formatted_lines.extend(additions)
        
        if modifications:
            if formatted_lines:
                formatted_lines.append("")
            formatted_lines.append("【行为调整】")
            formatted_lines.extend(modifications)
        
        return "\n".join(formatted_lines)
    
    def _clean_duplicate_content(self, content: str) -> str:
        """清理重复的增量更新内容"""
        if not content:
            return content
        
        lines = content.split('\n')
        seen_updates = set()
        cleaned_lines = []
        current_section = None
        
        for line in lines:
            line_stripped = line.strip()
            
            # 检测增量更新标记
            if '【增量更新' in line_stripped:
                # 跳过重复的更新标记
                update_signature = line_stripped.split('】')[0] + '】'
                if update_signature in seen_updates:
                    current_section = 'skip'
                    continue
                else:
                    seen_updates.add(update_signature)
                    current_section = 'keep'
                    cleaned_lines.append(line)
            elif current_section == 'skip':
                # 在跳过模式下，直到遇到新的更新标记或文件结束
                continue
            else:
                # 保留其他内容
                cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)
    
    def _record_update_history(self, group_id: str, content: str, persona_id: str):
        """记录更新历史"""
        if group_id not in self.update_history:
            self.update_history[group_id] = []
        
        record = {
            'timestamp': time.time(),
            'content': content,
            'persona_id': persona_id,
            'datetime': datetime.now().isoformat()
        }
        
        self.update_history[group_id].append(record)
        
        # 保持最近的20条记录
        if len(self.update_history[group_id]) > 20:
            self.update_history[group_id] = self.update_history[group_id][-20:]
    
    def get_update_history(self, group_id: str) -> List[Dict]:
        """获取群组的更新历史"""
        return self.update_history.get(group_id, [])
    
    def is_available(self) -> bool:
        """检查服务是否可用"""
        return self.persona_manager is not None