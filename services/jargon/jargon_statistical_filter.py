"""
Jargon statistical pre-filter.

Maintains per-group term frequency tables and applies three statistical
signals (cross-group IDF, burst frequency, user concentration) to identify
jargon candidates *before* any LLM call. This reduces LLM cost by 70-80%
by only forwarding high-confidence candidates to the inference engine.

Design notes:
    - All state is held in memory (dict-of-dicts) for O(1) update per message.
    - Tokenisation uses ``jieba`` (installed by the dependency installer).
      When jieba is unavailable the filter degrades to "no candidates"
      instead of raising on every message; the miner then falls back to
      LLM extraction.
    - The filter is stateless across restarts — rebuilt implicitly from the
      message stream. A future enhancement could persist snapshots to DB.
    - Per-group tables are capped (``_MAX_TRACKED_GROUPS``,
      ``_MAX_TERMS_PER_GROUP``) so a long-running bot with many groups
      cannot grow memory without bound.
    - Thread-safe for single-event-loop asyncio usage (no concurrent writes).
"""

import math
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Set

from astrbot.api import logger


# Minimum term length (characters) to consider as a candidate.
_MIN_TERM_LENGTH = 2

# Minimum frequency in a group before a term is considered.
_MIN_FREQUENCY = 5

# Maximum number of context examples to retain per term.
_MAX_CONTEXT_EXAMPLES = 10

# Memory caps. Groups are evicted LRU-first; within a group the coldest
# (oldest first-seen) terms are dropped once the cap is reached.
_MAX_TRACKED_GROUPS = 50
_MAX_TERMS_PER_GROUP = 2000

# Jieba dictionary frequency threshold.
# Words with frequency > this value in jieba's built-in dictionary are treated
# as standard vocabulary and excluded from jargon candidate tracking.
# Common words (的=318825, 是=796991) have very high frequencies, while
# internet slang recently added to jieba (破防=3, 躺平=3) have very low
# frequencies. Threshold of 100 filters standard vocabulary while preserving
# low-frequency slang entries that may be genuine jargon.
_JIEBA_FREQ_THRESHOLD = 100

# Score component weights.
_WEIGHT_IDF = 0.4
_WEIGHT_BURST = 0.3
_WEIGHT_CONCENTRATION = 0.3

# Common Chinese stopwords, punctuation and everyday words that are never
# jargon. Module-level so the ~170-entry set is built once, not per token.
_STOPWORDS = frozenset({
    # 虚词/助词/语气词
    "的", "了", "在", "是", "我", "有", "和", "就",
    "不", "人", "都", "一", "个", "上", "也", "很",
    "到", "说", "要", "去", "你", "会", "着", "没",
    "看", "好", "自", "这", "他", "她", "它", "们",
    "吗", "吧", "呢", "啊", "哦", "嗯", "呀", "哈",
    "那", "么", "什", "啦", "噢", "嘛", "哇",
    "来", "对", "把", "让", "被", "给", "从", "还",
    "比", "得", "过", "可", "能", "为", "以", "而",
    "但", "或", "如", "与", "等", "及", "其", "之",
    # 代词/指示词
    "这个", "那个", "什么", "怎么", "哪里", "这里", "那里",
    "自己", "大家", "我们", "你们", "他们", "她们", "谁",
    "哪个", "这些", "那些", "多少", "几个", "某个", "别人",
    # 常见动词
    "知道", "觉得", "感觉", "可以", "应该", "需要", "已经",
    "开始", "然后", "因为", "所以", "虽然", "如果",
    "不是", "没有", "不会", "不能", "不要", "不用", "不行",
    "出来", "出去", "进来", "起来", "下去", "回来", "过来",
    "喜欢", "希望", "想要", "能够", "可能", "一定", "必须",
    "告诉", "问题", "时候", "东西", "事情", "地方", "方面",
    # 时间词
    "今天", "昨天", "明天", "现在", "刚才", "以前", "以后",
    "时间", "上午", "下午", "晚上", "早上", "中午",
    # 常见形容词/副词
    "真的", "确实", "其实", "当然", "特别", "非常", "一直",
    "还是", "而且", "只是", "只有", "所有", "一些",
    "比较", "最后", "首先", "接着", "终于", "竟然",
    # 常见名词
    "朋友", "老师", "同学", "学生", "家里", "公司", "学校",
    "手机", "电脑", "工作", "生活",
    # 网络常用但含义明确的词（不是黑话）
    "哈哈", "哈哈哈", "呵呵", "嘻嘻", "啊啊", "嗯嗯",
    "谢谢", "感谢", "抱歉", "不好意思", "没关系",
    "图片", "表情", "语音", "视频", "文件", "链接",
})


