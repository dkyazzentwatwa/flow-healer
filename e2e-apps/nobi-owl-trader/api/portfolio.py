"""
Portfolio calculation engine with FIFO P&L matching.

This module provides the core portfolio management functionality including:
- Position tracking and management
- Realized P&L calculation using FIFO matching
- Unrealized P&L calculation
- Performance metrics (win rate, profit factor, Sharpe ratio, max drawdown)
"""

import os
import math
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from api.database import get_db_connection
from api.models import Trade, TradeRepository

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """Represents an open position in the portfolio"""
    symbol: str
    amount: float
    avg_entry_price: float
    total_cost: float
    side: str  # "long" or "short"
    opened_at: int
    last_updated: int


class PositionRepository:
    """Repository for managing position data in the database"""

    def __init__(self):
        self.conn = get_db_connection()

    def get_all(self) -> List[Position]:
        """Get all positions"""
        cursor = self.conn.cursor()
        rows = cursor.execute(
            "SELECT * FROM positions ORDER BY symbol"
        ).fetchall()

        return [Position(**dict(row)) for row in rows]

    def get_by_symbol(self, symbol: str) -> Optional[Position]:
        """Get position by symbol"""
        cursor = self.conn.cursor()
        row = cursor.execute(
            "SELECT * FROM positions WHERE symbol = ?", (symbol,)
        ).fetchone()

        if row is None:
            return None

        return Position(**dict(row))

    def upsert(self, position: Position) -> Position:
        """Insert or update a position"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO positions (
                symbol, amount, avg_entry_price, total_cost, side, opened_at, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                amount = excluded.amount,
                avg_entry_price = excluded.avg_entry_price,
                total_cost = excluded.total_cost,
                side = excluded.side,
                last_updated = excluded.last_updated
        """, (
            position.symbol, position.amount, position.avg_entry_price,
            position.total_cost, position.side, position.opened_at,
            position.last_updated
        ))
        self.conn.commit()
        return position

    def delete(self, symbol: str) -> None:
        """Delete a position"""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM positions WHERE symbol = ?", (symbol,))
        self.conn.commit()


