from dataclasses import asdict, dataclass
from typing import Optional, List, Dict, Any, ClassVar
from datetime import datetime, timedelta
import json
from api.database import get_db_connection


class SerializableModel:
    _bool_fields: ClassVar[tuple[str, ...]] = ()

    @staticmethod
    def _coerce_bool(value: Any) -> bool:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "t", "yes", "y", "on"}:
                return True
            if normalized in {"0", "false", "f", "no", "n", "off", ""}:
                return False
        return bool(value)

    def __post_init__(self):
        for field_name in self._bool_fields:
            setattr(self, field_name, self._coerce_bool(getattr(self, field_name)))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


@dataclass
class Trade(SerializableModel):
    _bool_fields: ClassVar[tuple[str, ...]] = ("paper", "is_trailing")
    id: str
    timestamp: int
    symbol: str
    side: str  # "buy" or "sell"
    amount: float
    price: float
    fee: float = 0.0
    fee_currency: Optional[str] = None
    status: str = "closed"
    paper: bool = False
    strategy: Optional[str] = None
    notes: Optional[str] = None
    stop_price: Optional[float] = None
    target_price: Optional[float] = None
    is_trailing: bool = False
    highest_price: Optional[float] = None
    lowest_price: Optional[float] = None

@dataclass
class AutomationRule(SerializableModel):
    _bool_fields: ClassVar[tuple[str, ...]] = (
        "only_if_in_position",
        "reduce_only",
        "is_active",
    )
    id: str
    name: str
    symbol: str
    timeframe: str
    side: str
    signal_type: str
    amount: float
    trigger_type: str = "signal"
    min_score: Optional[float] = None
    amount_type: str = "fixed"
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    trailing_stop_pct: Optional[float] = None
    only_if_in_position: bool = True
    reduce_only: bool = True
    min_profit_pct: Optional[float] = None
    break_even_after_pct: Optional[float] = None
    max_hold_bars: Optional[int] = None
    is_active: bool = True
    last_triggered: int = 0
    cooldown_minutes: int = 60
    conditions: Optional[str] = None # JSON string of logic conditions

@dataclass
class PortfolioSnapshot(SerializableModel):
    date: str
    total_value: float
    cash_balance: float
    unrealized_pnl: float
    realized_pnl_today: float

@dataclass
class LogEntry(SerializableModel):
    id: Optional[int]
    timestamp: int
    level: str
    message: str
    rule_id: Optional[str] = None
    symbol: Optional[str] = None
    details: Optional[str] = None

