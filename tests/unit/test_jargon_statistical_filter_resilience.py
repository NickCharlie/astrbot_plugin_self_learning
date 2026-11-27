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
def test_tracked_groups_and_terms_are_capped(monkeypatch):
    """长期运行下群数与词表都必须有上限，否则内存单调增长。"""
    monkeypatch.setattr(jf_module, "_MAX_TRACKED_GROUPS", 3)
    monkeypatch.setattr(jf_module, "_MAX_TERMS_PER_GROUP", 5)
    jfilter = JargonStatisticalFilter()
    # 绕过 jieba：直接按字符分词
    monkeypatch.setattr(jfilter, "_tokenize", lambda text: list(text.replace(" ", "")))

    for group in ("g1", "g2", "g3", "g4"):
        jfilter.update_from_message("一二三四五六七八九十", group, "u1")

    # 最早更新的群组被淘汰，活跃群组的表仍在
    assert list(jfilter._group_term_freq) == ["g2", "g3", "g4"]
    assert jfilter.get_jargon_candidates("g1") == []

    # 每个群词表不超过上限，且被淘汰的词在辅助表里也一并清理
    for group in ("g2", "g3", "g4"):
        assert len(jfilter._group_term_freq[group]) <= 5
        assert set(jfilter._user_term_freq[group]) <= set(jfilter._group_term_freq[group])
        assert set(jfilter._term_contexts[group]) <= set(jfilter._group_term_freq[group])


@pytest.mark.unit
def test_active_group_survives_eviction():
    """LRU 语义：持续有新消息的群组不应被后来创建的群组挤掉。"""
    jfilter = JargonStatisticalFilter()
    for group in ("g1", "g2", "g3"):
        jfilter._ensure_group_tables(group)
    # g1 再次活跃，插入 g4 时应淘汰最久未更新的 g2
    jfilter._ensure_group_tables("g1")
    jfilter._ensure_group_tables("g4")

    tracked = list(jfilter._group_term_freq)
    assert "g1" in tracked
    assert tracked[-1] == "g4"
    assert len(tracked) <= jf_module._MAX_TRACKED_GROUPS