class PortfolioEngine:
    """
    Core portfolio calculation engine.

    Handles all P&L calculations, position management, and performance metrics.
    Uses FIFO (First In, First Out) matching for realized P&L calculations.
    """

    def __init__(self):
        self.trade_repo = TradeRepository()
        self.position_repo = PositionRepository()

    def _match_trades_fifo(self, trades: List[Trade]) -> List[Dict[str, Any]]:
        """
        Match buys/sells using FIFO and return per-lot P&L and holding times.
        """
        if not trades:
            return []

        # Group by symbol
        symbols_trades: Dict[str, List[Trade]] = {}
        for trade in trades:
            symbols_trades.setdefault(trade.symbol, []).append(trade)

        matches: List[Dict[str, Any]] = []

        for _, sym_trades in symbols_trades.items():
            sorted_trades = sorted(sym_trades, key=lambda t: t.timestamp)

            buys = [t for t in sorted_trades if t.side == "buy"]
            sells = [t for t in sorted_trades if t.side == "sell"]

            if not buys or not sells:
                continue

            consumed_amounts: Dict[str, float] = {}

            for sell in sells:
                remaining_amount = sell.amount
                for buy in buys:
                    if remaining_amount <= 0:
                        break

                    already_consumed = consumed_amounts.get(buy.id, 0.0)
                    available = buy.amount - already_consumed
                    if available <= 1e-8:
                        continue

                    match_amount = min(remaining_amount, available)

                    pnl = (sell.price - buy.price) * match_amount
                    buy_fee_proportion = (buy.fee * match_amount / buy.amount) if buy.amount > 0 else 0
                    sell_fee_proportion = (sell.fee * match_amount / sell.amount) if sell.amount > 0 else 0
                    pnl -= (buy_fee_proportion + sell_fee_proportion)

                    hold_ms = max(sell.timestamp - buy.timestamp, 0)

                    matches.append({
                        "pnl": pnl,
                        "hold_ms": hold_ms,
                    })

                    consumed_amounts[buy.id] = already_consumed + match_amount
                    remaining_amount -= match_amount

        return matches

    def calculate_realized_pnl_from_trades(self, trades: List[Trade]) -> float:
        """Calculate realized P&L from a provided trade list using FIFO."""
        matches = self._match_trades_fifo(trades)
        return sum(m["pnl"] for m in matches)

    def calculate_realized_pnl(self, symbol: Optional[str] = None) -> float:
        """
        Calculate realized P&L from closed trades using FIFO matching.

        Args:
            symbol: Optional symbol to filter by. If None, calculates for all symbols.

        Returns:
            Total realized P&L in USD (or quote currency)

        The FIFO algorithm works as follows:
        1. Get all buy and sell trades for the symbol, sorted by timestamp
        2. For each sell, match it against the earliest unmatched buys
        3. Calculate P&L as (sell_price - buy_price) * amount - fees
        4. Track consumed amounts to handle partial matches
        """
        if symbol:
            trades = self.trade_repo.get_by_symbol(symbol)
        else:
            trades = self.trade_repo.get_all(limit=10000)

        return self.calculate_realized_pnl_from_trades(trades)

    def calculate_unrealized_pnl(self, current_prices: Dict[str, float]) -> Dict[str, float]:
        """
        Calculate unrealized P&L for all open positions.

        Args:
            current_prices: Dictionary mapping symbol to current price

        Returns:
            Dictionary mapping symbol to unrealized P&L

        Formula: (current_price - avg_entry_price) * amount
        For short positions: (avg_entry_price - current_price) * amount
        """
        positions = self.position_repo.get_all()
        unrealized_pnl = {}

        for position in positions:
            if position.symbol not in current_prices:
                unrealized_pnl[position.symbol] = 0.0
                continue

            current_price = current_prices[position.symbol]

            if position.side == "long":
                pnl = (current_price - position.avg_entry_price) * position.amount
            else:  # short
                pnl = (position.avg_entry_price - current_price) * position.amount

            unrealized_pnl[position.symbol] = pnl

        return unrealized_pnl

    def get_portfolio_value(self, cash_balance: float, current_prices: Dict[str, float]) -> float:
        """
        Calculate total portfolio value.

        Args:
            cash_balance: Current cash balance in USD (or quote currency)
            current_prices: Dictionary mapping symbol to current price

        Returns:
            Total portfolio value = cash + sum of position values
        """
        positions = self.position_repo.get_all()
        position_value = 0.0

        for position in positions:
            if position.symbol not in current_prices:
                position_value += position.total_cost
                continue

            current_price = current_prices[position.symbol]
            if position.side == "long":
                position_value += current_price * position.amount
            else:
                unrealized_pnl = (position.avg_entry_price - current_price) * position.amount
                position_value += (position.avg_entry_price * position.amount) + unrealized_pnl

        return cash_balance + position_value

    def calculate_performance_metrics(self) -> Dict[str, Any]:
        """
        Calculate comprehensive performance metrics.

        Returns:
            Dictionary containing:
            - total_trades: Total number of completed round trips
            - winning_trades: Number of profitable trades
            - losing_trades: Number of losing trades
            - win_rate: Percentage of winning trades
            - total_profit: Sum of all profits
            - total_loss: Sum of all losses (absolute value)
            - profit_factor: Ratio of total profit to total loss
            - avg_win: Average profit per winning trade
            - avg_loss: Average loss per losing trade
            - sharpe_ratio: Risk-adjusted return metric (simplified)
            - max_drawdown: Largest peak-to-trough decline
        """
        trades = self.trade_repo.get_all(limit=10000)

        if not trades:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "total_profit": 0.0,
                "total_loss": 0.0,
                "profit_factor": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0,
                "max_drawdown_percent": 0.0,
                "total_return": 0.0,
                "total_return_percent": 0.0,
                "day_return": 0.0,
                "day_return_percent": 0.0,
                "week_return": 0.0,
                "week_return_percent": 0.0,
                "month_return": 0.0,
                "month_return_percent": 0.0,
                "largest_win": 0.0,
                "largest_loss": 0.0,
                "avg_holding_period": 0.0,
            }

        # Calculate individual trade P&Ls and holding times using FIFO
        matches = self._match_trades_fifo(trades)
        trade_pnls = [m["pnl"] for m in matches]
        holding_periods = [m["hold_ms"] / (1000 * 60 * 60) for m in matches if m["hold_ms"] > 0]

        if not trade_pnls:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "total_profit": 0.0,
                "total_loss": 0.0,
                "profit_factor": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0,
                "max_drawdown_percent": 0.0,
                "total_return": 0.0,
                "total_return_percent": 0.0,
                "day_return": 0.0,
                "day_return_percent": 0.0,
                "week_return": 0.0,
                "week_return_percent": 0.0,
                "month_return": 0.0,
                "month_return_percent": 0.0,
                "largest_win": 0.0,
                "largest_loss": 0.0,
                "avg_holding_period": 0.0,
            }

        # Separate winning and losing trades
        winning_pnls = [pnl for pnl in trade_pnls if pnl > 0]
        losing_pnls = [pnl for pnl in trade_pnls if pnl < 0]

        total_trades = len(trade_pnls)
        winning_trades = len(winning_pnls)
        losing_trades = len(losing_pnls)

        total_profit = sum(winning_pnls) if winning_pnls else 0.0
        total_loss = abs(sum(losing_pnls)) if losing_pnls else 0.0

        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
        profit_factor = (total_profit / total_loss) if total_loss > 0 else (float('inf') if total_profit > 0 else 0.0)
        avg_win = (total_profit / winning_trades) if winning_trades > 0 else 0.0
        avg_loss = (total_loss / losing_trades) if losing_trades > 0 else 0.0

        # Calculate Sharpe ratio (simplified - annualized)
        if len(trade_pnls) > 1:
            avg_return = sum(trade_pnls) / len(trade_pnls)
            variance = sum((pnl - avg_return) ** 2 for pnl in trade_pnls) / len(trade_pnls)
            std_deviation = math.sqrt(variance) if variance > 0 else 0.0
            sharpe_ratio = (avg_return * math.sqrt(252) / std_deviation) if std_deviation > 0 else 0.0
        else:
            sharpe_ratio = 0.0

        # Calculate max drawdown
        max_drawdown = self._calculate_max_drawdown(trade_pnls)
        max_drawdown_percent = 0.0

        # Returns from snapshots if available
        returns = self._get_snapshot_returns()

        total_return = sum(trade_pnls)
        total_return_percent = returns.get("total_return_percent", 0.0)
        day_return = returns.get("day_return", 0.0)
        day_return_percent = returns.get("day_return_percent", 0.0)
        week_return = returns.get("week_return", 0.0)
        week_return_percent = returns.get("week_return_percent", 0.0)
        month_return = returns.get("month_return", 0.0)
        month_return_percent = returns.get("month_return_percent", 0.0)

        if returns.get("peak_equity", 0) > 0:
            max_drawdown_percent = max_drawdown / returns["peak_equity"] * 100

        largest_win = max(trade_pnls) if trade_pnls else 0.0
        largest_loss = min(trade_pnls) if trade_pnls else 0.0
        avg_holding_period = sum(holding_periods) / len(holding_periods) if holding_periods else 0.0

        return {
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": round(win_rate, 2),
            "total_profit": round(total_profit, 2),
            "total_loss": round(total_loss, 2),
            "profit_factor": round(profit_factor, 2) if profit_factor != float('inf') else 0.0,
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "sharpe_ratio": round(sharpe_ratio, 2),
            "max_drawdown": round(max_drawdown, 2),
            "max_drawdown_percent": round(max_drawdown_percent, 2),
            "total_return": round(total_return, 2),
            "total_return_percent": round(total_return_percent, 2),
            "day_return": round(day_return, 2),
            "day_return_percent": round(day_return_percent, 2),
            "week_return": round(week_return, 2),
            "week_return_percent": round(week_return_percent, 2),
            "month_return": round(month_return, 2),
            "month_return_percent": round(month_return_percent, 2),
            "largest_win": round(largest_win, 2),
            "largest_loss": round(largest_loss, 2),
            "avg_holding_period": round(avg_holding_period, 2),
        }

    def _get_snapshot_returns(self) -> Dict[str, float]:
        """Compute return stats from portfolio snapshots if available."""
        conn = get_db_connection()
        cursor = conn.cursor()
        rows = cursor.execute(
            "SELECT date, total_value FROM portfolio_snapshots ORDER BY date ASC"
        ).fetchall()

        if not rows:
            return {}

        def _parse_date(value: str) -> Optional[datetime]:
            try:
                return datetime.fromisoformat(value)
            except Exception:
                try:
                    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    return None

        snapshots = []
        for row in rows:
            dt = _parse_date(row["date"])
            if dt is None:
                continue
            snapshots.append((dt, row["total_value"]))

        if not snapshots:
            return {}

        snapshots.sort(key=lambda x: x[0])
        latest_dt, latest_value = snapshots[-1]
        first_dt, first_value = snapshots[0]
        peak_equity = max(v for _, v in snapshots)

        def _value_at(days_back: int) -> Optional[float]:
            target_dt = latest_dt - timedelta(days=days_back)
            candidates = [v for dt, v in snapshots if dt <= target_dt]
            return candidates[-1] if candidates else None

        day_value = _value_at(1)
        week_value = _value_at(7)
        month_value = _value_at(30)

        def _returns(base: Optional[float]) -> Dict[str, float]:
            if base is None or base <= 0:
                return {"abs": 0.0, "pct": 0.0}
            return {"abs": latest_value - base, "pct": (latest_value - base) / base * 100}

        day = _returns(day_value)
        week = _returns(week_value)
        month = _returns(month_value)

        total_return_percent = ((latest_value - first_value) / first_value * 100) if first_value > 0 else 0.0

        return {
            "peak_equity": peak_equity,
            "total_return_percent": total_return_percent,
            "day_return": day["abs"],
            "day_return_percent": day["pct"],
            "week_return": week["abs"],
            "week_return_percent": week["pct"],
            "month_return": month["abs"],
            "month_return_percent": month["pct"],
        }

    def get_peak_equity(self) -> float:
        conn = get_db_connection()
        cursor = conn.cursor()
        row = cursor.execute("SELECT MAX(total_value) AS peak FROM portfolio_snapshots").fetchone()
        return float(row["peak"]) if row and row["peak"] is not None else 0.0

    def _calculate_max_drawdown(self, pnls: List[float]) -> float:
        """
        Calculate maximum drawdown from a series of P&Ls.

        Max drawdown is the largest peak-to-trough decline in cumulative P&L.
        """
        if not pnls:
            return 0.0

        cumulative = 0.0
        peak = 0.0
        max_drawdown = 0.0

        for pnl in pnls:
            cumulative += pnl
            peak = max(peak, cumulative)
            drawdown = peak - cumulative
            max_drawdown = max(max_drawdown, drawdown)

        return max_drawdown

    def update_positions_from_trade(self, trade: Trade) -> None:
        """
        Update positions table when a trade executes.

        Uses FIFO matching logic to adjust positions:
        - Buy: Add to position or create new position
        - Sell: Reduce position or close position

        Args:
            trade: The trade that was executed
        """
        current_position = self.position_repo.get_by_symbol(trade.symbol)

        if trade.side == "buy":
            if current_position is None:
                # Create new long position
                position = Position(
                    symbol=trade.symbol,
                    amount=trade.amount,
                    avg_entry_price=trade.price,
                    total_cost=trade.amount * trade.price + trade.fee,
                    side="long",
                    opened_at=trade.timestamp,
                    last_updated=trade.timestamp
                )
                self.position_repo.upsert(position)
            else:
                # Update existing position
                new_total_cost = current_position.total_cost + (trade.amount * trade.price + trade.fee)
                new_amount = current_position.amount + trade.amount
                new_avg_price = (new_total_cost / new_amount) if new_amount > 0 else 0.0

                position = Position(
                    symbol=trade.symbol,
                    amount=new_amount,
                    avg_entry_price=new_avg_price,
                    total_cost=new_total_cost,
                    side=current_position.side,
                    opened_at=current_position.opened_at,
                    last_updated=trade.timestamp
                )
                self.position_repo.upsert(position)

        elif trade.side == "sell":
            if current_position is None:
                # Check if shorting is allowed (disabled by default for spot trading)
                allow_shorts = os.getenv("ALLOW_SHORT_POSITIONS", "false").lower() == "true"
                if not allow_shorts:
                    logger.warning(f"Sell order for {trade.symbol} with no existing position - ignoring (shorting disabled)")
                    return

                # Create new short position (if shorting is supported)
                position = Position(
                    symbol=trade.symbol,
                    amount=trade.amount,
                    avg_entry_price=trade.price,
                    total_cost=trade.amount * trade.price - trade.fee,
                    side="short",
                    opened_at=trade.timestamp,
                    last_updated=trade.timestamp
                )
                self.position_repo.upsert(position)
            else:
                # Reduce or close position
                new_amount = current_position.amount - trade.amount

                if new_amount <= 1e-8:  # Position closed
                    self.position_repo.delete(trade.symbol)
                else:
                    # Reduce position size but keep same avg entry price
                    # Proportionally reduce total cost
                    new_total_cost = current_position.total_cost * (new_amount / current_position.amount)

                    position = Position(
                        symbol=trade.symbol,
                        amount=new_amount,
                        avg_entry_price=current_position.avg_entry_price,
                        total_cost=new_total_cost,
                        side=current_position.side,
                        opened_at=current_position.opened_at,
                        last_updated=trade.timestamp
                    )
                    self.position_repo.upsert(position)
