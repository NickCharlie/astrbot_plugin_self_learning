"""
对话目标管理器 - 会话级动态目标系统
集成到现有的心理状态管理体系
"""
from typing import Optional, Dict, List
from datetime import datetime
import hashlib
from astrbot.api import logger

from ..repositories.conversation_goal_repository import ConversationGoalRepository


class ConversationGoalManager:
    """对话目标管理器 - 会话级动态目标系统"""

    # 预定义目标模板 (30+种类型，实际会动态调整)
    GOAL_TEMPLATES = {
        # ===== 情感支持类 =====
        "comfort": {
            "name": "安慰用户",
            "base_stages": ["初步共情", "弱化负面情绪", "给出轻量安慰"],
            "completion_signals": ["哈哈", "还好", "确实", "没事", "谢谢"],
            "min_rounds": 3
        },
        "emotional_support": {
            "name": "情感支持",
            "base_stages": ["倾听诉说", "识别核心问题", "表达理解", "提供建议", "给予鼓励"],
            "completion_signals": ["好多了", "有道理", "试试看", "感觉"],
            "min_rounds": 5
        },
        "empathy": {
            "name": "深度共情",
            "base_stages": ["理解情绪", "认同感受", "分享类似经历", "建立情感连接"],
            "completion_signals": ["你懂我", "就是这样", "对对对"],
            "min_rounds": 4
        },
        "encouragement": {
            "name": "鼓励打气",
            "base_stages": ["肯定成就", "指出优势", "激发信心", "鼓励行动"],
            "completion_signals": ["有道理", "我试试", "加油"],
            "min_rounds": 3
        },

        # ===== 信息交流类 =====
        "qa": {
            "name": "解答疑问",
            "base_stages": ["理解问题", "提供答案", "确认满意度"],
            "completion_signals": ["明白了", "懂了", "知道了", "谢谢"],
            "min_rounds": 2
        },
        "guide_share": {
            "name": "引导分享",
            "base_stages": ["引发兴趣", "提出开放式问题", "深入追问", "鼓励详细描述"],
            "completion_signals": ["详细说", "具体是", "举个例子", "比如"],
            "min_rounds": 4
        },
        "teach": {
            "name": "教学指导",
            "base_stages": ["评估水平", "讲解概念", "举例说明", "练习巩固"],
            "completion_signals": ["学会了", "原来如此", "明白了"],
            "min_rounds": 4
        },
        "discuss": {
            "name": "深度讨论",
            "base_stages": ["抛出观点", "互相论证", "拓展思考", "总结共识"],
            "completion_signals": ["有意思", "新视角", "学到了"],
            "min_rounds": 5
        },
        "storytelling": {
            "name": "讲故事",
            "base_stages": ["铺垫背景", "展开情节", "制造悬念", "揭晓结局"],
            "completion_signals": ["然后呢", "好看", "有意思"],
            "min_rounds": 4
        },

        # ===== 娱乐互动类 =====
        "casual_chat": {
            "name": "闲聊互动",
            "base_stages": ["回应话题", "自然互动"],
            "completion_signals": [],
            "min_rounds": 1
        },
        "tease": {
            "name": "友好调侃",
            "base_stages": ["轻松吐槽", "开玩笑", "自嘲化解", "保持友好"],
            "completion_signals": ["哈哈", "笑死", "你也是"],
            "min_rounds": 3
        },
        "flirt": {
            "name": "俏皮调戏",
            "base_stages": ["轻微撩拨", "玩笑互动", "保持分寸", "及时收尾"],
            "completion_signals": ["讨厌", "哈哈", "你这样"],
            "min_rounds": 3
        },
        "joke": {
            "name": "幽默搞笑",
            "base_stages": ["铺垫笑点", "抛出包袱", "制造反转"],
            "completion_signals": ["哈哈", "笑死", "绷不住"],
            "min_rounds": 2
        },
        "meme": {
            "name": "梗文化互动",
            "base_stages": ["引用梗", "玩梗互动", "创造新梗"],
            "completion_signals": ["懂", "经典", "绷不住"],
            "min_rounds": 3
        },
        "roleplay": {
            "name": "角色扮演",
            "base_stages": ["设定角色", "入戏互动", "推进剧情", "自然收尾"],
            "completion_signals": ["有意思", "继续", "好玩"],
            "min_rounds": 4
        },

        # ===== 社交互动类 =====
        "greeting": {
            "name": "问候寒暄",
            "base_stages": ["回应问候", "关心近况", "自然过渡"],
            "completion_signals": ["还好", "不错", "嗯嗯"],
            "min_rounds": 2
        },
        "compliment": {
            "name": "赞美夸奖",
            "base_stages": ["发现亮点", "真诚夸赞", "具体说明"],
            "completion_signals": ["谢谢", "哈哈", "过奖"],
            "min_rounds": 2
        },
        "celebrate": {
            "name": "庆祝祝贺",
            "base_stages": ["表达祝贺", "分享喜悦", "送上祝福"],
            "completion_signals": ["谢谢", "开心", "好的"],
            "min_rounds": 2
        },
        "apologize": {
            "name": "道歉和解",
            "base_stages": ["表达歉意", "说明原因", "请求原谅", "承诺改进"],
            "completion_signals": ["没事", "算了", "好吧"],
            "min_rounds": 3
        },
        "gossip": {
            "name": "八卦闲聊",
            "base_stages": ["引出话题", "互相爆料", "评论吐槽"],
            "completion_signals": ["真的吗", "天呐", "哈哈"],
            "min_rounds": 4
        },

        # ===== 建议指导类 =====
        "advise": {
            "name": "提供建议",
            "base_stages": ["理解需求", "分析情况", "给出建议", "补充说明"],
            "completion_signals": ["有道理", "试试看", "好的"],
            "min_rounds": 3
        },
        "brainstorm": {
            "name": "头脑风暴",
            "base_stages": ["明确目标", "发散思维", "提出创意", "筛选方案"],
            "completion_signals": ["不错", "可以", "有意思"],
            "min_rounds": 4
        },
        "plan": {
            "name": "制定计划",
            "base_stages": ["设定目标", "拆解步骤", "分配资源", "设定时间"],
            "completion_signals": ["明白了", "好的", "开始"],
            "min_rounds": 4
        },
        "analyze": {
            "name": "分析问题",
            "base_stages": ["明确问题", "收集信息", "分析原因", "提出方案"],
            "completion_signals": ["明白了", "原来如此", "有道理"],
            "min_rounds": 4
        },

        # ===== 情绪调节类 =====
        "calm_down": {
            "name": "情绪安抚",
            "base_stages": ["承认情绪", "理解原因", "引导冷静", "转移注意"],
            "completion_signals": ["好多了", "冷静了", "算了"],
            "min_rounds": 4
        },
        "vent": {
            "name": "倾听发泄",
            "base_stages": ["鼓励表达", "认真倾听", "适当回应", "情绪释放"],
            "completion_signals": ["舒服了", "好多了", "谢谢"],
            "min_rounds": 4
        },
        "motivate": {
            "name": "激励鼓舞",
            "base_stages": ["唤起初心", "激发斗志", "描绘愿景", "注入能量"],
            "completion_signals": ["对", "加油", "冲"],
            "min_rounds": 3
        },

        # ===== 兴趣分享类 =====
        "recommend": {
            "name": "推荐分享",
            "base_stages": ["了解偏好", "推荐内容", "说明亮点", "引发兴趣"],
            "completion_signals": ["试试看", "记下了", "好的"],
            "min_rounds": 3
        },
        "review": {
            "name": "评价点评",
            "base_stages": ["陈述观点", "分析优缺点", "给出评分", "总结建议"],
            "completion_signals": ["有道理", "确实", "同意"],
            "min_rounds": 3
        },
        "hobby_chat": {
            "name": "爱好交流",
            "base_stages": ["分享经历", "互相学习", "深入探讨", "约定继续"],
            "completion_signals": ["有意思", "学到了", "下次聊"],
            "min_rounds": 4
        },

        # ===== 特殊场景类 =====
        "debate": {
            "name": "友好辩论",
            "base_stages": ["阐述观点", "论证立场", "反驳质疑", "求同存异"],
            "completion_signals": ["有道理", "各有道理", "算了"],
            "min_rounds": 5
        },
        "confess": {
            "name": "倾诉秘密",
            "base_stages": ["营造氛围", "倾听秘密", "保密承诺", "给予支持"],
            "completion_signals": ["谢谢", "放心", "好多了"],
            "min_rounds": 3
        },
        "nostalgia": {
            "name": "怀旧回忆",
            "base_stages": ["引出回忆", "分享往事", "情感共鸣", "珍惜当下"],
            "completion_signals": ["是啊", "怀念", "那时候"],
            "min_rounds": 4
        },

        # ===== 冲突场景类 =====
        "argument": {
            "name": "激烈争论",
            "base_stages": ["理解立场", "冷静回应", "寻找共识", "缓和气氛"],
            "completion_signals": ["算了", "好吧", "随便"],
            "min_rounds": 3
        },
        "quarrel": {
            "name": "吵架互怼",
            "base_stages": ["保持冷静", "不激化矛盾", "转移话题", "和解收尾"],
            "completion_signals": ["不说了", "随你", "行了"],
            "min_rounds": 4
        },
        "insult_exchange": {
            "name": "互骂对喷",
            "base_stages": ["避免升级", "幽默化解", "打破僵局", "引导停火"],
            "completion_signals": ["无聊", "没意思", "算了"],
            "min_rounds": 3
        },
        "provoke": {
            "name": "挑衅应对",
            "base_stages": ["识别意图", "冷静应对", "反制或化解", "控制局面"],
            "completion_signals": ["没劲", "算了", "无聊"],
            "min_rounds": 3
        },
        "complaint": {
            "name": "抱怨吐槽",
            "base_stages": ["倾听抱怨", "表示理解", "轻量安慰", "转换心情"],
            "completion_signals": ["确实", "就是", "算了"],
            "min_rounds": 3
        }
    }

    def __init__(self, database_manager, llm_adapter, config):
        """
        初始化对话目标管理器

        Args:
            database_manager: SQLAlchemyDatabaseManager实例
            llm_adapter: FrameworkLLMAdapter实例
            config: PluginConfig实例
        """
        self.db_manager = database_manager
        self.llm = llm_adapter
        self.config = config

        # 会话超时时间 (24小时)
        self.session_timeout_hours = 24

        # 初始化提示词保护服务
        from ..services.prompt_sanitizer import PromptProtectionService
        self.prompt_protection = PromptProtectionService(wrapper_template_index=0)

        # 初始化Guardrails管理器用于JSON验证
        from ..utils.guardrails_manager import get_guardrails_manager
        self.guardrails = get_guardrails_manager()

    def _generate_session_id(self, group_id: str, user_id: str) -> str:
        """生成会话ID (24小时内保持不变)"""
        date_key = datetime.now().strftime("%Y%m%d")
        base = f"{group_id}_{user_id}_{date_key}"
        return f"sess_{hashlib.md5(base.encode()).hexdigest()[:12]}"

    async def get_or_create_conversation_goal(
        self,
        user_id: str,
        group_id: str,
        user_message: str
    ) -> Optional[Dict]:
        """
        获取或创建对话目标 (自动处理会话管理)

        Args:
            user_id: 用户ID
            group_id: 群组ID
            user_message: 用户消息

        Returns:
            对话目标字典
        """
        try:
            async with self.db_manager.get_session() as session:
                repo = ConversationGoalRepository(session)

                # 1. 检查是否有活跃会话
                current_goal_orm = await repo.get_active_goal_by_user(user_id, group_id)

                if current_goal_orm:
                    # 转换为字典返回
                    return self._orm_to_dict(current_goal_orm)

                # 2. 创建新会话
                new_goal_dict = await self._create_new_session(
                    repo, session, user_id, group_id, user_message
                )

                await session.commit()
                return new_goal_dict

        except Exception as e:
            logger.error(f"获取或创建对话目标失败: {e}", exc_info=True)
            return None

    async def _create_new_session(
        self,
        repo: ConversationGoalRepository,
        session,
        user_id: str,
        group_id: str,
        user_message: str
    ) -> Dict:
        """
        创建新会话 (使用LLM检测初始目标)

        Returns:
            新会话目标数据
        """
        try:
            # 1. LLM分析: 检测初始目标
            goal_analysis = await self._analyze_initial_goal(user_message)

            goal_type = goal_analysis.get('goal_type', 'casual_chat')
            topic = goal_analysis.get('topic', '闲聊')
            confidence = goal_analysis.get('confidence', 0.5)

            # 获取模板，如果是自定义类型则使用默认模板
            if goal_type in self.GOAL_TEMPLATES:
                template = self.GOAL_TEMPLATES[goal_type]
            else:
                # 自定义目标类型，创建基础模板
                logger.info(f"检测到自定义目标类型: {goal_type}")
                template = {
                    "name": goal_type.replace('_', ' ').title(),
                    "base_stages": ["了解需求", "深入互动", "达成目标"],
                    "completion_signals": ["好的", "明白", "谢谢"],
                    "min_rounds": 2
                }

            # 2. LLM规划: 生成动态阶段规划
            planned_stages = await self._plan_dynamic_stages(
                goal_type, topic, user_message, template['base_stages']
            )

            # 3. 构建会话目标数据
            session_id = self._generate_session_id(group_id, user_id)

            final_goal = {
                "type": goal_type,
                "name": template['name'],
                "detected_at": datetime.now().isoformat(),
                "confidence": confidence,
                "topic": topic,
                "topic_status": "active"
            }

            current_stage = {
                "index": 0,
                "task": planned_stages[0] if planned_stages else "自然互动",
                "strategy": "倾听和回应",
                "adjusted_at": datetime.now().isoformat(),
                "adjustment_reason": "会话初始化"
            }

            conversation_history = [
                {
                    "role": "user",
                    "content": user_message,
                    "timestamp": datetime.now().isoformat()
                }
            ]

            metrics = {
                "rounds": 0,
                "completion_signals": 0,
                "user_engagement": 0.5,
                "goal_progress": 0.0
            }

            # 4. 持久化
            goal_orm = await repo.create(
                session_id=session_id,
                user_id=user_id,
                group_id=group_id,
                final_goal=final_goal,
                current_stage=current_stage,
                planned_stages=planned_stages,
                conversation_history=conversation_history,
                metrics=metrics
            )

            logger.info(f"创建新会话: user={user_id}, session={session_id}, goal={goal_type}, topic={topic}")

            return self._orm_to_dict(goal_orm)

        except Exception as e:
            logger.error(f"创建新会话失败: {e}", exc_info=True)
            # 返回默认会话
            return self._get_default_session(user_id, group_id, user_message)

    async def _analyze_initial_goal(self, user_message: str) -> Dict:
        """
        LLM分析: 检测初始对话目标

        Returns:
            {
                "goal_type": "emotional_support",
                "topic": "工作压力",
                "confidence": 0.85,
                "reasoning": "用户表达了工作压力相关的负面情绪"
            }
        """
        # 构建所有可用目标类型的列表
        goal_types_desc = []
        for idx, (goal_key, goal_info) in enumerate(self.GOAL_TEMPLATES.items(), 1):
            goal_types_desc.append(f"{idx}. {goal_key} - {goal_info['name']}")

        goal_types_text = "\n".join(goal_types_desc)

        prompt = f"""分析用户的消息，判断合适的对话目标类型。

用户消息: "{user_message}"

可选目标类型（共38种预设，也可自由创建新类型）:
{goal_types_text}

注意事项:
1. 优先从上述38种预设类型中选择最合适的
2. 如果预设类型都不合适，可以创建新的goal_type（使用英文蛇形命名，如"casual_tech_discussion"）
3. 创建新类型时，请确保goal_type简洁明了，反映对话目的

请返回JSON格式:
{{
    "goal_type": "emotional_support",
    "topic": "工作压力",
    "confidence": 0.85,
    "reasoning": "简短理由"
}}"""

        try:
            # 使用提示词保护包装
            protected_prompt = self.prompt_protection.wrap_prompt(prompt, register_for_filter=True)

            response = await self.llm.filter_chat_completion(
                prompt=protected_prompt,
                temperature=0.3,
                max_tokens=200
            )

            # 消毒响应
            sanitized_response, report = self.prompt_protection.sanitize_response(response)

            # 使用guardrails验证和清理JSON
            result = self.guardrails.validate_and_clean_json(
                sanitized_response,
                fallback={
                    "goal_type": "casual_chat",
                    "topic": "闲聊",
                    "confidence": 0.5,
                    "reasoning": "无法识别明确目标"
                }
            )

            return result

        except Exception as e:
            logger.warning(f"LLM分析初始目标失败: {e}")
            # 默认返回闲聊
            return {
                "goal_type": "casual_chat",
                "topic": "闲聊",
                "confidence": 0.5,
                "reasoning": "无法识别明确目标"
            }

    async def _plan_dynamic_stages(
        self,
        goal_type: str,
        topic: str,
        user_message: str,
        base_stages: List[str]
    ) -> List[str]:
        """
        LLM规划: 动态生成阶段任务

        Args:
            goal_type: 目标类型
            topic: 话题
            user_message: 用户消息
            base_stages: 基础阶段模板

        Returns:
            动态规划的阶段列表
        """
        prompt = f"""根据对话目标和用户消息，规划对话的阶段任务。

目标类型: {goal_type}
话题: {topic}
用户消息: "{user_message}"

基础阶段模板: {', '.join(base_stages)}

请生成3-5个具体的阶段任务，要求:
1. 符合当前对话目标
2. 针对具体话题调整
3. 循序渐进，自然流畅
4. 每个阶段控制在15字以内

返回JSON数组:
["阶段1", "阶段2", "阶段3"]"""

        try:
            # 使用提示词保护包装
            protected_prompt = self.prompt_protection.wrap_prompt(prompt, register_for_filter=True)

            response = await self.llm.filter_chat_completion(
                prompt=protected_prompt,
                temperature=0.5,
                max_tokens=150
            )

            # 消毒响应
            sanitized_response, report = self.prompt_protection.sanitize_response(response)

            # 使用guardrails验证和清理JSON
            stages = self.guardrails.validate_and_clean_json(
                sanitized_response,
                fallback=base_stages
            )

            if isinstance(stages, list) and len(stages) >= 2:
                return stages
            else:
                return base_stages

        except Exception as e:
            logger.warning(f"动态规划阶段失败: {e}, 使用基础模板")
            return base_stages

    async def update_goal_with_dynamic_adjustment(
        self,
        user_id: str,
        group_id: str,
        user_message: str,
        bot_response: str
    ) -> Optional[Dict]:
        """
        动态调整对话目标和阶段 (核心方法)

        包括:
        1. 检测目标切换需求
        2. 判断话题是否完结
        3. 动态调整当前阶段
        4. 更新进度和指标

        Returns:
            更新后的目标状态
        """
        try:
            async with self.db_manager.get_session() as session:
                repo = ConversationGoalRepository(session)

                # 获取当前目标
                goal_orm = await repo.get_active_goal_by_user(user_id, group_id)
                if not goal_orm:
                    logger.warning(f"未找到活跃目标: user={user_id}, group={group_id}")
                    return None

                # 转为可变字典
                goal = self._orm_to_mutable_dict(goal_orm)

                # 1. 更新对话历史
                goal['conversation_history'].append({
                    "role": "user",
                    "content": user_message,
                    "timestamp": datetime.now().isoformat()
                })
                goal['conversation_history'].append({
                    "role": "assistant",
                    "content": bot_response,
                    "timestamp": datetime.now().isoformat()
                })

                # 保留最近20轮
                if len(goal['conversation_history']) > 40:
                    goal['conversation_history'] = goal['conversation_history'][-40:]

                goal['metrics']['rounds'] += 1

                # 2. LLM分析: 综合意图分析
                analysis = await self._analyze_conversation_intent(goal, user_message, bot_response)

                # 3. 处理目标切换
                if analysis.get('goal_switch_needed'):
                    await self._handle_goal_switch(goal, analysis)

                # 4. 处理阶段调整
                if analysis.get('stage_adjustment_needed'):
                    await self._handle_stage_adjustment(goal, analysis)
                elif analysis.get('stage_completed'):
                    await self._advance_to_next_stage(goal, analysis)

                # 5. 更新指标
                goal['metrics']['completion_signals'] += analysis.get('completion_signals', 0)
                goal['metrics']['user_engagement'] = analysis.get('user_engagement', 0.5)
                goal['metrics']['goal_progress'] = self._calculate_progress(goal)

                # 6. 检查话题完结
                if analysis.get('topic_completed'):
                    goal['final_goal']['topic_status'] = 'completed'
                    logger.info(f"话题完结: user={user_id}, topic={goal['final_goal']['topic']}")

                # 7. 检查会话完成
                if self._is_session_completed(goal):
                    goal['status'] = 'completed'
                    logger.info(f"会话完成: user={user_id}, session={goal['session_id']}")

                # 8. 持久化更新
                self._update_orm_from_dict(goal_orm, goal)
                await repo.update(goal_orm)
                await session.commit()

                return goal

        except Exception as e:
            logger.error(f"动态调整目标失败: {e}", exc_info=True)
            return None

    async def _analyze_conversation_intent(
        self,
        goal: Dict,
        user_message: str,
        bot_response: str
    ) -> Dict:
        """
        LLM分析: 综合意图分析

        Returns:
            {
                "goal_switch_needed": false,
                "new_goal_type": null,
                "topic_completed": false,
                "stage_completed": true,
                "stage_adjustment_needed": false,
                "suggested_stage": "识别核心问题",
                "completion_signals": 1,
                "user_engagement": 0.8,
                "reasoning": "用户开始详细描述问题，当前阶段已完成"
            }
        """
        current_goal_type = goal['final_goal']['type']
        current_topic = goal['final_goal']['topic']
        current_stage = goal['current_stage']['task']
        planned_stages = goal['planned_stages']

        # 获取最近3轮对话上下文
        recent_history = goal['conversation_history'][-6:]
        history_text = "\n".join([
            f"{'用户' if msg['role'] == 'user' else 'Bot'}: {msg['content']}"
            for msg in recent_history
        ])

        prompt = f"""分析对话的意图变化和阶段进展。

当前状态:
- 最终目标: {current_goal_type} ({goal['final_goal']['name']})
- 当前话题: {current_topic}
- 当前阶段: {current_stage}
- 规划阶段: {', '.join(planned_stages)}

最近对话:
{history_text}

本轮对话:
用户: {user_message}
Bot: {bot_response}

请分析:
1. 用户意图是否发生重大转变(需要切换目标类型)?
2. 当前话题是否已经聊完(可以切换新话题)?
3. 当前阶段任务是否完成?
4. 是否需要调整当前阶段策略?
5. 用户参与度如何(0-1)?
6. 检测到的完成信号数量(0-N)?

返回JSON:
{{
    "goal_switch_needed": false,
    "new_goal_type": null,
    "new_topic": null,
    "topic_completed": false,
    "stage_completed": true,
    "stage_adjustment_needed": false,
    "suggested_stage": "下一阶段任务",
    "completion_signals": 1,
    "user_engagement": 0.8,
    "reasoning": "简短理由(20字内)"
}}"""

        try:
            # 使用提示词保护包装
            protected_prompt = self.prompt_protection.wrap_prompt(prompt, register_for_filter=True)

            response = await self.llm.refine_chat_completion(
                prompt=protected_prompt,
                temperature=0.3,
                max_tokens=300
            )

            # 消毒响应
            sanitized_response, report = self.prompt_protection.sanitize_response(response)

            # 使用guardrails验证和清理JSON
            analysis = self.guardrails.validate_and_clean_json(
                sanitized_response,
                fallback={
                    "goal_switch_needed": False,
                    "topic_completed": False,
                    "stage_completed": False,
                    "stage_adjustment_needed": False,
                    "completion_signals": 0,
                    "user_engagement": 0.5,
                    "reasoning": "分析失败"
                }
            )

            return analysis

        except Exception as e:
            logger.warning(f"意图分析失败: {e}")
            # 返回默认分析
            return {
                "goal_switch_needed": False,
                "topic_completed": False,
                "stage_completed": False,
                "stage_adjustment_needed": False,
                "completion_signals": 0,
                "user_engagement": 0.5,
                "reasoning": "分析失败"
            }

    async def _handle_goal_switch(self, goal: Dict, analysis: Dict):
        """处理目标切换"""
        # 只在话题完结时才切换最终目标
        if not analysis.get('topic_completed'):
            logger.info("检测到目标切换需求，但话题未完结，暂不切换")
            return

        new_goal_type = analysis.get('new_goal_type')
        new_topic = analysis.get('new_topic', '新话题')

        if new_goal_type and new_goal_type in self.GOAL_TEMPLATES:
            old_goal_type = goal['final_goal']['type']

            # 记录切换
            goal['goal_switches'].append({
                "from": old_goal_type,
                "to": new_goal_type,
                "reason": analysis.get('reasoning', '未知原因'),
                "timestamp": datetime.now().isoformat()
            })

            # 更新最终目标
            template = self.GOAL_TEMPLATES[new_goal_type]
            goal['final_goal'] = {
                "type": new_goal_type,
                "name": template['name'],
                "detected_at": datetime.now().isoformat(),
                "confidence": 0.8,
                "topic": new_topic,
                "topic_status": "active"
            }

            # 重新规划阶段
            user_message = goal['conversation_history'][-2]['content'] if len(goal['conversation_history']) >= 2 else ""
            planned_stages = await self._plan_dynamic_stages(
                new_goal_type, new_topic, user_message, template['base_stages']
            )

            goal['planned_stages'] = planned_stages
            goal['current_stage'] = {
                "index": 0,
                "task": planned_stages[0] if planned_stages else "自然互动",
                "strategy": "重新开始",
                "adjusted_at": datetime.now().isoformat(),
                "adjustment_reason": f"目标切换: {old_goal_type} -> {new_goal_type}"
            }

            logger.info(f"目标已切换: {old_goal_type} -> {new_goal_type}, 新话题: {new_topic}")

    async def _handle_stage_adjustment(self, goal: Dict, analysis: Dict):
        """处理阶段调整"""
        suggested_stage = analysis.get('suggested_stage')

        if suggested_stage:
            # 记录当前阶段到历史
            goal['stage_history'].append({
                "task": goal['current_stage']['task'],
                "adjusted_at": datetime.now().isoformat(),
                "effectiveness": goal['metrics']['user_engagement']
            })

            # 更新当前阶段
            goal['current_stage'] = {
                "index": goal['current_stage']['index'],
                "task": suggested_stage,
                "strategy": "动态调整",
                "adjusted_at": datetime.now().isoformat(),
                "adjustment_reason": analysis.get('reasoning', '根据对话调整')
            }

            logger.info(f"阶段已调整: {suggested_stage}")

    async def _advance_to_next_stage(self, goal: Dict, analysis: Dict):
        """推进到下一阶段"""
        current_index = goal['current_stage']['index']
        planned_stages = goal['planned_stages']

        # 记录完成的阶段
        goal['stage_history'].append({
            "task": goal['current_stage']['task'],
            "completed_at": datetime.now().isoformat(),
            "effectiveness": goal['metrics']['user_engagement']
        })

        # 推进到下一阶段
        next_index = current_index + 1

        if next_index < len(planned_stages):
            goal['current_stage'] = {
                "index": next_index,
                "task": planned_stages[next_index],
                "strategy": "顺序推进",
                "adjusted_at": datetime.now().isoformat(),
                "adjustment_reason": "上一阶段已完成"
            }
            logger.info(f"推进到下一阶段: {planned_stages[next_index]}")
        else:
            # 所有阶段完成
            goal['current_stage']['task'] = "自然收尾"
            logger.info("所有阶段已完成，进入收尾阶段")

    def _calculate_progress(self, goal: Dict) -> float:
        """计算总体进度"""
        current_index = goal['current_stage']['index']
        total_stages = len(goal['planned_stages'])

        if total_stages == 0:
            return 0.0

        return min(1.0, (current_index + 1) / total_stages)

    def _is_session_completed(self, goal: Dict) -> bool:
        """判断会话是否完成"""
        # 条件1: 话题完结
        topic_completed = goal['final_goal']['topic_status'] == 'completed'

        # 条件2: 所有阶段完成
        all_stages_done = goal['current_stage']['index'] >= len(goal['planned_stages'])

        # 条件3: 用户参与度低
        low_engagement = goal['metrics']['user_engagement'] < 0.3

        # 条件4: 对话轮次足够
        enough_rounds = goal['metrics']['rounds'] >= 5

        return (topic_completed or all_stages_done) and (low_engagement or enough_rounds)

    def _orm_to_dict(self, goal_orm) -> Dict:
        """将ORM对象转换为字典"""
        return {
            "session_id": goal_orm.session_id,
            "user_id": goal_orm.user_id,
            "group_id": goal_orm.group_id,
            "final_goal": goal_orm.final_goal,
            "current_stage": goal_orm.current_stage,
            "stage_history": goal_orm.stage_history or [],
            "planned_stages": goal_orm.planned_stages,
            "conversation_history": goal_orm.conversation_history or [],
            "goal_switches": goal_orm.goal_switches or [],
            "metrics": goal_orm.metrics,
            "status": goal_orm.status,
            "created_at": datetime.fromtimestamp(goal_orm.created_at / 1000).isoformat(),
            "last_updated": datetime.fromtimestamp(goal_orm.last_updated / 1000).isoformat()
        }

    def _orm_to_mutable_dict(self, goal_orm) -> Dict:
        """将ORM对象转换为可变字典（用于更新）"""
        return {
            "session_id": goal_orm.session_id,
            "user_id": goal_orm.user_id,
            "group_id": goal_orm.group_id,
            "final_goal": dict(goal_orm.final_goal) if goal_orm.final_goal else {},
            "current_stage": dict(goal_orm.current_stage) if goal_orm.current_stage else {},
            "stage_history": list(goal_orm.stage_history) if goal_orm.stage_history else [],
            "planned_stages": list(goal_orm.planned_stages) if goal_orm.planned_stages else [],
            "conversation_history": list(goal_orm.conversation_history) if goal_orm.conversation_history else [],
            "goal_switches": list(goal_orm.goal_switches) if goal_orm.goal_switches else [],
            "metrics": dict(goal_orm.metrics) if goal_orm.metrics else {},
            "status": goal_orm.status
        }

    def _update_orm_from_dict(self, goal_orm, goal_dict: Dict):
        """从字典更新ORM对象"""
        goal_orm.final_goal = goal_dict['final_goal']
        goal_orm.current_stage = goal_dict['current_stage']
        goal_orm.stage_history = goal_dict['stage_history']
        goal_orm.planned_stages = goal_dict['planned_stages']
        goal_orm.conversation_history = goal_dict['conversation_history']
        goal_orm.goal_switches = goal_dict['goal_switches']
        goal_orm.metrics = goal_dict['metrics']
        goal_orm.status = goal_dict['status']

    def _get_default_session(self, user_id: str, group_id: str, user_message: str) -> Dict:
        """获取默认会话(降级方案)"""
        session_id = self._generate_session_id(group_id, user_id)

        return {
            "session_id": session_id,
            "user_id": user_id,
            "group_id": group_id,
            "final_goal": {
                "type": "casual_chat",
                "name": "闲聊互动",
                "detected_at": datetime.now().isoformat(),
                "confidence": 0.5,
                "topic": "闲聊",
                "topic_status": "active"
            },
            "current_stage": {
                "index": 0,
                "task": "自然互动",
                "strategy": "回应用户",
                "adjusted_at": datetime.now().isoformat(),
                "adjustment_reason": "默认会话"
            },
            "stage_history": [],
            "planned_stages": ["自然互动"],
            "conversation_history": [
                {"role": "user", "content": user_message, "timestamp": datetime.now().isoformat()}
            ],
            "goal_switches": [],
            "metrics": {
                "rounds": 0,
                "completion_signals": 0,
                "user_engagement": 0.5,
                "goal_progress": 0.0
            },
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "status": "active"
        }

    async def get_conversation_goal(self, user_id: str, group_id: str) -> Optional[Dict]:
        """获取当前对话目标(向后兼容接口)"""
        try:
            async with self.db_manager.get_session() as session:
                repo = ConversationGoalRepository(session)
                goal_orm = await repo.get_active_goal_by_user(user_id, group_id)

                if not goal_orm:
                    return None

                return self._orm_to_dict(goal_orm)

        except Exception as e:
            logger.error(f"获取对话目标失败: {e}", exc_info=True)
            return None

    async def clear_conversation_goal(self, user_id: str, group_id: str) -> bool:
        """清除对话目标"""
        try:
            async with self.db_manager.get_session() as session:
                repo = ConversationGoalRepository(session)
                goal_orm = await repo.get_active_goal_by_user(user_id, group_id)

                if not goal_orm:
                    return False

                success = await repo.delete_by_session_id(goal_orm.session_id)
                await session.commit()

                logger.info(f"已清除对话目标: user={user_id}, group={group_id}")
                return success

        except Exception as e:
            logger.error(f"清除目标失败: {e}", exc_info=True)
            return False

    async def get_goal_statistics(self) -> Dict:
        """获取目标统计信息"""
        try:
            async with self.db_manager.get_session() as session:
                repo = ConversationGoalRepository(session)
                return await repo.get_goal_statistics()

        except Exception as e:
            logger.error(f"获取统计信息失败: {e}", exc_info=True)
            return {
                "total_sessions": 0,
                "active_sessions": 0,
                "completed_sessions": 0,
                "by_type": {},
                "total_goal_switches": 0,
                "avg_switches_per_session": 0
            }