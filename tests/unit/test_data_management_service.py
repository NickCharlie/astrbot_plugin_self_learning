from types import SimpleNamespace
from unittest.mock import AsyncMock

from webui.services.data_management_service import DataManagementService


def test_clear_learning_file_artifacts_removes_file_backed_learning_data(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)

    data_dir = tmp_path / "plugin_data"
    data_dir.mkdir()

    removable_files = [
        "learning.log",
        "persona_updates.txt",
        "cross_group_memories.json",
        "group_interests.json",
        "knowledge_graph.json",
        "knowledge_entities.json",
        "learning_data_export_1700000000.json",
    ]
    retained_files = ["config.json", "password.json", ".secret_key", "messages.db"]
    removable_dirs = ["lightrag", "mem0_qdrant", "persona_backups", "persona_updates"]
    retained_dirs = ["files"]

    for name in removable_files + retained_files:
        (data_dir / name).write_text("{}", encoding="utf-8")
    for name in removable_dirs + retained_dirs:
        directory = data_dir / name
        directory.mkdir()
        (directory / "payload.txt").write_text("payload", encoding="utf-8")

    legacy_dir = tmp_path / "data" / "persona_updates"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "group_123_incremental_updates.txt").write_text(
        "+ style", encoding="utf-8"
    )
    (legacy_dir / "keep.txt").write_text("not learning export", encoding="utf-8")

    service = DataManagementService(
        SimpleNamespace(
            plugin_config=SimpleNamespace(data_dir=str(data_dir)),
            database_manager=AsyncMock(),
        )
    )

    deleted, errors = service._clear_learning_file_artifacts()

    assert errors == []
    assert deleted == len(removable_files) + len(removable_dirs) + 1
    for name in removable_files + removable_dirs:
        assert not (data_dir / name).exists()
    assert not (legacy_dir / "group_123_incremental_updates.txt").exists()
    for name in retained_files + retained_dirs:
        assert (data_dir / name).exists()
    assert (legacy_dir / "keep.txt").exists()


def test_clear_learning_file_artifacts_clears_legacy_persona_updates_without_config(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    legacy_dir = tmp_path / "data" / "persona_updates"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "group_abc_incremental_updates.txt").write_text(
        "+ style", encoding="utf-8"
    )

    service = DataManagementService(
        SimpleNamespace(
            plugin_config=SimpleNamespace(data_dir=""),
            database_manager=AsyncMock(),
        )
    )

    deleted, errors = service._clear_learning_file_artifacts()

    assert errors == []
    assert deleted == 1
    assert not legacy_dir.exists()
