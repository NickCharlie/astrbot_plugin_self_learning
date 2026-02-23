"""
黑话挖掘器 - 核心黑话学习服务

智能识别和学习群组黑话
"""
import json
import time
import asyncio
from typing import List, Dict, Optional, Any
from datetime import datetime

from astrbot.api import logger

from ...models.jargon import Jargon
from ...core.framework_llm_adapter import FrameworkLLMAdapter
from ...core.patterns import AsyncServiceBase
from ...utils.json_utils import safe_parse_llm_json


class JargonInferenceEngine:
    """黑话推断引擎 - 实现三步推断法"""

    def __init__(self, llm_adapter: FrameworkLLMAdapter):
        self.llm = llm_adapter
        self._init_prompts()

    def _init_prompts(self):
        """初始化推断Prompts"""

        # Prompt 1: 基于上下文推断
        self.prompt_infer_with_context = """**词条内容**
{content}

**词条出现的上下文**
{raw_content}

请根据以上词条内容和上下文，推断这个词条的含义。
- 如果这是一个黑话、俚语或网络用语，请推断其含义
- 如果含义明确（常规词汇），也请说明
- 如果上下文信息不足，无法推断含义，请设置 no_info 为 true

以 JSON 格式输出：
{{
  "meaning": "详细含义说明（包含使用场景、来源、具体解释等）",
  "no_info": false
}}
注意：如果信息不足无法推断，请设置 "no_info": true，此时 meaning 可以为空字符串"""

        # Prompt 2: 仅基于词条推断
        self.prompt_infer_content_only = """**词条内容**
{content}

请仅根据这个词条本身，推断其含义。
- 如果这是一个黑话、俚语或网络用语，请推断其含义
- 如果含义明确（常规词汇），也请说明

以 JSON 格式输出：
{{
  "meaning": "详细含义说明（包含使用场景、来源、具体解释等）"
}}"""

        # Prompt 3: 对比两个推断
        self.prompt_compare_inference = """**推断结果1（基于上下文）**
{inference1}

**推断结果2（仅基于词条）**
{inference2}

请比较这两个推断结果，判断它们是否相同或类似。
- 如果两个推断结果的"含义"相同或类似，说明这个词条不是黑话（含义明确）
- 如果两个推断结果有差异，说明这个词条可能是黑话（需要上下文才能理解）

以 JSON 格式输出：
{{
  "is_similar": true/false,
  "reason": "判断理由"
}}"""

    async def infer_meaning(
        self,
        content: str,
        raw_content_list: List[str]
    ) -> Optional[Dict[str, Any]]:
        """
        使用三步推断法判断黑话

        Returns:
            {
                'is_jargon': bool,      # 是否为黑话
                'meaning': str,          # 推断的含义
                'no_info': bool          # 是否信息不足
            }
            或 None (如果推断失败)
        """
        try:
            # 步骤1: 基于上下文推断
            raw_content_text = "\n".join(raw_content_list)
            prompt1 = self.prompt_infer_with_context.format(
                content=content,
                raw_content=raw_content_text
            )

            response1 = await self.llm.generate_response(prompt1, temperature=0.3)
            if not response1:
                logger.warning(f"黑话 {content} 推断1失败：无响应")
                return None

            # 解析推断1
            inference1 = safe_parse_llm_json(response1.strip())
            if not isinstance(inference1, dict):
                logger.warning(f"黑话 {content} 推断1解析失败")
                return None

            # 检查是否信息不足
            if inference1.get('no_info'):
                logger.info(f"黑话 {content} 信息不足，等待下次推断")
                return {'no_info': True}

            meaning1 = inference1.get('meaning', '').strip()
            if not meaning1:
                return {'no_info': True}

            # 步骤2: 仅基于词条推断
            prompt2 = self.prompt_infer_content_only.format(content=content)
            response2 = await self.llm.generate_response(prompt2, temperature=0.3)

            if not response2:
                logger.warning(f"黑话 {content} 推断2失败：无响应")
                return None

            inference2 = safe_parse_llm_json(response2.strip())
            if not isinstance(inference2, dict):
                logger.warning(f"黑话 {content} 推断2解析失败")
                return None

            # 步骤3: 对比判断
            prompt3 = self.prompt_compare_inference.format(
                inference1=json.dumps(inference1, ensure_ascii=False),
                inference2=json.dumps(inference2, ensure_ascii=False)
            )

            response3 = await self.llm.generate_response(prompt3, temperature=0.3)
            if not response3:
                logger.warning(f"黑话 {content} 对比失败：无响应")
                return None

            comparison = safe_parse_llm_json(response3.strip())
            if not isinstance(comparison, dict):
                logger.warning(f"黑话 {content} 对比解析失败")
                return None

            # 判断是否为黑话
            is_similar = comparison.get('is_similar', False)
            is_jargon = not is_similar

            return {
                'is_jargon': is_jargon,
                'meaning': meaning1 if is_jargon else inference2.get('meaning', ''),
                'no_info': False
            }

        except Exception as e:
            logger.error(f"黑话推断异常: {e}")
            import traceback
            traceback.print_exc()
            return None


