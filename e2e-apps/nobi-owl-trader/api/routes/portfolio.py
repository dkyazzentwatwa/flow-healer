"""
Portfolio API endpoints for FastAPI.

Provides REST endpoints for:
- Portfolio summary (total value, P&L)
- Open positions with unrealized P&L
- Performance metrics (win rate, profit factor, etc.)
- Historical portfolio snapshots for charting
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Dict, Any, List, Optional
import os
import time
import math
import ccxt
from datetime import datetime, timedelta, UTC
from api.portfolio import PortfolioEngine, PositionRepository
from api.paper import PaperAccount
from api.models import TradeRepository
from api.database import get_db_connection

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

_exchange = None


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return number


def _safe_round(value: Any, digits: int = 2, default: float = 0.0) -> float:
    return round(_safe_float(value, default=default), digits)


def _get_exchange():
    global _exchange
    if _exchange is None:
        exchange_name = os.getenv("DEFAULT_EXCHANGE", "binanceus")
        exchange_class = getattr(ccxt, exchange_name)
        _exchange = exchange_class({"enableRateLimit": True, "verbose": False})
    return _exchange


def _get_current_prices(symbols: List[str]) -> Dict[str, float]:
    prices = {}
    exchange = _get_exchange()
    for symbol in symbols:
        try:
            ticker = exchange.fetch_ticker(symbol)
            last = ticker.get("last")
            if last is not None:
                price = _safe_float(last, default=None)
                if price is not None:
                    prices[symbol] = price
        except Exception:
            continue
    return prices


@router.get("/summary")
async def get_portfolio_summary() -> Dict[str, Any]:
    """
    Get portfolio summary with current values.

    Returns:
        - total_value: Total portfolio value (cash + positions)
        - cash_balance: Current cash balance
        - unrealized_pnl: Total unrealized P&L from open positions
        - realized_pnl_today: Realized P&L for today
    """
    try:
        engine = PortfolioEngine()
        position_repo = PositionRepository()
        paper_account = PaperAccount()

        balances = paper_account.get_balances()
        base_currency = paper_account.base_currency
        cash_balance = _safe_float(balances.get("free", {}).get(base_currency, 0.0))

        positions = position_repo.get_all()
        symbols = [p.symbol for p in positions]
        current_prices = _get_current_prices(symbols)

        # Calculate unrealized P&L
        unrealized_pnl_dict = engine.calculate_unrealized_pnl(current_prices)
        total_unrealized_pnl = sum(
            _safe_float(value) for value in unrealized_pnl_dict.values()
        )

        # Calculate realized P&L today
        now = datetime.now(UTC)
        start_of_today = datetime(now.year, now.month, now.day, tzinfo=UTC)
        start_of_today_ts = int(start_of_today.timestamp() * 1000)
        
        repo = TradeRepository()
        today_trades = repo.get_between(
            start_of_today_ts, int(datetime.now(UTC).timestamp() * 1000)
        )

        # Calculate total realized P&L from closed trades (all-time)
        total_realized_pnl = engine.calculate_realized_pnl()

        # Calculate realized P&L today using FIFO on today's trades
        realized_pnl_today = engine.calculate_realized_pnl_from_trades(today_trades)

        total_value = _safe_float(engine.get_portfolio_value(cash_balance, current_prices))
        total_cost = sum(_safe_float(p.total_cost) for p in positions)
        total_pnl = total_realized_pnl + total_unrealized_pnl
        total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0.0
        unrealized_pnl_pct = (
            total_unrealized_pnl / total_cost * 100 if total_cost > 0 else 0.0
        )

        return {
            "portfolio": {
                "totalValue": _safe_round(total_value, 2),
                "cash": _safe_round(cash_balance, 2),
                "positions": len(positions),
                "totalCost": _safe_round(total_cost, 2),
                "unrealizedPnl": _safe_round(total_unrealized_pnl, 2),
                "unrealizedPnlPercent": _safe_round(unrealized_pnl_pct, 2),
                "realizedPnl": _safe_round(realized_pnl_today, 2),
                "totalPnl": _safe_round(total_pnl, 2),
                "totalPnlPercent": _safe_round(total_pnl_pct, 2),
                "timestamp": int(time.time() * 1000),
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get portfolio summary: {str(e)}")


@router.get("/positions")
async def get_positions() -> Dict[str, List[Dict[str, Any]]]:
    """
    Get all open positions with unrealized P&L.

    Returns list of positions with:
        - symbol: Trading pair symbol
        - amount: Position size
        - avg_entry_price: Average entry price
        - current_price: Current market price
        - unrealized_pnl: Unrealized profit/loss
        - side: Position side (long/short)
        - opened_at: Timestamp when position opened
    """
    try:
        position_repo = PositionRepository()
        engine = PortfolioEngine()

        positions = position_repo.get_all()
        current_prices = _get_current_prices([p.symbol for p in positions])

        # Calculate unrealized P&L for each position
        unrealized_pnl_dict = engine.calculate_unrealized_pnl(current_prices)

        result: List[Dict[str, Any]] = []
        for position in positions:
            current_price = _safe_float(
                current_prices.get(position.symbol, position.avg_entry_price),
                default=_safe_float(position.avg_entry_price),
            )
            if position.side == "short":
                unrealized_pnl = (
                    _safe_float(position.avg_entry_price) - current_price
                ) * _safe_float(position.amount)
            else:
                unrealized_pnl = _safe_float(
                    unrealized_pnl_dict.get(position.symbol, 0.0)
                )
            cost_basis = _safe_float(position.avg_entry_price) * _safe_float(position.amount)
            unrealized_pnl_pct = (unrealized_pnl / cost_basis * 100) if cost_basis > 0 else 0.0
            market_value = current_price * _safe_float(position.amount)

            result.append({
                "symbol": position.symbol,
                "quantity": _safe_float(position.amount),
                "avgCost": _safe_round(position.avg_entry_price, 6),
                "currentPrice": _safe_round(current_price, 6),
                "marketValue": _safe_round(market_value, 2),
                "unrealizedPnl": _safe_round(unrealized_pnl, 2),
                "unrealizedPnlPercent": _safe_round(unrealized_pnl_pct, 2),
                "realizedPnl": 0.0,
                "totalPnl": _safe_round(unrealized_pnl, 2),
                "totalPnlPercent": _safe_round(unrealized_pnl_pct, 2),
                "firstBuyDate": position.opened_at,
                "lastBuyDate": position.last_updated,
                "trades": [],
            })

        return {"positions": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get positions: {str(e)}")


@router.get("/metrics")
async def get_performance_metrics() -> Dict[str, Any]:
    """
    Get performance metrics for the portfolio.

    Returns:
        - total_trades: Total number of completed trades
        - winning_trades: Number of profitable trades
        - losing_trades: Number of losing trades
        - win_rate: Win rate percentage
        - total_profit: Total profit from winning trades
        - total_loss: Total loss from losing trades (absolute value)
        - profit_factor: Ratio of total profit to total loss
        - avg_win: Average profit per winning trade
        - avg_loss: Average loss per losing trade
        - sharpe_ratio: Risk-adjusted return metric
        - max_drawdown: Maximum drawdown
    """
    try:
        engine = PortfolioEngine()
        metrics = engine.calculate_performance_metrics()
        return metrics
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to calculate metrics: {str(e)}")


@router.get("/trades")
async def get_trades(limit: int = Query(default=100, ge=1, le=1000)) -> Dict[str, Any]:
    try:
        repo = TradeRepository()
        trades = repo.get_all(limit=limit)
        result = []
        for trade in trades:
            result.append(
                {
                    "id": trade.id,
                    "symbol": trade.symbol,
                    "side": trade.side,
                    "amount": trade.amount,
                    "price": trade.price,
                    "total": round(trade.amount * trade.price, 6),
                    "fee": trade.fee,
                    "fee_currency": trade.fee_currency,
                    "timestamp": trade.timestamp,
                    "status": trade.status,
                    "paper": trade.paper,
                    "strategy": trade.strategy,
                    "notes": trade.notes,
                }
            )
        return {"trades": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get trades: {str(e)}")


@router.get("/history")
async def get_portfolio_history(
    days: int = Query(default=30, ge=1, le=365, description="Number of days of history to retrieve")
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Get historical portfolio snapshots for charting.

    Query Parameters:
        - days: Number of days to retrieve (default: 30, max: 365)

    Returns list of daily snapshots with:
        - date: Date string (YYYY-MM-DD)
        - total_value: Total portfolio value
        - cash_balance: Cash balance
        - unrealized_pnl: Unrealized P&L
        - realized_pnl_today: Realized P&L for that day
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Calculate cutoff date
        cutoff_date = (datetime.now(UTC) - timedelta(days=days)).strftime('%Y-%m-%d')

        # Query portfolio snapshots
        rows = cursor.execute("""
            SELECT date, total_value, cash_balance, unrealized_pnl, realized_pnl_today
            FROM portfolio_snapshots
            WHERE date >= ?
            ORDER BY date ASC
        """, (cutoff_date,)).fetchall()

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
            total_value = _safe_float(row["total_value"])
            cash_balance = _safe_float(row["cash_balance"])
            positions_value = total_value - cash_balance
            total_pnl = _safe_float(row["unrealized_pnl"]) + _safe_float(
                row["realized_pnl_today"]
            )
            total_pnl_pct = (total_pnl / total_value * 100) if total_value > 0 else 0.0

            snapshots.append({
                "timestamp": int(dt.timestamp()),
                "totalValue": _safe_round(total_value, 2),
                "cash": _safe_round(cash_balance, 2),
                "positionsValue": _safe_round(positions_value, 2),
                "totalPnl": _safe_round(total_pnl, 2),
                "totalPnlPercent": _safe_round(total_pnl_pct, 2),
            })

        if not snapshots:
            return {"history": []}

        # Compute day-over-day changes
        history = []
        prev = None
        for snap in snapshots:
            if prev:
                day_change = snap["totalValue"] - prev["totalValue"]
                day_change_pct = (day_change / prev["totalValue"] * 100) if prev["totalValue"] > 0 else 0.0
            else:
                day_change = 0.0
                day_change_pct = 0.0

            history.append({
                **snap,
                "dayChange": _safe_round(day_change, 2),
                "dayChangePercent": _safe_round(day_change_pct, 2),
            })
            prev = snap

        return {"history": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get portfolio history: {str(e)}")
