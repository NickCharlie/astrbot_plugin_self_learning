from pathlib import Path


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
