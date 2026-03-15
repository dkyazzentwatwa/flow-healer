from __future__ import annotations

import pytest
import os

from api.database import close_db, get_db_connection, init_db, bootstrap_db

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


def test_bootstrap_seeds_risk_limits():
    """Test that bootstrap creates default risk limits."""
    init_db(":memory:")
    bootstrap_db(":memory:")

    conn = get_db_connection()
    cursor = conn.cursor()

    # Check risk limits were seeded
    row = cursor.execute("SELECT * FROM risk_limits WHERE id = 1").fetchone()
    assert row is not None
    assert row["max_daily_loss"] == 500.0
    assert row["max_drawdown_pct"] == 20.0
    assert row["max_position_size_pct"] == 20.0
    assert row["max_exposure_pct"] == 80.0
    assert row["stop_loss_pct"] == 5.0
    assert row["take_profit_pct"] == 10.0
    assert row["trailing_stop_pct"] == 3.0

    close_db()


def test_bootstrap_seeds_paper_balances():
    """Test that bootstrap creates default paper balances."""
    init_db(":memory:")
    bootstrap_db(":memory:")

    conn = get_db_connection()
    cursor = conn.cursor()

    # Check paper balances were seeded
    rows = cursor.execute("SELECT * FROM paper_balances").fetchall()
    assert len(rows) > 0

    # Default balance should be USDT with 10000
    usdt_row = cursor.execute(
        "SELECT * FROM paper_balances WHERE currency = 'USDT'"
    ).fetchone()
    assert usdt_row is not None
    assert usdt_row["total"] == 10000.0
    assert usdt_row["available"] == 10000.0
    assert usdt_row["locked"] == 0.0

    close_db()


def test_bootstrap_is_idempotent():
    """Test that bootstrap can be called multiple times safely."""
    init_db(":memory:")
    bootstrap_db(":memory:")
    bootstrap_db(":memory:")  # Should not raise

    conn = get_db_connection()
    cursor = conn.cursor()

    # Verify data still exists and is intact
    risk_row = cursor.execute("SELECT COUNT(*) as cnt FROM risk_limits").fetchone()
    assert risk_row["cnt"] == 1

    balance_row = cursor.execute("SELECT COUNT(*) as cnt FROM paper_balances").fetchone()
    assert balance_row["cnt"] == 1

    close_db()


def test_bootstrap_respects_environment_variables(monkeypatch):
    """Test that bootstrap uses environment variables for paper balance."""
    monkeypatch.setenv("PAPER_BASE_CURRENCY", "BTC")
    monkeypatch.setenv("PAPER_START_BALANCE", "5.5")

    init_db(":memory:")
    bootstrap_db(":memory:")

    conn = get_db_connection()
    cursor = conn.cursor()

    # Check that custom currency and balance are used
    btc_row = cursor.execute(
        "SELECT * FROM paper_balances WHERE currency = 'BTC'"
    ).fetchone()
    assert btc_row is not None
    assert btc_row["total"] == 5.5
    assert btc_row["available"] == 5.5

    close_db()
