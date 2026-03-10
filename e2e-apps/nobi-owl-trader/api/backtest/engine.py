import pandas as pd
import numpy as np
import json
import uuid
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict

from api.models import AutomationRule, Trade
from api.trading_engine import TradingEngine, TrendSignal
from api.backtest.downloader import DataDownloader
from api.logger import nobi_logger

@dataclass
class BacktestTrade:
    entry_time: int
    exit_time: Optional[int]
    symbol: str
    side: str
    entry_price: float
    exit_price: Optional[float]
    amount: float
    pnl: float = 0.0
    pnl_pct: float = 0.0
    reason: str = ""

class BacktestEngine:
    """
    Simulates the AutomationScheduler logic over historical data.
    """
    def __init__(self, trading_engine: TradingEngine):
        self.engine = trading_engine
        self.downloader = DataDownloader(trading_engine)

    def _rule_triggered(self, rule: AutomationRule, scan_result: Any) -> bool:
        should_trigger = False
        if rule.conditions:
            try:
                conditions = json.loads(rule.conditions)
                should_trigger = self._evaluate_logic(conditions, scan_result)
            except Exception:
                should_trigger = False
        else:
            if scan_result.trade_signal.value == rule.signal_type.lower():
                should_trigger = True
            if rule.min_score is not None:
                if rule.signal_type.upper() in ["BUY", "STRONG_BUY"]:
                    should_trigger = scan_result.score_total >= rule.min_score
                else:
                    should_trigger = scan_result.score_total <= rule.min_score
        return should_trigger

    @staticmethod
    def _timeframe_to_seconds(timeframe: str) -> int:
        if not timeframe:
            return 0
        unit = timeframe[-1]
        try:
            value = int(timeframe[:-1])
        except ValueError:
            return 0
        if unit == "m":
            return value * 60
        if unit == "h":
            return value * 3600
        if unit == "d":
            return value * 86400
        if unit == "w":
            return value * 604800
        return 0

    def run(self, rule: AutomationRule, start_dt: datetime, end_dt: datetime, initial_balance: float = 10000.0):
        nobi_logger.info(f"Starting backtest for {rule.name} on {rule.symbol}")
        
        # 1. Get historical data
        df = self.downloader.get_data_as_df(rule.symbol, rule.timeframe, start_dt, end_dt)
        if df.empty or len(df) < 50:
            return {"error": "Not enough historical data. Try downloading it first."}

        # 2. Simulation State
        balance = initial_balance
        equity_curve = []
        trades: List[BacktestTrade] = []
        active_trade: Optional[BacktestTrade] = None
        break_even_armed = False

        def close_trade(close_amount: float, exit_price: float, exit_time: int, reason: str):
            nonlocal active_trade, balance, break_even_armed
            if not active_trade or close_amount <= 0:
                return

            closed = BacktestTrade(
                entry_time=active_trade.entry_time,
                exit_time=exit_time,
                symbol=active_trade.symbol,
                side=active_trade.side,
                entry_price=active_trade.entry_price,
                exit_price=exit_price,
                amount=close_amount,
            )

            if active_trade.side == "buy":
                closed.pnl = (closed.exit_price - closed.entry_price) * close_amount
            else:
                closed.pnl = (closed.entry_price - closed.exit_price) * close_amount

            closed.pnl_pct = (closed.pnl / (closed.entry_price * close_amount)) * 100
            closed.reason = reason

            balance += closed.pnl
            trades.append(closed)

            active_trade.amount -= close_amount
            if active_trade.amount <= 0:
                active_trade = None
                break_even_armed = False
        
        # 3. Step through time
        # To be realistic, we need a "lookback" for indicators
        # We start simulation from index 50
        for i in range(50, len(df)):
            current_row = df.iloc[i]
            window = df.iloc[i-49:i+1] # The "visible" data up to now
            
            # --- MONITOR POSITION (SL/TP) ---
            if active_trade:
                curr_price = current_row['close']
                should_close = False
                exit_reason = ""
                exit_price = curr_price

                # Max hold bars exit
                if rule.max_hold_bars:
                    bar_seconds = self._timeframe_to_seconds(rule.timeframe)
                    if bar_seconds > 0:
                        held_bars = (current_row["timestamp"] - active_trade.entry_time) / (bar_seconds * 1000)
                        if held_bars >= rule.max_hold_bars:
                            close_trade(active_trade.amount, curr_price, int(current_row['timestamp']), "Max Hold")
                            continue
                
                # Simple SL/TP logic
                if active_trade.side == "buy":
                    if rule.stop_loss_pct and curr_price <= active_trade.entry_price * (1 - rule.stop_loss_pct/100):
                        should_close = True
                        exit_reason = "Stop Loss"
                    elif rule.take_profit_pct and curr_price >= active_trade.entry_price * (1 + rule.take_profit_pct/100):
                        should_close = True
                        exit_reason = "Take Profit"
                else: # sell
                    if rule.stop_loss_pct and curr_price >= active_trade.entry_price * (1 + rule.stop_loss_pct/100):
                        should_close = True
                        exit_reason = "Stop Loss"
                    elif rule.take_profit_pct and curr_price <= active_trade.entry_price * (1 - rule.take_profit_pct/100):
                        should_close = True
                        exit_reason = "Take Profit"

                # Break-even logic after profit threshold
                if active_trade and rule.break_even_after_pct:
                    if active_trade.side == "buy":
                        profit_pct = (curr_price - active_trade.entry_price) / active_trade.entry_price * 100
                        if profit_pct >= rule.break_even_after_pct:
                            break_even_armed = True
                        if break_even_armed and curr_price <= active_trade.entry_price:
                            should_close = True
                            exit_reason = "Break Even"
                    else:
                        profit_pct = (active_trade.entry_price - curr_price) / active_trade.entry_price * 100
                        if profit_pct >= rule.break_even_after_pct:
                            break_even_armed = True
                        if break_even_armed and curr_price >= active_trade.entry_price:
                            should_close = True
                            exit_reason = "Break Even"

                if should_close:
                    close_trade(active_trade.amount, exit_price, int(current_row['timestamp']), exit_reason)

            # --- CHECK AUTOMATION RULE ---
            only_if_in_position = True if rule.only_if_in_position is None else rule.only_if_in_position
            if rule.side == "sell" and only_if_in_position and not active_trade:
                pass
            elif not active_trade and rule.side == "buy":
                try:
                    # Calculate indicators using the window data
                    scan_result = self.engine.scan_market(rule.symbol, rule.timeframe, df=window)

                    # Evaluate rule conditions
                    should_trigger = False

                    # Check custom conditions if defined
                    if rule.conditions:
                        try:
                            conditions = json.loads(rule.conditions)
                            should_trigger = self._evaluate_logic(conditions, scan_result)
                        except Exception:
                            should_trigger = False
                    else:
                        # Legacy signal-based logic
                        if scan_result.trade_signal.value == rule.signal_type.lower():
                            should_trigger = True

                        # Check min score if provided
                        if rule.min_score is not None:
                            if rule.signal_type.upper() in ["BUY", "STRONG_BUY"]:
                                should_trigger = scan_result.score_total >= rule.min_score
                            else:
                                should_trigger = scan_result.score_total <= rule.min_score

                    if should_trigger:
                        # Open a new trade
                        entry_price = current_row['close']
                        trade_amount = rule.amount

                        # Handle percent-based amount
                        if rule.amount_type == "percent":
                            trade_amount = (balance * rule.amount / 100) / entry_price

                        active_trade = BacktestTrade(
                            entry_time=int(current_row['timestamp']),
                            exit_time=None,
                            symbol=rule.symbol,
                            side=rule.side,
                            entry_price=entry_price,
                            exit_price=None,
                            amount=trade_amount,
                        )
                        break_even_armed = False

                except Exception as e:
                    nobi_logger.warning(f"Backtest indicator calculation failed: {e}")
                    continue
            elif active_trade and rule.side == "sell":
                try:
                    scan_result = self.engine.scan_market(rule.symbol, rule.timeframe, df=window)

                    should_trigger = False

                    if rule.conditions:
                        try:
                            conditions = json.loads(rule.conditions)
                            should_trigger = self._evaluate_logic(conditions, scan_result)
                        except Exception:
                            should_trigger = False
                    else:
                        if scan_result.trade_signal.value == rule.signal_type.lower():
                            should_trigger = True
                        if rule.min_score is not None:
                            if rule.signal_type.upper() in ["BUY", "STRONG_BUY"]:
                                should_trigger = scan_result.score_total >= rule.min_score
                            else:
                                should_trigger = scan_result.score_total <= rule.min_score

                    if rule.max_hold_bars:
                        bar_seconds = self._timeframe_to_seconds(rule.timeframe)
                        if bar_seconds > 0:
                            held_bars = (current_row["timestamp"] - active_trade.entry_time) / (bar_seconds * 1000)
                            if held_bars >= rule.max_hold_bars:
                                should_trigger = True

                    if should_trigger:
                        curr_price = current_row["close"]
                        if rule.min_profit_pct is not None:
                            profit_pct = (curr_price - active_trade.entry_price) / active_trade.entry_price * 100
                            if profit_pct < rule.min_profit_pct:
                                should_trigger = False

                    if should_trigger:
                        if rule.amount_type == "percent":
                            close_amount = active_trade.amount * (rule.amount / 100)
                        else:
                            close_amount = min(rule.amount, active_trade.amount)

                        close_trade(close_amount, current_row["close"], int(current_row["timestamp"]), "Sell Signal")
                except Exception as e:
                    nobi_logger.warning(f"Backtest indicator calculation failed: {e}")
                    continue

            unrealized = 0.0
            if active_trade:
                if active_trade.side == "buy":
                    unrealized = (current_row["close"] - active_trade.entry_price) * active_trade.amount
                else:
                    unrealized = (active_trade.entry_price - current_row["close"]) * active_trade.amount

            equity_curve.append({
                "timestamp": int(current_row['timestamp']),
                "equity": balance + unrealized
            })

        # 4. Calculate Stats
        wins = [t for t in trades if t.pnl > 0]
        win_rate = (len(wins) / len(trades) * 100) if trades else 0

        # Max drawdown from equity curve
        peak_equity = equity_curve[0]["equity"] if equity_curve else initial_balance
        max_drawdown = 0.0
        for point in equity_curve:
            peak_equity = max(peak_equity, point["equity"])
            drawdown = peak_equity - point["equity"]
            max_drawdown = max(max_drawdown, drawdown)
        max_drawdown_percent = (max_drawdown / peak_equity * 100) if peak_equity > 0 else 0.0
        
        result = {
            "id": str(uuid.uuid4()),
            "timestamp": int(time.time() * 1000),
            "rule_name": rule.name,
            "symbol": rule.symbol,
            "timeframe": rule.timeframe,
            "initial_balance": initial_balance,
            "final_balance": balance,
            "total_trades": len(trades),
            "win_rate": round(win_rate, 2),
            "max_drawdown": round(max_drawdown, 2),
            "max_drawdown_percent": round(max_drawdown_percent, 2),
            "trades": [asdict(t) for t in trades],
            "equity_curve": equity_curve
        }

        return result

    def run_pair(
        self,
        entry_rule: AutomationRule,
        exit_rule: AutomationRule,
        start_dt: datetime,
        end_dt: datetime,
        initial_balance: float = 10000.0,
    ):
        if entry_rule.symbol != exit_rule.symbol or entry_rule.timeframe != exit_rule.timeframe:
            return {"error": "Entry and exit rules must match symbol/timeframe"}

        nobi_logger.info(
            f"Starting paired backtest for {entry_rule.name} + {exit_rule.name} on {entry_rule.symbol}"
        )

        df = self.downloader.get_data_as_df(entry_rule.symbol, entry_rule.timeframe, start_dt, end_dt)
        if df.empty or len(df) < 50:
            return {"error": "Not enough historical data. Try downloading it first."}

        balance = initial_balance
        equity_curve = []
        trades: List[BacktestTrade] = []
        active_trade: Optional[BacktestTrade] = None
        break_even_armed = False
        stop_price = None
        target_price = None
        trail_high = None
        trail_low = None

        def close_trade(close_amount: float, exit_price: float, exit_time: int, reason: str):
            nonlocal active_trade, balance, break_even_armed, stop_price, target_price, trail_high, trail_low
            if not active_trade or close_amount <= 0:
                return

            closed = BacktestTrade(
                entry_time=active_trade.entry_time,
                exit_time=exit_time,
                symbol=active_trade.symbol,
                side=active_trade.side,
                entry_price=active_trade.entry_price,
                exit_price=exit_price,
                amount=close_amount,
            )

            if active_trade.side == "buy":
                closed.pnl = (closed.exit_price - closed.entry_price) * close_amount
            else:
                closed.pnl = (closed.entry_price - closed.exit_price) * close_amount

            closed.pnl_pct = (closed.pnl / (closed.entry_price * close_amount)) * 100
            closed.reason = reason
            balance += closed.pnl
            trades.append(closed)

            active_trade.amount -= close_amount
            if active_trade.amount <= 0:
                active_trade = None
                break_even_armed = False
                stop_price = None
                target_price = None
                trail_high = None
                trail_low = None

        for i in range(50, len(df)):
            current_row = df.iloc[i]
            window = df.iloc[i-49:i+1]
            curr_price = current_row["close"]

            if active_trade:
                # Update trailing stops
                if entry_rule.trailing_stop_pct:
                    if active_trade.side == "buy":
                        if trail_high is None or curr_price > trail_high:
                            trail_high = curr_price
                        new_stop = trail_high * (1 - entry_rule.trailing_stop_pct / 100)
                        stop_price = new_stop if stop_price is None else max(stop_price, new_stop)
                    else:
                        if trail_low is None or curr_price < trail_low:
                            trail_low = curr_price
                        new_stop = trail_low * (1 + entry_rule.trailing_stop_pct / 100)
                        stop_price = new_stop if stop_price is None else min(stop_price, new_stop)

                # Break-even after profit threshold
                if exit_rule.break_even_after_pct:
                    if active_trade.side == "buy":
                        profit_pct = (curr_price - active_trade.entry_price) / active_trade.entry_price * 100
                        if profit_pct >= exit_rule.break_even_after_pct:
                            break_even_armed = True
                        if break_even_armed and curr_price <= active_trade.entry_price:
                            close_trade(active_trade.amount, curr_price, int(current_row["timestamp"]), "Break Even")
                            continue
                    else:
                        profit_pct = (active_trade.entry_price - curr_price) / active_trade.entry_price * 100
                        if profit_pct >= exit_rule.break_even_after_pct:
                            break_even_armed = True
                        if break_even_armed and curr_price >= active_trade.entry_price:
                            close_trade(active_trade.amount, curr_price, int(current_row["timestamp"]), "Break Even")
                            continue

                # Max hold bars
                if exit_rule.max_hold_bars:
                    bar_seconds = self._timeframe_to_seconds(entry_rule.timeframe)
                    if bar_seconds > 0:
                        held_bars = (current_row["timestamp"] - active_trade.entry_time) / (bar_seconds * 1000)
                        if held_bars >= exit_rule.max_hold_bars:
                            close_trade(active_trade.amount, curr_price, int(current_row["timestamp"]), "Max Hold")
                            continue

                # SL/TP
                if active_trade.side == "buy":
                    if stop_price and curr_price <= stop_price:
                        close_trade(active_trade.amount, curr_price, int(current_row["timestamp"]), "Stop Loss")
                        continue
                    if target_price and curr_price >= target_price:
                        close_trade(active_trade.amount, curr_price, int(current_row["timestamp"]), "Take Profit")
                        continue
                else:
                    if stop_price and curr_price >= stop_price:
                        close_trade(active_trade.amount, curr_price, int(current_row["timestamp"]), "Stop Loss")
                        continue
                    if target_price and curr_price <= target_price:
                        close_trade(active_trade.amount, curr_price, int(current_row["timestamp"]), "Take Profit")
                        continue

            scan_result = None
            try:
                scan_result = self.engine.scan_market(entry_rule.symbol, entry_rule.timeframe, df=window)
            except Exception:
                scan_result = None

            if not active_trade:
                if scan_result and self._rule_triggered(entry_rule, scan_result):
                    entry_price = curr_price
                    trade_amount = entry_rule.amount
                    if entry_rule.amount_type == "percent":
                        trade_amount = (balance * entry_rule.amount / 100) / entry_price

                    active_trade = BacktestTrade(
                        entry_time=int(current_row["timestamp"]),
                        exit_time=None,
                        symbol=entry_rule.symbol,
                        side=entry_rule.side,
                        entry_price=entry_price,
                        exit_price=None,
                        amount=trade_amount,
                    )
                    break_even_armed = False
                    stop_price = None
                    target_price = None
                    trail_high = entry_price
                    trail_low = entry_price
                    if entry_rule.stop_loss_pct:
                        stop_price = entry_price * (1 - entry_rule.stop_loss_pct / 100)
                    if entry_rule.take_profit_pct:
                        target_price = entry_price * (1 + entry_rule.take_profit_pct / 100)

            elif active_trade and scan_result:
                if self._rule_triggered(exit_rule, scan_result):
                    if exit_rule.min_profit_pct is not None:
                        profit_pct = (curr_price - active_trade.entry_price) / active_trade.entry_price * 100
                        if profit_pct < exit_rule.min_profit_pct:
                            pass
                        else:
                            close_amount = active_trade.amount
                            if exit_rule.amount_type == "percent":
                                close_amount = active_trade.amount * (exit_rule.amount / 100)
                            else:
                                close_amount = min(exit_rule.amount, active_trade.amount)
                            close_trade(close_amount, curr_price, int(current_row["timestamp"]), "Sell Signal")
                    else:
                        close_amount = active_trade.amount
                        if exit_rule.amount_type == "percent":
                            close_amount = active_trade.amount * (exit_rule.amount / 100)
                        else:
                            close_amount = min(exit_rule.amount, active_trade.amount)
                        close_trade(close_amount, curr_price, int(current_row["timestamp"]), "Sell Signal")

            unrealized = 0.0
            if active_trade:
                unrealized = (curr_price - active_trade.entry_price) * active_trade.amount
            equity_curve.append({"timestamp": int(current_row["timestamp"]), "equity": balance + unrealized})

        wins = [t for t in trades if t.pnl > 0]
        win_rate = (len(wins) / len(trades) * 100) if trades else 0

        peak_equity = equity_curve[0]["equity"] if equity_curve else initial_balance
        max_drawdown = 0.0
        for point in equity_curve:
            peak_equity = max(peak_equity, point["equity"])
            drawdown = peak_equity - point["equity"]
            max_drawdown = max(max_drawdown, drawdown)
        max_drawdown_percent = (max_drawdown / peak_equity * 100) if peak_equity > 0 else 0.0

        return {
            "id": str(uuid.uuid4()),
            "timestamp": int(time.time() * 1000),
            "rule_name": f"{entry_rule.name} + {exit_rule.name}",
            "symbol": entry_rule.symbol,
            "timeframe": entry_rule.timeframe,
            "initial_balance": initial_balance,
            "final_balance": balance,
            "total_trades": len(trades),
            "win_rate": round(win_rate, 2),
            "max_drawdown": round(max_drawdown, 2),
            "max_drawdown_percent": round(max_drawdown_percent, 2),
            "trades": [asdict(t) for t in trades],
            "equity_curve": equity_curve,
            "entry_rule": entry_rule.id,
            "exit_rule": exit_rule.id,
        }

    def _evaluate_logic(self, logic: dict, scan: Any) -> bool:
        """
        Evaluates complex JSON logic against scan results.
        Example logic: {"operator": "AND", "rules": [{"indicator": "RSI", "op": "<", "val": 30}]}
        """
        operator = logic.get("operator", "AND").upper()
        rules = logic.get("rules", [])

        results = []
        for r in rules:
            indicator_name = r.get("indicator")
            op = r.get("op")
            val = r.get("val")

            # Find indicator in scan results
            indicator = next((ind for ind in scan.indicators if ind.name.upper() == indicator_name.upper()), None)
            if not indicator:
                results.append(False)
                continue

            curr_val = indicator.value

            if op == "<":
                results.append(curr_val < val)
            elif op == ">":
                results.append(curr_val > val)
            elif op == "==":
                results.append(curr_val == val)
            elif op == "crosses_above":
                prev_val = indicator.prev_value
                if prev_val is not None:
                    results.append(prev_val < val and curr_val >= val)
                else:
                    results.append(False)
            elif op == "crosses_below":
                prev_val = indicator.prev_value
                if prev_val is not None:
                    results.append(prev_val > val and curr_val <= val)
                else:
                    results.append(False)
            else:
                results.append(False)

        if operator == "AND":
            return all(results) if results else False
        else:  # OR
            return any(results) if results else False
