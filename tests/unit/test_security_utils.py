"""
Unit tests for security utilities module

Tests the security infrastructure:
- PasswordHasher: hash generation, salt handling, verification
- LoginAttemptTracker: attempt recording, lockout, rate limiting
- SecurityValidator: password strength, input sanitization, token validation
- Password migration: plaintext to hashed format
"""
import time
import pytest
from unittest.mock import patch

from utils.security_utils import (
    PasswordHasher,
    LoginAttemptTracker,
    SecurityValidator,
    migrate_password_to_hashed,
    verify_password_with_migration,
)


@pytest.mark.unit
@pytest.mark.security
class TestPasswordHasher:
    """Test PasswordHasher functionality."""

    def test_hash_password_returns_tuple(self):
        """Test hash_password returns (hash, salt) tuple."""
        hashed, salt = PasswordHasher.hash_password("test_password")

        assert isinstance(hashed, str)
        assert isinstance(salt, str)
        assert len(hashed) == 32  # MD5 hex digest length
        assert len(salt) == 32  # 16 bytes = 32 hex chars

    def test_hash_password_with_custom_salt(self):
        """Test hash_password with a provided salt."""
        hashed, salt = PasswordHasher.hash_password("test_password", salt="fixed_salt")

        assert salt == "fixed_salt"
        assert len(hashed) == 32

    def test_same_password_same_salt_same_hash(self):
        """Test deterministic hashing with same password and salt."""
        h1, _ = PasswordHasher.hash_password("password", salt="salt123")
        h2, _ = PasswordHasher.hash_password("password", salt="salt123")

        assert h1 == h2

    def test_same_password_different_salt_different_hash(self):
        """Test different salts produce different hashes."""
        h1, _ = PasswordHasher.hash_password("password", salt="salt_a")
        h2, _ = PasswordHasher.hash_password("password", salt="salt_b")

        assert h1 != h2

    def test_different_password_same_salt_different_hash(self):
        """Test different passwords produce different hashes."""
        h1, _ = PasswordHasher.hash_password("password1", salt="same_salt")
        h2, _ = PasswordHasher.hash_password("password2", salt="same_salt")

        assert h1 != h2

    def test_verify_correct_password(self):
        """Test password verification with correct password."""
        hashed, salt = PasswordHasher.hash_password("correct_password")

        result = PasswordHasher.verify_password("correct_password", hashed, salt)
        assert result is True

    def test_verify_incorrect_password(self):
        """Test password verification with incorrect password."""
        hashed, salt = PasswordHasher.hash_password("correct_password")

        result = PasswordHasher.verify_password("wrong_password", hashed, salt)
        assert result is False


@pytest.mark.unit
@pytest.mark.security
class TestLoginAttemptTracker:
    """Test LoginAttemptTracker functionality."""

    def test_initial_state_not_locked(self):
        """Test new IP is not locked."""
        tracker = LoginAttemptTracker(max_attempts=3)

        locked, remaining = tracker.is_locked("192.168.1.1")
        assert locked is False
        assert remaining == 0

    def test_full_remaining_attempts_for_new_ip(self):
        """Test new IP has full remaining attempts."""
        tracker = LoginAttemptTracker(max_attempts=5)

        remaining = tracker.get_remaining_attempts("192.168.1.1")
        assert remaining == 5

    def test_failed_attempt_decreases_remaining(self):
        """Test failed attempt decreases remaining count."""
        tracker = LoginAttemptTracker(max_attempts=5)

        tracker.record_attempt("192.168.1.1", success=False)

        remaining = tracker.get_remaining_attempts("192.168.1.1")
        assert remaining == 4

    def test_lockout_after_max_attempts(self):
        """Test IP is locked after max failed attempts."""
        tracker = LoginAttemptTracker(max_attempts=3, lockout_duration=300)

        for _ in range(3):
            tracker.record_attempt("192.168.1.1", success=False)

        locked, remaining_seconds = tracker.is_locked("192.168.1.1")
        assert locked is True
        assert remaining_seconds > 0

    def test_successful_login_clears_attempts(self):
        """Test successful login clears failed attempt history."""
        tracker = LoginAttemptTracker(max_attempts=5)

        tracker.record_attempt("192.168.1.1", success=False)
        tracker.record_attempt("192.168.1.1", success=False)
        tracker.record_attempt("192.168.1.1", success=True)

        remaining = tracker.get_remaining_attempts("192.168.1.1")
        assert remaining == 5

    def test_different_ips_independent(self):
        """Test tracking is independent per IP."""
        tracker = LoginAttemptTracker(max_attempts=3)

        tracker.record_attempt("192.168.1.1", success=False)
        tracker.record_attempt("192.168.1.1", success=False)

        remaining_ip1 = tracker.get_remaining_attempts("192.168.1.1")
        remaining_ip2 = tracker.get_remaining_attempts("192.168.1.2")

        assert remaining_ip1 == 1
        assert remaining_ip2 == 3

    def test_clear_ip_record(self):
        """Test clearing a specific IP record."""
        tracker = LoginAttemptTracker(max_attempts=3)

        tracker.record_attempt("192.168.1.1", success=False)
        tracker.clear_ip_record("192.168.1.1")

        remaining = tracker.get_remaining_attempts("192.168.1.1")
        assert remaining == 3

    def test_clear_all_records(self):
        """Test clearing all IP records."""
        tracker = LoginAttemptTracker(max_attempts=3)

        tracker.record_attempt("192.168.1.1", success=False)
        tracker.record_attempt("192.168.1.2", success=False)
        tracker.clear_all_records()

        assert tracker.get_remaining_attempts("192.168.1.1") == 3
        assert tracker.get_remaining_attempts("192.168.1.2") == 3


