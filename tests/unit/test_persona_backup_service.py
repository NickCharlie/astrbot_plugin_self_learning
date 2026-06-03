"""Unit tests for WebUI persona backup management service."""
from unittest.mock import AsyncMock

import pytest

from webui.services.persona_backup_service import PersonaBackupService


@pytest.mark.asyncio
async def test_list_backups_returns_summaries(mock_container):
    mock_container.database_manager.get_persona_backups = AsyncMock(return_value=[
        {
            'id': 3,
            'group_id': 'default',
            'backup_name': 'before-update',
            'timestamp': 1710000000,
            'backup_reason': 'Auto backup before update',
            'original_persona': {'name': 'Default', 'prompt': 'hello'},
        }
    ])
    service = PersonaBackupService(mock_container)

    result = await service.list_backups(group_id='default', limit='50')

    assert result['available'] is True
    assert result['total'] == 1
    assert result['backups'][0]['id'] == 3
    assert result['backups'][0]['persona_name'] == 'Default'
    assert result['backups'][0]['prompt_length'] == 5
    mock_container.database_manager.get_persona_backups.assert_awaited_once_with(
        group_id='default',
        limit=50,
        include_content=True,
    )


@pytest.mark.asyncio
async def test_get_backup_uses_database_detail(mock_container):
    mock_container.database_manager.get_persona_backup = AsyncMock(return_value={
        'id': 7,
        'group_id': 'default',
        'backup_name': 'manual',
        'original_persona': {'name': 'Manual Persona', 'prompt': 'content'},
        'imitation_dialogues': [],
    })
    service = PersonaBackupService(mock_container)

    result = await service.get_backup(7, group_id='default')

    assert result['id'] == 7
    assert result['summary']['backup_name'] == 'manual'
    assert result['summary']['prompt_length'] == len('content')


@pytest.mark.asyncio
async def test_restore_backup_falls_back_to_persona_manager(mock_container):
    mock_container.persona_backup_manager = None
    mock_container.persona_web_manager = None
    mock_container.database_manager.get_persona_backup = AsyncMock(return_value={
        'id': 9,
        'group_id': 'default',
        'backup_name': 'restore-me',
        'original_persona': {
            'persona_id': 'default',
            'name': 'Default Persona',
            'prompt': 'restored prompt',
        },
        'imitation_dialogues': [],
    })
    mock_container.persona_manager.update_persona = AsyncMock(return_value=True)
    service = PersonaBackupService(mock_container)

    success, message = await service.restore_backup(9, group_id='default')

    assert success is True
    assert '恢复成功' in message
    mock_container.persona_manager.update_persona.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_backup_uses_database_manager(mock_container):
    mock_container.database_manager.delete_persona_backup = AsyncMock(return_value=True)
    service = PersonaBackupService(mock_container)

    success, message = await service.delete_backup(11, group_id='default')

    assert success is True
    assert '已删除' in message
    mock_container.database_manager.delete_persona_backup.assert_awaited_once_with(
        11,
        group_id='default',
    )
