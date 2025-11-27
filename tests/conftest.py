"""
Common test fixtures and utilities

This module provides reusable test fixtures for WebUI testing:
- Mock ServiceContainer
- Mock managers (persona, database, etc.)
- Test data factories
- Async test helpers
"""
import pytest
import asyncio
from typing import Dict, Any, Optional
from unittest.mock import Mock, AsyncMock, MagicMock
from datetime import datetime
import time


# ============================================================================
# Async Test Utilities
# ============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# Mock ServiceContainer
# ============================================================================

@pytest.fixture
def mock_plugin_config():
    """Mock plugin configuration"""
    config = Mock()
    config.enabled = True
    config.llm_provider = "openai"
    config.model_name = "gpt-4"
    config.temperature = 0.7
    config.max_tokens = 2000
    config.learning_enabled = True
    config.auto_learning = True
    config.learning_interval = 3600
    config.min_confidence = 0.6
    config.bug_report_enabled = True
    return config


@pytest.fixture
def mock_persona_manager():
    """Mock PersonaManager"""
    manager = AsyncMock()

    # Default persona
    default_persona = {
        'persona_id': 'default',
        'name': 'Default Persona',
        'prompt': 'You are a helpful assistant.',
        'version': '1.0',
        'created_at': time.time()
    }

    manager.get_default_persona_v3 = AsyncMock(return_value=default_persona)
    manager.get_persona = AsyncMock(return_value=default_persona)
    manager.get_all_personas = AsyncMock(return_value=[default_persona])
    manager.create_persona = AsyncMock(return_value=True)
    manager.update_persona = AsyncMock(return_value=True)
    manager.delete_persona = AsyncMock(return_value=True)
    manager.export_persona = AsyncMock(return_value={'persona_id': 'default', 'data': 'test'})
    manager.import_persona = AsyncMock(return_value=True)

    return manager


@pytest.fixture
def mock_database_manager():
    """Mock DatabaseManager"""
    manager = AsyncMock()

    # Style learning methods
    manager.get_pending_style_reviews = AsyncMock(return_value=[])
    manager.update_style_review_status = AsyncMock(return_value=True)
    manager.get_style_learning_results = AsyncMock(return_value={
        'total': 0,
        'approved': 0,
        'rejected': 0,
        'pending': 0
    })

    # Persona learning methods
    manager.get_pending_persona_learning_reviews = AsyncMock(return_value=[])
    manager.update_persona_learning_review_status = AsyncMock(return_value=True)
    manager.get_persona_learning_review_by_id = AsyncMock(return_value=None)
    manager.delete_persona_learning_review_by_id = AsyncMock(return_value=True)
    manager.get_reviewed_persona_learning_updates = AsyncMock(return_value=[])

    # Jargon methods
    manager.get_jargon_stats = AsyncMock(return_value={
        'total': 10,
        'global': 5,
        'group_specific': 5
    })
    manager.get_jargon_list = AsyncMock(return_value=([], 0))
    manager.search_jargon = AsyncMock(return_value=[])
    manager.delete_jargon = AsyncMock(return_value=True)

    # Chat history methods
    manager.get_chat_history = AsyncMock(return_value=[])
    manager.get_chat_message_detail = AsyncMock(return_value=None)
    manager.delete_chat_message = AsyncMock(return_value=True)

    # Metrics methods
    manager.get_diversity_metrics = AsyncMock(return_value={
        'vocabulary_diversity': 0.5,
        'topic_diversity': 0.6,
        'style_diversity': 0.7,
        'total_score': 0.6
    })
    manager.get_affection_metrics = AsyncMock(return_value={
        'average_affection': 50,
        'total_users': 10,
        'high_affection_count': 3,
        'low_affection_count': 2,
        'distribution': []
    })

    return manager


@pytest.fixture
def mock_persona_updater():
    """Mock PersonaUpdater"""
    updater = AsyncMock()

    updater.get_pending_persona_updates = AsyncMock(return_value=[])
    updater.review_persona_update = AsyncMock(return_value=True)
    updater.revert_persona_update_review = AsyncMock(return_value=True)
    updater.delete_persona_update_review = AsyncMock(return_value=True)
    updater.get_reviewed_persona_updates = AsyncMock(return_value=[])
    updater.update_persona_with_style = AsyncMock(return_value=True)
    updater.record_persona_update_for_review = AsyncMock(return_value=1)

    return updater


@pytest.fixture
def mock_factory_manager():
    """Mock FactoryManager"""
    factory = Mock()

    # Social relation manager
    social_manager = AsyncMock()
    social_manager.get_social_relations = AsyncMock(return_value={
        'relations': [],
        'members': [],
        'metadata': {}
    })
    social_manager.get_available_groups = AsyncMock(return_value=[])
    social_manager.analyze_social_relations = AsyncMock(return_value=True)
    social_manager.clear_social_relations = AsyncMock(return_value=True)
    social_manager.get_user_relations = AsyncMock(return_value={
        'relations': [],
        'profile': {}
    })

    factory.get_social_relation_manager = Mock(return_value=social_manager)

    return factory


