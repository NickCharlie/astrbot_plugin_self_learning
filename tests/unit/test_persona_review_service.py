"""
Unit tests for PersonaReviewService

Tests the persona review service including:
- Three-source integration (traditional, persona learning, style learning)
- Review approval/rejection
- Batch operations
"""
import pytest
from unittest.mock import Mock, AsyncMock
from webui.services.persona_review_service import PersonaReviewService


class TestPersonaReviewService:
    """Test suite for PersonaReviewService"""

    def test_init(self, mock_container):
        """Test PersonaReviewService initialization"""
        service = PersonaReviewService(mock_container)

        assert service.container == mock_container
        assert service.persona_updater == mock_container.persona_updater
        assert service.database_manager == mock_container.database_manager
        assert service.persona_manager == mock_container.persona_manager

    @pytest.mark.asyncio
    async def test_get_pending_persona_updates_traditional(self, mock_container, sample_review_data):
        """Test getting traditional persona updates"""
        service = PersonaReviewService(mock_container)

        # Mock traditional updates
        mock_record = Mock()
        mock_record.id = 1
        mock_record.timestamp = sample_review_data['timestamp']
        mock_record.group_id = 'test_group'
        mock_record.update_type = 'prompt_update'
        mock_record.original_content = 'Original'
        mock_record.new_content = 'Updated'
        mock_record.reason = 'Test reason'
        mock_record.status = 'pending'
        mock_record.reviewer_comment = None
        mock_record.review_time = None

        mock_container.persona_updater.get_pending_persona_updates.return_value = [mock_record]
        mock_container.database_manager.get_pending_persona_learning_reviews.return_value = []
        mock_container.database_manager.get_pending_style_reviews.return_value = []

        result = await service.get_pending_persona_updates()

        assert result['success'] is True
        assert result['total'] == 1
        assert len(result['updates']) == 1
        assert result['updates'][0]['review_source'] == 'traditional'

    @pytest.mark.asyncio
    async def test_get_pending_persona_updates_three_sources(
        self, mock_container, sample_review_data, sample_style_review_data
    ):
        """Test getting updates from all three sources"""
        service = PersonaReviewService(mock_container)

        # Mock traditional
        mock_traditional = Mock()
        mock_traditional.__dict__ = {'id': 1, 'timestamp': 1000, 'group_id': 'g1',
                                     'update_type': 'prompt_update', 'original_content': 'A',
                                     'new_content': 'B', 'reason': 'R', 'status': 'pending',
                                     'reviewer_comment': None, 'review_time': None}
        mock_container.persona_updater.get_pending_persona_updates.return_value = [mock_traditional]

        # Mock persona learning
        mock_container.database_manager.get_pending_persona_learning_reviews.return_value = [sample_review_data]

        # Mock style learning
        mock_container.database_manager.get_pending_style_reviews.return_value = [sample_style_review_data]
        mock_container.persona_manager.get_default_persona_v3.return_value = {
            'prompt': 'Original persona prompt'
        }

        result = await service.get_pending_persona_updates()

        assert result['success'] is True
        assert result['total'] >= 2  # At least persona learning + style learning
        sources = [u['review_source'] for u in result['updates']]
        assert 'traditional' in sources or 'persona_learning' in sources or 'style_learning' in sources

    @pytest.mark.asyncio
    async def test_review_persona_update_approve_traditional(self, mock_container):
        """Test approving traditional persona update"""
        service = PersonaReviewService(mock_container)

        mock_container.persona_updater.review_persona_update.return_value = True

        success, message = await service.review_persona_update('1', 'approve', 'Good update')

        assert success is True
        mock_container.persona_updater.review_persona_update.assert_called_once_with(1, 'approved', 'Good update')

    @pytest.mark.asyncio
    async def test_review_persona_update_approve_style_learning(self, mock_container, sample_style_review_data):
        """Test approving style learning review"""
        service = PersonaReviewService(mock_container)

        # Mock database methods
        mock_container.database_manager.get_pending_style_reviews.return_value = [sample_style_review_data]
        mock_container.database_manager.update_style_review_status.return_value = True
        mock_container.persona_updater.update_persona_with_style.return_value = True

        success, message = await service.review_persona_update('style_1', 'approve')

        assert success is True
        assert '批准' in message or 'approved' in message.lower()
        mock_container.database_manager.update_style_review_status.assert_called()

    @pytest.mark.asyncio
    async def test_review_persona_update_reject(self, mock_container):
        """Test rejecting persona update"""
        service = PersonaReviewService(mock_container)

        mock_container.persona_updater.review_persona_update.return_value = True

        success, message = await service.review_persona_update('1', 'reject', 'Not good')

        assert success is True
        mock_container.persona_updater.review_persona_update.assert_called_once_with(1, 'rejected', 'Not good')

    @pytest.mark.asyncio
    async def test_review_persona_update_invalid_action(self, mock_container):
        """Test invalid action"""
        service = PersonaReviewService(mock_container)

        success, message = await service.review_persona_update('1', 'invalid_action')

        assert success is False
        assert 'invalid' in message.lower() or 'must be' in message.lower()

    @pytest.mark.asyncio
    async def test_get_reviewed_persona_updates(self, mock_container):
        """Test getting reviewed updates"""
        service = PersonaReviewService(mock_container)

        traditional = [{'id': 1, 'status': 'approved', 'review_time': 1000}]
        persona_learning = [{'id': 2, 'status': 'approved', 'review_time': 2000}]
        style = [{'id': 3, 'status': 'rejected', 'review_time': 1500}]

        mock_container.persona_updater.get_reviewed_persona_updates.return_value = traditional
        mock_container.database_manager.get_reviewed_persona_learning_updates.return_value = persona_learning
        mock_container.database_manager.get_reviewed_style_learning_updates.return_value = style

        result = await service.get_reviewed_persona_updates(limit=50, offset=0)

        assert result['success'] is True
        assert result['total'] == 3
        # Should be sorted by review_time (descending)
        assert result['updates'][0]['review_time'] == 2000

    @pytest.mark.asyncio
    async def test_revert_persona_update_traditional(self, mock_container):
        """Test reverting traditional persona update"""
        service = PersonaReviewService(mock_container)

        mock_container.persona_updater.revert_persona_update_review.return_value = True

        success, message = await service.revert_persona_update('1', 'Mistake')

        assert success is True
        mock_container.persona_updater.revert_persona_update_review.assert_called_once_with(1, 'Mistake')

    @pytest.mark.asyncio
    async def test_revert_persona_update_style_learning(self, mock_container):
        """Test reverting style learning review"""
        service = PersonaReviewService(mock_container)

        mock_container.database_manager.update_style_review_status.return_value = True

        success, message = await service.revert_persona_update('style_1', 'Revert reason')

        assert success is True
        mock_container.database_manager.update_style_review_status.assert_called_once_with(1, 'pending')

    @pytest.mark.asyncio
    async def test_delete_persona_update_success(self, mock_container):
        """Test deleting persona update"""
        service = PersonaReviewService(mock_container)

        mock_container.database_manager.delete_persona_learning_review_by_id.return_value = True

        success, message = await service.delete_persona_update('persona_learning_1')

        assert success is True
        mock_container.database_manager.delete_persona_learning_review_by_id.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_delete_persona_update_not_found(self, mock_container):
        """Test deleting non-existent update"""
        service = PersonaReviewService(mock_container)

        mock_container.database_manager.delete_persona_learning_review_by_id.return_value = False
        mock_container.persona_updater.delete_persona_update_review.return_value = False

        success, message = await service.delete_persona_update('999')

        assert success is False

    @pytest.mark.asyncio
    async def test_batch_delete_persona_updates(self, mock_container):
        """Test batch deleting updates"""
        service = PersonaReviewService(mock_container)

        # Mock successful deletion for 2 out of 3
        mock_container.database_manager.delete_persona_learning_review_by_id.side_effect = [True, False, True]

        result = await service.batch_delete_persona_updates(['persona_learning_1', 'persona_learning_2', 'persona_learning_3'])

        assert result['success'] is True
        assert result['details']['success_count'] == 2
        assert result['details']['failed_count'] == 1

    @pytest.mark.asyncio
    async def test_batch_review_persona_updates_approve(self, mock_container):
        """Test batch approving updates"""
        service = PersonaReviewService(mock_container)

        # Mock successful review
        mock_container.persona_updater.review_persona_update.return_value = True

        result = await service.batch_review_persona_updates(['1', '2'], 'approve', 'Batch approve')

        assert result['success'] is True
        assert result['details']['success_count'] == 2
        assert result['details']['failed_count'] == 0

    @pytest.mark.asyncio
    async def test_batch_review_invalid_action(self, mock_container):
        """Test batch review with invalid action"""
        service = PersonaReviewService(mock_container)

        result = await service.batch_review_persona_updates(['1'], 'invalid', 'Comment')

        assert result['success'] is False
        assert 'approve' in result.get('error', '').lower() or 'reject' in result.get('error', '').lower()
