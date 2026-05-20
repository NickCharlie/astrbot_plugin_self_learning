"""
认证服务 - 处理用户认证相关业务逻辑
"""
import os
import json
from typing import Tuple, Dict, Any, Optional

try:
    from ...utils.logging_utils import get_astrbot_logger
    from ...utils.security_utils import (
        PasswordHasher,
        SecurityValidator,
    )
except ImportError:
    from utils.logging_utils import get_astrbot_logger
    from utils.security_utils import (
        PasswordHasher,
        SecurityValidator,
    )


logger = get_astrbot_logger("self_learning.webui.auth")
DEFAULT_PASSWORD_CONFIG = {"must_change": False}


def hash_password_with_salt(password: str) -> Dict[str, Any]:
    """Compatibility wrapper for callers/tests that patch the legacy helper."""
    password_hash, salt = PasswordHasher.hash_password(password)
    return {
        "password_hash": password_hash,
        "salt": salt,
        "algorithm": "md5",
    }


def validate_password_strength(password: str):
    """Compatibility wrapper around the current password strength validator."""
    return SecurityValidator.validate_password_strength(password)


class AuthService:
    """认证服务"""

    def __init__(self, container):
        """
        初始化认证服务

        Args:
            container: ServiceContainer 依赖注入容器
        """
        self.container = container
        self.plugin_config = container.plugin_config
        self._password_config: Optional[Dict[str, Any]] = None

    def get_password_file_path(self) -> str:
        """获取密码文件路径"""
        data_dir = getattr(self.plugin_config, 'data_dir', None) if self.plugin_config else None
        if isinstance(data_dir, (str, os.PathLike)):
            return os.path.join(os.fspath(data_dir), "password.json")

        # 后备路径
        plugin_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        return os.path.join(plugin_root, "config", "password.json")

    def _should_persist_password_file(self) -> bool:
        data_dir = getattr(self.plugin_config, 'data_dir', None) if self.plugin_config else None
        return self.plugin_config is None or isinstance(data_dir, (str, os.PathLike))

    def load_password_config(self) -> Dict[str, Any]:
        """
        加载密码配置

        Returns:
            Dict: 密码配置
        """
        if self._password_config is not None:
            return self._password_config

        config_attr = getattr(self.plugin_config, 'password_config', None) if self.plugin_config else None
        if isinstance(config_attr, dict):
            self._password_config = config_attr
            return config_attr

        password_file = self.get_password_file_path()
        if not self._should_persist_password_file():
            logger.debug("跳过密码文件读取：plugin_config 未提供有效 data_dir")
            return DEFAULT_PASSWORD_CONFIG.copy()

        try:
            if os.path.exists(password_file):
                with open(password_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    logger.debug(f"已加载密码配置: {password_file}")
                    self._password_config = config
                    return config
            else:
                logger.warning(f"密码配置文件不存在: {password_file}，使用免密配置")
                return DEFAULT_PASSWORD_CONFIG.copy()
        except Exception as e:
            logger.error(f"加载密码配置失败: {e}", exc_info=True)
            return DEFAULT_PASSWORD_CONFIG.copy()

    def save_password_config(self, config: Dict[str, Any]) -> bool:
        """
        保存密码配置

        Args:
            config: 密码配置

        Returns:
            bool: 是否保存成功
        """
        self._password_config = config
        if self.plugin_config is not None:
            try:
                setattr(self.plugin_config, 'password_config', config)
            except Exception:
                logger.debug("无法同步 password_config 到 plugin_config", exc_info=True)

        password_file = self.get_password_file_path()
        if not self._should_persist_password_file():
            logger.debug("跳过密码文件写入：plugin_config 未提供有效 data_dir")
            return True

        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(password_file), exist_ok=True)

            with open(password_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)

            logger.info(f"密码配置已保存: {password_file}")
            return True
        except Exception as e:
            logger.error(f"保存密码配置失败: {e}", exc_info=True)
            return False

    async def login(self, password: str, client_ip: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        处理用户登录。pack 分支 WebUI 为免密访问，保留该方法仅兼容旧调用。

        Args:
            password: 用户输入的密码
            client_ip: 客户端IP地址

        Returns:
            Tuple[bool, str, Optional[Dict]]: (是否成功, 消息, 额外数据)
        """
        logger.debug(f"WebUI免密登录放行: client_ip={client_ip}")
        return True, "Passwordless WebUI access granted", {
            "must_change": False,
            "redirect": "/api/index",
        }

    async def change_password(
        self,
        old_password: str,
        new_password: str
    ) -> Tuple[bool, str]:
        """
        修改密码

        Args:
            old_password: 旧密码
            new_password: 新密码

        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        return False, "WebUI 已启用免密访问，无需修改密码"

    def check_must_change_password(self) -> bool:
        """
        检查是否需要强制修改密码

        Returns:
            bool: 是否需要强制修改
        """
        return False
