import pytest

from api.database import close_db, get_db_connection, init_db

def test_database_initialization():
    """Test that database creates all required tables"""
    init_db(":memory:")  # Use in-memory DB for testing
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check tables exist
    tables = cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    table_names = [t[0] for t in tables]

    assert "trades" in table_names
    assert "positions" in table_names
    assert "portfolio_snapshots" in table_names
    assert "balances" in table_names

    close_db()


def test_database_initialization_reports_path_on_open_failure(tmp_path):
    """Test that database startup failures include the target path."""
    blocked_parent = tmp_path / "occupied"
    blocked_parent.write_text("not a directory")
    invalid_path = blocked_parent / "trading_data.db"

    with pytest.raises(RuntimeError, match=str(invalid_path)):
        init_db(str(invalid_path))

    close_db()
