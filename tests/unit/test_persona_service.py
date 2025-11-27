"""
Unit tests for PersonaService

Tests persona management functionality including:
- CRUD operations
- Import/export
- Default persona handling
"""
import pytest
from unittest.mock import Mock, AsyncMock
from webui.services.persona_service import PersonaService


class TestPersonaService:
    """Test suite for PersonaService"""

    def test_init(self, mock_container):
        """Test PersonaService initialization"""
        service = PersonaService(mock_container)

        assert service.container == mock_container
        assert service.persona_manager == mock_container.persona_manager

    @pytest.mark.asyncio
    async def test_get_all_personas_success(self, mock_container):
        """Test getting all personas"""
        service = PersonaService(mock_container)

        personas_data = [
            {'persona_id': 'persona1', 'name': 'Persona 1'},
            {'persona_id': 'persona2', 'name': 'Persona 2'}
        ]

        mock_container.persona_manager.get_all_personas.return_value = personas_data

        result = await service.get_all_personas()

        assert len(result) == 2
        assert result[0]['persona_id'] == 'persona1'
        mock_container.persona_manager.get_all_personas.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_all_personas_no_manager(self, mock_container):
        """Test getting personas when manager is None"""
        mock_container.persona_manager = None
        service = PersonaService(mock_container)

        with pytest.raises(ValueError, match="PersonaManager未初始化"):
            await service.get_all_personas()

    @pytest.mark.asyncio
    async def test_get_persona_details_success(self, mock_container, sample_persona_data):
        """Test getting persona details"""
        service = PersonaService(mock_container)

        mock_container.persona_manager.get_persona.return_value = sample_persona_data

        result = await service.get_persona_details('test_persona')

        assert result['persona_id'] == 'test_persona'
        assert result['name'] == 'Test Persona'
        mock_container.persona_manager.get_persona.assert_called_once_with('test_persona')

    @pytest.mark.asyncio
    async def test_get_persona_details_not_found(self, mock_container):
        """Test getting non-existent persona"""
        service = PersonaService(mock_container)

        mock_container.persona_manager.get_persona.return_value = None

        with pytest.raises(ValueError, match="not found|未找到"):
            await service.get_persona_details('non_existent')

    @pytest.mark.asyncio
    async def test_create_persona_success(self, mock_container, sample_persona_data):
        """Test creating a new persona"""
        service = PersonaService(mock_container)

        mock_container.persona_manager.create_persona.return_value = True

        success, message, persona_id = await service.create_persona(sample_persona_data)

        assert success is True
        assert persona_id == 'test_persona'
        mock_container.persona_manager.create_persona.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_persona_missing_fields(self, mock_container):
        """Test creating persona with missing required fields"""
        service = PersonaService(mock_container)

        incomplete_data = {
            'persona_id': 'test'
            # Missing 'prompt' field
        }

        success, message, persona_id = await service.create_persona(incomplete_data)

        assert success is False
        assert '必需字段' in message or 'required' in message.lower()

    @pytest.mark.asyncio
    async def test_update_persona_success(self, mock_container, sample_persona_data):
        """Test updating an existing persona"""
        service = PersonaService(mock_container)

        mock_container.persona_manager.get_persona.return_value = sample_persona_data
        mock_container.persona_manager.update_persona.return_value = True

        updated_data = sample_persona_data.copy()
        updated_data['prompt'] = 'Updated prompt'

        success, message = await service.update_persona('test_persona', updated_data)

        assert success is True
        mock_container.persona_manager.update_persona.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_persona_not_found(self, mock_container):
        """Test updating non-existent persona"""
        service = PersonaService(mock_container)

        mock_container.persona_manager.get_persona.return_value = None

        success, message = await service.update_persona('non_existent', {})

        assert success is False
        assert 'not found' in message.lower() or '未找到' in message

    @pytest.mark.asyncio
    async def test_delete_persona_success(self, mock_container):
        """Test deleting a persona"""
        service = PersonaService(mock_container)

        mock_container.persona_manager.delete_persona.return_value = True

        success, message = await service.delete_persona('test_persona')

        assert success is True
        mock_container.persona_manager.delete_persona.assert_called_once_with('test_persona')

    @pytest.mark.asyncio
    async def test_get_default_persona_success(self, mock_container, sample_persona_data):
        """Test getting default persona"""
        service = PersonaService(mock_container)

        mock_container.persona_manager.get_default_persona_v3.return_value = sample_persona_data

        result = await service.get_default_persona('test_group')

        assert result['persona_id'] == 'test_persona'
        mock_container.persona_manager.get_default_persona_v3.assert_called_once_with('test_group')

    @pytest.mark.asyncio
    async def test_get_default_persona_fallback(self, mock_container):
        """Test getting default persona with fallback"""
        service = PersonaService(mock_container)

        # First call returns None, second call returns default
        mock_container.persona_manager.get_default_persona_v3.side_effect = [
            None,
            {'persona_id': 'default', 'prompt': 'Default'}
        ]

        result = await service.get_default_persona('test_group')

        assert result['persona_id'] == 'default'
        # Should be called twice (once for group, once for 'default')
        assert mock_container.persona_manager.get_default_persona_v3.call_count == 2

    @pytest.mark.asyncio
    async def test_export_persona_success(self, mock_container, sample_persona_data):
        """Test exporting a persona"""
        service = PersonaService(mock_container)

        mock_container.persona_manager.get_persona.return_value = sample_persona_data

        result = await service.export_persona('test_persona')

        assert result['persona_id'] == 'test_persona'
        assert 'prompt' in result
        assert 'metadata' in result

    @pytest.mark.asyncio
    async def test_export_persona_not_found(self, mock_container):
        """Test exporting non-existent persona"""
        service = PersonaService(mock_container)

        mock_container.persona_manager.get_persona.return_value = None

        with pytest.raises(ValueError, match="not found|未找到"):
            await service.export_persona('non_existent')

    @pytest.mark.asyncio
    async def test_import_persona_success(self, mock_container, sample_persona_data):
        """Test importing a persona"""
        service = PersonaService(mock_container)

        mock_container.persona_manager.get_persona.return_value = None
        mock_container.persona_manager.create_persona.return_value = True

        success, message, persona_id = await service.import_persona(sample_persona_data)

        assert success is True
        assert persona_id == 'test_persona'
        mock_container.persona_manager.create_persona.assert_called_once()

    @pytest.mark.asyncio
    async def test_import_persona_overwrite_protection(self, mock_container, sample_persona_data):
        """Test import with overwrite protection"""
        service = PersonaService(mock_container)

        # Persona already exists
        mock_container.persona_manager.get_persona.return_value = sample_persona_data

        import_data = sample_persona_data.copy()
        import_data['overwrite'] = False

        success, message, persona_id = await service.import_persona(import_data)

        assert success is False
        assert 'exists' in message.lower() or '存在' in message

    @pytest.mark.asyncio
    async def test_import_persona_with_overwrite(self, mock_container, sample_persona_data):
        """Test import with overwrite enabled"""
        service = PersonaService(mock_container)

        # Persona already exists
        mock_container.persona_manager.get_persona.return_value = sample_persona_data
        mock_container.persona_manager.update_persona.return_value = True

        import_data = sample_persona_data.copy()
        import_data['overwrite'] = True

        success, message, persona_id = await service.import_persona(import_data)

        assert success is True
        mock_container.persona_manager.update_persona.assert_called_once()

    @pytest.mark.asyncio
    async def test_import_persona_missing_fields(self, mock_container):
        """Test importing persona with missing required fields"""
        service = PersonaService(mock_container)

        incomplete_data = {
            'persona_id': 'test'
            # Missing 'prompt' and 'system_prompt'
        }

        success, message, persona_id = await service.import_persona(incomplete_data)

        assert success is False
        assert '必需字段' in message or 'required' in message.lower()
