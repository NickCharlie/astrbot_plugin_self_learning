"""
认证服务 - 处理用户认证相关业务逻辑
"""
import os
import json
import time
from typing import Tuple, Dict, Any, Optional

try:
    from ...utils.logging_utils import get_astrbot_logger
    from ...utils.security_utils import (
        PasswordHasher,
        login_attempt_tracker,
        SecurityValidator,
        verify_password_with_migration,
    )
except ImportError:
    from utils.logging_utils import get_astrbot_logger
    from utils.security_utils import (
        PasswordHasher,
        login_attempt_tracker,
        SecurityValidator,
        verify_password_with_migration,
    )


logger = get_astrbot_logger("self_learning.webui.auth")
PASSWORDLESS_PASSWORD_CONFIG = {"must_change": False}
DEFAULT_WEBUI_PASSWORD = "self_learning_pwd"
DEFAULT_PASSWORD_CONFIG = {
    "password": DEFAULT_WEBUI_PASSWORD,
    "must_change": True,
}


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

    def is_password_enabled(self) -> bool:
        """Return whether WebUI password auth is explicitly enabled."""
        return getattr(self.plugin_config, "enable_webui_password", False) is True

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
        if isinstance(config_attr, dict) and (config_attr or not self.is_password_enabled()):
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
                if self.is_password_enabled():
                    logger.warning(
                        f"密码配置文件不存在: {password_file}，使用默认初始密码"
                    )
                    config = DEFAULT_PASSWORD_CONFIG.copy()
                else:
                    logger.debug(f"密码配置文件不存在: {password_file}，使用免密配置")
                    config = PASSWORDLESS_PASSWORD_CONFIG.copy()
                self._password_config = config
                return config
        except Exception as e:
            logger.error(f"加载密码配置失败: {e}", exc_info=True)
            config = (
                DEFAULT_PASSWORD_CONFIG.copy()
                if self.is_password_enabled()
                else PASSWORDLESS_PASSWORD_CONFIG.copy()
            )
            self._password_config = config
            return config

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
        处理用户登录。默认免密；启用 WebUI 密码后执行校验。

        Args:
            password: 用户输入的密码
            client_ip: 客户端IP地址

        Returns:
            Tuple[bool, str, Optional[Dict]]: (是否成功, 消息, 额外数据)
        """
        if not self.is_password_enabled():
            logger.debug(f"WebUI免密登录放行: client_ip={client_ip}")
            return True, "Passwordless WebUI access granted", {
                "must_change": False,
                "redirect": "/api/index",
            }

        password = SecurityValidator.sanitize_input(password, max_length=128)
        if not password:
            return False, "密码不能为空", None

        is_locked, remaining_time = login_attempt_tracker.is_locked(client_ip)
        if is_locked:
            logger.warning(f"IP {client_ip} 被锁定，剩余 {remaining_time} 秒")
            return False, f"登录尝试次数过多，请在 {remaining_time} 秒后重试", {
                "locked": True,
                "remaining_time": remaining_time,
            }

        password_config = self.load_password_config()
        is_valid, updated_config = verify_password_with_migration(
            password,
            password_config,
        )

        if is_valid:
            if updated_config != password_config:
                self.save_password_config(updated_config)
                password_config = updated_config

            login_attempt_tracker.record_attempt(client_ip, success=True)
            must_change = bool(password_config.get("must_change", False))
            redirect = "/api/plugin_change_password" if must_change else "/api/index"
            message = (
                "Login successful, but password must be changed"
                if must_change
                else "Login successful"
            )
            return True, message, {
                "must_change": must_change,
                "redirect": redirect,
            }

        login_attempt_tracker.record_attempt(client_ip, success=False)
        remaining_attempts = login_attempt_tracker.get_remaining_attempts(client_ip)
        logger.warning(f"IP {client_ip} 登录失败，剩余尝试次数: {remaining_attempts}")

        error_msg = "密码错误"
        if remaining_attempts <= 2:
            error_msg = f"密码错误，还剩 {remaining_attempts} 次尝试机会"

        return False, error_msg, {"remaining_attempts": remaining_attempts}

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
        if not self.is_password_enabled():
            return False, "WebUI 已启用免密访问，无需修改密码"

        old_password = SecurityValidator.sanitize_input(old_password, max_length=128)
        new_password = SecurityValidator.sanitize_input(new_password, max_length=128)

        if not old_password or not new_password:
            return False, "旧密码和新密码不能为空"

        password_config = self.load_password_config()
        is_valid, updated_config = verify_password_with_migration(
            old_password,
            password_config,
        )
        if not is_valid:
            return False, "当前密码错误"
        if updated_config != password_config:
            self.save_password_config(updated_config)

        if old_password == new_password:
            return False, "新密码不能与当前密码相同"

        strength_result = SecurityValidator.validate_password_strength(new_password)
        if not strength_result["valid"]:
            issues = "、".join(strength_result["issues"]) if strength_result["issues"] else "密码强度不足"
            return False, issues

        password_hash, salt = PasswordHasher.hash_password(new_password)
        new_config = {
            "password_hash": password_hash,
            "salt": salt,
            "must_change": False,
            "version": 2,
            "last_changed": time.time(),
        }

        if self.save_password_config(new_config):
            logger.info("WebUI 密码已更新")
            return True, "密码修改成功"
        return False, "保存密码配置失败"

    def check_must_change_password(self) -> bool:
        """
        检查是否需要强制修改密码

        Returns:
            bool: 是否需要强制修改
        """
        if not self.is_password_enabled():
            return False
        return bool(self.load_password_config().get("must_change", False))
