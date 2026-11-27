"""黑话统计预筛的健壮性回归：依赖缺失、内存上限、开关语义。"""

import builtins

import pytest

from self_learning_EterU.services.jargon import jargon_statistical_filter as jf_module
from self_learning_EterU.services.jargon.jargon_statistical_filter import (
    JargonStatisticalFilter,
)


def _block_jieba(monkeypatch):
    """让 ``import jieba`` 失败，模拟用户未安装依赖。"""
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "jieba":
            raise ImportError("No module named 'jieba'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)


@pytest.mark.unit
def test_missing_jieba_degrades_instead_of_raising(monkeypatch):
    """jieba 缺失时每消息都抛 ImportError 会让学习流水线持续报错。"""
    _block_jieba(monkeypatch)
    jfilter = JargonStatisticalFilter()

    # 连续两次都不应抛异常，且不产生候选
    jfilter.update_from_message("这是一条测试消息", "g1", "u1")
    jfilter.update_from_message("这是第二条测试消息", "g1", "u1")

    assert jfilter._jieba_checked is True
    assert jfilter._jieba_available is False
    assert jfilter.get_jargon_candidates("g1") == []


@pytest.mark.unit
def test_terms_per_group_are_capped(monkeypatch):
    """单群词表超上限时只淘汰低频词，保留高频词与辅助表一致性。"""
    monkeypatch.setattr(jf_module, "_MAX_TERMS_PER_GROUP", 5)
    jfilter = JargonStatisticalFilter()
    # 绕过 jieba：直接按字符分词
    monkeypatch.setattr(jfilter, "_tokenize", lambda text: list(text.replace(" ", "")))

    # 先让前 5 个词累积次数，再灌入一批只出现一次的词把表顶超上限
    jfilter.update_from_message("一二三四五", "g1", "u1")
    jfilter.update_from_message("一二三四五六七八九十", "g1", "u1")

    terms = jfilter._group_term_freq["g1"]
    assert len(terms) == 5
    # 高频词优先保留，只出现一次的词被淘汰（而非整表清空）
    assert set(terms) == set("一二三四五")
    assert set(jfilter._user_term_freq["g1"]) == set(terms)
    assert set(jfilter._term_contexts["g1"]) == set(terms)


@pytest.mark.unit
def test_group_table_is_lru_capped(monkeypatch):
    """群组数超上限时淘汰最久未更新的群，并清理其辅助表。"""
    monkeypatch.setattr(jf_module, "_MAX_TRACKED_GROUPS", 3)
    jfilter = JargonStatisticalFilter()
    monkeypatch.setattr(jfilter, "_tokenize", lambda text: list(text.replace(" ", "")))

    for group in ("g1", "g2", "g3", "g4"):
        jfilter.update_from_message("一二三", group, "u1")

    assert list(jfilter._group_term_freq) == ["g2", "g3", "g4"]
    assert jfilter.get_jargon_candidates("g1") == []
    # 被淘汰群组的辅助表必须一并清掉，否则内存不降
    assert "g1" not in jfilter._user_term_freq
    assert "g1" not in jfilter._term_first_seen
    assert "g1" not in jfilter._term_contexts


@pytest.mark.unit
def test_sender_map_per_term_is_bounded(monkeypatch):
    """单个热词被大量用户使用时，发送者计数表同样不能无限增长。"""
    monkeypatch.setattr(jf_module, "_MAX_SENDERS_PER_TERM", 3)
    jfilter = JargonStatisticalFilter()
    monkeypatch.setattr(jfilter, "_tokenize", lambda text: ["热词"])

    for index in range(6):
        jfilter.update_from_message("热词", "g1", f"user-{index}")

    senders = jfilter._user_term_freq["g1"]["热词"]
    assert len(senders) == 3
    # 被保留的是发言最多的发送者；此处每人一次，保留任意 3 个即可
    assert set(senders) <= {f"user-{index}" for index in range(6)}
    # 候选统计仍可正常产出（unique_users 取保留数量）
    candidates = jfilter.get_jargon_candidates("g1")
    assert candidates == [] or candidates[0]["unique_users"] <= 3


@pytest.mark.unit
def test_active_group_survives_eviction(monkeypatch):
    """LRU 语义：持续有新消息的群组不应被后来创建的群组挤掉。"""
    monkeypatch.setattr(jf_module, "_MAX_TRACKED_GROUPS", 3)
    jfilter = JargonStatisticalFilter()
    for group in ("g1", "g2", "g3"):
        jfilter._ensure_group_tables(group)
    # g1 再次活跃，插入 g4 时应淘汰最久未更新的 g2
    jfilter._ensure_group_tables("g1")
    jfilter._ensure_group_tables("g4")

    tracked = list(jfilter._group_term_freq)
    assert tracked == ["g3", "g1", "g4"]
