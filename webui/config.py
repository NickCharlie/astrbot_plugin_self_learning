"""
WebUI 配置管理
"""
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class WebUIConfig:
    """WebUI 配置"""

    # 路径配置
    plugin_root_dir: str
    static_dir: str
    template_dir: str
    data_dir: str

    # Bug 报告配置
    bug_report_enabled: bool = True
    bug_cloud_url: str = ""
    bug_cloud_verify_code: str = ""
    bug_report_timeout_seconds: int = 30
    bug_report_max_images: int = 1
    bug_report_max_image_bytes: int = 8 * 1024 * 1024  # 8MB
    bug_report_max_log_bytes: int = 20000

    # 安全配置
    max_upload_size: int = 8 * 1024 * 1024  # 8MB

    @classmethod
    def from_plugin_config(cls, plugin_config) -> 'WebUIConfig':
        """从插件配置创建 WebUI 配置"""
        # 获取插件根目录
        plugin_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

        return cls(
            plugin_root_dir=plugin_root,
            static_dir=os.path.join(plugin_root, "web_res", "static"),
            template_dir=os.path.join(plugin_root, "web_res", "static", "html"),
            data_dir=plugin_config.data_dir if plugin_config else "./data",
            bug_cloud_url=os.getenv(
                "ASTRBOT_BUG_CLOUD_URL",
                "http://zentao-g-submit-rwpsiodjrb.cn-hangzhou.fcapp.run/zentao-bug-submit/submit-bug"
            ),
            bug_cloud_verify_code=os.getenv("ASTRBOT_BUG_CLOUD_VERIFY_CODE", "zentao123")
        )
