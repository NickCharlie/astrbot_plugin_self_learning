"""
智能对话服务 - 目标驱动对话实现
会话级动态目标系统，支持动态目标和阶段调整
"""
from typing import Optional, Dict
import asyncio
from astrbot.api import logger


class IntelligentChatService:
    """智能对话服务 - 薄封装层，协调心理状态管理器和上下文注入器"""

    def __init__(
        self,
        psychological_state_manager,
        social_context_injector,
        llm_adapter,
        config
    ):
        """
        初始化智能对话服务

        Args:
            psychological_state_manager: EnhancedPsychologicalStateManager实例
            social_context_injector: SocialContextInjector实例
            llm_adapter: FrameworkLLMAdapter实例
            config: PluginConfig实例
        """
        self.psych_manager = psychological_state_manager
        self.context_injector = social_context_injector
        self.llm_adapter = llm_adapter
        self.config = config

    async def chat_with_goal(
        self,
        user_id: str,
        user_message: str,
        group_id: str,
        force_normal_mode: bool = False
    ) -> Dict:
        """
        带目标引导的对话 (支持动态调整)

        Args:
            user_id: 用户ID
            user_message: 用户消息
            group_id: 群组ID
            force_normal_mode: 强制普通对话模式

        Returns:
            {
                "response": "机器人回复",
                "mode": "goal_driven" / "normal",
                "task_info": {任务信息} / None
            }
        """
        try:
            # 1. 获取或创建会话目标 (自动检测初始目标)
            current_goal = None
            if not force_normal_mode:
                current_goal = await self.psych_manager.get_or_create_conversation_goal(
                    user_id, group_id, user_message
                )

            # 2. 构建上下文
            mode = "goal_driven" if current_goal else "normal"

            context = await self.context_injector.format_complete_context(
                group_id=group_id,
                user_id=user_id,
                include_conversation_goal=(mode == "goal_driven")
            )

            # 3. 【即时回复】调用LLM
            bot_response = await self._call_llm(context, user_message)

            # 4. 【后台异步】动态调整目标和阶段 (不等待)
            if mode == "goal_driven" and current_goal:
                asyncio.create_task(
                    self.psych_manager.update_goal_with_dynamic_adjustment(
                        user_id, group_id, user_message, bot_response
                    )
                )

            # 5. 返回结果
            return {
                "response": bot_response,
                "mode": mode,
                "task_info": self._format_task_info(current_goal) if mode == "goal_driven" else None
            }

        except Exception as e:
            logger.error(f"对话处理失败: {e}", exc_info=True)
            return {
                "response": "抱歉，我遇到了一些问题，请稍后再试。",
                "mode": "error",
                "task_info": None
            }

    async def _call_llm(self, context: Optional[str], user_message: str) -> str:
        """调用LLM生成回复"""
        try:
            # 使用refine模型(强模型)确保质量
            response = await self.llm_adapter.refine_chat_completion(
                prompt=user_message,
                system_prompt=context if context else "你是一个友好温暖的聊天助手。",
                temperature=0.8,
                max_tokens=200
            )
            return response if response else "我现在有点累了，稍后再聊好吗？"
        except Exception as e:
            logger.error(f"调用LLM失败: {e}", exc_info=True)
            return "抱歉，我现在有点累了，稍后再聊好吗？"

    def _format_task_info(self, goal: Optional[Dict]) -> Optional[Dict]:
        """格式化任务信息"""
        if not goal:
            return None

        final_goal = goal.get('final_goal', {})
        current_stage = goal.get('current_stage', {})
        metrics = goal.get('metrics', {})
        planned_stages = goal.get('planned_stages', [])

        return {
            "session_id": goal.get('session_id'),
            "goal_type": final_goal.get('type'),
            "goal_name": final_goal.get('name'),
            "topic": final_goal.get('topic'),
            "current_task": current_stage.get('task'),
            "task_index": current_stage.get('index'),
            "total_tasks": len(planned_stages),
            "progress": metrics.get('goal_progress', 0.0),
            "conversation_rounds": metrics.get('rounds', 0),
            "user_engagement": metrics.get('user_engagement', 0.5),
            "status": goal.get('status', 'active')
        }

    async def get_user_goal_status(self, user_id: str, group_id: str) -> Optional[Dict]:
        """获取用户当前目标状态"""
        goal = await self.psych_manager.get_conversation_goal(user_id, group_id)
        return self._format_task_info(goal)

    async def clear_user_goal(self, user_id: str, group_id: str) -> bool:
        """清除用户当前目标"""
        return await self.psych_manager.clear_conversation_goal(user_id, group_id)

    async def get_goal_statistics(self) -> Dict:
        """获取全局目标统计"""
        return await self.psych_manager.get_goal_statistics()