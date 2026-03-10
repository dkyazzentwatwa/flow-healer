import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "trading_data.db"
_connection: Optional[sqlite3.Connection] = None


class DatabaseInitializationError(RuntimeError):
    """Raised when the application database cannot be initialized."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id TEXT PRIMARY KEY,
    timestamp INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    amount REAL NOT NULL,
    price REAL NOT NULL,
    fee REAL DEFAULT 0,
    fee_currency TEXT,
    status TEXT DEFAULT 'closed',
    paper BOOLEAN DEFAULT 0,
    strategy TEXT,
    notes TEXT,
    stop_price REAL,
    target_price REAL,
    is_trailing BOOLEAN DEFAULT 0,
    highest_price REAL,
    lowest_price REAL
);

CREATE TABLE IF NOT EXISTS positions (
    symbol TEXT PRIMARY KEY,
    amount REAL NOT NULL,
    avg_entry_price REAL NOT NULL,
    total_cost REAL NOT NULL,
    side TEXT NOT NULL,
    opened_at INTEGER NOT NULL,
    last_updated INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    date TEXT PRIMARY KEY,
    total_value REAL NOT NULL,
    cash_balance REAL NOT NULL,
    unrealized_pnl REAL NOT NULL,
    realized_pnl_today REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS automation_rules (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    side TEXT NOT NULL,         -- "buy" or "sell"
    trigger_type TEXT DEFAULT 'signal', -- 'signal' or 'price'
    signal_type TEXT NOT NULL,  -- "STRONG_BUY", "BUY", "SELL", "STRONG_SELL"
    min_score REAL,             -- Optional: trigger if score > min_score
    amount REAL NOT NULL,       -- Amount to trade
    amount_type TEXT DEFAULT 'fixed', -- 'fixed' or 'percent'
    stop_loss_pct REAL,
    take_profit_pct REAL,
    trailing_stop_pct REAL,
    only_if_in_position BOOLEAN DEFAULT 1,
    reduce_only BOOLEAN DEFAULT 1,
    min_profit_pct REAL,
    break_even_after_pct REAL,
    max_hold_bars INTEGER,
    is_active BOOLEAN DEFAULT 1,
    last_triggered INTEGER DEFAULT 0,
    cooldown_minutes INTEGER DEFAULT 60,
    conditions TEXT
);

CREATE TABLE IF NOT EXISTS balances (
    timestamp INTEGER PRIMARY KEY,
    currency TEXT NOT NULL,
    total REAL NOT NULL,
    available REAL NOT NULL,
    locked REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_balances (
    currency TEXT PRIMARY KEY,
    total REAL NOT NULL,
    available REAL NOT NULL,
    locked REAL NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    rule_id TEXT,
    symbol TEXT,
    details TEXT
);

CREATE TABLE IF NOT EXISTS ohlcv_data (
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    PRIMARY KEY (symbol, timeframe, timestamp)
);

CREATE TABLE IF NOT EXISTS backtest_results (
    id TEXT PRIMARY KEY,
    timestamp INTEGER NOT NULL,
    rule_id TEXT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    initial_balance REAL NOT NULL,
    final_balance REAL NOT NULL,
    total_trades INTEGER NOT NULL,
    win_rate REAL NOT NULL,
    max_drawdown REAL NOT NULL,
    details TEXT -- JSON blob of trade list
);

CREATE TABLE IF NOT EXISTS risk_limits (
    id INTEGER PRIMARY KEY,
    max_daily_loss REAL NOT NULL,
    max_drawdown_pct REAL NOT NULL,
    max_position_size_pct REAL NOT NULL,
    max_exposure_pct REAL NOT NULL,
    stop_loss_pct REAL NOT NULL,
    take_profit_pct REAL NOT NULL,
    trailing_stop_pct REAL NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_snapshots_date ON portfolio_snapshots(date);
"""

def _get_columns(conn: sqlite3.Connection, table: str) -> set:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    if not rows:
        return set()
    if isinstance(rows[0], sqlite3.Row):
        return {row["name"] for row in rows}
    return {row[1] for row in rows}

def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict):
    existing = _get_columns(conn, table)
    for name, definition in columns.items():
        if name in existing:
            continue
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def _prepare_db_path(db_path: Optional[str]) -> str:
    path = db_path if db_path else str(DB_PATH)
    if path != ":memory:":
        Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    return path


def init_db(db_path: str = None):
    """Initialize database with schema"""
    global _connection
    close_db()
    path = db_path if db_path else str(DB_PATH)

    try:
        path = _prepare_db_path(db_path)
        connection = sqlite3.connect(path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.executescript(SCHEMA)
        _ensure_columns(
            connection,
            "trades",
            {
                "fee_currency": "TEXT",
                "strategy": "TEXT",
                "notes": "TEXT",
                "stop_price": "REAL",
                "target_price": "REAL",
                "is_trailing": "BOOLEAN DEFAULT 0",
                "highest_price": "REAL",
                "lowest_price": "REAL",
                "paper": "BOOLEAN DEFAULT 0",
            },
        )
        _ensure_columns(
            connection,
            "automation_rules",
            {
                "trigger_type": "TEXT DEFAULT 'signal'",
                "min_score": "REAL",
                "amount_type": "TEXT DEFAULT 'fixed'",
                "stop_loss_pct": "REAL",
                "take_profit_pct": "REAL",
                "trailing_stop_pct": "REAL",
                "only_if_in_position": "BOOLEAN DEFAULT 1",
                "reduce_only": "BOOLEAN DEFAULT 1",
                "min_profit_pct": "REAL",
                "break_even_after_pct": "REAL",
                "max_hold_bars": "INTEGER",
                "is_active": "BOOLEAN DEFAULT 1",
                "last_triggered": "INTEGER DEFAULT 0",
                "cooldown_minutes": "INTEGER DEFAULT 60",
                "conditions": "TEXT",
            },
        )
        connection.execute(
            "UPDATE automation_rules SET only_if_in_position = 1 WHERE only_if_in_position IS NULL"
        )
        connection.execute(
            "UPDATE automation_rules SET reduce_only = 1 WHERE reduce_only IS NULL"
        )
        connection.commit()
    except (OSError, sqlite3.Error) as exc:
        if "connection" in locals():
            connection.close()
        _connection = None
        raise DatabaseInitializationError(
            f"Failed to initialize database at '{path}': {exc}"
        ) from exc

    _connection = connection

def get_db_connection() -> sqlite3.Connection:
    """Get database connection"""
    if _connection is None:
        init_db()
    return _connection

def close_db():
    """Close database connection"""
    global _connection
    if _connection:
        _connection.close()
        _connection = None