@pytest.fixture
def mock_intelligence_metrics_service():
    """Mock IntelligenceMetricsService"""
    service = AsyncMock()

    service.calculate_metrics = AsyncMock(return_value={
        'overall_score': 75,
        'dimensions': {
            'coherence': 80,
            'relevance': 75,
            'creativity': 70
        },
        'trends': []
    })

    return service


@pytest.fixture
def mock_webui_config():
    """Mock WebUIConfig"""
    config = Mock()
    config.host = '0.0.0.0'
    config.port = 7833
    config.static_dir = '/path/to/static'
    config.template_dir = '/path/to/templates'
    config.bug_report_enabled = True
    config.secret_key = 'test-secret-key'
    return config


@pytest.fixture
def mock_container(
    mock_plugin_config,
    mock_persona_manager,
    mock_database_manager,
    mock_persona_updater,
    mock_factory_manager,
    mock_intelligence_metrics_service,
    mock_webui_config
):
    """
    Mock ServiceContainer with all dependencies

    This is the main fixture that provides a complete mock container
    for testing services and blueprints.
    """
    container = Mock()
    container.plugin_config = mock_plugin_config
    container.persona_manager = mock_persona_manager
    container.database_manager = mock_database_manager
    container.persona_updater = mock_persona_updater
    container.factory_manager = mock_factory_manager
    container.intelligence_metrics_service = mock_intelligence_metrics_service
    container.webui_config = mock_webui_config

    return container


# ============================================================================
# Test Data Factories
# ============================================================================

@pytest.fixture
def sample_persona_data():
    """Sample persona data for testing"""
    return {
        'persona_id': 'test_persona',
        'name': 'Test Persona',
        'prompt': 'You are a test assistant.',
        'version': '1.0',
        'created_at': time.time(),
        'metadata': {
            'author': 'Test User',
            'description': 'A test persona'
        }
    }


@pytest.fixture
def sample_review_data():
    """Sample review data for testing"""
    return {
        'id': 1,
        'timestamp': time.time(),
        'group_id': 'test_group',
        'update_type': 'progressive_learning',
        'original_content': 'Original prompt',
        'new_content': 'Updated prompt with learning',
        'proposed_content': 'Updated prompt with learning',
        'reason': 'Progressive learning update',
        'status': 'pending',
        'reviewer_comment': None,
        'review_time': None,
        'confidence_score': 0.8,
        'metadata': {
            'features_content': 'Learning features',
            'llm_response': 'LLM analysis',
            'total_raw_messages': 100,
            'messages_analyzed': 50
        }
    }


@pytest.fixture
def sample_style_review_data():
    """Sample style learning review data"""
    return {
        'id': 1,
        'timestamp': time.time(),
        'group_id': 'test_group',
        'description': 'Few-shot style learning',
        'few_shots_content': 'Example 1\nExample 2\nExample 3',
        'status': 'pending',
        'learned_patterns': [
            {'pattern': 'greeting', 'frequency': 10},
            {'pattern': 'farewell', 'frequency': 8}
        ]
    }


@pytest.fixture
def sample_jargon_data():
    """Sample jargon data"""
    return {
        'id': 1,
        'original_text': 'lol',
        'replacement': 'laugh out loud',
        'group_id': 'test_group',
        'is_global': False,
        'usage_count': 10,
        'created_at': time.time()
    }


@pytest.fixture
def sample_chat_message():
    """Sample chat message"""
    return {
        'id': 1,
        'group_id': 'test_group',
        'user_id': 'user123',
        'message': 'Hello, this is a test message',
        'timestamp': time.time(),
        'role': 'user',
        'metadata': {}
    }


# ============================================================================
# Authentication Test Helpers
# ============================================================================

@pytest.fixture
def sample_password_config():
    """Sample password configuration"""
    return {
        'password_hash': '5f4dcc3b5aa765d61d8327deb882cf99',  # MD5 of 'password'
        'salt': 'test_salt',
        'algorithm': 'md5',
        'created_at': time.time(),
        'updated_at': time.time()
    }


@pytest.fixture
def sample_login_attempt():
    """Sample login attempt data"""
    return {
        'ip': '127.0.0.1',
        'attempts': 0,
        'locked_until': None
    }


# ============================================================================
# Async Helper Functions
# ============================================================================

@pytest.fixture
def async_return():
    """Helper to create async return values"""
    def _async_return(value):
        async def _inner():
            return value
        return _inner()
    return _async_return


@pytest.fixture
def async_raise():
    """Helper to create async exceptions"""
    def _async_raise(exception):
        async def _inner():
            raise exception
        return _inner()
    return _async_raise
