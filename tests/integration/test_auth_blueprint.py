"""
Integration tests for Authentication Blueprint

Tests the auth blueprint routes with mock dependencies
"""
import pytest
from quart import Quart
from unittest.mock import Mock, AsyncMock, patch
from webui.blueprints.auth import auth_bp
from webui.dependencies import ServiceContainer


@pytest.fixture
async def app(mock_container):
    """Create test Quart application"""
    app = Quart(__name__)
    app.config['TESTING'] = True
    app.secret_key = 'test-secret-key'

    # Register blueprint
    app.register_blueprint(auth_bp)

    # Mock get_container to return our mock
    with patch('webui.blueprints.auth.get_container', return_value=mock_container):
        yield app


@pytest.fixture
async def client(app):
    """Create test client"""
    return app.test_client()


class TestAuthBlueprint:
    """Integration tests for auth blueprint"""

    @pytest.mark.asyncio
    async def test_login_get(self, client):
        """Test GET /api/login returns login page"""
        response = await client.get('/api/login')

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_login_post_success(self, client, mock_container):
        """Test POST /api/login with correct credentials"""
        with patch('webui.blueprints.auth.get_container', return_value=mock_container):
            with patch('webui.blueprints.auth.AuthService') as MockAuthService:
                # Mock successful login
                mock_service = MockAuthService.return_value
                mock_service.login = AsyncMock(return_value=(
                    True,
                    'Login successful',
                    {'must_change': False, 'redirect': '/api/index'}
                ))

                response = await client.post('/api/login', json={
                    'password': 'correct_password'
                })

                assert response.status_code == 200
                data = await response.get_json()
                assert data['message'] == 'Login successful'
                assert data['must_change'] is False

    @pytest.mark.asyncio
    async def test_login_post_incorrect(self, client, mock_container):
        """Test POST /api/login with incorrect credentials"""
        with patch('webui.blueprints.auth.get_container', return_value=mock_container):
            with patch('webui.blueprints.auth.AuthService') as MockAuthService:
                # Mock failed login
                mock_service = MockAuthService.return_value
                mock_service.login = AsyncMock(return_value=(
                    False,
                    'Incorrect password',
                    {'attempts_remaining': 4}
                ))

                response = await client.post('/api/login', json={
                    'password': 'wrong_password'
                })

                assert response.status_code == 401
                data = await response.get_json()
                assert 'error' in data

    @pytest.mark.asyncio
    async def test_login_post_locked(self, client, mock_container):
        """Test POST /api/login when IP is locked"""
        with patch('webui.blueprints.auth.get_container', return_value=mock_container):
            with patch('webui.blueprints.auth.AuthService') as MockAuthService:
                # Mock locked account
                mock_service = MockAuthService.return_value
                mock_service.login = AsyncMock(return_value=(
                    False,
                    'Account locked',
                    {'locked': True, 'remaining_time': 300}
                ))

                response = await client.post('/api/login', json={
                    'password': 'any_password'
                })

                assert response.status_code == 429
                data = await response.get_json()
                assert data.get('locked') is True
                assert data.get('remaining_time') == 300

    @pytest.mark.asyncio
    async def test_logout(self, client):
        """Test POST /api/logout"""
        # First login to create session
        async with client.session_transaction() as session:
            session['authenticated'] = True

        response = await client.post('/api/logout')

        assert response.status_code == 200
        data = await response.get_json()
        assert data.get('message') is not None

    @pytest.mark.asyncio
    async def test_change_password_success(self, client, mock_container):
        """Test POST /api/plugin_change_password with valid data"""
        # Setup authenticated session
        async with client.session_transaction() as session:
            session['authenticated'] = True

        with patch('webui.blueprints.auth.get_container', return_value=mock_container):
            with patch('webui.blueprints.auth.AuthService') as MockAuthService:
                mock_service = MockAuthService.return_value
                mock_service.change_password = AsyncMock(return_value=(
                    True,
                    'Password changed successfully'
                ))

                response = await client.post('/api/plugin_change_password', json={
                    'old_password': 'OldPass123!',
                    'new_password': 'NewPass456!'
                })

                assert response.status_code == 200
                data = await response.get_json()
                assert data.get('success') is True

    @pytest.mark.asyncio
    async def test_change_password_weak(self, client, mock_container):
        """Test POST /api/plugin_change_password with weak password"""
        async with client.session_transaction() as session:
            session['authenticated'] = True

        with patch('webui.blueprints.auth.get_container', return_value=mock_container):
            with patch('webui.blueprints.auth.AuthService') as MockAuthService:
                mock_service = MockAuthService.return_value
                mock_service.change_password = AsyncMock(return_value=(
                    False,
                    'Password too weak'
                ))

                response = await client.post('/api/plugin_change_password', json={
                    'old_password': 'OldPass123!',
                    'new_password': 'weak'
                })

                assert response.status_code == 400
                data = await response.get_json()
                assert 'weak' in data.get('error', '').lower()

    @pytest.mark.asyncio
    async def test_index_authenticated(self, client):
        """Test GET /api/index when authenticated"""
        async with client.session_transaction() as session:
            session['authenticated'] = True

        response = await client.get('/api/index')

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_index_not_authenticated(self, client):
        """Test GET /api/index redirects when not authenticated"""
        response = await client.get('/api/index')

        # Should redirect to login
        assert response.status_code in [302, 303, 307]


class TestAuthMiddleware:
    """Test authentication middleware"""

    @pytest.mark.asyncio
    async def test_require_auth_decorator_authenticated(self, client, mock_container):
        """Test @require_auth allows authenticated requests"""
        async with client.session_transaction() as session:
            session['authenticated'] = True

        with patch('webui.blueprints.auth.get_container', return_value=mock_container):
            # Try accessing a protected route
            response = await client.post('/api/logout')

            # Should not redirect, should process request
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_require_auth_decorator_not_authenticated(self, client):
        """Test @require_auth blocks unauthenticated requests"""
        # Don't set session

        # Try accessing a protected route (change password requires auth)
        response = await client.post('/api/plugin_change_password', json={
            'old_password': 'old',
            'new_password': 'new'
        })

        # Should redirect or return 401/403
        assert response.status_code in [401, 403, 302, 303, 307]
