"""
WebUI 蓝图模块 - Blueprint 注册
"""
from typing import List
from quart import Blueprint

from .auth import auth_bp
from .config import config_bp
from .personas import personas_bp
from .learning import learning_bp
from .jargon import jargon_bp
from .chat import chat_bp
from .bug_report import bug_report_bp
from .metrics import metrics_bp
from .social import social_bp
from .persona_reviews import persona_reviews_bp
from .intelligent_chat import intelligent_chat_bp

# monitoring blueprint requires prometheus_client; degrade gracefully
try:
    from .monitoring import monitoring_bp
    _has_monitoring = True
except ImportError:
    _has_monitoring = False


def get_blueprints() -> List[Blueprint]:
    """
    获取所有蓝图

    Returns:
        List[Blueprint]: 蓝图列表
    """
    bps = [
        auth_bp,
        config_bp,
        personas_bp,
        learning_bp,
        jargon_bp,
        chat_bp,
        bug_report_bp,
        metrics_bp,
        social_bp,
        persona_reviews_bp,
        intelligent_chat_bp,
    ]
    if _has_monitoring:
        bps.append(monitoring_bp)
    return bps


def register_blueprints(app):
    """
    注册所有蓝图到应用

    Args:
        app: Quart 应用实例
    """
    blueprints = get_blueprints()
    for bp in blueprints:
        app.register_blueprint(bp)
        print(f" [WebUI] 已注册蓝图: {bp.name}")


__all__ = [
    'auth_bp',
    'config_bp',
    'personas_bp',
    'learning_bp',
    'jargon_bp',
    'chat_bp',
    'bug_report_bp',
    'metrics_bp',
    'social_bp',
    'persona_reviews_bp',
    'intelligent_chat_bp',
    'get_blueprints',
    'register_blueprints'
]

if _has_monitoring:
    __all__.append('monitoring_bp')
