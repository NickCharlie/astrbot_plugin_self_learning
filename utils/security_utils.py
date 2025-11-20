"""
安全工具模块 - 提供密码加密、验证等安全相关功能
"""
import hashlib
import time
import secrets
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

from astrbot.api import logger


class PasswordHasher:
    """密码哈希工具类 - 使用MD5+盐值"""

    @staticmethod
    def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
        """
        使用MD5+盐值对密码进行哈希

        Args:
            password: 原始密码
            salt: 可选的盐值，如果不提供则自动生成

        Returns:
            Tuple[str, str]: (哈希后的密码, 盐值)
        """
        if salt is None:
            salt = secrets.token_hex(16)

        # 使用MD5+盐值进行哈希
        salted_password = f"{salt}{password}"
        hashed = hashlib.md5(salted_password.encode('utf-8')).hexdigest()

        return hashed, salt

    @staticmethod
    def verify_password(password: str, hashed_password: str, salt: str) -> bool:
        """
        验证密码是否正确

        Args:
            password: 用户输入的明文密码
            hashed_password: 存储的哈希密码
            salt: 存储的盐值

        Returns:
            bool: 密码是否匹配
        """
        computed_hash, _ = PasswordHasher.hash_password(password, salt)
        return computed_hash == hashed_password


class LoginAttemptTracker:
    """登录尝试追踪器 - 用于防止暴力破解"""

    def __init__(
        self,
        max_attempts: int = 5,
        lockout_duration: int = 300,  # 5分钟
        attempt_window: int = 600  # 10分钟内的尝试计数
    ):
        """
        初始化登录尝试追踪器

        Args:
            max_attempts: 最大允许失败次数
            lockout_duration: 锁定时长（秒）
            attempt_window: 尝试计数窗口（秒）
        """
        self.max_attempts = max_attempts
        self.lockout_duration = lockout_duration
        self.attempt_window = attempt_window

        # 存储登录尝试记录: {ip_address: {'attempts': [], 'locked_until': timestamp}}
        self._attempts: Dict[str, Dict[str, Any]] = {}

    def record_attempt(self, ip_address: str, success: bool) -> None:
        """
        记录登录尝试

        Args:
            ip_address: 客户端IP地址
            success: 是否成功
        """
        current_time = time.time()

        if ip_address not in self._attempts:
            self._attempts[ip_address] = {
                'attempts': [],
                'locked_until': 0
            }

        record = self._attempts[ip_address]

        # 清理过期的尝试记录
        record['attempts'] = [
            t for t in record['attempts']
            if current_time - t < self.attempt_window
        ]

        if success:
            # 登录成功，清除该IP的尝试记录
            record['attempts'] = []
            record['locked_until'] = 0
            logger.info(f"登录成功，清除IP {ip_address} 的尝试记录")
        else:
            # 登录失败，记录尝试
            record['attempts'].append(current_time)

            # 检查是否需要锁定
            if len(record['attempts']) >= self.max_attempts:
                record['locked_until'] = current_time + self.lockout_duration
                logger.warning(
                    f"IP {ip_address} 登录失败次数过多 ({len(record['attempts'])}次)，"
                    f"已锁定至 {datetime.fromtimestamp(record['locked_until']).strftime('%Y-%m-%d %H:%M:%S')}"
                )

    def is_locked(self, ip_address: str) -> Tuple[bool, int]:
        """
        检查IP是否被锁定

        Args:
            ip_address: 客户端IP地址

        Returns:
            Tuple[bool, int]: (是否被锁定, 剩余锁定秒数)
        """
        if ip_address not in self._attempts:
            return False, 0

        record = self._attempts[ip_address]
        current_time = time.time()

        if record['locked_until'] > current_time:
            remaining = int(record['locked_until'] - current_time)
            return True, remaining

        return False, 0

    def get_remaining_attempts(self, ip_address: str) -> int:
        """
        获取剩余尝试次数

        Args:
            ip_address: 客户端IP地址

        Returns:
            int: 剩余尝试次数
        """
        if ip_address not in self._attempts:
            return self.max_attempts

        record = self._attempts[ip_address]
        current_time = time.time()

        # 清理过期记录
        valid_attempts = [
            t for t in record['attempts']
            if current_time - t < self.attempt_window
        ]

        return max(0, self.max_attempts - len(valid_attempts))

    def clear_ip_record(self, ip_address: str) -> None:
        """
        清除指定IP的记录

        Args:
            ip_address: 客户端IP地址
        """
        if ip_address in self._attempts:
            del self._attempts[ip_address]
            logger.info(f"已清除IP {ip_address} 的登录尝试记录")

    def clear_all_records(self) -> None:
        """清除所有记录"""
        self._attempts.clear()
        logger.info("已清除所有IP的登录尝试记录")


