from scripts.validate_database_access import validate


def test_production_runtime_has_no_direct_sqlite_bypass() -> None:
    result = validate()

    assert result["status"] == "PASS", result
    assert result["unauthorized_direct_sqlite_access"] == []
    assert result["duplicate_db_factories"] == []