@pytest.mark.unit
@pytest.mark.security
class TestSecurityValidator:
    """Test SecurityValidator functionality."""

    def test_strong_password(self):
        """Test strong password validation."""
        result = SecurityValidator.validate_password_strength("Str0ng!P@ss")

        assert result['valid'] is True
        assert result['strength'] == 'strong'
        assert result['checks']['length'] is True
        assert result['checks']['lowercase'] is True
        assert result['checks']['uppercase'] is True
        assert result['checks']['numbers'] is True
        assert result['checks']['symbols'] is True

    def test_weak_password_short(self):
        """Test weak password: too short."""
        result = SecurityValidator.validate_password_strength("abc")

        assert result['valid'] is False
        assert result['strength'] == 'weak'
        assert result['checks']['length'] is False

    def test_medium_password(self):
        """Test medium strength password."""
        result = SecurityValidator.validate_password_strength("Password1")

        assert result['valid'] is True
        assert result['strength'] in ('medium', 'strong')

    def test_extra_long_password_bonus(self):
        """Test extra long password gets bonus score."""
        result = SecurityValidator.validate_password_strength("ThisIsAVeryLongPassword123!")

        assert result['score'] > 80

    def test_sanitize_input_strips_whitespace(self):
        """Test input sanitization strips whitespace."""
        result = SecurityValidator.sanitize_input("  hello world  ")
        assert result == "hello world"

    def test_sanitize_input_truncates(self):
        """Test input sanitization truncates to max_length."""
        result = SecurityValidator.sanitize_input("a" * 300, max_length=10)
        assert len(result) == 10

    def test_sanitize_empty_input(self):
        """Test sanitizing empty input."""
        assert SecurityValidator.sanitize_input("") == ""
        assert SecurityValidator.sanitize_input(None) == ""

    def test_valid_session_token(self):
        """Test valid session token validation."""
        token = "a" * 32  # 32-char hex string
        assert SecurityValidator.is_valid_session_token(token) is True

    def test_invalid_session_token_too_short(self):
        """Test invalid session token: too short."""
        assert SecurityValidator.is_valid_session_token("abc123") is False

    def test_invalid_session_token_non_hex(self):
        """Test invalid session token: non-hex characters."""
        assert SecurityValidator.is_valid_session_token("z" * 32) is False

    def test_empty_session_token(self):
        """Test empty session token is invalid."""
        assert SecurityValidator.is_valid_session_token("") is False
        assert SecurityValidator.is_valid_session_token(None) is False


@pytest.mark.unit
@pytest.mark.security
class TestPasswordMigration:
    """Test password migration from plaintext to hashed format."""

    def test_migrate_plaintext_password(self):
        """Test migrating plaintext password to hashed format."""
        old_config = {'password': 'my_password', 'must_change': False}

        new_config = migrate_password_to_hashed(old_config)

        assert 'password_hash' in new_config
        assert 'salt' in new_config
        assert new_config['version'] == 2
        assert new_config['migrated_from_plaintext'] is True

    def test_already_hashed_not_migrated(self):
        """Test already hashed config is not re-migrated."""
        hashed_config = {
            'password_hash': 'existing_hash',
            'salt': 'existing_salt',
            'version': 2,
        }

        result = migrate_password_to_hashed(hashed_config)

        assert result is hashed_config  # Same object

    def test_verify_with_old_format(self):
        """Test verification with old plaintext format triggers migration."""
        old_config = {'password': 'test_pass'}

        is_valid, new_config = verify_password_with_migration('test_pass', old_config)

        assert is_valid is True
        assert 'password_hash' in new_config

    def test_verify_with_old_format_wrong_password(self):
        """Test verification with wrong password in old format."""
        old_config = {'password': 'correct_pass'}

        is_valid, config = verify_password_with_migration('wrong_pass', old_config)

        assert is_valid is False

    def test_verify_with_new_format(self):
        """Test verification with new hashed format."""
        hashed, salt = PasswordHasher.hash_password("secure_pwd")
        new_config = {'password_hash': hashed, 'salt': salt}

        is_valid, config = verify_password_with_migration('secure_pwd', new_config)

        assert is_valid is True

    def test_verify_with_new_format_wrong_password(self):
        """Test verification with wrong password in new format."""
        hashed, salt = PasswordHasher.hash_password("correct_pwd")
        new_config = {'password_hash': hashed, 'salt': salt}

        is_valid, config = verify_password_with_migration('wrong_pwd', new_config)

        assert is_valid is False

    def test_verify_with_missing_hash_or_salt(self):
        """Test verification fails gracefully when hash or salt is missing."""
        config = {'password_hash': '', 'salt': ''}

        is_valid, _ = verify_password_with_migration('any_pwd', config)
        assert is_valid is False
