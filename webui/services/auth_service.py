"""
认证服务 - 处理用户认证相关业务逻辑
"""
import os
import json
import time
from typing import Tuple, Dict, Any, Optional
from astrbot.api import logger

from ...utils.security_utils import (
    PasswordHasher,
    login_attempt_tracker,
    verify_password_with_migration,
    SecurityValidator
)


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
        if self.plugin_config and hasattr(self.plugin_config, 'data_dir'):
            return os.path.join(self.plugin_config.data_dir, "password.json")
        else:
            # 后备路径
            plugin_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            return os.path.join(plugin_root, "config", "password.json")

    def load_password_config(self) -> Dict[str, Any]:
        """
        加载密码配置

        Returns:
            Dict: 密码配置
        """
        password_file = self.get_password_file_path()

        try:
            if os.path.exists(password_file):
                with open(password_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    logger.debug(f"已加载密码配置: {password_file}")
                    return config
            else:
                logger.warning(f"密码配置文件不存在: {password_file}，使用默认密码")
                return {"password": "self_learning_pwd", "must_change": True}
        except Exception as e:
            logger.error(f"加载密码配置失败: {e}", exc_info=True)
            return {"password": "self_learning_pwd", "must_change": True}

    def save_password_config(self, config: Dict[str, Any]) -> bool:
        """
        保存密码配置

        Args:
            config: 密码配置

        Returns:
            bool: 是否保存成功
        """
        password_file = self.get_password_file_path()

        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(password_file), exist_ok=True)

            with open(password_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)

            logger.info(f"密码配置已保存: {password_file}")
            self._password_config = config  # 更新缓存
            return True
        except Exception as e:
            logger.error(f"保存密码配置失败: {e}", exc_info=True)
            return False

    async def login(self, password: str, client_ip: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        处理用户登录

        Args:
            password: 用户输入的密码
            client_ip: 客户端IP地址

        Returns:
            Tuple[bool, str, Optional[Dict]]: (是否成功, 消息, 额外数据)
        """
        # 清理输入
        password = SecurityValidator.sanitize_input(password, max_length=128)

        if not password:
            return False, "密码不能为空", None

        # 检查IP是否被锁定
        is_locked, remaining_time = login_attempt_tracker.is_locked(client_ip)
        if is_locked:
            logger.warning(f"IP {client_ip} 被锁定，剩余 {remaining_time} 秒")
            return False, f"登录尝试次数过多，请在 {remaining_time} 秒后重试", {
                "locked": True,
                "remaining_time": remaining_time
            }

        # 加载密码配置
        password_config = self.load_password_config()

        # 验证密码（支持自动迁移）
        is_valid, updated_config = verify_password_with_migration(password, password_config)

        if is_valid:
            # 如果配置被更新（迁移），保存新配置
            if updated_config != password_config:
                self.save_password_config(updated_config)
                password_config = updated_config

            # 登录成功，清除失败记录
            login_attempt_tracker.record_attempt(client_ip, success=True)

            # 检查是否需要强制修改密码
            must_change = password_config.get("must_change", False)

            extra_data = {
                "must_change": must_change,
                "redirect": "/api/plugin_change_password" if must_change else "/api/index"
            }

            message = "Login successful, but password must be changed" if must_change else "Login successful"
            return True, message, extra_data

        # 登录失败，记录尝试
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
        # 清理输入
        old_password = SecurityValidator.sanitize_input(old_password, max_length=128)
        new_password = SecurityValidator.sanitize_input(new_password, max_length=128)

        if not old_password or not new_password:
            return False, "旧密码和新密码不能为空"

        # 加载密码配置
        password_config = self.load_password_config()

        # 验证旧密码
        is_valid, _ = verify_password_with_migration(old_password, password_config)
        if not is_valid:
            return False, "当前密码错误"

        # 检查新密码是否与旧密码相同
        if old_password == new_password:
            return False, "新密码不能与当前密码相同"

        # 验证新密码强度
        strength_result = SecurityValidator.validate_password_strength(new_password)
        if not strength_result['valid']:
            issues = "、".join(strength_result['issues']) if strength_result['issues'] else "密码强度不足"
            return False, issues

        # 生成新的哈希密码
        password_hash, salt = PasswordHasher.hash_password(new_password)

        # 更新配置
        new_config = {
            "password_hash": password_hash,
            "salt": salt,
            "must_change": False,
            "version": 2,
            "last_changed": time.time()
        }

        if self.save_password_config(new_config):
            logger.info("密码已更新为MD5哈希格式")
            return True, "密码修改成功"
        else:
            return False, "保存密码配置失败"

    def check_must_change_password(self) -> bool:
        """
        检查是否需要强制修改密码

        Returns:
            bool: 是否需要强制修改
        """
        password_config = self.load_password_config()
        return password_config.get("must_change", False)
