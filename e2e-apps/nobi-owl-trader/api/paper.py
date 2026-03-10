"""
Paper trading account and balance management.

Stores balances in SQLite and provides helpers for paper trade execution.
"""

import os
import time
from dataclasses import dataclass
from typing import Dict, Tuple

from api.database import get_db_connection


@dataclass
class PaperBalance:
    currency: str
    total: float
    available: float
    locked: float
    updated_at: int


class PaperAccount:
    def __init__(self):
        self.conn = get_db_connection()
        self.base_currency = os.getenv("PAPER_BASE_CURRENCY", "USDT")
        self.start_balance = float(os.getenv("PAPER_START_BALANCE", "10000"))
        self._ensure_seed()

    def _ensure_seed(self) -> None:
        cursor = self.conn.cursor()
        row = cursor.execute("SELECT COUNT(*) as cnt FROM paper_balances").fetchone()
        if row and row["cnt"] == 0:
            now = int(time.time() * 1000)
            cursor.execute(
                """
                INSERT INTO paper_balances (currency, total, available, locked, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (self.base_currency, self.start_balance, self.start_balance, 0.0, now),
            )
            self.conn.commit()

    def _get_row(self, currency: str) -> PaperBalance:
        cursor = self.conn.cursor()
        row = cursor.execute(
            "SELECT * FROM paper_balances WHERE currency = ?", (currency,)
        ).fetchone()
        if row is None:
            now = int(time.time() * 1000)
            cursor.execute(
                """
                INSERT INTO paper_balances (currency, total, available, locked, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (currency, 0.0, 0.0, 0.0, now),
            )
            self.conn.commit()
            return PaperBalance(currency=currency, total=0.0, available=0.0, locked=0.0, updated_at=now)
        return PaperBalance(**dict(row))

    def get_balances(self) -> Dict[str, Dict[str, float]]:
        cursor = self.conn.cursor()
        rows = cursor.execute("SELECT * FROM paper_balances ORDER BY currency").fetchall()
        total = {}
        free = {}
        used = {}
        for row in rows:
            total[row["currency"]] = row["total"]
            free[row["currency"]] = row["available"]
            used[row["currency"]] = row["locked"]
        return {"total": total, "free": free, "used": used}

    def set_balance(self, currency: str, total: float, available: float = None, locked: float = None) -> None:
        if available is None:
            available = total
        if locked is None:
            locked = max(total - available, 0.0)
        if available < 0 or locked < 0:
            raise ValueError("Balances cannot be negative")
        now = int(time.time() * 1000)
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO paper_balances (currency, total, available, locked, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(currency) DO UPDATE SET
                total = excluded.total,
                available = excluded.available,
                locked = excluded.locked,
                updated_at = excluded.updated_at
            """,
            (currency, total, available, locked, now),
        )
        self.conn.commit()

    def reset(self, start_balance: float = None) -> None:
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM paper_balances")
        self.conn.commit()
        if start_balance is not None:
            self.start_balance = float(start_balance)
        self._ensure_seed()

    def update_balance(self, currency: str, delta_available: float, delta_locked: float = 0.0) -> PaperBalance:
        row = self._get_row(currency)
        available = row.available + delta_available
        locked = row.locked + delta_locked
        if available < -1e-8 or locked < -1e-8:
            raise ValueError("Insufficient balance")
        total = available + locked
        now = int(time.time() * 1000)
        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE paper_balances
            SET total = ?, available = ?, locked = ?, updated_at = ?
            WHERE currency = ?
            """,
            (total, available, locked, now, currency),
        )
        self.conn.commit()
        return PaperBalance(currency=currency, total=total, available=available, locked=locked, updated_at=now)

    def apply_trade(
        self, symbol: str, side: str, amount: float, price: float, fee: float
    ) -> Tuple[float, float]:
        base, quote = symbol.split("/")
        if amount <= 0:
            raise ValueError("Trade amount must be positive")

        if side.lower() == "buy":
            cost = amount * price + fee
            self.update_balance(quote, -cost)
            self.update_balance(base, amount)
            return amount, cost

        if side.lower() == "sell":
            proceeds = amount * price - fee
            self.update_balance(base, -amount)
            self.update_balance(quote, proceeds)
            return amount, proceeds

        raise ValueError("Unsupported trade side")
