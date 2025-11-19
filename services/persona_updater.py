"""
人格更新服务 - 基于AstrBot框架的人格管理
"""
import os
import logging
import time # 导入 time 模块
from datetime import datetime
from typing import Dict, List, Any, Optional

from astrbot.api.star import Context
from astrbot.core.db.po import Personality
from ..config import PluginConfig

from ..core.interfaces import IPersonaUpdater, IPersonaBackupManager, MessageData, AnalysisResult, PersonaUpdateRecord # 导入 PersonaUpdateRecord
from .persona_manager_updater import PersonaManagerUpdater

from ..exceptions import PersonaUpdateError, SelfLearningError # 导入 PersonaUpdateError
from .database_manager import DatabaseManager # 导入 DatabaseManager

# MaiBot功能模块导入 - 结合MaiBot的学习功能
from .expression_pattern_learner import ExpressionPatternLearner
from .memory_graph_manager import MemoryGraphManager
from .knowledge_graph_manager import KnowledgeGraphManager


class PersonaUpdater(IPersonaUpdater):
    """
    基于AstrBot框架的人格更新器
    直接操作框架的 curr_personality 属性
    """
    
    def __init__(self, config: PluginConfig, context: Context, backup_manager: IPersonaBackupManager, llm_client: Optional[Any] = None, db_manager: DatabaseManager = None):
        self.config = config
        self.context = context
        self.backup_manager = backup_manager
        # llm_client参数保持为了兼容性，但不使用
        self.db_manager = db_manager # 添加 db_manager
        self._logger = logging.getLogger(self.__class__.__name__)
        
        # 初始化PersonaManager更新器
        self.persona_manager_updater = PersonaManagerUpdater(config, context)
        
        # 初始化MaiBot组件 - 结合MaiBot功能
        # 创建FrameworkLLMAdapter for expression learner
        from ..core.framework_llm_adapter import FrameworkLLMAdapter
        expression_llm_adapter = FrameworkLLMAdapter(context)
        expression_llm_adapter.initialize_providers(config)
        
        self.expression_learner = ExpressionPatternLearner.get_instance(
            config=config,
            db_manager=db_manager,
            context=context,
            llm_adapter=expression_llm_adapter
        )
        self.memory_graph_manager = MemoryGraphManager.get_instance()
        self.knowledge_graph_manager = KnowledgeGraphManager.get_instance()
        
        self._logger.info("PersonaUpdater初始化完成，已集成MaiBot功能模块和PersonaManager更新器")
        
    async def update_persona_with_style(self, group_id: str, style_analysis: Dict[str, Any], filtered_messages: List[MessageData]) -> bool:
        """根据风格分析和筛选过的消息更新人格"""
        try:
            # 使用新版框架的PersonaManager获取默认人格
            if not hasattr(self.context, 'persona_manager') or not self.context.persona_manager:
                self._logger.error("无法获取PersonaManager")
                return False

            # 获取当前人格
            current_persona = await self.context.persona_manager.get_default_persona_v3()
            if not current_persona:
                self._logger.error("无法获取当前人格")
                return False

            persona_name = current_persona.get('name', 'unknown') if isinstance(current_persona, dict) else current_persona['name']
            self._logger.info(f"当前人格: {persona_name} for group {group_id}")
            
            # ===== 创建备份（如果启用） =====
            backup_id = None
            if self.config.persona_update_backup_enabled:
                try:
                    backup_id = await self.backup_manager.create_backup_before_update(
                        group_id, 
                        f"风格学习更新前备份 - {style_analysis.get('source', '未知来源')}"
                    )
                    self._logger.info(f"群组 {group_id} 创建备份成功，备份ID: {backup_id}")
                except Exception as backup_error:
                    self._logger.error(f"创建备份失败: {backup_error}")
                    # 不阻止更新继续进行
            
            # ===== 保存更新前的人格状态用于对比 =====
            def clone_persona_data(persona_data: Any) -> Dict[str, Any]:
                """临时克隆人格数据用于对比"""
                try:
                    if isinstance(persona_data, dict):
                        return persona_data.copy()
                    else:
                        # 如果是对象，转换为字典
                        return {
                            'name': getattr(persona_data, 'name', ''),
                            'prompt': getattr(persona_data, 'prompt', ''),
                            'settings': getattr(persona_data, 'settings', {})
                        }
                except Exception as e:
                    self._logger.error(f"克隆人格数据失败: {e}")
                    return {}
            
            before_persona = clone_persona_data(current_persona)

            # 更新人格prompt
            if 'enhanced_prompt' in style_analysis:
                # Personality是TypedDict,直接使用字典访问
                original_prompt = current_persona.get('prompt', '')
                enhanced_prompt = self._merge_prompts(original_prompt, style_analysis['enhanced_prompt'])
                
                # 记录人格更新以便人工审查
                await self.record_persona_update_for_review(PersonaUpdateRecord(
                    timestamp=time.time(),
                    group_id=group_id,
                    update_type="prompt_update",
                    original_content=original_prompt,
                    new_content=enhanced_prompt,
                    reason="风格分析建议更新prompt"
                ))

                # Personality是TypedDict,需要通过PersonaManager更新
                # 注意: 在这个阶段我们只是在内存中修改，真正的持久化由PersonaManager处理
                current_persona['prompt'] = enhanced_prompt
                self._logger.info(f"人格prompt已更新，长度: {len(enhanced_prompt)} for group {group_id}")
            
            # 3. 更新对话风格特征（使用MaiBot的表达模式学习而不是直接保存对话）
            if filtered_messages:
                await self._update_style_based_features_with_maibot(current_persona, style_analysis, filtered_messages)
            
            # 更新其他风格属性
            if 'style_attributes' in style_analysis: # 从 style_analysis 中获取 style_attributes
                await self._apply_style_attributes(current_persona, style_analysis['style_attributes'])
            
            # ===== 生成并输出格式化的更新报告 =====
            after_persona = clone_persona_data(current_persona)
            update_details = {
                'new_features_count': len(style_analysis.get('style_features', [])),
                'style_adjustments': self._extract_style_adjustments(style_analysis),
                'reason': '风格学习更新'
            }
            
            # 生成格式化报告
            update_report = await self.format_persona_update_report(
                group_id, before_persona, after_persona, update_details
            )
            
            # 输出到日志
            self._logger.info(f"人格更新报告:\n{update_report}")
            
            self._logger.info(f"人格更新成功 for group {group_id}")
            return True
            
        except Exception as e:
            self._logger.error(f"人格更新失败 for group {group_id}: {e}")
            raise SelfLearningError(f"人格更新失败: {str(e)}")
    
    async def record_persona_update_for_review(self, record: PersonaUpdateRecord) -> int:
        """记录需要人工审查的人格更新"""
        try:
            record_dict = record.__dict__
            # 移除 id 字段，因为它是自增的
            record_dict.pop('id', None) 
            record_id = await self.db_manager.save_persona_update_record(record_dict)
            self._logger.info(f"已记录人格更新待审查，ID: {record_id}")
            return record_id
        except Exception as e:
            self._logger.error(f"记录人格更新待审查失败: {e}")
            raise PersonaUpdateError(f"记录人格更新待审查失败: {str(e)}")

    async def get_pending_persona_updates(self) -> List[PersonaUpdateRecord]:
        """获取所有待审查的人格更新"""
        try:
            records_data = await self.db_manager.get_pending_persona_update_records()
            records = []
            for data in records_data:
                # 确保数据包含所需字段，并提供默认值
                record = PersonaUpdateRecord(
                    id=data.get('id'),
                    timestamp=data.get('timestamp', time.time()),
                    group_id=data.get('group_id', 'default'),
                    update_type=data.get('update_type', 'unknown'),
                    original_content=data.get('original_content', ''),
                    new_content=data.get('new_content', ''),
                    reason=data.get('reason', ''),
                    status=data.get('status', 'pending'),
                    reviewer_comment=data.get('reviewer_comment'),
                    review_time=data.get('review_time')
                )
                records.append(record)
            self._logger.info(f"获取到 {len(records)} 条待审查的人格更新记录")
            return records
        except Exception as e:
            self._logger.error(f"获取待审查人格更新失败: {e}")
            return []

    async def review_persona_update(self, update_id: int, status: str, reviewer_comment: Optional[str] = None) -> bool:
        """审查人格更新"""
        try:
            # 如果是批准操作,先创建备份和已批准人格
            if status == "approved":
                backup_success = await self._create_approved_persona_backup(update_id)
                if not backup_success:
                    self._logger.error(f"创建批准人格失败，取消审查操作")
                    raise PersonaUpdateError("创建批准人格失败，请检查日志")

            result = await self.db_manager.update_persona_update_record_status(update_id, status, reviewer_comment)
            if result:
                self._logger.info(f"人格更新 {update_id} 已审查为 {status}")
            return result
        except Exception as e:
            self._logger.error(f"审查人格更新失败: {e}")
            raise PersonaUpdateError(f"审查人格更新失败: {str(e)}")

    async def _create_approved_persona_backup(self, update_id: int) -> bool:
        """在批准人格更新时,创建备份人格和已批准人格"""
        try:
            # 获取当前人格信息
            if not hasattr(self.context, 'persona_manager') or not self.context.persona_manager:
                self._logger.warning("无法获取PersonaManager，跳过备份")
                return False

            current_persona = await self.context.persona_manager.get_default_persona_v3()
            if not current_persona:
                self._logger.warning("无法获取当前人格信息，跳过备份")
                return False

            # 提取原人格信息
            original_prompt = current_persona.get('prompt', '')
            original_name = current_persona.get('name', '默认人格')

            if not original_prompt:
                self._logger.warning("无法解析当前人格数据")
                return False

            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')

            # 1. 创建备份人格（格式：原人格名_时间_备份人格）
            backup_persona_id = f"{original_name}_{timestamp}_备份人格"

            persona_manager = self.persona_manager_updater.persona_manager if hasattr(self, 'persona_manager_updater') else self.context.persona_manager

            if persona_manager:
                self._logger.info(f"开始创建备份人格: {backup_persona_id}")
                backup_persona = await persona_manager.create_persona(
                    persona_id=backup_persona_id,
                    system_prompt=original_prompt,
                    begin_dialogs=current_persona.get('begin_dialogs', []),
                    tools=current_persona.get('tools')
                )

                if backup_persona:
                    self._logger.info(f"✓ 成功创建备份人格: {backup_persona_id}")
                else:
                    self._logger.error(f"✗ 创建备份人格失败: {backup_persona_id}")
                    return False

                # 2. 获取审查记录中的新内容
                self._logger.info(f"正在获取更新记录 ID={update_id}...")
                update_record = await self.db_manager.get_persona_update_record_by_id(update_id)
                if not update_record:
                    self._logger.error(f"✗ 无法获取更新记录 {update_id}")
                    return False

                self._logger.info(f"✓ 成功获取更新记录: type={update_record.get('update_type')}, status={update_record.get('status')}")

                # 3. 创建批准更新人格（格式：原人格名_时间_批准更新）
                approved_persona_id = f"{original_name}_{timestamp}_批准更新"
                approved_prompt = update_record.get('new_content', '')

                if not approved_prompt:
                    self._logger.error(f"✗ 更新记录 {update_id} 中没有新内容(new_content)")
                    self._logger.error(f"   update_record keys: {list(update_record.keys())}")
                    return False

                self._logger.info(f"开始创建批准更新人格: {approved_persona_id}")
                self._logger.info(f"  原人格prompt长度: {len(original_prompt)} 字符")
                self._logger.info(f"  新人格prompt长度: {len(approved_prompt)} 字符")
                self._logger.debug(f"  新人格prompt前100字: {approved_prompt[:100]}...")

                self._logger.info(f"调用 PersonaManager.create_persona()...")
                approved_persona = await persona_manager.create_persona(
                    persona_id=approved_persona_id,
                    system_prompt=approved_prompt,
                    begin_dialogs=current_persona.get('begin_dialogs', []),
                    tools=current_persona.get('tools')
                )
                self._logger.info(f"PersonaManager.create_persona() 返回值: {approved_persona is not None}")

                if approved_persona:
                    self._logger.info(f"✓ 成功创建批准更新人格: {approved_persona_id}")

                    # 验证人格是否真的创建成功
                    self._logger.info(f"验证人格是否存在...")
                    verify_persona = await persona_manager.get_persona(approved_persona_id)
                    self._logger.info(f"PersonaManager.get_persona() 返回值: {verify_persona is not None}")

                    if verify_persona:
                        self._logger.info(f"✓ 验证成功: 批准更新人格已存在于PersonaManager中")
                        self._logger.info(f"✓✓✓ 完整流程成功: 备份人格和批准更新人格都已创建")
                        return True
                    else:
                        self._logger.error(f"✗ 验证失败: 批准更新人格创建后无法找到")
                        self._logger.error(f"   尝试列出所有人格...")
                        try:
                            all_personas = await persona_manager.get_all_personas()
                            self._logger.error(f"   当前所有人格: {[p.get('name', 'unknown') for p in all_personas] if all_personas else '无法获取'}")
                        except Exception as list_error:
                            self._logger.error(f"   列出人格失败: {list_error}")
                        return False
                else:
                    self._logger.error(f"✗ 创建批准更新人格失败: {approved_persona_id}")
                    self._logger.error(f"   PersonaManager.create_persona() 返回了 None 或 False")
                    self._logger.error(f"   参数检查: persona_id='{approved_persona_id}', system_prompt长度={len(approved_prompt)}")
                    return False
            else:
                self._logger.error("PersonaManager不可用，无法创建备份")
                return False

        except Exception as e:
            self._logger.error(f"创建批准后人格备份失败: {e}")
            return False

    async def get_reviewed_persona_updates(self, limit: int = 50, offset: int = 0, status_filter: str = None) -> List[Dict[str, Any]]:
        """获取已审查的传统人格更新记录"""
        try:
            # 从数据库获取已审查的记录
            reviewed_records = await self.db_manager.get_reviewed_persona_update_records(limit, offset, status_filter)
            
            # 转换为统一格式
            updates = []
            for record in reviewed_records:
                updates.append({
                    'id': record.get('id'),
                    'group_id': record.get('group_id', 'default'),
                    'original_content': record.get('original_content', ''),
                    'proposed_content': record.get('new_content', ''),
                    'reason': record.get('reason', '传统人格更新'),
                    'confidence_score': 0.9,  # 传统更新默认较高置信度
                    'status': record.get('status'),
                    'reviewer_comment': record.get('reviewer_comment'),
                    'review_time': record.get('review_time'),
                    'timestamp': record.get('timestamp'),
                    'update_type': 'traditional_persona_update'
                })
            
            return updates
            
        except Exception as e:
            self._logger.error(f"获取已审查人格更新失败: {e}")
            return []

    async def revert_persona_update_review(self, update_id: int, reason: str) -> bool:
        """撤回人格更新审查"""
        try:
            # 将状态重置为pending
            result = await self.db_manager.update_persona_update_record_status(
                update_id, "pending", f"撤回操作: {reason}"
            )
            
            if result:
                self._logger.info(f"人格更新 {update_id} 审查已撤回")
            
            return result
            
        except Exception as e:
            self._logger.error(f"撤回人格更新审查失败: {e}")
            raise PersonaUpdateError(f"撤回人格更新审查失败: {str(e)}")

    async def delete_persona_update_review(self, update_id: int) -> bool:
        """删除人格更新审查记录"""
        try:
            result = await self.db_manager.delete_persona_update_record(update_id)
            
            if result:
                self._logger.info(f"人格更新审查记录 {update_id} 已删除")
            else:
                self._logger.warning(f"未找到人格更新审查记录 {update_id}")
            
            return result
            
        except Exception as e:
            self._logger.error(f"删除人格更新审查记录失败: {e}")
            raise PersonaUpdateError(f"删除人格更新审查记录失败: {str(e)}")

    async def get_current_persona_description(self, group_id: str) -> Optional[str]:
        """获取当前人格的描述"""
        try:
            # 使用PersonaManager获取当前人格
            if not hasattr(self.context, 'persona_manager') or not self.context.persona_manager:
                self._logger.error("无法获取PersonaManager")
                return None

            persona = await self.context.persona_manager.get_default_persona_v3(group_id)
            if persona:
                if isinstance(persona, dict):
                    return persona.get('prompt', '')
            return None
        except Exception as e:
            self._logger.error(f"获取当前人格描述失败 for group {group_id}: {e}")
            return None

    async def get_current_persona(self, group_id: str) -> Optional[Dict[str, Any]]:
        """获取当前人格信息"""
        try:
            # 使用PersonaManager获取当前人格
            if not hasattr(self.context, 'persona_manager') or not self.context.persona_manager:
                self._logger.error("无法获取PersonaManager")
                return None

            persona = await self.context.persona_manager.get_default_persona_v3(group_id)
            if persona and isinstance(persona, dict):
                return dict(persona)
            return None

        except Exception as e:
            self._logger.error(f"获取当前人格失败 for group {group_id}: {e}")
            return None
    
    def _merge_prompts(self, original: str, enhancement: str) -> str:
        """合并原始prompt和增强prompt"""
        if not original:
            return enhancement
        
        if not enhancement:
            return original
        
        # 智能合并策略
        if self.config.persona_merge_strategy == "replace":
            return enhancement
        elif self.config.persona_merge_strategy == "append":
            return f"{original}\n\n{enhancement}"
        elif self.config.persona_merge_strategy == "prepend":
            return f"{enhancement}\n\n{original}"
        else:  # smart merge
            return self._smart_merge_prompts(original, enhancement)
    
    def _smart_merge_prompts(self, original: str, enhancement: str) -> str:
        """智能合并prompt"""
        # 检查enhancement是否已经包含了original（避免重复）
        # 如果enhancement包含original的主要内容，说明enhancement已经是完整的新人格，直接使用
        if original and original.strip() in enhancement:
            self._logger.info("检测到enhancement已包含original内容，直接使用enhancement")
            return enhancement

        # 检查重叠内容，避免重复
        words_original = set(original.lower().split())
        words_enhancement = set(enhancement.lower().split())

        overlap_ratio = len(words_original.intersection(words_enhancement)) / max(len(words_original), 1)

        if overlap_ratio > 0.7:  # 高重叠，选择较长的
            return enhancement if len(enhancement) > len(original) else original
        else:  # 低重叠，合并
            return f"{original}\n\n补充风格特征：{enhancement}"
    
    async def _update_mood_imitation_dialogs(self, persona: Personality, filtered_messages: List[Dict[str, Any]]):
        """更新对话风格模仿 - 只使用经过验证的真实消息特征"""
        try:
            current_dialogs = persona.get('mood_imitation_dialogs', [])
            
            # 从过滤后的消息中提取高质量对话特征（不是原始对话）
            new_features = []
            for msg in filtered_messages[-10:]:  # 取最近10条
                message_text = msg.get('message', '').strip()
                if message_text and len(message_text) > self.config.message_min_length:
                    if self._is_authentic_message(message_text) and message_text not in current_dialogs:
                        # 提取语言特征而不是保存原始对话
                        feature = f"风格特征: {message_text[:30]}..." if len(message_text) > 30 else f"风格特征: {message_text}"
                        new_features.append(feature)
            
            if new_features:
                # 过滤现有对话中的虚假内容
                validated_current = [d for d in current_dialogs if self._is_authentic_message(d)]
                
                # 保持对话列表长度合理
                max_dialogs = self.config.max_mood_imitation_dialogs or 20
                all_features = validated_current + new_features
                
                if len(all_features) > max_dialogs:
                    # 保留最新的特征
                    all_features = all_features[-max_dialogs:]
                
                persona['mood_imitation_dialogs'] = all_features
                self._logger.info(f"更新对话风格模仿，新增{len(new_features)}条验证后特征，总计{len(all_features)}条")
            
        except Exception as e:
            self._logger.error(f"更新对话风格模仿失败: {e}")
    
    def _is_authentic_message(self, text: str) -> bool:
        """验证消息是否为真实消息（非虚假对话）"""
        if not text or len(text.strip()) < 3:
            return False
        
        # 检测虚假对话模式
        fake_patterns = [
            r'A:\s*你最近干.*呢.*\?',
            r'B:\s*',
            r'用户\d+:\s*',
            r'.*:\s*你最近.*',
            r'开场对话列表',
            r'情绪模拟对话列表',
            r'风格特征:.*',  # 避免重复嵌套
        ]
        
        import re
        for pattern in fake_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return False
        
        return True
    
    async def _apply_style_attributes(self, persona: Personality, style_attributes: Dict[str, Any]):
        """应用风格属性"""
        try:
            current_prompt = persona.get('prompt', '')
            
            # 根据风格属性调整prompt
            if 'tone' in style_attributes:
                tone = style_attributes['tone']
                tone_instruction = f"请保持{tone}的语调。"
                if tone_instruction not in current_prompt:
                    current_prompt = f"{current_prompt}\n\n{tone_instruction}"
            
            if 'formality' in style_attributes:
                formality = style_attributes['formality']
                if formality == 'formal':
                    formality_instruction = "请使用正式的表达方式。"
                elif formality == 'casual':
                    formality_instruction = "请使用轻松随意的表达方式。"
                else:
                    formality_instruction = ""
                
                if formality_instruction and formality_instruction not in current_prompt:
                    current_prompt = f"{current_prompt}\n\n{formality_instruction}"
            
            if 'emotion' in style_attributes:
                emotion = style_attributes['emotion']
                if emotion and f"情感倾向：{emotion}" not in current_prompt:
                    current_prompt = f"{current_prompt}\n\n情感倾向：{emotion}"
            
            persona['prompt'] = current_prompt
            self._logger.info("风格属性应用成功")
            
        except Exception as e:
            self._logger.error(f"应用风格属性失败: {e}")
    
    async def _update_style_based_features_with_maibot(self, current_persona: Personality, style_analysis: Dict[str, Any], filtered_messages: List[MessageData]):
        """使用MaiBot功能更新风格相关特征"""
        try:
            self._logger.info("开始使用MaiBot功能更新风格特征")

            # 1. 使用表达模式学习器分析消息并保存
            if hasattr(self, 'expression_learner') and self.expression_learner:
                group_id = current_persona.get('group_id', 'default')

                # 使用trigger_learning_for_group以确保保存到数据库
                learning_success = await self.expression_learner.trigger_learning_for_group(group_id, filtered_messages)

                if learning_success:
                    self._logger.info(f"表达模式学习成功并已保存到数据库 for group {group_id}")
                else:
                    self._logger.info(f"表达模式学习未触发或没有学到新模式 for group {group_id}")

            # 2. 更新记忆图谱
            if hasattr(self, 'memory_graph_manager') and self.memory_graph_manager:
                for msg in filtered_messages:
                    await self.memory_graph_manager.add_memory_node(
                        memory_id=f"msg_{msg.timestamp}",
                        content=msg.message,
                        memory_type="dialogue_style",
                        tags=['style_learning'],
                        metadata={'sender': msg.sender_name, 'group_id': msg.group_id}
                    )
                self._logger.info(f"向记忆图谱添加了 {len(filtered_messages)} 个风格记忆节点")

            # 3. 更新知识图谱
            if hasattr(self, 'knowledge_graph_manager') and self.knowledge_graph_manager:
                style_entity = {
                    'entity_id': f"style_{current_persona.get('group_id', 'default')}_{int(time.time())}",
                    'entity_type': 'communication_style',
                    'properties': style_analysis.get('style_attributes', {}),
                    'context': '用户交流风格特征'
                }

                await self.knowledge_graph_manager.add_entity(
                    entity_id=style_entity['entity_id'],
                    entity_type=style_entity['entity_type'],
                    properties=style_entity['properties'],
                    context=style_entity['context']
                )
                self._logger.info("向知识图谱添加了风格实体")

        except Exception as e:
            self._logger.error(f"使用MaiBot更新风格特征失败: {e}")
    
    def _extract_style_adjustments(self, style_analysis: Dict[str, Any]) -> str:
        """从风格分析中提取风格调整信息"""
        try:
            adjustments = []
            
            if 'style_attributes' in style_analysis:
                attrs = style_analysis['style_attributes']
                if isinstance(attrs, dict):
                    for key, value in attrs.items():
                        if key in ['tone', 'formality', 'enthusiasm']:
                            adjustments.append(f"{key}: {value}")
            
            if 'expression_patterns' in style_analysis:
                patterns = style_analysis['expression_patterns']
                if isinstance(patterns, list) and patterns:
                    adjustments.append(f"表达模式: {len(patterns)}项")
            
            return ', '.join(adjustments) if adjustments else '无特定调整'
            
        except Exception as e:
            return f"提取失败: {str(e)}"
    
    async def analyze_persona_compatibility(self, target_style: Dict[str, Any]) -> AnalysisResult:
        """分析目标风格与当前人格的兼容性"""
        try:
            current_persona = await self.get_current_persona()
            if not current_persona:
                return AnalysisResult(
                    success=False,
                    confidence=0.0,
                    data={},
                    error="无法获取当前人格"
                )
            
            current_prompt = current_persona.get('prompt', '')
            target_attributes = target_style.get('style_attributes', {})
            
            # 简单的兼容性评分
            compatibility_score = 0.8  # 基础分数
            
            # 检查风格冲突
            conflicts = []
            if 'tone' in target_attributes:
                target_tone = target_attributes['tone'].lower()
                if ('严肃' in current_prompt.lower() and target_tone == 'humor') or \
                   ('幽默' in current_prompt.lower() and target_tone == 'serious'):
                    conflicts.append('语调冲突')
                    compatibility_score -= 0.2
            
            return AnalysisResult(
                success=True,
                confidence=compatibility_score,
                data={
                    'compatibility_score': compatibility_score,
                    'conflicts': conflicts,
                    'current_persona_name': current_persona.get('name', 'unknown'),
                    'recommended_action': 'merge' if compatibility_score > 0.6 else 'replace'
                }
            )
            
        except Exception as e:
            self._logger.error(f"人格兼容性分析失败: {e}")
            return AnalysisResult(
                success=False,
                confidence=0.0,
                data={},
                error=str(e)
            )

    async def _apply_persona_manager_update(self, group_id: str, update_content: str) -> bool:
        """使用PersonaManager应用增量更新"""
        try:
            if not self.persona_manager_updater.is_available():
                self._logger.warning("PersonaManager不可用")
                return False
            
            # 如果启用备份，先创建备份persona
            if self.config.persona_update_backup_enabled:
                await self._create_backup_persona_with_manager(group_id)
            
            # 应用增量更新
            success = await self.persona_manager_updater.apply_incremental_update(group_id, update_content)
            
            if success:
                self._logger.info(f"群组 {group_id} PersonaManager增量更新成功")
                
                # 如果启用自动应用且是自动学习模式
                if self.config.auto_apply_persona_updates:
                    # 清理旧版本（保留最近5个）
                    await self.persona_manager_updater.cleanup_old_personas(group_id, keep_count=5)
                
                return True
            else:
                self._logger.error(f"群组 {group_id} PersonaManager增量更新失败")
                return False
                
        except Exception as e:
            self._logger.error(f"PersonaManager更新失败: {e}")
            return False

    async def _create_backup_persona_with_manager(self, group_id: str) -> bool:
        """使用PersonaManager创建备份persona，格式：原人格名_年月日时间_备份人格"""
        try:
            # 使用PersonaManager获取当前人格信息
            if not hasattr(self.context, 'persona_manager') or not self.context.persona_manager:
                self._logger.warning("无法获取PersonaManager，跳过备份")
                return False

            current_persona = await self.context.persona_manager.get_default_persona_v3(group_id)
            if not current_persona:
                self._logger.warning("无法获取当前人格信息，跳过备份")
                return False

            # 提取原人格信息 (Personality是TypedDict)
            original_prompt = current_persona.get('prompt', '')
            original_name = current_persona.get('name', '默认人格')

            if not original_prompt:
                self._logger.warning("无法解析当前人格数据")
                return False
            
            # 生成备份persona名称：原人格名_年月日时间_备份人格
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            backup_persona_id = f"{original_name}_{timestamp}_备份人格"
            
            # 创建备份persona，包含完整的原始内容
            persona_manager = self.persona_manager_updater.persona_manager
            if persona_manager:
                backup_persona = await persona_manager.create_persona(
                    persona_id=backup_persona_id,
                    system_prompt=original_prompt,
                    begin_dialogs=current_persona.get('begin_dialogs', []),
                    tools=current_persona.get('tools')
                )
                
                if backup_persona:
                    self._logger.info(f"成功创建备份persona: {backup_persona_id}")
                    return True
                else:
                    self._logger.error("创建备份persona失败")
                    return False
            else:
                self._logger.error("PersonaManager不可用，无法创建备份")
                return False
                
        except Exception as e:
            self._logger.error(f"创建备份persona失败: {e}")
            return False

    async def format_persona_update_report(self, group_id: str, before_persona: Dict[str, Any], 
                                         after_persona: Dict[str, Any], update_details: Dict[str, Any]) -> str:
        """
        格式化人格更新报告
        
        Args:
            group_id: 群组ID
            before_persona: 更新前的人格数据
            after_persona: 更新后的人格数据
            update_details: 更新详情
        
        Returns:
            格式化的人格更新报告
        """
        try:
            from ..statics.messages import CommandMessages
            
            # 生成变化摘要
            change_summary = await self._generate_change_summary(before_persona, after_persona, update_details)
            
            # 格式化前后对比
            before_content = self._format_persona_content(before_persona)
            after_content = self._format_persona_content(after_persona)
            
            # 构建完整报告
            report = CommandMessages.PERSONA_UPDATE_HEADER.format(group_id=group_id)
            report += "\n" + CommandMessages.PERSONA_UPDATE_SUCCESS
            report += "\n" + CommandMessages.PERSONA_BEFORE_AFTER.format(
                before_content=before_content,
                after_content=after_content,
                change_summary=change_summary
            )
            
            return report
            
        except Exception as e:
            self._logger.error(f"格式化人格更新报告失败: {e}")
            from ..statics.messages import CommandMessages
            return CommandMessages.PERSONA_UPDATE_FAILED.format(error=str(e))
    
    def _format_persona_content(self, persona_data: Dict[str, Any]) -> str:
        """格式化人格内容"""
        try:
            if isinstance(persona_data, dict):
                name = persona_data.get('name', '未知人格')
                prompt = persona_data.get('prompt', '无描述')
            else:
                name = getattr(persona_data, 'name', '未知人格')
                prompt = getattr(persona_data, 'prompt', '无描述')
            
            # 截断过长的prompt
            if len(prompt) > 200:
                prompt = prompt[:200] + "..."
            
            return f"人格名称: {name}\n人格描述: {prompt}"
            
        except Exception as e:
            return f"格式化失败: {str(e)}"
    
    async def _generate_change_summary(self, before_persona: Dict[str, Any], 
                                     after_persona: Dict[str, Any], 
                                     update_details: Dict[str, Any]) -> str:
        """生成变化摘要"""
        try:
            from ..statics.messages import CommandMessages
            
            # 计算prompt长度变化
            before_prompt = self._get_persona_prompt(before_persona)
            after_prompt = self._get_persona_prompt(after_persona)
            
            length_before = len(before_prompt)
            length_after = len(after_prompt)
            length_change = f"+{length_after - length_before}" if length_after > length_before else str(length_after - length_before)
            
            # 统计新增特征
            new_features_count = update_details.get('new_features_count', 0)
            style_adjustments = update_details.get('style_adjustments', '无')
            update_reason = update_details.get('reason', '风格学习更新')
            
            return CommandMessages.PERSONA_CHANGE_SUMMARY.format(
                prompt_length_before=length_before,
                prompt_length_after=length_after,
                length_change=length_change,
                new_features_count=new_features_count,
                style_adjustments=style_adjustments,
                update_reason=update_reason
            )
            
        except Exception as e:
            return f"生成变化摘要失败: {str(e)}"
    
    def _get_persona_prompt(self, persona_data: Any) -> str:
        """获取人格prompt"""
        if isinstance(persona_data, dict):
            return persona_data.get('prompt', '')
        else:
            return getattr(persona_data, 'prompt', '')


