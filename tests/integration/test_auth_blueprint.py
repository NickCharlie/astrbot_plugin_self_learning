"""
Integration tests for Authentication Blueprint

Tests the auth blueprint routes with mock dependencies
"""
import pytest
from quart import Quart
from webui.blueprints.auth import auth_bp


@pytest.fixture
async def app(mock_container):
    """Create test Quart application"""
    app = Quart(__name__)
    app.config['TESTING'] = True
    app.secret_key = 'test-secret-key'

    # Register blueprint
    app.register_blueprint(auth_bp)

    yield app


@pytest.fixture
async def client(app):
    """Create test client"""
    return app.test_client()


class TestAuthBlueprint:
    """Integration tests for auth blueprint"""

    @pytest.mark.asyncio
    async def test_login_get(self, client):
        """GET /api/login is kept as a compatibility redirect."""
        response = await client.get('/api/login')

        assert response.status_code in [302, 303, 307]
        assert response.headers["Location"].endswith("/api/index")

    @pytest.mark.asyncio
    async def test_login_post_success(self, client, mock_container):
        """POST /api/login succeeds without credentials in pack branch."""
        response = await client.post('/api/login', json={})

        assert response.status_code == 200
        data = await response.get_json()
        assert data['message'] == 'Passwordless WebUI access granted'
        assert data['must_change'] is False
        assert data['redirect'] == '/api/index'

    @pytest.mark.asyncio
    async def test_login_post_incorrect(self, client, mock_container):
        """Password payloads are ignored in passwordless mode."""
        response = await client.post('/api/login', json={
            'password': 'wrong_password'
        })

        assert response.status_code == 200
        data = await response.get_json()
        assert data['redirect'] == '/api/index'

    @pytest.mark.asyncio
    async def test_login_post_locked(self, client, mock_container):
        """Passwordless mode does not apply login lockout."""
        response = await client.post('/api/login', json={
            'password': 'any_password'
        })

        assert response.status_code == 200
        data = await response.get_json()
        assert data['must_change'] is False

    @pytest.mark.asyncio
    async def test_logout(self, client):
        """Logout is a compatibility no-op in passwordless mode."""

        response = await client.post('/api/logout')

        assert response.status_code == 200
        data = await response.get_json()
        assert data.get('redirect') == '/api/index'

    @pytest.mark.asyncio
    async def test_change_password_success(self, client, mock_container):
        """Password change is disabled because there is no WebUI password."""
        response = await client.post('/api/plugin_change_password', json={
            'old_password': 'OldPass123!',
            'new_password': 'NewPass456!'
        })

        assert response.status_code == 410
        data = await response.get_json()
        assert data.get('success') is False
        assert data.get('redirect') == '/api/index'

    @pytest.mark.asyncio
    async def test_change_password_weak(self, client, mock_container):
        """Password strength is irrelevant when password changes are disabled."""
        response = await client.post('/api/plugin_change_password', json={
            'old_password': 'OldPass123!',
            'new_password': 'weak'
        })

        assert response.status_code == 410
        data = await response.get_json()
        assert '免密访问' in data.get('error', '')

    @pytest.mark.asyncio
    async def test_index_authenticated(self, client):
        """Test GET /api/index when authenticated"""
        async with client.session_transaction() as session:
            session['authenticated'] = True

        response = await client.get('/api/index')

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_index_not_authenticated(self, client):
        """GET /api/index opens directly without an authenticated session."""
        response = await client.get('/api/index')

        assert response.status_code == 200


class TestAuthMiddleware:
    """Test authentication middleware"""

    @pytest.mark.asyncio
    async def test_require_auth_decorator_authenticated(self, client, mock_container):
        """Test @require_auth allows authenticated requests"""
        async with client.session_transaction() as session:
            session['authenticated'] = True

        response = await client.post('/api/logout')

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_require_auth_decorator_not_authenticated(self, client):
        """@require_auth is pass-through in pack passwordless mode."""
        response = await client.post('/api/logout')

        assert response.status_code == 200
