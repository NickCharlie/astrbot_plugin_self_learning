"""
人格审查服务 - 处理人格更新审查相关业务逻辑
"""
from typing import Dict, Any, List, Tuple, Optional
from astrbot.api import logger
from datetime import datetime

# Import update type constants
from ...statics.messages import (
    UPDATE_TYPE_STYLE_LEARNING,
    normalize_update_type,
    get_review_source_from_update_type
)


class PersonaReviewService:
    """人格审查服务 - 整合三种人格审查来源"""

    def __init__(self, container):
        """
        初始化人格审查服务

        Args:
            container: ServiceContainer 依赖注入容器
        """
        self.container = container
        self.persona_updater = container.persona_updater
        self.database_manager = container.database_manager
        self.persona_manager = container.persona_manager
        self.persona_web_manager = getattr(container, 'persona_web_manager', None)
        self.plugin_config = getattr(container, 'plugin_config', None)
        self.group_id_to_unified_origin = getattr(container, 'group_id_to_unified_origin', {})
        # AstrBot框架PersonaManager（用于直接更新默认人格）
        self.astrbot_persona_manager = getattr(container, 'astrbot_persona_manager', None)

    def _resolve_umo(self, group_id: str) -> str:
        """将group_id解析为unified_msg_origin以支持多配置文件"""
        return self.group_id_to_unified_origin.get(group_id, group_id)

    async def get_pending_persona_updates(self, limit: int = 0, offset: int = 0) -> Dict[str, Any]:
        """
        获取所有待审查的人格更新 (整合三种数据源，支持分页)

        Args:
            limit: 每页数量，0 表示返回全部
            offset: 偏移量

        Returns:
            Dict: 包含待审查更新的字典，含 total 字段
        """
        all_updates = []

        # 1. 获取传统的人格更新审查
        if self.persona_updater:
            try:
                logger.info("正在获取传统人格更新...")
                traditional_updates = await self.persona_updater.get_pending_persona_updates()
                logger.info(f"获取到 {len(traditional_updates)} 个传统人格更新")

                # 将PersonaUpdateRecord对象转换为字典格式
                for record in traditional_updates:
                    if hasattr(record, '__dict__'):
                        record_dict = record.__dict__.copy()
                    else:
                        # 手动构建字典
                        record_dict = {
                            'id': getattr(record, 'id', None),
                            'timestamp': getattr(record, 'timestamp', 0),
                            'group_id': getattr(record, 'group_id', 'default'),
                            'update_type': getattr(record, 'update_type', 'unknown'),
                            'original_content': getattr(record, 'original_content', ''),
                            'new_content': getattr(record, 'new_content', ''),
                            'reason': getattr(record, 'reason', ''),
                            'status': getattr(record, 'status', 'pending'),
                            'reviewer_comment': getattr(record, 'reviewer_comment', None),
                            'review_time': getattr(record, 'review_time', None)
                        }

                    # 添加前端需要的字段
                    record_dict['proposed_content'] = record_dict.get('new_content', '')
                    record_dict['confidence_score'] = 0.8
                    record_dict['reviewed'] = record_dict.get('status', 'pending') != 'pending'
                    record_dict['approved'] = record_dict.get('status', 'pending') == 'approved'
                    record_dict['review_source'] = 'traditional'

                    all_updates.append(record_dict)

            except Exception as e:
                logger.error(f"获取传统人格更新失败: {e}", exc_info=True)
        else:
            logger.warning("persona_updater 不可用")

        # 2. 获取人格学习审查（包括渐进式学习、表达学习等）
        if self.database_manager:
            try:
                logger.info("正在获取人格学习审查...")
                persona_learning_reviews = await self.database_manager.get_pending_persona_learning_reviews(limit=999999)
                logger.info(f"获取到 {len(persona_learning_reviews)} 个人格学习审查")

                for review in persona_learning_reviews:
                    # 使用常量进行类型标准化和分类
                    raw_update_type = review.get('update_type', '')
                    normalized_type = normalize_update_type(raw_update_type)
                    review_source = get_review_source_from_update_type(raw_update_type)

                    # 跳过风格学习（在步骤3单独处理）
                    if normalized_type == UPDATE_TYPE_STYLE_LEARNING:
                        logger.debug(f"跳过风格学习记录 ID={review['id']}，在步骤3处理")
                        continue

                    # 获取原人格文本（如果数据库中为空，实时获取）
                    original_content = review['original_content']
                    group_id = review['group_id']

                    if not original_content or original_content.strip() == '':
                        logger.info(f"数据库中没有原人格文本，实时获取群组 {group_id} 的原人格")
                        try:
                            if self.astrbot_persona_manager:
                                current_persona = await self.astrbot_persona_manager.get_default_persona_v3(self._resolve_umo(group_id))
                                if current_persona and current_persona.get('prompt'):
                                    original_content = current_persona.get('prompt', '')
                                    logger.info(f"成功获取群组 {group_id} 的原人格文本，长度: {len(original_content)}")
                                else:
                                    original_content = "[无法获取原人格文本]"
                                    logger.warning(f"无法获取群组 {group_id} 的原人格文本")
                            else:
                                original_content = "[PersonaManager未初始化]"
                                logger.warning("PersonaManager未初始化，无法获取原人格")
                        except Exception as e:
                            logger.warning(f"获取群组 {group_id} 原人格失败: {e}", exc_info=True)
                            original_content = f"[获取原人格失败: {str(e)}]"

                    # 转换为统一的审查格式
                    review_dict = {
                        'id': f"persona_learning_{review['id']}" if review_source == 'persona_learning' else str(review['id']),
                        'timestamp': review['timestamp'],
                        'group_id': group_id,
                        'update_type': raw_update_type,
                        'normalized_type': normalized_type,
                        'original_content': original_content,
                        'new_content': review['new_content'],
                        'proposed_content': review.get('proposed_content', review['new_content']),
                        'reason': review['reason'],
                        'status': review['status'],
                        'reviewer_comment': review['reviewer_comment'],
                        'review_time': review['review_time'],
                        'confidence_score': review.get('confidence_score', 0.5),
                        'reviewed': False,
                        'approved': False,
                        'review_source': review_source,
                        'persona_learning_review_id': review['id'],
                        'features_content': review.get('metadata', {}).get('features_content', ''),
                        'llm_response': review.get('metadata', {}).get('llm_response', ''),
                        'total_raw_messages': review.get('metadata', {}).get('total_raw_messages', 0),
                        'messages_analyzed': review.get('metadata', {}).get('messages_analyzed', 0),
                        'metadata': review.get('metadata', {}),
                        'incremental_content': review.get('metadata', {}).get('incremental_content', ''),
                        'incremental_start_pos': review.get('metadata', {}).get('incremental_start_pos', 0)
                    }

                    all_updates.append(review_dict)
                    logger.debug(f"添加审查记录: ID={review_dict['id']}, type={raw_update_type}, source={review_source}")

            except Exception as e:
                logger.error(f"获取人格学习审查失败: {e}", exc_info=True)
        else:
            logger.warning("database_manager 不可用")

        # 3. 获取风格学习审查（Few-shot样本学习）
        if self.database_manager:
            try:
                logger.info("正在获取风格学习审查...")
                style_reviews = await self.database_manager.get_pending_style_reviews(limit=999999)
                logger.info(f"获取到 {len(style_reviews)} 个风格学习审查")

                for review in style_reviews:
                    group_id = review['group_id']
                    original_persona_text = ""

                    try:
                        # 通过 persona_manager 获取当前人格
                        if self.astrbot_persona_manager:
                            current_persona = await self.astrbot_persona_manager.get_default_persona_v3(self._resolve_umo(group_id))
                            if current_persona and current_persona.get('prompt'):
                                original_persona_text = current_persona.get('prompt', '')
                            else:
                                original_persona_text = "[无法获取原人格文本]"
                        else:
                            original_persona_text = "[PersonaManager未初始化]"
                    except Exception as e:
                        logger.warning(f"获取群组 {group_id} 原人格失败: {e}", exc_info=True)
                        original_persona_text = f"[获取原人格失败: {str(e)}]"

                    # 构建完整的新内容（原人格 + Few-shot内容）
                    few_shots_content = review['few_shots_content']
                    full_new_content = original_persona_text + "\n\n" + few_shots_content if original_persona_text else few_shots_content

                    # 转换为统一的审查格式
                    review_dict = {
                        'id': f"style_{review['id']}",
                        'timestamp': review['timestamp'],
                        'group_id': group_id,
                        'update_type': UPDATE_TYPE_STYLE_LEARNING,
                        'normalized_type': UPDATE_TYPE_STYLE_LEARNING,
                        'original_content': original_persona_text,
                        'new_content': full_new_content,
                        'proposed_content': few_shots_content,
                        'reason': review['description'],
                        'status': review['status'],
                        'reviewer_comment': None,
                        'review_time': None,
                        'confidence_score': 0.9,
                        'reviewed': False,
                        'approved': False,
                        'review_source': 'style_learning',
                        'learned_patterns': review.get('learned_patterns', []),
                        'style_review_id': review['id'],
                        'incremental_start_pos': len(original_persona_text) + 2 if original_persona_text else 0
                    }

                    all_updates.append(review_dict)

            except Exception as e:
                logger.error(f"获取风格学习审查失败: {e}", exc_info=True)

        # 按时间倒序排列
        all_updates.sort(key=lambda x: x.get('timestamp', 0), reverse=True)

        total = len(all_updates)

        logger.info(f"共 {total} 条人格更新记录 (传统: {len([u for u in all_updates if u['review_source'] == 'traditional'])}, "
                    f"人格学习: {len([u for u in all_updates if u['review_source'] == 'persona_learning'])}, "
                    f"风格学习: {len([u for u in all_updates if u['review_source'] == 'style_learning'])})")

        # 应用分页
        if limit > 0:
            paged_updates = all_updates[offset:offset + limit]
            logger.info(f"分页返回: offset={offset}, limit={limit}, 本页 {len(paged_updates)} 条")
        else:
            paged_updates = all_updates

        return {
            "success": True,
            "updates": paged_updates,
            "total": total
        }

    async def review_persona_update(
        self,
        update_id: str,
        action: str,
        comment: str = "",
        modified_content: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        审查人格更新内容 (批准/拒绝)

        Args:
            update_id: 更新ID (可能带前缀: style_, persona_learning_)
            action: 操作 ('approve' 或 'reject')
            comment: 审查备注
            modified_content: 用户修改后的内容

        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        logger.info(f"=== 开始审查人格更新 {update_id} ===")

        # 将action转换为status
        if action == "approve":
            status = "approved"
        elif action == "reject":
            status = "rejected"
        else:
            return False, "Invalid action, must be 'approve' or 'reject'"

        # 判断审查类型
        if update_id.startswith("style_"):
            # 风格学习审查
            style_review_id = int(update_id.replace("style_", ""))

            if action == "approve":
                return await self._approve_style_learning_review(style_review_id)
            else:
                return await self._reject_style_learning_review(style_review_id)

        elif update_id.startswith("persona_learning_"):
            # 人格学习审查
            persona_learning_review_id = int(update_id.replace("persona_learning_", ""))

            if not self.database_manager:
                return False, "Database manager not initialized"

            # 更新审查状态
            success = await self.database_manager.update_persona_learning_review_status(
                persona_learning_review_id, status, comment, modified_content
            )

            if success:
                if action == "approve":
                    # 批准后创建新人格
                    try:
                        review_data = await self.database_manager.get_persona_learning_review_by_id(persona_learning_review_id)
                        if review_data:
                            content_to_apply = modified_content if modified_content else review_data.get('proposed_content')
                            group_id = review_data.get('group_id', 'default')

                            if self.persona_web_manager and content_to_apply:
                                try:
                                    logger.info(f"开始为群组 {group_id} 创建新人格（来源：人格学习审查 {persona_learning_review_id}）")
                                    logger.info(f"新人格内容长度: {len(content_to_apply)} 字符")

                                    # 获取当前使用的原人格名称
                                    base_persona_name = "default"
                                    try:
                                        if self.persona_manager:
                                            current_persona = await self.persona_manager.get_default_persona_v3(self._resolve_umo(group_id))
                                            if current_persona and hasattr(current_persona, 'persona_id'):
                                                base_persona_name = current_persona.persona_id
                                            elif isinstance(current_persona, dict) and 'persona_id' in current_persona:
                                                base_persona_name = current_persona['persona_id']
                                    except Exception as e:
                                        logger.warning(f"获取原人格名称失败，使用默认值: {e}")

                                    # 生成新人格ID: 原人格名-具体时间-批准人格
                                    from datetime import datetime
                                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                                    new_persona_id = f"{base_persona_name}-{timestamp}-approved"

                                    # 使用PersonaWebManager创建新人格
                                    create_result = await self.persona_web_manager.create_persona_via_web({
                                        "persona_id": new_persona_id,
                                        "system_prompt": content_to_apply,
                                        "begin_dialogs": [],
                                        "tools": []
                                    })

                                    if create_result.get('success'):
                                        logger.info(f"人格学习审查 {persona_learning_review_id} 已批准，成功创建新人格: {new_persona_id}")
                                        message = f"人格学习审查 {persona_learning_review_id} 已批准，成功创建新人格: {new_persona_id}"

                                        # 自动应用到默认人格
                                        auto_apply_msg = await self._auto_apply_to_default_persona(
                                            group_id, base_persona_name, content_to_apply
                                        )
                                        if auto_apply_msg:
                                            message += f"；{auto_apply_msg}"
                                    else:
                                        error_msg = create_result.get('error', '未知错误')
                                        logger.warning(f" 人格学习审查 {persona_learning_review_id} 批准成功但创建新人格失败: {error_msg}")
                                        message = f"人格学习审查 {persona_learning_review_id} 已批准，但创建新人格失败: {error_msg}"

                                except Exception as apply_error:
                                    logger.error(f" 创建新人格失败: {apply_error}", exc_info=True)
                                    message = f"人格学习审查 {persona_learning_review_id} 已批准，但创建新人格过程出错: {str(apply_error)}"
                            elif not self.persona_web_manager:
                                logger.warning("PersonaWebManager未初始化，无法创建新人格")
                                message = f"人格学习审查 {persona_learning_review_id} 已批准，但无法创建新人格（PersonaWebManager未初始化）"
                            else:
                                logger.warning(f"人格学习审查 {persona_learning_review_id} 缺少人格内容")
                                message = f"人格学习审查 {persona_learning_review_id} 已批准，但缺少人格内容"
                        else:
                            logger.error(f"无法获取人格学习审查 {persona_learning_review_id} 的详情")
                            message = f"人格学习审查 {persona_learning_review_id} 已批准，但无法获取详情"
                    except Exception as e:
                        logger.error(f"批准人格学习审查失败: {e}", exc_info=True)
                        message = f"人格学习审查 {persona_learning_review_id} 已批准，但处理过程出错: {str(e)}"
                else:
                    message = f"人格学习审查 {persona_learning_review_id} 已拒绝"

                return True, message
            else:
                return False, "Failed to update persona learning review status"

        else:
            # 传统人格审查
            if self.persona_updater:
                result = await self.persona_updater.review_persona_update(int(update_id), status, comment)
                if result:
                    return True, f"人格更新 {update_id} 已{action}"
                else:
                    return False, "Failed to update persona review status"
            else:
                return False, "Persona updater not initialized"

    async def _approve_style_learning_review(self, review_id: int) -> Tuple[bool, str]:
        """批准风格学习审查（内部方法）- 创建新人格"""
        if not self.database_manager:
            return False, "数据库管理器未初始化"

        # 获取审查详情
        pending_reviews = await self.database_manager.get_pending_style_reviews()
        target_review = None
        for review in pending_reviews:
            if review['id'] == review_id:
                target_review = review
                break

        if not target_review:
            return False, '审查记录不存在'

        # 更新状态
        success = await self.database_manager.update_style_review_status(
            review_id, 'approved', target_review['group_id']
        )

        if success and target_review['few_shots_content']:
            group_id = target_review.get('group_id', 'default')

            if self.persona_web_manager:
                try:
                    # 获取当前使用的原人格名称
                    base_persona_name = "default"
                    try:
                        if self.astrbot_persona_manager:
                            current_persona = await self.astrbot_persona_manager.get_default_persona_v3(self._resolve_umo(group_id))
                            if current_persona and hasattr(current_persona, 'persona_id'):
                                base_persona_name = current_persona.persona_id
                            elif isinstance(current_persona, dict) and 'persona_id' in current_persona:
                                base_persona_name = current_persona['persona_id']
                    except Exception as e:
                        logger.warning(f"获取原人格名称失败，使用默认值: {e}")

                    # 生成新人格ID: 原人格名-具体时间-批准人格
                    from datetime import datetime
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    new_persona_id = f"{base_persona_name}-{timestamp}-approved"

                    # 使用PersonaWebManager创建新人格
                    create_result = await self.persona_web_manager.create_persona_via_web({
                        "persona_id": new_persona_id,
                        "system_prompt": target_review['few_shots_content'],
                        "begin_dialogs": [],
                        "tools": []
                    })

                    if create_result.get('success'):
                        logger.info(f"风格学习审查 {review_id} 已批准，成功创建新人格: {new_persona_id}")
                        msg = f"风格学习审查 {review_id} 已批准，成功创建新人格: {new_persona_id}"

                        # 自动应用到默认人格
                        auto_apply_msg = await self._auto_apply_to_default_persona(
                            group_id, base_persona_name, target_review['few_shots_content']
                        )
                        if auto_apply_msg:
                            msg += f"；{auto_apply_msg}"

                        return True, msg
                    else:
                        error_msg = create_result.get('error', '未知错误')
                        logger.warning(f" 风格学习审查 {review_id} 批准成功但创建新人格失败: {error_msg}")
                        return True, f"风格学习审查 {review_id} 已批准，但创建新人格失败: {error_msg}"

                except Exception as e:
                    logger.error(f" 创建新人格失败: {e}", exc_info=True)
                    return True, f"风格学习审查 {review_id} 已批准，但创建新人格过程出错: {str(e)}"
            else:
                logger.warning("PersonaWebManager未初始化，无法创建新人格")
                return True, f"风格学习审查 {review_id} 已批准，但PersonaWebManager未初始化"
        else:
            return True, f"风格学习审查 {review_id} 已批准"

    async def _auto_apply_to_default_persona(
        self, group_id: str, base_persona_name: str, content: str
    ) -> Optional[str]:
        """
        自动将批准内容应用到默认人格（危险功能，需配置开启）

        流程：先创建副本（已在调用方完成），再更新默认人格的system_prompt。

        Args:
            group_id: 群组ID
            base_persona_name: 当前默认人格的persona_id/name
            content: 要应用的人格内容

        Returns:
            成功/失败消息，如果功能未启用则返回None
        """
        # 检查是否启用自动应用
        if not self.plugin_config or not getattr(self.plugin_config, 'auto_apply_approved_persona', False):
            return None

        if not content or not content.strip():
            return None

        pm = self.astrbot_persona_manager
        if not pm:
            logger.warning("AstrBot PersonaManager不可用，无法自动应用到默认人格")
            return "自动应用失败：PersonaManager不可用"

        try:
            # 获取当前默认人格
            umo = self._resolve_umo(group_id)
            current_persona = await pm.get_default_persona_v3(umo)
            if not current_persona:
                return "自动应用失败：无法获取当前默认人格"

            persona_name = current_persona.get('name', 'default')
            if persona_name == 'default':
                logger.warning("默认人格为系统内置default，跳过自动应用（避免覆盖内置人格）")
                return "自动应用跳过：当前为系统内置default人格，无法覆盖"

            # 更新默认人格的system_prompt
            await pm.update_persona(
                persona_id=persona_name,
                system_prompt=content
            )

            logger.info(f"已自动将批准内容应用到默认人格 [{persona_name}]（群组 {group_id}）")
            return f"已自动应用到默认人格 [{persona_name}]"

        except Exception as e:
            logger.error(f"自动应用到默认人格失败: {e}", exc_info=True)
            return f"自动应用失败: {str(e)}"

    async def _reject_style_learning_review(self, review_id: int) -> Tuple[bool, str]:
        """拒绝风格学习审查（内部方法）"""
        if not self.database_manager:
            return False, "数据库管理器未初始化"

        success = await self.database_manager.update_style_review_status(
            review_id, 'rejected'
        )

        if success:
            return True, f"风格学习审查 {review_id} 已拒绝"
        else:
            return False, "拒绝审查失败"

    async def get_reviewed_persona_updates(
        self,
        limit: int = 50,
        offset: int = 0,
        status_filter: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取已审查的人格更新列表

        Args:
            limit: 限制数量
            offset: 偏移量
            status_filter: 状态筛选 ('approved' 或 'rejected' 或 None)

        Returns:
            Dict: 包含已审查更新的字典
        """
        reviewed_updates = []

        # 从传统人格更新审查获取
        if self.persona_updater:
            traditional_updates = await self.persona_updater.get_reviewed_persona_updates(limit, offset, status_filter)
            reviewed_updates.extend(traditional_updates)

        # 从人格学习审查获取
        if self.database_manager:
            persona_learning_updates = await self.database_manager.get_reviewed_persona_learning_updates(limit, offset, status_filter)
            reviewed_updates.extend(persona_learning_updates)

        # 从风格学习审查获取
        if self.database_manager:
            style_updates = await self.database_manager.get_reviewed_style_learning_updates(limit, offset, status_filter)
            # 将风格审查转换为统一格式
            for update in style_updates:
                if 'id' in update:
                    update['id'] = f"style_{update['id']}"
            reviewed_updates.extend(style_updates)

        # 按审查时间排序
        reviewed_updates.sort(key=lambda x: x.get('review_time', 0), reverse=True)

        return {
            "success": True,
            "updates": reviewed_updates,
            "total": len(reviewed_updates)
        }

    async def revert_persona_update(self, update_id: str, reason: str = "撤回审查决定") -> Tuple[bool, str]:
        """
        撤回人格更新审查

        Args:
            update_id: 更新ID
            reason: 撤回原因

        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        # 判断撤回类型
        if update_id.startswith("style_"):
            # 风格学习审查撤回
            style_review_id = int(update_id.replace("style_", ""))

            if not self.database_manager:
                return False, "Database manager not initialized"

            success = await self.database_manager.update_style_review_status(
                style_review_id, "pending"
            )

            if success:
                return True, f"风格学习审查 {style_review_id} 已撤回，重新回到待审查状态"
            else:
                return False, "Failed to revert style learning review"

        elif update_id.startswith("persona_learning_"):
            # 人格学习审查撤回
            persona_learning_review_id = int(update_id.replace("persona_learning_", ""))

            if not self.database_manager:
                return False, "Database manager not initialized"

            success = await self.database_manager.update_persona_learning_review_status(
                persona_learning_review_id, "pending", f"撤回操作: {reason}"
            )

            if success:
                return True, f"人格学习审查 {persona_learning_review_id} 已撤回，重新回到待审查状态"
            else:
                return False, "Failed to revert persona learning review"
        else:
            # 传统人格审查撤回
            if self.persona_updater:
                result = await self.persona_updater.revert_persona_update_review(int(update_id), reason)
                if result:
                    return True, f"人格更新 {update_id} 审查已撤回，重新回到待审查状态"
                else:
                    return False, "Failed to revert persona update review"
            else:
                return False, "Persona updater not initialized"

    async def delete_persona_update(self, update_id: str) -> Tuple[bool, str]:
        """
        删除人格更新审查记录

        Args:
            update_id: 更新ID

        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        if not self.database_manager:
            return False, "Database manager not available"

        # 解析update_id，处理前缀
        if isinstance(update_id, str):
            if update_id.startswith("persona_learning_"):
                numeric_id = int(update_id.replace("persona_learning_", ""))
                success = await self.database_manager.delete_persona_learning_review_by_id(numeric_id)
                if success:
                    return True, f"人格学习审查记录 {numeric_id} 已删除"
                else:
                    return False, f"未找到人格学习审查记录: {numeric_id}"

            elif update_id.startswith("style_"):
                numeric_id = int(update_id.replace("style_", ""))
                success = await self.database_manager.delete_style_review_by_id(numeric_id)
                if success:
                    return True, f"风格学习审查记录 {numeric_id} 已删除"
                else:
                    return False, f"未找到风格学习审查记录: {numeric_id}"
            else:
                # 尝试作为纯数字ID处理
                try:
                    numeric_id = int(update_id)
                except ValueError:
                    return False, f"无效的ID格式: {update_id}"
        else:
            numeric_id = int(update_id)

        # 尝试删除人格学习审查记录
        success = await self.database_manager.delete_persona_learning_review_by_id(numeric_id)

        if success:
            return True, f"人格学习审查记录 {numeric_id} 已删除"
        else:
            # 如果人格学习审查记录不存在，尝试删除传统人格审查记录
            if self.persona_updater:
                result = await self.persona_updater.delete_persona_update_review(numeric_id)
                if result:
                    return True, f"人格更新审查记录 {numeric_id} 已删除"
                else:
                    return False, "Record not found"
            else:
                return False, "Record not found"

    async def batch_delete_persona_updates(self, update_ids: List[str]) -> Dict[str, Any]:
        """
        批量删除人格更新审查记录

        Args:
            update_ids: 更新ID列表

        Returns:
            Dict: 包含操作结果的字典
        """
        if not self.database_manager:
            return {
                "success": False,
                "error": "Database manager not available"
            }

        success_count = 0
        failed_count = 0

        for update_id in update_ids:
            try:
                success, _ = await self.delete_persona_update(update_id)
                if success:
                    success_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                logger.error(f"删除人格更新审查记录 {update_id} 失败: {e}", exc_info=True)
                failed_count += 1

        return {
            "success": True,
            "message": f"批量删除完成：成功 {success_count} 条，失败 {failed_count} 条",
            "details": {
                "success_count": success_count,
                "failed_count": failed_count,
                "total_count": len(update_ids)
            }
        }

    async def batch_review_persona_updates(
        self,
        update_ids: List[str],
        action: str,
        comment: str = ""
    ) -> Dict[str, Any]:
        """
        批量审查人格更新记录

        Args:
            update_ids: 更新ID列表
            action: 操作 ('approve' 或 'reject')
            comment: 审查备注

        Returns:
            Dict: 包含操作结果的字典
        """
        if action not in ['approve', 'reject']:
            return {
                "success": False,
                "error": "action must be 'approve' or 'reject'"
            }

        if not self.database_manager:
            return {
                "success": False,
                "error": "Database manager not available"
            }

        success_count = 0
        failed_count = 0

        for update_id in update_ids:
            try:
                success, _ = await self.review_persona_update(update_id, action, comment)
                if success:
                    success_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                logger.error(f"批量审查人格更新记录 {update_id} 失败: {e}", exc_info=True)
                failed_count += 1

        action_text = "批准" if action == 'approve' else "拒绝"
        return {
            "success": True,
            "message": f"批量{action_text}完成：成功 {success_count} 条，失败 {failed_count} 条",
            "details": {
                "success_count": success_count,
                "failed_count": failed_count,
                "total_count": len(update_ids)
            }
        }