class JargonStatisticalFilter:
    """Zero-cost statistical pre-filter for jargon candidate detection.

    Call ``update_from_message`` on every incoming message (< 1 ms cost).
    Call ``get_jargon_candidates`` when batch analysis triggers to retrieve
    high-confidence candidates ranked by a composite statistical score.

    Usage::

        jfilter = JargonStatisticalFilter()

        # Per-message (zero LLM cost):
        jfilter.update_from_message(text, group_id, sender_id)

        # Batch trigger:
        candidates = jfilter.get_jargon_candidates(group_id, top_k=20)
    """

    def __init__(self) -> None:
        # group_id → {term → count}. OrderedDict keeps LRU insertion order so
        # the oldest group can be evicted once _MAX_TRACKED_GROUPS is reached.
        self._group_term_freq: Dict[str, Dict[str, int]] = OrderedDict()

        # group_id → {term → {sender_id → count}}
        self._user_term_freq: Dict[str, Dict[str, Dict[str, int]]] = {}

        # group_id → {term → first_seen_timestamp}
        self._term_first_seen: Dict[str, Dict[str, float]] = {}

        # group_id → {term → [context_examples]}
        self._term_contexts: Dict[str, Dict[str, List[str]]] = {}

        # jieba state (lazy-loaded). ``_jieba_available`` is False both before
        # the first attempt and after a failed import, so a missing dependency
        # is reported once and never raises on the message hot path.
        self._jieba_checked = False
        self._jieba_available = False
        self._jieba_freq: Dict[str, int] = {}  # cached reference to jieba.dt.FREQ

    # Public API

    def update_from_message(
        self,
        content: str,
        group_id: str,
        sender_id: str,
    ) -> None:
        """Update term frequency tables from a single message.

        This method is designed to be called on every incoming message.
        Typical wall-clock cost is < 1 ms (dominated by jieba tokenisation).

        Args:
            content: The raw message text.
            group_id: Chat group identifier.
            sender_id: Message sender identifier.
        """
        if not content or not group_id:
            return

        tokens = self._tokenize(content)
        if not tokens:
            return

        now = time.time()
        self._ensure_group_tables(group_id)
        group_freq = self._group_term_freq[group_id]
        user_freq = self._user_term_freq[group_id]
        first_seen = self._term_first_seen[group_id]
        contexts = self._term_contexts[group_id]

        for token in tokens:
            group_freq[token] = group_freq.get(token, 0) + 1
            user_freq.setdefault(token, {})
            user_freq[token][sender_id] = user_freq[token].get(sender_id, 0) + 1

            if token not in first_seen:
                first_seen[token] = now

            # Store limited context examples.
            ctx_list = contexts.setdefault(token, [])
            ctx_list.append(content)
            del ctx_list[:-_MAX_CONTEXT_EXAMPLES]

        self._evict_cold_terms(group_id)

    def _ensure_group_tables(self, group_id: str) -> None:
        """Create per-group tables, evicting the least recently updated group."""
        if group_id in self._group_term_freq:
            # Refresh LRU position so active groups survive eviction.
            self._group_term_freq.move_to_end(group_id)
            return

        while len(self._group_term_freq) >= _MAX_TRACKED_GROUPS:
            oldest_group, _ = self._group_term_freq.popitem(last=False)
            self._drop_group_tables(oldest_group)
            logger.debug(
                f"[JargonFilter] 群组数达到上限 {_MAX_TRACKED_GROUPS}，"
                f"已淘汰最久未更新的群组 {oldest_group}"
            )

        self._group_term_freq[group_id] = {}
        self._user_term_freq[group_id] = {}
        self._term_first_seen[group_id] = {}
        self._term_contexts[group_id] = {}

    def _evict_cold_terms(self, group_id: str) -> None:
        """Drop the oldest-seen terms once a group exceeds its term cap."""
        term_freq = self._group_term_freq.get(group_id)
        if not term_freq or len(term_freq) <= _MAX_TERMS_PER_GROUP:
            return

        first_seen = self._term_first_seen.get(group_id, {})
        overflow = len(term_freq) - _MAX_TERMS_PER_GROUP
        coldest = sorted(term_freq, key=lambda term: first_seen.get(term, 0.0))[:overflow]
        for term in coldest:
            term_freq.pop(term, None)
            self._user_term_freq.get(group_id, {}).pop(term, None)
            self._term_first_seen.get(group_id, {}).pop(term, None)
            self._term_contexts.get(group_id, {}).pop(term, None)

        logger.debug(
            f"[JargonFilter] 群组 {group_id} 词表超过 {_MAX_TERMS_PER_GROUP}，"
            f"已淘汰 {len(coldest)} 个最久远词条"
        )

    def _drop_group_tables(self, group_id: str) -> None:
        """Remove every table belonging to *group_id*."""
        self._user_term_freq.pop(group_id, None)
        self._term_first_seen.pop(group_id, None)
        self._term_contexts.pop(group_id, None)

    def get_jargon_candidates(
        self,
        group_id: str,
        top_k: int = 20,
        exclude_terms: Optional[Set[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve top-K jargon candidates ranked by composite score.

        The composite score combines three signals:
            1. **Cross-group IDF** (weight 0.4): Terms frequent within the
               group but rare across other groups.
            2. **Burst frequency** (weight 0.3): Terms that appeared recently
               and gained frequency rapidly.
            3. **User concentration** (weight 0.3): Terms used by only a few
               users (insider language).

        Args:
            group_id: The group to analyse.
            top_k: Maximum candidates to return.
            exclude_terms: Set of terms to skip (e.g. already-confirmed
                jargon in the database).

        Returns:
            List of candidate dicts sorted by score descending, each with
            keys: ``term``, ``score``, ``frequency``, ``idf``,
            ``burst_score``, ``unique_users``, ``context_examples``.
        """
        group_freq = self._group_term_freq.get(group_id)
        if not group_freq:
            return []

        exclude = exclude_terms or set()
        num_groups = max(len(self._group_term_freq), 1)
        candidates: List[Dict[str, Any]] = []

        for term, freq in group_freq.items():
            if freq < _MIN_FREQUENCY:
                continue
            if term in exclude:
                continue

            # Signal 1: Cross-group IDF.
            groups_containing = sum(
                1 for gf in self._group_term_freq.values() if term in gf
            )
            idf = math.log(num_groups / max(groups_containing, 1))

            # Signal 2: Burst frequency (frequency / age_days).
            burst_score = self._calc_burst_score(term, group_id)

            # Signal 3: User concentration (1 / unique_users).
            unique_users = len(
                self._user_term_freq.get(group_id, {}).get(term, {})
            )
            concentration = 1.0 / max(unique_users, 1)

            # Composite score.
            score = (
                idf * _WEIGHT_IDF
                + burst_score * _WEIGHT_BURST
                + concentration * _WEIGHT_CONCENTRATION
            )

            candidates.append({
                "term": term,
                "score": round(score, 4),
                "frequency": freq,
                "idf": round(idf, 4),
                "burst_score": round(burst_score, 4),
                "unique_users": unique_users,
                "context_examples": self._term_contexts.get(
                    group_id, {}
                ).get(term, [])[-5:],
            })

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:top_k]

    def get_group_stats(self, group_id: str) -> Dict[str, Any]:
        """Return summary statistics for a group's term table.

        Useful for monitoring and dashboard display.
        """
        group_freq = self._group_term_freq.get(group_id, {})
        return {
            "total_unique_terms": len(group_freq),
            "total_occurrences": sum(group_freq.values()),
            "terms_above_threshold": sum(
                1 for f in group_freq.values() if f >= _MIN_FREQUENCY
            ),
        }

    def reset_group(self, group_id: str) -> None:
        """Clear all statistical data for a specific group."""
        self._group_term_freq.pop(group_id, None)
        self._drop_group_tables(group_id)
        logger.debug(f"[JargonFilter] Reset statistics for group {group_id}")

    # Internal helpers

    def _tokenize(self, text: str) -> List[str]:
        """Segment text into tokens using jieba.

        Returns tokens with length >= _MIN_TERM_LENGTH, excluding
        common stopwords, punctuation, @mentions, URLs, and pure numbers.
        Returns an empty list when jieba is unavailable — callers treat that
        as "no statistical candidates" and fall back to LLM extraction.
        """
        import re

        # 预处理：移除 @mention、URL、纯数字序列
        text = re.sub(r'@\S+', '', text)
        text = re.sub(r'https?://\S+', '', text)
        text = re.sub(r'\[.*?\]', '', text)  # 移除 [图片] [表情] 等

        if not self._ensure_jieba():
            return []

        import jieba

        tokens = []
        for word in jieba.cut(text):
            word = word.strip()
            if len(word) < _MIN_TERM_LENGTH:
                continue
            if self._is_stopword(word):
                continue
            # 跳过纯数字、纯标点、纯英文常见词
            if re.match(r'^[\d\s]+$', word):
                continue
            if re.match(r'^[^\w]+$', word):
                continue
            # 过滤jieba词典中的标准词汇（频率 > 阈值即为已知词）
            if self._is_standard_vocabulary(word):
                continue
            tokens.append(word)
        return tokens

    def _ensure_jieba(self) -> bool:
        """Lazily initialise jieba; return whether it is usable.

        The attempt runs once per instance. A missing dependency is logged a
        single time and permanently degrades to "no candidates", so the
        per-message hot path never raises ``ImportError``.
        """
        if self._jieba_checked:
            return self._jieba_available

        self._jieba_checked = True
        try:
            import jieba
            jieba.setLogLevel(20) # Suppress jieba's verbose logging.
            # Trigger dictionary load so jieba.dt.FREQ is populated.
            if not jieba.dt.initialized:
                jieba.initialize()
            self._jieba_freq = jieba.dt.FREQ  # cache reference for fast lookup
            self._jieba_available = True
            logger.info(
                f"[JargonFilter] jieba loaded, dictionary contains "
                f"{len(self._jieba_freq)} entries for standard vocabulary filtering "
                f"(threshold={_JIEBA_FREQ_THRESHOLD})"
            )
        except ImportError:
            logger.warning(
                "[JargonFilter] jieba 未安装，黑话统计预筛停用，"
                "将回退到 LLM 候选提取。安装方式：pip install jieba"
            )
        except Exception as exc:
            logger.warning(
                f"[JargonFilter] jieba 初始化失败，黑话统计预筛停用: {exc}"
            )
        return self._jieba_available

    def _is_standard_vocabulary(self, word: str) -> bool:
        """Check if a word is standard vocabulary using jieba's frequency dictionary.

        Words with high frequency in jieba's built-in dictionary are known
        standard Chinese vocabulary. Group-specific jargon (abbreviations,
        inside jokes, memes) either won't appear in the dictionary or will
        have very low frequency.

        Uses the cached ``_jieba_freq`` reference for O(1) lookup per token.
        Returns ``False`` (don't filter) if jieba is not loaded.
        """
        if not self._jieba_available:
            return False
        return self._jieba_freq.get(word, 0) > _JIEBA_FREQ_THRESHOLD

    def _calc_burst_score(self, term: str, group_id: str) -> float:
        """Calculate burst frequency: freq / age_in_days.

        A high value means the term gained popularity quickly.
        """
        first_seen = self._term_first_seen.get(group_id, {}).get(term, 0)
        if first_seen == 0:
            return 0.0
        age_days = max((time.time() - first_seen) / 86400.0, 1.0)
        freq = self._group_term_freq.get(group_id, {}).get(term, 0)
        return freq / age_days

    @staticmethod
    def _is_stopword(word: str) -> bool:
        """Quick check for common Chinese stopwords, punctuation, and everyday words."""
        return word in _STOPWORDS
