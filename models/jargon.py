"""
黑话学习系统 - 数据模型

基于 MaiBot 的黑话学习系统设计，实现三步推断法智能识别群组黑话
"""
from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime


@dataclass
class Jargon:
    """黑话数据模型"""

    id: Optional[int] = None
    content: str = ""                        # 黑话词条
    raw_content: str = "[]"                 # JSON数组: 多个使用上下文
    meaning: Optional[str] = None           # 推断的含义
    is_jargon: Optional[bool] = None        # 是否确定为黑话 (None=未推断)
    count: int = 1                          # 出现次数
    last_inference_count: int = 0           # 上次推断时的count值
    is_complete: bool = False               # 是否完成所有推断 (count>=100)
    is_global: bool = False                 # 是否全局黑话
    chat_id: str = ""                       # 群组ID
    created_at: Optional[datetime] = None   # 创建时间
    updated_at: Optional[datetime] = None   # 更新时间

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'id': self.id,
            'content': self.content,
            'raw_content': self.raw_content,
            'meaning': self.meaning,
            'is_jargon': self.is_jargon,
            'count': self.count,
            'last_inference_count': self.last_inference_count,
            'is_complete': self.is_complete,
            'is_global': self.is_global,
            'chat_id': self.chat_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Jargon':
        """从字典创建"""
        created_at = None
        if data.get('created_at'):
            if isinstance(data['created_at'], str):
                created_at = datetime.fromisoformat(data['created_at'])
            else:
                created_at = data['created_at']

        updated_at = None
        if data.get('updated_at'):
            if isinstance(data['updated_at'], str):
                updated_at = datetime.fromisoformat(data['updated_at'])
            else:
                updated_at = data['updated_at']

        return cls(
            id=data.get('id'),
            content=data.get('content', ''),
            raw_content=data.get('raw_content', '[]'),
            meaning=data.get('meaning'),
            is_jargon=data.get('is_jargon'),
            count=data.get('count', 1),
            last_inference_count=data.get('last_inference_count', 0),
            is_complete=data.get('is_complete', False),
            is_global=data.get('is_global', False),
            chat_id=data.get('chat_id', ''),
            created_at=created_at,
            updated_at=updated_at
        )


# SQL 表创建语句
CREATE_JARGON_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS jargon (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    raw_content TEXT DEFAULT '[]',
    meaning TEXT,
    is_jargon BOOLEAN,
    count INTEGER DEFAULT 1,
    last_inference_count INTEGER DEFAULT 0,
    is_complete BOOLEAN DEFAULT 0,
    is_global BOOLEAN DEFAULT 0,
    chat_id TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(chat_id, content)
);
"""

# 索引创建语句
CREATE_JARGON_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_jargon_content ON jargon(content);",
    "CREATE INDEX IF NOT EXISTS idx_jargon_chat_id ON jargon(chat_id);",
    "CREATE INDEX IF NOT EXISTS idx_jargon_is_jargon ON jargon(is_jargon);",
    "CREATE INDEX IF NOT EXISTS idx_jargon_count ON jargon(count);",
]