class PersonaAnalyzer:
    """人格分析器 - 分析人格特征和变化"""
    
    def __init__(self, config: PluginConfig):
        self.config = config
        self._logger = logging.getLogger(self.__class__.__name__)
    
    async def analyze_persona_evolution(self, persona_history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析人格演化趋势"""
        if len(persona_history) < 2:
            return {
                'evolution_detected': False,
                'message': '人格历史数据不足'
            }
        
        try:
            # 分析prompt长度变化
            prompt_lengths = [len(p.get('prompt', '')) for p in persona_history]
            length_trend = 'increasing' if prompt_lengths[-1] > prompt_lengths else 'decreasing'
            
            # 分析关键词变化
            all_keywords = []
            for persona in persona_history:
                prompt = persona.get('prompt', '').lower()
                keywords = self._extract_keywords(prompt)
                all_keywords.extend(keywords)
            
            keyword_frequency = {}
            for keyword in all_keywords:
                keyword_frequency[keyword] = keyword_frequency.get(keyword, 0) + 1
            
            most_common_keywords = sorted(keyword_frequency.items(), key=lambda x: x, reverse=True)[:10][1]
            
            return {
                'evolution_detected': True,
                'prompt_length_trend': length_trend,
                'most_common_keywords': most_common_keywords,
                'total_versions': len(persona_history),
                'analysis_time': datetime.now().isoformat()
            }
            
        except Exception as e:
            self._logger.error(f"人格演化分析失败: {e}")
            return {
                'evolution_detected': False,
                'error': str(e)
            }
    
    def _extract_keywords(self, text: str) -> List[str]:
        """从文本中提取关键词"""
        # 简单的关键词提取
        words = text.split()
        keywords = []
        
        important_words = ['友好', '专业', '幽默', '严肃', '活泼', '温和', '耐心', '热情']
        
        for word in words:
            if any(important in word for important in important_words):
                keywords.append(word)
        
        return keywords

    async def stop(self):
        """停止服务"""
        try:
            self._logger.info("人格更新服务已停止")
            return True
        except Exception as e:
            self._logger.error(f"停止人格更新服务失败: {e}")
            return False

    # ===== 人格格式化输出功能 =====
    
    async def format_current_persona_display(self, group_id: str) -> str:
        """
        格式化当前人格显示
        
        Args:
            group_id: 群组ID
        
        Returns:
            格式化的当前人格信息
        """
        try:
            from ..statics.messages import CommandMessages
            
            # 获取当前人格信息
            current_persona = await self.get_current_persona(group_id)
            if not current_persona:
                return "❌ 无法获取当前人格信息"
            
            # 获取人格统计信息
            stats = await self._get_persona_statistics(group_id)
            
            # 获取备份状态
            backup_status = await self._get_backup_status(group_id)
            
            # 获取学习到的风格特征
            style_features = await self._get_learned_style_features(group_id)
            
            # 格式化人格名称和描述
            persona_name = self._get_persona_name(current_persona)
            persona_prompt = self._format_persona_prompt(current_persona)
            
            # 构建显示内容
            display_content = CommandMessages.PERSONA_CURRENT_DISPLAY.format(
                persona_name=persona_name,
                persona_prompt=persona_prompt,
                update_count=stats.get('update_count', 0),
                last_update=stats.get('last_update', '从未更新'),
                quality_score=stats.get('quality_score', 0.0)
            )
            
            # 添加备份状态
            display_content += "\n" + CommandMessages.PERSONA_BACKUP_STATUS.format(
                total_backups=backup_status.get('total_backups', 0),
                latest_backup=backup_status.get('latest_backup', '无'),
                auto_backup_status=backup_status.get('auto_backup_status', '未启用')
            )
            
            # 添加风格特征
            if style_features:
                display_content += "\n" + CommandMessages.PERSONA_STYLE_FEATURES.format(
                    style_features=style_features
                )
            
            return display_content
            
        except Exception as e:
            self._logger.error(f"格式化当前人格显示失败: {e}")
            return f"❌ 获取人格信息失败: {str(e)}"
    
    def _get_persona_name(self, persona_data: Any) -> str:
        """获取人格名称"""
        if isinstance(persona_data, dict):
            return persona_data.get('name', '默认人格')
        else:
            return getattr(persona_data, 'name', '默认人格')
    
    def _format_persona_prompt(self, persona_data: Any) -> str:
        """格式化人格prompt用于显示"""
        prompt = self._get_persona_prompt(persona_data)
        
        # 如果prompt太长，进行格式化处理
        if len(prompt) > 500:
            lines = prompt.split('\n')
            formatted_lines = []
            char_count = 0
            
            for line in lines:
                if char_count + len(line) > 500:
                    formatted_lines.append("...")
                    break
                formatted_lines.append(line)
                char_count += len(line)
            
            return '\n'.join(formatted_lines)
        
        return prompt
    
    async def _get_persona_statistics(self, group_id: str) -> Dict[str, Any]:
        """获取人格统计信息"""
        try:
            # 这里可以从数据库获取实际的统计信息
            # 暂时返回模拟数据
            return {
                'update_count': 0,
                'last_update': '从未更新',
                'quality_score': 8.5
            }
        except Exception as e:
            self._logger.error(f"获取人格统计信息失败: {e}")
            return {}
    
    async def _get_backup_status(self, group_id: str) -> Dict[str, Any]:
        """获取备份状态"""
        try:
            if self.backup_manager:
                return await self.backup_manager.get_backup_statistics(group_id)
            return {}
        except Exception as e:
            self._logger.error(f"获取备份状态失败: {e}")
            return {}
    
    async def _get_learned_style_features(self, group_id: str) -> str:
        """获取学习到的风格特征"""
        try:
            # 读取增量更新文件获取学习到的特征
            file_path = f"data/persona_updates/group_{group_id}_incremental_updates.txt"
            
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 提取特征行
                features = []
                for line in content.split('\n'):
                    line = line.strip()
                    if line.startswith('+') or line.startswith('~'):
                        features.append(line)
                
                if features:
                    return '\n'.join(features[-10:])  # 显示最近10个特征
            
            return "暂无学习到的风格特征"
            
        except Exception as e:
            self._logger.error(f"获取学习到的风格特征失败: {e}")
            return "获取风格特征失败"
    
    # ===== 辅助方法 =====
    
    async def _clone_persona_data(self, persona_data: Any) -> Dict[str, Any]:
        """克隆人格数据用于对比"""
        try:
            if isinstance(persona_data, dict):
                return persona_data.copy()
            else:
                # 如果是对象，转换为字典
                return {
                    'name': getattr(persona_data, 'name', ''),
                    'prompt': getattr(persona_data, 'prompt', ''),
                    'settings': getattr(persona_data, 'settings', {})
                }
        except Exception as e:
            self._logger.error(f"克隆人格数据失败: {e}")
            return {}
    
    async def apply_persona_update(self, group_id: str, update_content: str) -> bool:
        """应用人格更新 - 外部调用接口"""
        try:
            self._logger.info(f"开始应用群组 {group_id} 的人格更新")
            
            # 使用PersonaManager应用更新
            if self.config.use_persona_manager_updates:
                success = await self._apply_persona_manager_update(group_id, update_content)
            else:
                # 使用传统方式（如果有的话）
                self._logger.warning("PersonaManager更新已禁用，使用传统方式")
                success = await self._apply_traditional_persona_update(group_id, update_content)
            
            if success:
                self._logger.info(f"群组 {group_id} 人格更新应用成功")
            else:
                self._logger.error(f"群组 {group_id} 人格更新应用失败")
                
            return success
            
        except Exception as e:
            self._logger.error(f"应用人格更新失败: {e}")
            return False

    async def _apply_traditional_persona_update(self, group_id: str, update_content: str) -> bool:
        """传统方式应用人格更新（直接修改当前人格）"""
        try:
            # 使用PersonaManager获取当前人格
            if not hasattr(self.context, 'persona_manager') or not self.context.persona_manager:
                self._logger.error("无法获取PersonaManager")
                return False

            current_persona = await self.context.persona_manager.get_default_persona_v3(group_id)
            if not current_persona:
                self._logger.error("无法获取当前人格")
                return False

            # 获取persona_id用于更新
            persona_id = current_persona.get('name', 'default')

            # 获取当前prompt
            current_prompt = current_persona.get('prompt', '')

            # 根据合并策略处理更新
            if self.config.persona_merge_strategy == "append":
                new_prompt = current_prompt + "\n\n" + update_content
            elif self.config.persona_merge_strategy == "prepend":
                new_prompt = update_content + "\n\n" + current_prompt
            elif self.config.persona_merge_strategy == "replace":
                new_prompt = update_content
            else:
                # 默认智能合并模式
                new_prompt = self._merge_prompts(current_prompt, update_content)

            # 使用PersonaManager更新人格
            await self.context.persona_manager.update_persona(
                persona_id=persona_id,
                system_prompt=new_prompt,
                begin_dialogs=current_persona.get('begin_dialogs'),
                tools=current_persona.get('tools')
            )

            self._logger.info(f"群组 {group_id} 传统方式人格更新完成")
            return True

        except Exception as e:
            self._logger.error(f"传统方式应用人格更新失败: {e}")
            return False