class TradeRepository:
    def __init__(self):
        self.conn = get_db_connection()

    def create(self, trade: Trade) -> Trade:
        """Create a new trade"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO trades (
                id, timestamp, symbol, side, amount, price, fee,
                fee_currency, status, paper, strategy, notes,
                stop_price, target_price, is_trailing, highest_price, lowest_price
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trade.id, trade.timestamp, trade.symbol, trade.side,
            trade.amount, trade.price, trade.fee, trade.fee_currency,
            trade.status, trade.paper, trade.strategy, trade.notes,
            trade.stop_price, trade.target_price, trade.is_trailing,
            trade.highest_price, trade.lowest_price
        ))
        self.conn.commit()
        return trade

    def get_by_id(self, trade_id: str) -> Optional[Trade]:
        """Get trade by ID"""
        cursor = self.conn.cursor()
        row = cursor.execute(
            "SELECT * FROM trades WHERE id = ?", (trade_id,)
        ).fetchone()

        if row is None:
            return None

        return Trade(**dict(row))

    def get_all(self, limit: int = 100, offset: int = 0) -> List[Trade]:
        """Get all trades with pagination"""
        cursor = self.conn.cursor()
        rows = cursor.execute(
            "SELECT * FROM trades ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ).fetchall()

        return [Trade(**dict(row)) for row in rows]

    def get_by_symbol(self, symbol: str) -> List[Trade]:
        """Get all trades for a symbol"""
        cursor = self.conn.cursor()
        rows = cursor.execute(
            "SELECT * FROM trades WHERE symbol = ? ORDER BY timestamp DESC",
            (symbol,)
        ).fetchall()

        return [Trade(**dict(row)) for row in rows]

    def get_between(self, start_ts: int, end_ts: int, symbol: Optional[str] = None) -> List[Trade]:
        """Get trades between timestamps (inclusive)"""
        cursor = self.conn.cursor()
        if symbol:
            rows = cursor.execute(
                """
                SELECT * FROM trades
                WHERE symbol = ? AND timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp ASC
                """,
                (symbol, start_ts, end_ts),
            ).fetchall()
        else:
            rows = cursor.execute(
                """
                SELECT * FROM trades
                WHERE timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp ASC
                """,
                (start_ts, end_ts),
            ).fetchall()

        return [Trade(**dict(row)) for row in rows]

class AutomationRuleRepository:
    def __init__(self):
        self.conn = get_db_connection()

    def create(self, rule: AutomationRule) -> AutomationRule:
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO automation_rules (
                id, name, symbol, timeframe, side, trigger_type, signal_type, min_score,
                amount, amount_type, stop_loss_pct, take_profit_pct, trailing_stop_pct,
                only_if_in_position, reduce_only, min_profit_pct, break_even_after_pct,
                max_hold_bars, is_active, last_triggered, cooldown_minutes, conditions
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            rule.id, rule.name, rule.symbol, rule.timeframe, rule.side, rule.trigger_type, rule.signal_type,
            rule.min_score, rule.amount, rule.amount_type, rule.stop_loss_pct, rule.take_profit_pct,
            rule.trailing_stop_pct, rule.only_if_in_position, rule.reduce_only, rule.min_profit_pct,
            rule.break_even_after_pct, rule.max_hold_bars, rule.is_active, rule.last_triggered,
            rule.cooldown_minutes, rule.conditions
        ))
        self.conn.commit()
        return rule

    def get_all(self) -> List[AutomationRule]:
        cursor = self.conn.cursor()
        rows = cursor.execute("SELECT * FROM automation_rules").fetchall()
        return [AutomationRule(**dict(row)) for row in rows]

    def get_by_id(self, rule_id: str) -> Optional[AutomationRule]:
        cursor = self.conn.cursor()
        row = cursor.execute(
            "SELECT * FROM automation_rules WHERE id = ?",
            (rule_id,)
        ).fetchone()
        return AutomationRule(**dict(row)) if row else None

    def get_active(self) -> List[AutomationRule]:
        cursor = self.conn.cursor()
        rows = cursor.execute("SELECT * FROM automation_rules WHERE is_active = 1").fetchall()
        return [AutomationRule(**dict(row)) for row in rows]

    def update_last_triggered(self, rule_id: str, timestamp: int):
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE automation_rules SET last_triggered = ? WHERE id = ?",
            (timestamp, rule_id)
        )
        self.conn.commit()

    def delete(self, rule_id: str):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM automation_rules WHERE id = ?", (rule_id,))
        self.conn.commit()
    
    def toggle_active(self, rule_id: str, is_active: bool):
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE automation_rules SET is_active = ? WHERE id = ?", 
            (is_active, rule_id)
        )
        self.conn.commit()

    def update(self, rule_id: str, updates: Dict[str, Any]) -> Optional[AutomationRule]:
        if not updates:
            return self.get_by_id(rule_id)

        columns = []
        values = []
        for key, value in updates.items():
            columns.append(f"{key} = ?")
            values.append(value)

        values.append(rule_id)
        cursor = self.conn.cursor()
        cursor.execute(
            f"UPDATE automation_rules SET {', '.join(columns)} WHERE id = ?",
            tuple(values)
        )
        self.conn.commit()
        return self.get_by_id(rule_id)

class PortfolioSnapshotRepository:
    def __init__(self):
        self.conn = get_db_connection()

    def create(self, snapshot: PortfolioSnapshot) -> PortfolioSnapshot:
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO portfolio_snapshots (
                date, total_value, cash_balance, unrealized_pnl, realized_pnl_today
            ) VALUES (?, ?, ?, ?, ?)
        """, (
            snapshot.date, snapshot.total_value, snapshot.cash_balance,
            snapshot.unrealized_pnl, snapshot.realized_pnl_today
        ))
        self.conn.commit()
        return snapshot

    def get_history(self, limit: int = 30) -> List[PortfolioSnapshot]:
        cursor = self.conn.cursor()
        rows = cursor.execute(
            "SELECT * FROM portfolio_snapshots ORDER BY date DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [PortfolioSnapshot(**dict(row)) for row in rows]

class LogRepository:
    def __init__(self):
        self.conn = get_db_connection()

    def create(self, entry: LogEntry) -> LogEntry:
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO logs (
                timestamp, level, message, rule_id, symbol, details
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            entry.timestamp, entry.level, entry.message, entry.rule_id,
            entry.symbol, entry.details
        ))
        self.conn.commit()
        entry.id = cursor.lastrowid
        return entry

    def get_all(self, limit: int = 100, offset: int = 0, level: str = None) -> List[LogEntry]:
        cursor = self.conn.cursor()
        if level:
            rows = cursor.execute(
                "SELECT * FROM logs WHERE level = ? ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (level, limit, offset)
            ).fetchall()
        else:
            rows = cursor.execute(
                "SELECT * FROM logs ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (limit, offset)
            ).fetchall()
        
        return [LogEntry(**dict(row)) for row in rows]

    def clear(self, days: int = 7):
        """Clear logs older than X days (or all logs if days <= 0)."""
        cursor = self.conn.cursor()
        if days <= 0:
            cursor.execute("DELETE FROM logs")
        else:
            cutoff = int((datetime.utcnow() - timedelta(days=days)).timestamp() * 1000)
            cursor.execute("DELETE FROM logs WHERE timestamp < ?", (cutoff,))
        self.conn.commit()
