import pytest
from api.database import init_db, get_db_connection

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

    conn.close()
