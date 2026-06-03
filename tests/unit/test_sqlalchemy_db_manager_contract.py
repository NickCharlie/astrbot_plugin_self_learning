from inspect import signature
from pathlib import Path

from services.sqlalchemy_database_manager import SQLAlchemyDatabaseManager


SQLALCHEMY_DB_MANAGER_PATH = (
    Path(__file__).resolve().parents[2] / "services" / "sqlalchemy_database_manager.py"
)


def _read_source() -> str:
    return SQLALCHEMY_DB_MANAGER_PATH.read_text(encoding="utf-8")


def test_persona_review_orm_methods_exist():
    source = _read_source()

    required_defs = [
        "async def save_persona_update_record(",
        "async def update_persona_update_record_status(",
        "async def delete_persona_update_record(",
        "async def get_persona_update_record_by_id(",
    ]

    for method_def in required_defs:
        assert method_def in source, f"缺少 ORM 方法定义: {method_def}"


def test_reviewed_persona_updates_signature_matches_legacy_call_order():
    source = _read_source()

    expected_signature = (
        "async def get_reviewed_persona_update_records(\n"
        "        self,\n"
        "        limit: int = 50,\n"
        "        offset: int = 0,\n"
        "        status_filter: Optional[str] = None\n"
        "    ) -> List[Dict[str, Any]]:"
    )

    assert expected_signature in source, (
        "签名顺序必须兼容 legacy 调用: "
        "get_reviewed_persona_update_records(limit, offset, status_filter)"
    )


def test_persona_backup_management_signatures_match_legacy_call_order():
    expected_params_by_method = {
        "get_persona_backups": ("self", "group_id", "limit", "include_content"),
        "get_persona_backup": ("self", "backup_id", "group_id"),
        "restore_persona_backup": ("self", "group_id", "backup_id"),
        "delete_persona_backup": ("self", "backup_id", "group_id"),
    }

    for method_name, expected_params in expected_params_by_method.items():
        method = getattr(SQLAlchemyDatabaseManager, method_name, None)
        assert method is not None, f"缺少人格备份管理 ORM 方法定义: {method_name}"

        param_names = tuple(signature(method).parameters.keys())
        assert param_names[:len(expected_params)] == expected_params, (
            f"人格备份管理方法 `{method_name}` 的参数签名与 legacy 调用不兼容；"
            f"期望前 {len(expected_params)} 个参数为 {expected_params}，实际为 {param_names}"
        )