class JargonMiner(AsyncServiceBase):
    """黑话挖掘器 - 管理黑话提取和学习"""

    # 推断阈值
    INFERENCE_THRESHOLDS = [3, 6, 10, 20, 40, 60, 100]

    def __init__(
        self,
        chat_id: str,
        llm_adapter: FrameworkLLMAdapter,
        db_manager,
        config
    ):
        super().__init__(f"jargon_miner_{chat_id}")
        self.chat_id = chat_id
        self.llm = llm_adapter
        self.db = db_manager
        self.config = config

        # 推断引擎
        self.inference_engine = JargonInferenceEngine(llm_adapter)

        # 频率控制
        self.min_messages = getattr(config, 'jargon_min_messages', 10)
        self.min_interval = getattr(config, 'jargon_min_interval', 20)
        self.last_learning_time = time.time()

        # 候选提取Prompt
        self._init_extract_prompt()

    def _init_extract_prompt(self):
        """初始化黑话提取Prompt"""
        self.extract_prompt_template = """**聊天内容**
{chat_str}

请从上面这段聊天内容中提取"黑话/俚语/网络缩写"候选项。

**必须满足的条件（全部满足才提取）：**
- 是对话中真实出现过的短词或短语（2-8个字符）
- 是特定圈子/群组才会使用的词语，普通人看不懂的
- 脱离上下文后无法理解其含义

**严格排除以下内容（出现即跳过）：**
- @xxx、@某人 等 at 提及
- 人名、昵称、群名、ID
- 日常用语：吃饭、睡觉、上班、回家、好的、可以、谢谢 等
- 常见名词：手机、电脑、学校、公司、时间 等
- 语气词：哈哈、嗯嗯、啊啊、呵呵 等
- 表情描述：[图片]、[表情]、[语音] 等
- 纯数字、纯标点、URL链接
- 含义清晰明确的词语（即使不常见）

**黑话的典型特征：**
- 拼音首字母缩写：yyds、xswl、nbcs、zqsg
- 特定圈子内的暗语、缩写、谐音梗
- 群内独创的表达方式，外人无法理解

以 JSON 数组输出（严格按结构）：
[
  {{"content": "词条", "raw_content": "包含该词条的完整对话上下文原文"}}
]

如果没有找到符合条件的黑话，输出空数组 []

现在请输出："""

    def should_trigger(self, recent_message_count: int) -> bool:
        """判断是否应该触发学习"""
        # 冷却时间检查
        if time.time() - self.last_learning_time < self.min_interval:
            return False

        # 消息数量检查
        if recent_message_count < self.min_messages:
            return False

        return True

    def _should_infer_meaning(self, jargon: Jargon) -> bool:
        """
        判断是否需要进行含义推断
        在 count 达到 3,6,10,20,40,60,100 时进行推断
        """
        if jargon.is_complete:
            return False

        count = jargon.count or 0
        last_inference = jargon.last_inference_count or 0

        if count < self.INFERENCE_THRESHOLDS[0]:
            return False

        if count <= last_inference:
            return False

        # 找到下一个阈值
        next_threshold = None
        for threshold in self.INFERENCE_THRESHOLDS:
            if threshold > last_inference:
                next_threshold = threshold
                break

        if next_threshold is None:
            return False

        return count >= next_threshold

    async def extract_candidates(
        self,
        chat_messages: str
    ) -> List[Dict[str, Any]]:
        """使用LLM提取候选黑话"""
        import re

        prompt = self.extract_prompt_template.format(chat_str=chat_messages)

        try:
            response = await self.llm.generate_response(prompt, temperature=0.2)
            if not response:
                return []

            # 解析JSON
            parsed = safe_parse_llm_json(response.strip())

            if isinstance(parsed, dict):
                parsed = [parsed]

            if not isinstance(parsed, list):
                return []

            # 提取有效条目
            candidates = []
            for item in parsed:
                if not isinstance(item, dict):
                    continue

                content = str(item.get('content', '')).strip()
                raw_content = item.get('raw_content', '')

                if not content:
                    continue

                # 硬编码过滤：@mention、纯数字、过短/过长、常见词
                if self._should_filter_candidate(content):
                    continue

                # 处理 raw_content
                if isinstance(raw_content, list):
                    raw_content_list = [str(rc).strip() for rc in raw_content if str(rc).strip()]
                elif isinstance(raw_content, str):
                    raw_content_list = [raw_content.strip()] if raw_content.strip() else []
                else:
                    raw_content_list = []

                if raw_content_list:
                    candidates.append({
                        'content': content,
                        'raw_content': raw_content_list
                    })

            return candidates

        except Exception as e:
            logger.error(f"提取黑话候选失败: {e}")
            return []

    @staticmethod
    def _should_filter_candidate(content: str) -> bool:
        """硬编码过滤规则，过滤明显不是黑话的候选项"""
        import re

        # 包含 @ 的（@mention）
        if '@' in content:
            return True

        # 纯数字
        if re.match(r'^[\d\s.]+$', content):
            return True

        # 纯标点/特殊字符
        if re.match(r'^[^\w\u4e00-\u9fff]+$', content):
            return True

        # 太短（单字）或太长（>15字符）
        if len(content) < 2 or len(content) > 15:
            return True

        # [图片] [表情] 等标记
        if re.match(r'^\[.+\]$', content):
            return True

        # URL
        if re.match(r'https?://', content):
            return True

        # 常见日常词汇（不是黑话）
        _COMMON_WORDS = frozenset({
            "吃饭", "睡觉", "上班", "下班", "回家", "出门", "上课",
            "工作", "学习", "考试", "运动", "休息", "洗澡",
            "好的", "可以", "谢谢", "没事", "不用", "不是", "没有",
            "手机", "电脑", "学校", "公司", "医院", "超市",
            "今天", "昨天", "明天", "现在", "刚才", "马上",
            "哈哈", "哈哈哈", "嗯嗯", "呵呵", "嘻嘻", "啊啊",
            "朋友", "同学", "老师", "家人", "爸爸", "妈妈",
            "真的", "确实", "其实", "当然", "觉得", "感觉",
            "知道", "不知道", "怎么", "什么", "为什么", "这个", "那个",
        })
        if content in _COMMON_WORDS:
            return True

        return False

    async def save_or_update_jargon(
        self,
        content: str,
        raw_content_list: List[str]
    ) -> Optional[Jargon]:
        """保存或更新黑话到数据库"""

        try:
            # 查询现有记录 (返回字典或None)
            existing_dict = await self.db.get_jargon(self.chat_id, content)

            if existing_dict:
                # 转换为Jargon对象
                existing = Jargon(
                    id=existing_dict.get('id'),
                    content=existing_dict.get('content', ''),
                    raw_content=existing_dict.get('raw_content', '[]'),
                    meaning=existing_dict.get('meaning'),
                    is_jargon=existing_dict.get('is_jargon'),
                    count=existing_dict.get('count', 1),
                    last_inference_count=existing_dict.get('last_inference_count', 0),
                    is_complete=existing_dict.get('is_complete', False),
                    is_global=existing_dict.get('is_global', False),
                    chat_id=existing_dict.get('chat_id', ''),
                    created_at=existing_dict.get('created_at'),
                    updated_at=existing_dict.get('updated_at')
                )

                # 更新现有记录
                existing.count = (existing.count or 0) + 1

                # 合并 raw_content
                existing_list = safe_parse_llm_json(existing.raw_content) or []
                if not isinstance(existing_list, list):
                    existing_list = [existing_list] if existing_list else []

                merged_list = list(dict.fromkeys(existing_list + raw_content_list))
                existing.raw_content = json.dumps(merged_list)
                existing.updated_at = datetime.now()

                # 转换为字典进行更新
                await self.db.update_jargon(self._jargon_to_dict(existing))
                return existing
            else:
                # 创建新记录
                jargon = Jargon(
                    content=content,
                    raw_content=json.dumps(raw_content_list),
                    chat_id=self.chat_id,
                    count=1,
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                )

                jargon_id = await self.db.insert_jargon(self._jargon_to_dict(jargon))
                jargon.id = jargon_id
                return jargon

        except Exception as e:
            logger.error(f"保存黑话失败: content={content}, error={e}")
            return None

    def _jargon_to_dict(self, jargon: Jargon) -> Dict[str, Any]:
        """将Jargon对象转换为字典"""
        return {
            'id': jargon.id,
            'content': jargon.content,
            'raw_content': jargon.raw_content,
            'meaning': jargon.meaning,
            'is_jargon': jargon.is_jargon,
            'count': jargon.count,
            'last_inference_count': jargon.last_inference_count,
            'is_complete': jargon.is_complete,
            'is_global': jargon.is_global,
            'chat_id': jargon.chat_id,
            'created_at': jargon.created_at,
            'updated_at': jargon.updated_at
        }

    async def infer_and_update(self, jargon: Jargon):
        """推断黑话含义并更新"""

        try:
            raw_content_list = safe_parse_llm_json(jargon.raw_content) or []
            if not isinstance(raw_content_list, list):
                raw_content_list = [raw_content_list] if raw_content_list else []

            if not raw_content_list:
                logger.warning(f"黑话 {jargon.content} 没有上下文，跳过推断")
                return

            # 执行推断
            result = await self.inference_engine.infer_meaning(
                jargon.content,
                raw_content_list
            )

            if not result:
                return

            if result.get('no_info'):
                # 信息不足，更新推断计数但不改变状态
                jargon.last_inference_count = jargon.count
                await self.db.update_jargon(self._jargon_to_dict(jargon))
                return

            # 更新推断结果
            jargon.is_jargon = result['is_jargon']
            jargon.meaning = result['meaning']
            jargon.last_inference_count = jargon.count

            # 如果达到100次，标记为完成
            if jargon.count >= 100:
                jargon.is_complete = True

            jargon.updated_at = datetime.now()
            await self.db.update_jargon(self._jargon_to_dict(jargon))

            # 记录日志
            if jargon.is_jargon:
                logger.info(f"[{self.chat_id}] 识别黑话: {jargon.content} → {jargon.meaning}")
            else:
                logger.info(f"[{self.chat_id}] {jargon.content} 不是黑话")

        except Exception as e:
            logger.error(f"推断黑话失败: {e}")

    async def run_once(
        self,
        chat_messages: str,
        message_count: int,
        statistical_candidates: Optional[List[Dict[str, Any]]] = None,
    ):
        """Execute a single jargon learning iteration.

        Args:
            chat_messages: Formatted chat text for LLM extraction.
            message_count: Number of recent messages.
            statistical_candidates: Pre-filtered candidates from
                ``JargonStatisticalFilter``.  When provided, LLM-based
                candidate extraction is skipped, saving one LLM call.
        """

        try:
            if not self.should_trigger(message_count):
                return

            # 1. Get candidates — prefer statistical pre-filter over LLM.
            if statistical_candidates:
                candidates = [
                    {
                        "content": c["term"],
                        "raw_content": c.get("context_examples", []),
                    }
                    for c in statistical_candidates
                    if c.get("term")
                ]
                logger.info(
                    f"[{self.chat_id}] Using {len(candidates)} statistical "
                    f"candidates (LLM extraction skipped)"
                )
            else:
                candidates = await self.extract_candidates(chat_messages)

            if not candidates:
                return

            logger.info(f"[{self.chat_id}] 提取到 {len(candidates)} 个疑似黑话")

            # 2. 保存或更新数据库
            saved_count = 0
            updated_count = 0

            for candidate in candidates:
                content = candidate['content']
                raw_content_list = candidate['raw_content']

                jargon = await self.save_or_update_jargon(content, raw_content_list)

                if not jargon:
                    continue

                if jargon.count == 1:
                    saved_count += 1
                else:
                    updated_count += 1

                # 3. 检查是否需要推断
                if self._should_infer_meaning(jargon):
                    # 异步执行推断，不阻塞主流程
                    asyncio.create_task(self.infer_and_update(jargon))

            if saved_count or updated_count:
                logger.info(
                    f"[{self.chat_id}] 黑话更新: 新增{saved_count}条，更新{updated_count}条"
                )

            # 更新学习时间
            self.last_learning_time = time.time()

        except Exception as e:
            logger.error(f"黑话学习失败: {e}")
            import traceback
            traceback.print_exc()


class JargonMinerManager:
    """黑话挖掘器管理器"""

    def __init__(self, llm_adapter: FrameworkLLMAdapter, db_manager, config):
        self.llm = llm_adapter
        self.db = db_manager
        self.config = config
        self._miners: Dict[str, JargonMiner] = {}

    def get_miner(self, chat_id: str) -> JargonMiner:
        """获取指定群组的黑话挖掘器"""
        if chat_id not in self._miners:
            self._miners[chat_id] = JargonMiner(
                chat_id,
                self.llm,
                self.db,
                self.config
            )
        return self._miners[chat_id]

    def get_or_create_miner(self, chat_id: str) -> JargonMiner:
        """获取或创建指定群组的黑话挖掘器 (别名方法)"""
        return self.get_miner(chat_id)

    async def learn_from_chat(
        self,
        chat_id: str,
        chat_messages: str,
        message_count: int
    ):
        """从聊天记录中学习黑话"""
        miner = self.get_miner(chat_id)
        await miner.run_once(chat_messages, message_count)
