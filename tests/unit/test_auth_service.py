"""
Unit tests for AuthService

Tests the authentication service layer including:
- Login with MD5+salt verification
- Password change functionality
- IP lockout mechanism
- Password configuration loading/saving
"""
import pytest
import time
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from webui.services.auth_service import AuthService


class TestAuthService:
    """Test suite for AuthService"""

    def test_init(self, mock_container):
        """Test AuthService initialization"""
        service = AuthService(mock_container)

        assert service.container == mock_container
        assert service.plugin_config == mock_container.plugin_config
        assert service._password_config is None

    @pytest.mark.asyncio
    async def test_login_success_with_md5(self, mock_container, sample_password_config):
        """Test successful login with MD5 password"""
        service = AuthService(mock_container)

        # Mock load_password_config
        service.load_password_config = Mock(return_value=sample_password_config)

        # Mock verify_password_with_migration
        with patch('webui.services.auth_service.verify_password_with_migration') as mock_verify:
            mock_verify.return_value = (True, sample_password_config)

            success, message, extra_data = await service.login('password', '127.0.0.1')

            assert success is True
            assert 'success' in message.lower() or '成功' in message
            assert extra_data is not None

    @pytest.mark.asyncio
    async def test_login_empty_password(self, mock_container):
        """Test login with empty password"""
        service = AuthService(mock_container)

        success, message, extra_data = await service.login('', '127.0.0.1')

        assert success is False
        assert '密码' in message

    @pytest.mark.asyncio
    async def test_login_ip_lockout(self, mock_container):
        """Test login with IP lockout active"""
        service = AuthService(mock_container)

        # Mock login attempt tracker to return locked status
        with patch('webui.services.auth_service.login_attempt_tracker') as mock_tracker:
            mock_tracker.is_locked.return_value = (True, 300)  # Locked for 300 seconds

            success, message, extra_data = await service.login('password', '127.0.0.1')

            assert success is False
            assert '锁定' in message or 'locked' in message.lower()
            assert extra_data is not None
            assert extra_data.get('locked') is True
            assert extra_data.get('remaining_time') == 300

    @pytest.mark.asyncio
    async def test_login_incorrect_password(self, mock_container, sample_password_config):
        """Test login with incorrect password"""
        service = AuthService(mock_container)
        service.load_password_config = Mock(return_value=sample_password_config)

        with patch('webui.services.auth_service.verify_password_with_migration') as mock_verify:
            with patch('webui.services.auth_service.login_attempt_tracker') as mock_tracker:
                mock_tracker.is_locked.return_value = (False, 0)
                mock_verify.return_value = (False, sample_password_config)

                success, message, extra_data = await service.login('wrong_password', '192.168.1.1')

                assert success is False
                # Should record failed attempt
                mock_tracker.record_attempt.assert_called_once_with('192.168.1.1', success=False)

    @pytest.mark.asyncio
    async def test_change_password_success(self, mock_container, sample_password_config):
        """Test successful password change"""
        service = AuthService(mock_container)
        service.load_password_config = Mock(return_value=sample_password_config)
        service.save_password_config = Mock()

        with patch('webui.services.auth_service.verify_password_with_migration') as mock_verify:
            with patch('webui.services.auth_service.hash_password_with_salt') as mock_hash:
                mock_verify.return_value = (True, sample_password_config)
                mock_hash.return_value = {
                    'password_hash': 'new_hash',
                    'salt': 'new_salt',
                    'algorithm': 'md5'
                }

                success, message = await service.change_password('old_password', 'NewPassword123!')

                assert success is True
                assert '成功' in message or 'success' in message.lower()
                service.save_password_config.assert_called_once()

    @pytest.mark.asyncio
    async def test_change_password_weak(self, mock_container):
        """Test password change with weak password"""
        service = AuthService(mock_container)

        with patch('webui.services.auth_service.validate_password_strength') as mock_validate:
            mock_validate.return_value = (False, 'Password is too weak')

            success, message = await service.change_password('old_password', 'weak')

            assert success is False
            assert 'weak' in message.lower()

    @pytest.mark.asyncio
    async def test_change_password_incorrect_old(self, mock_container, sample_password_config):
        """Test password change with incorrect old password"""
        service = AuthService(mock_container)
        service.load_password_config = Mock(return_value=sample_password_config)

        with patch('webui.services.auth_service.verify_password_with_migration') as mock_verify:
            with patch('webui.services.auth_service.validate_password_strength') as mock_validate:
                mock_validate.return_value = (True, 'Password is strong')
                mock_verify.return_value = (False, sample_password_config)

                success, message = await service.change_password('wrong_old', 'NewPassword123!')

                assert success is False
                assert '原密码' in message or 'incorrect' in message.lower()

    def test_load_password_config_success(self, mock_container):
        """Test loading password configuration"""
        service = AuthService(mock_container)

        mock_config_data = {
            'password_hash': 'test_hash',
            'salt': 'test_salt',
            'algorithm': 'md5'
        }

        # Mock config attribute access
        mock_container.plugin_config.password_config = mock_config_data

        config = service.load_password_config()

        assert config == mock_config_data
        assert service._password_config == mock_config_data

    def test_load_password_config_cached(self, mock_container):
        """Test loading password configuration from cache"""
        service = AuthService(mock_container)
        cached_config = {'password_hash': 'cached'}

        service._password_config = cached_config

        config = service.load_password_config()

        assert config == cached_config

    def test_save_password_config(self, mock_container):
        """Test saving password configuration"""
        service = AuthService(mock_container)

        new_config = {
            'password_hash': 'new_hash',
            'salt': 'new_salt'
        }

        service.save_password_config(new_config)

        assert service._password_config == new_config
        assert mock_container.plugin_config.password_config == new_config


@pytest.mark.asyncio
class TestAuthServiceIntegration:
    """Integration tests for AuthService with real password operations"""

    async def test_full_login_flow(self, mock_container):
        """Test complete login flow with password verification"""
        service = AuthService(mock_container)

        # Setup initial password config (plaintext migration scenario)
        initial_config = {
            'password': 'testpassword',  # Plaintext
            'algorithm': None
        }

        service.load_password_config = Mock(return_value=initial_config)
        service.save_password_config = Mock()

        with patch('webui.services.auth_service.verify_password_with_migration') as mock_verify:
            with patch('webui.services.auth_service.login_attempt_tracker') as mock_tracker:
                # Simulate successful verification with migration
                mock_tracker.is_locked.return_value = (False, 0)
                mock_verify.return_value = (True, {
                    'password_hash': 'migrated_hash',
                    'salt': 'new_salt',
                    'algorithm': 'md5'
                })

                success, message, extra_data = await service.login('testpassword', '127.0.0.1')

                assert success is True
                # Config should be saved due to migration
                service.save_password_config.assert_called_once()
                mock_tracker.record_attempt.assert_called_with('127.0.0.1', success=True)
