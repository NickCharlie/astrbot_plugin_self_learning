"""clean_db_text / truncate_for_db 数据库文本安全回归（issue #273）。"""
from utils.text_utils import clean_db_text, truncate_for_db


def test_clean_db_text_removes_nul_bytes():
    payload = "\n\x1a\x12\x18群名片\x92\x10\x00"
    assert clean_db_text(payload) == "\n\x1a\x12\x18群名片\x92\x10"


def test_clean_db_text_drops_lone_surrogates():
    assert clean_db_text("abc\ud83ddef") == "abcdef"


def test_clean_db_text_combines_surrogate_pairs_back_to_real_characters():
    # 双重转义产生的两个孤立代理码点应合并回真实字符，而不是一起丢弃
    assert clean_db_text("ab\ud83d\ude04cd") == "ab\U0001f604cd"
    assert clean_db_text("hello 😄 世界") == "hello 😄 世界"


def test_clean_db_text_keeps_normal_text():
    text = "普通昵称 with spaces\nand newlines\tand 中文"
    assert clean_db_text(text) == text


def test_clean_db_text_passthrough_non_str_and_empty():
    assert clean_db_text(None) is None
    assert clean_db_text("") == ""
    assert clean_db_text(123) == 123


def test_truncate_for_db_cleans_nul_before_length_check():
    # 清理后 60000 字节恰好达到上限，不应被截断
    text = "\x00" + "y" * 60000
    assert truncate_for_db(text) == "y" * 60000


def test_truncate_for_db_truncates_and_appends_marker():
    result = truncate_for_db("x" * 70000)
    assert result == "x" * (60000 - len("...[truncated]")) + "...[truncated]"


def test_truncate_for_db_passthrough_non_str_and_empty():
    assert truncate_for_db(None) is None
    assert truncate_for_db("") == ""
