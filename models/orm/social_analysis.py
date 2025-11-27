"""
社交关系分析相关的 ORM 模型
"""
from sqlalchemy import Column, Integer, String, Text, Float, Index, BigInteger
from .base import Base


class SocialRelationAnalysisResult(Base):
    """社交关系分析结果表"""
    __tablename__ = 'social_relation_analysis_results'

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(255), nullable=False, index=True)
    analysis_type = Column(String(50), nullable=False)
    result_data = Column(Text, nullable=False)  # JSON 格式
    created_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index('idx_social_analysis_group', 'group_id'),
        Index('idx_social_analysis_type', 'analysis_type'),
    )


class SocialNetworkNode(Base):
    """社交网络节点表"""
    __tablename__ = 'social_network_nodes'

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(255), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    node_type = Column(String(50), default='user')
    display_name = Column(String(255))
    properties = Column(Text)  # JSON 格式
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index('idx_social_node_group_user', 'group_id', 'user_id', unique=True),
    )


class SocialNetworkEdge(Base):
    """社交网络边表"""
    __tablename__ = 'social_network_edges'

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(255), nullable=False, index=True)
    from_user_id = Column(String(255), nullable=False, index=True)
    to_user_id = Column(String(255), nullable=False, index=True)
    edge_type = Column(String(50), nullable=False)
    weight = Column(Float, default=1.0)
    properties = Column(Text)  # JSON 格式
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index('idx_social_edge_from_to', 'group_id', 'from_user_id', 'to_user_id'),
    )