class SecurityValidator:
    """安全验证器 - 提供各种安全相关的验证功能"""

    @staticmethod
    def validate_password_strength(password: str) -> Dict[str, Any]:
        """
        验证密码强度

        Args:
            password: 待验证的密码

        Returns:
            Dict: 包含验证结果和详情
        """
        result = {
            'valid': True,
            'score': 0,
            'strength': 'weak',
            'issues': [],
            'checks': {
                'length': False,
                'lowercase': False,
                'uppercase': False,
                'numbers': False,
                'symbols': False
            }
        }

        # 长度检查
        if len(password) >= 8:
            result['checks']['length'] = True
            result['score'] += 20
        else:
            result['issues'].append('密码长度至少需要8个字符')

        # 小写字母
        if any(c.islower() for c in password):
            result['checks']['lowercase'] = True
            result['score'] += 20

        # 大写字母
        if any(c.isupper() for c in password):
            result['checks']['uppercase'] = True
            result['score'] += 20

        # 数字
        if any(c.isdigit() for c in password):
            result['checks']['numbers'] = True
            result['score'] += 20

        # 特殊符号
        if any(not c.isalnum() for c in password):
            result['checks']['symbols'] = True
            result['score'] += 20

        # 额外长度加分
        if len(password) >= 12:
            result['score'] += 10
        if len(password) >= 16:
            result['score'] += 10

        # 确定强度等级
        if result['score'] >= 80:
            result['strength'] = 'strong'
        elif result['score'] >= 50:
            result['strength'] = 'medium'
        else:
            result['strength'] = 'weak'

        # 基本有效性（至少8位）
        result['valid'] = result['checks']['length']

        return result

    @staticmethod
    def sanitize_input(input_str: str, max_length: int = 255) -> str:
        """
        清理用户输入，防止注入攻击

        Args:
            input_str: 用户输入
            max_length: 最大长度限制

        Returns:
            str: 清理后的字符串
        """
        if not input_str:
            return ""

        # 移除首尾空白
        cleaned = input_str.strip()

        # 限制长度
        if len(cleaned) > max_length:
            cleaned = cleaned[:max_length]

        return cleaned

    @staticmethod
    def is_valid_session_token(token: str) -> bool:
        """
        验证会话令牌格式

        Args:
            token: 会话令牌

        Returns:
            bool: 是否有效
        """
        if not token:
            return False

        # 会话令牌应该是有效的十六进制字符串
        try:
            int(token, 16)
            return len(token) >= 32
        except ValueError:
            return False


# 全局登录尝试追踪器实例
login_attempt_tracker = LoginAttemptTracker(
    max_attempts=5,
    lockout_duration=300,  # 5分钟锁定
    attempt_window=600  # 10分钟窗口
)


def migrate_password_to_hashed(password_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    将旧的明文密码迁移到MD5哈希格式

    Args:
        password_config: 原始密码配置

    Returns:
        Dict: 更新后的密码配置
    """
    # 检查是否已经是新格式
    if 'password_hash' in password_config and 'salt' in password_config:
        logger.debug("密码已是哈希格式，无需迁移")
        return password_config

    # 获取旧密码
    old_password = password_config.get('password', 'self_learning_pwd')

    # 生成MD5哈希（带盐值）
    password_hash, salt = PasswordHasher.hash_password(old_password)

    # 创建新格式配置
    new_config = {
        'password_hash': password_hash,
        'salt': salt,
        'must_change': password_config.get('must_change', True),
        'migrated_from_plaintext': True,
        'migration_time': time.time(),
        'version': 2  # 密码配置版本
    }

    logger.info("密码配置已从明文迁移到MD5哈希格式")

    return new_config


def verify_password_with_migration(
    password: str,
    password_config: Dict[str, Any]
) -> Tuple[bool, Dict[str, Any]]:
    """
    验证密码，同时处理从明文到哈希的迁移

    Args:
        password: 用户输入的明文密码
        password_config: 密码配置

    Returns:
        Tuple[bool, Dict]: (验证结果, 可能更新的配置)
    """
    # 如果是旧格式（明文存储）
    if 'password' in password_config and 'password_hash' not in password_config:
        stored_password = password_config.get('password', '')

        # 直接比较明文
        if password == stored_password:
            # 验证成功后迁移到新格式
            new_config = migrate_password_to_hashed(password_config)
            return True, new_config

        return False, password_config

    # 新格式验证：将用户输入的明文密码进行MD5+盐值哈希后对比
    password_hash = password_config.get('password_hash', '')
    salt = password_config.get('salt', '')

    if not password_hash or not salt:
        logger.error("密码配置格式错误：缺少password_hash或salt")
        return False, password_config

    # 对用户输入的明文密码进行哈希验证
    return PasswordHasher.verify_password(password, password_hash, salt), password_config


__all__ = [
    'PasswordHasher',
    'LoginAttemptTracker',
    'SecurityValidator',
    'login_attempt_tracker',
    'migrate_password_to_hashed',
    'verify_password_with_migration',
]
