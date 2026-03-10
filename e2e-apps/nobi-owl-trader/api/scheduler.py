import logging
import time
import json
from datetime import datetime
from typing import Any
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from api.models import AutomationRuleRepository, PortfolioSnapshotRepository, PortfolioSnapshot
from api.portfolio import PortfolioEngine
from api.trading_engine import TradingEngine, TrendSignal
from api.logger import nobi_logger

class AutomationScheduler:
    def __init__(self, engine: TradingEngine):
        self.engine = engine
        self.scheduler = AsyncIOScheduler()
        self.rule_repo = AutomationRuleRepository()
        self.snapshot_repo = PortfolioSnapshotRepository()
        self.portfolio_engine = PortfolioEngine()

    def start(self):
        """Start the scheduler and add jobs"""
        # Run automation rules check every minute
        self.scheduler.add_job(
            self.check_automation_rules,
            "interval",
            minutes=1,
            id="check_rules",
            replace_existing=True
        )

        # Take portfolio snapshot every hour
        self.scheduler.add_job(
            self.snapshot_portfolio,
            "interval",
            hours=1,
            id="snapshot_portfolio",
            replace_existing=True
        )

        # Monitor open positions every 30 seconds for SL/TP
        self.scheduler.add_job(
            self.monitor_positions,
            "interval",
            seconds=30,
            id="monitor_positions",
            replace_existing=True
        )

        self.scheduler.start()
        nobi_logger.info("Automation Scheduler started")

    def stop(self):
        """Stop the scheduler"""
        self.scheduler.shutdown()
        nobi_logger.info("Automation Scheduler stopped")

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

    async def monitor_positions(self):
        """Check all open trades for SL/TP hits and close them if necessary"""
        try:
            # 1. Get all open trades that have SL/TP targets
            cursor = self.rule_repo.conn.cursor()
            # We look for trades that are 'closed' (meaning executed) but part of an active position
            # A better way is to track 'active' trades or check against positions table
            # For simplicity, let's find trades with SL/TP that don't have a corresponding 'exit' trade yet
            open_trades = cursor.execute("""
                SELECT * FROM trades 
                WHERE (stop_price IS NOT NULL OR target_price IS NOT NULL)
                AND status = 'closed'
            """).fetchall()
            
            if not open_trades:
                return

            # 2. Get current positions to verify what's actually held
            positions = {p.symbol: p for p in self.portfolio_engine.position_repo.get_all()}
            
            # 3. Check each trade
            for trade_row in open_trades:
                symbol = trade_row["symbol"]
                if symbol not in positions:
                    continue
                
                position = positions[symbol]
                stop_price = trade_row["stop_price"]
                target_price = trade_row["target_price"]
                side = trade_row["side"]
                is_trailing = trade_row["is_trailing"]
                highest_price = trade_row["highest_price"]
                lowest_price = trade_row["lowest_price"]
                
                # Fetch current price
                try:
                    ticker = self.engine.get_ticker(symbol)
                    current_price = ticker["last"]
                except Exception:
                    continue

                should_close = False
                reason = ""

                # 4. Handle Trailing Stop logic
                cursor.execute(
                    """
                    SELECT trailing_stop_pct, break_even_after_pct
                    FROM automation_rules
                    WHERE symbol = ? AND side = ?
                    LIMIT 1
                    """,
                    (symbol, side),
                )
                rule_row = cursor.fetchone()
                ts_pct = rule_row["trailing_stop_pct"] if rule_row else None
                break_even_after_pct = rule_row["break_even_after_pct"] if rule_row else None

                if is_trailing and ts_pct:
                        if highest_price is None:
                            highest_price = current_price
                        if lowest_price is None:
                            lowest_price = current_price

                        # Initialize stop if missing
                        if stop_price is None:
                            if side == "buy":
                                stop_price = current_price * (1 - ts_pct / 100)
                            else:
                                stop_price = current_price * (1 + ts_pct / 100)
                            cursor.execute(
                                "UPDATE trades SET stop_price = ?, highest_price = ?, lowest_price = ? WHERE id = ?",
                                (stop_price, highest_price, lowest_price, trade_row["id"])
                            )
                            self.rule_repo.conn.commit()

                        if side == "buy": # Long
                            if current_price > highest_price:
                                new_stop = current_price * (1 - ts_pct / 100)
                                if new_stop > stop_price:
                                    stop_price = new_stop
                                    highest_price = current_price
                                    cursor.execute("UPDATE trades SET stop_price = ?, highest_price = ? WHERE id = ?", (stop_price, highest_price, trade_row["id"]))
                                    self.rule_repo.conn.commit()
                                    nobi_logger.info(f"Trailing SL moved UP to {stop_price} for {symbol}")
                        else: # Sell/Short
                            if current_price < lowest_price:
                                new_stop = current_price * (1 + ts_pct / 100)
                                if new_stop < stop_price:
                                    stop_price = new_stop
                                    lowest_price = current_price
                                    cursor.execute("UPDATE trades SET stop_price = ?, lowest_price = ? WHERE id = ?", (stop_price, lowest_price, trade_row["id"]))
                                    self.rule_repo.conn.commit()
                                    nobi_logger.info(f"Trailing SL moved DOWN to {stop_price} for {symbol}")

                # Break-even stop once profit threshold is reached
                try:
                    entry_price = trade_row["price"]
                    if break_even_after_pct and entry_price:
                        if side == "buy":
                            profit_pct = (current_price - entry_price) / entry_price * 100
                            if profit_pct >= break_even_after_pct and (stop_price is None or stop_price < entry_price):
                                stop_price = entry_price
                        else:
                            profit_pct = (entry_price - current_price) / entry_price * 100
                            if profit_pct >= break_even_after_pct and (stop_price is None or stop_price > entry_price):
                                stop_price = entry_price

                        if stop_price == entry_price:
                            cursor.execute(
                                "UPDATE trades SET stop_price = ? WHERE id = ?",
                                (stop_price, trade_row["id"]),
                            )
                            self.rule_repo.conn.commit()
                except Exception:
                    pass

                if side == "buy": # Long position
                    if stop_price and current_price <= stop_price:
                        should_close = True
                        reason = f"Stop-Loss hit at {current_price}"
                    elif target_price and current_price >= target_price:
                        should_close = True
                        reason = f"Take-Profit hit at {current_price}"
                else: # Sell/Short position
                    if stop_price and current_price >= stop_price:
                        should_close = True
                        reason = f"Stop-Loss hit at {current_price}"
                    elif target_price and current_price <= target_price:
                        should_close = True
                        reason = f"Take-Profit hit at {current_price}"

                if should_close:
                    nobi_logger.trade(f"Closing position for {symbol}: {reason}", symbol=symbol)
                    
                    # Execute exit trade
                    exit_side = "sell" if side == "buy" else "buy"
                    try:
                        self.engine.place_order(
                            symbol=symbol,
                            side=exit_side,
                            amount=position.amount,
                            order_type="market"
                        )
                        
                        # Mark the original trade as 'processed' so we don't monitor it again
                        # In a more robust system, we'd link entry and exit trades
                        cursor.execute(
                            "UPDATE trades SET stop_price = NULL, target_price = NULL, notes = ? WHERE id = ?",
                            (f"Closed: {reason}", trade_row["id"])
                        )
                        self.rule_repo.conn.commit()
                        
                    except Exception as e:
                        nobi_logger.error(f"Failed to close position for {symbol}: {e}")

        except Exception as e:
            nobi_logger.error(f"Error in position monitor: {e}")

    async def check_automation_rules(self):
        """Iterate through active rules and execute trades if conditions are met"""
        nobi_logger.info("Checking automation rules...")
        active_rules = self.rule_repo.get_active()
        
        for rule in active_rules:
            try:
                # Check cooldown
                now = int(time.time())
                if now < rule.last_triggered + (rule.cooldown_minutes * 60):
                    continue

                # Run market scan
                result = self.engine.scan_market(rule.symbol, rule.timeframe)
                
                # Evaluate condition
                should_trigger = False
                force_exit = False
                
                # 1. Custom conditions (Strategy Builder)
                if rule.conditions:
                    try:
                        conditions = json.loads(rule.conditions)
                        should_trigger = self.evaluate_logic(conditions, result)
                    except Exception as e:
                        nobi_logger.error(f"Error evaluating custom logic for {rule.name}: {e}")
                        should_trigger = False
                # 2. Legacy signal-based logic
                else:
                    # 1. Check signal type
                    if result.trade_signal.value == rule.signal_type.lower():
                        should_trigger = True
                    
                    # 2. Check min score if provided
                    if rule.min_score is not None:
                        if rule.signal_type.upper() in ["BUY", "STRONG_BUY"]:
                            should_trigger = result.score_total >= rule.min_score
                        else: # SELL, STRONG_SELL
                            should_trigger = result.score_total <= rule.min_score

                # Position-aware sell checks
                position = None
                current_price = None
                if rule.side.lower() == "sell":
                    position = self.portfolio_engine.position_repo.get_by_symbol(rule.symbol)
                    only_if_in_position = True if rule.only_if_in_position is None else rule.only_if_in_position
                    reduce_only = True if rule.reduce_only is None else rule.reduce_only

                    if only_if_in_position and (not position or position.amount <= 0):
                        continue

                    try:
                        current_price = result.ohlcv.get("close") if result.ohlcv else None
                    except Exception:
                        current_price = None

                    if position and rule.max_hold_bars:
                        bar_seconds = self._timeframe_to_seconds(rule.timeframe)
                        if bar_seconds > 0:
                            held_bars = (now * 1000 - position.opened_at) / (bar_seconds * 1000)
                            if held_bars >= rule.max_hold_bars:
                                should_trigger = True
                                force_exit = True

                    if position and current_price and rule.min_profit_pct is not None and not force_exit:
                        profit_pct = (current_price - position.avg_entry_price) / position.avg_entry_price * 100
                        if profit_pct < rule.min_profit_pct:
                            continue

                if should_trigger:
                    nobi_logger.trade(f"Rule '{rule.name}' triggered for {rule.symbol}", rule_id=rule.id, symbol=rule.symbol)

                    # 1. Determine trade amount
                    trade_amount = rule.amount
                    if rule.amount_type == "percent":
                        # Get balance for quote currency
                        base, quote = rule.symbol.split("/")
                        balances = self.engine.fetch_balance()
                        free_balances = balances.get("free", {})

                        if rule.side.lower() == "buy":
                            free_quote = free_balances.get(quote, 0.0)
                            if free_quote <= 0:
                                nobi_logger.warning(f"Insufficient {quote} balance for rule {rule.name}: {free_quote}")
                                continue

                            quote_amount = free_quote * (rule.amount / 100)
                            try:
                                ticker = self.engine.get_ticker(rule.symbol)
                                trade_amount = quote_amount / ticker["last"]
                            except Exception as e:
                                nobi_logger.error(f"Failed to calculate trade amount: {e}")
                                continue
                        else:
                            free_base = free_balances.get(base, 0.0)
                            if free_base <= 0:
                                nobi_logger.warning(f"Insufficient {base} balance for rule {rule.name}: {free_base}")
                                continue
                            trade_amount = free_base * (rule.amount / 100)

                    if rule.side.lower() == "sell" and position and reduce_only:
                        trade_amount = min(trade_amount, position.amount)

                    # Validate trade amount
                    min_trade_size = 0.0001  # Minimum trade size
                    if trade_amount <= 0:
                        nobi_logger.warning(f"Invalid trade amount {trade_amount} for rule {rule.name}")
                        continue
                    if trade_amount < min_trade_size:
                        nobi_logger.warning(f"Trade amount {trade_amount} below minimum {min_trade_size} for {rule.symbol}")
                        continue

                    # 2. Execute trade
                    try:
                        order = self.engine.place_order(
                            symbol=rule.symbol,
                            side=rule.side,
                            amount=trade_amount,
                            order_type="market"
                        )
                        
                        # 3. Handle SL/TP calculation for the trade record
                        # We need to find the trade record created by place_order and update it
                        # Or place_order should handle it. Let's update the trade record in DB.
                        trade_id = order.get("id")
                        if trade_id and (rule.stop_loss_pct or rule.take_profit_pct or rule.trailing_stop_pct):
                            execution_price = order.get("price")
                            if execution_price:
                                stop_price = None
                                target_price = None
                                
                                if rule.side.lower() == "buy":
                                    if rule.stop_loss_pct:
                                        stop_price = execution_price * (1 - rule.stop_loss_pct / 100)
                                    if rule.take_profit_pct:
                                        target_price = execution_price * (1 + rule.take_profit_pct / 100)
                                else: # sell
                                    if rule.stop_loss_pct:
                                        stop_price = execution_price * (1 + rule.stop_loss_pct / 100)
                                    if rule.take_profit_pct:
                                        target_price = execution_price * (1 - rule.take_profit_pct / 100)

                                if rule.trailing_stop_pct and stop_price is None:
                                    if rule.side.lower() == "buy":
                                        stop_price = execution_price * (1 - rule.trailing_stop_pct / 100)
                                    else:
                                        stop_price = execution_price * (1 + rule.trailing_stop_pct / 100)
                                
                                # Update trade record in DB
                                cursor = self.rule_repo.conn.cursor()
                                is_trailing = 1 if rule.trailing_stop_pct else 0
                                cursor.execute(
                                    "UPDATE trades SET stop_price = ?, target_price = ?, is_trailing = ?, highest_price = ?, lowest_price = ? WHERE id = ?",
                                    (stop_price, target_price, is_trailing, execution_price, execution_price, trade_id)
                                )
                                self.rule_repo.conn.commit()
                                nobi_logger.info(f"Set SL: {stop_price}, TP: {target_price}, Trailing: {is_trailing} for trade {trade_id}")

                    except Exception as e:
                        nobi_logger.error(f"Failed to execute trade for {rule.name}: {e}")
                    
                    # Update last triggered
                    self.rule_repo.update_last_triggered(rule.id, now)

            except Exception as e:
                nobi_logger.error(f"Error evaluating rule {rule.name}: {e}", rule_id=rule.id)

    def evaluate_logic(self, logic: dict, scan: Any) -> bool:
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
            
            if op == "<": results.append(curr_val < val)
            elif op == ">": results.append(curr_val > val)
            elif op == "==": results.append(curr_val == val)
            elif op == "crosses_above":
                # Check if indicator crossed above the threshold value
                prev_val = indicator.prev_value
                if prev_val is not None:
                    results.append(prev_val < val and curr_val >= val)
                else:
                    results.append(False)
            elif op == "crosses_below":
                # Check if indicator crossed below the threshold value
                prev_val = indicator.prev_value
                if prev_val is not None:
                    results.append(prev_val > val and curr_val <= val)
                else:
                    results.append(False)
            else: results.append(False)
            
        if operator == "AND":
            return all(results) if results else False
        else: # OR
            return any(results) if results else False

    async def snapshot_portfolio(self):
        """Take a snapshot of current portfolio value"""
        nobi_logger.info("Taking portfolio snapshot...")
        try:
            # 1. Get current balances
            balances = self.engine.fetch_balance()
            
            # Use total in quote currency (usually USDT)
            # This is a simplification. A better way would be to convert all holdings to USD.
            # For now, let's assume paper trading uses USDT.
            cash_balance = 0.0
            if self.engine.paper_trading:
                cash_balance = balances.get("total", {}).get("USDT", 0.0)
            else:
                # For live trading, we'd need to handle different quote currencies
                cash_balance = balances.get("total", {}).get("USDT", 0.0)

            # 2. Get current prices for open positions
            positions = self.portfolio_engine.position_repo.get_all()
            current_prices = {}
            for pos in positions:
                try:
                    ticker = self.engine.get_ticker(pos.symbol)
                    current_prices[pos.symbol] = ticker["last"]
                except Exception:
                    nobi_logger.warning(f"Could not fetch price for {pos.symbol}", symbol=pos.symbol)

            # 3. Calculate metrics
            total_value = self.portfolio_engine.get_portfolio_value(cash_balance, current_prices)
            unrealized_pnl = sum(self.portfolio_engine.calculate_unrealized_pnl(current_prices).values())
            
            # Realized P&L today (UTC)
            now = datetime.utcnow()
            start_of_today = datetime(now.year, now.month, now.day)
            start_ts = int(start_of_today.timestamp() * 1000)
            end_ts = int(now.timestamp() * 1000)
            today_trades = self.portfolio_engine.trade_repo.get_between(start_ts, end_ts)
            realized_pnl_today = self.portfolio_engine.calculate_realized_pnl_from_trades(today_trades)

            # 4. Save snapshot
            snapshot = PortfolioSnapshot(
                date=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                total_value=total_value,
                cash_balance=cash_balance,
                unrealized_pnl=unrealized_pnl,
                realized_pnl_today=realized_pnl_today
            )
            self.snapshot_repo.create(snapshot)
            nobi_logger.info(f"Snapshot saved: {total_value} USDT")

        except Exception as e:
            nobi_logger.error(f"Error taking snapshot: {e}")
