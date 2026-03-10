"""
NobiBot Trading Engine - Modern wrapper around the original trading logic
Provides clean interfaces for the FastAPI application
"""

import ccxt
import talib as ta
import numpy as np
import pandas as pd
import os
import time
import uuid
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from dotenv import load_dotenv

from api.paper import PaperAccount
from api.models import Trade, TradeRepository
from api.portfolio import PortfolioEngine
from api.risk import RiskLimitsRepository, RiskManager

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TrendSignal(str, Enum):
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


@dataclass
class IndicatorResult:
    name: str
    value: float
    score: float
    signal: str
    details: Dict[str, Any] = field(default_factory=dict)
    prev_value: float = None  # Previous candle's indicator value for crossover detection


@dataclass
class ScanResult:
    symbol: str
    exchange: str
    timeframe: str
    timestamp: datetime
    score_total: float
    trade_signal: TrendSignal
    indicators: List[IndicatorResult]
    ohlcv: Dict[str, Any]


class RateLimiter:
    """Simple rate limiter with exponential backoff"""

    def __init__(self, max_retries: int = 2, base_delay: float = 0.5):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.retry_count = 0

    def wait(self):
        if self.retry_count > 0:
            delay = self.base_delay * (2 ** (self.retry_count - 1))
            logger.info(f"Rate limited. Waiting {delay}s before retry...")
            time.sleep(delay)

    def success(self):
        self.retry_count = 0

    def failure(self) -> bool:
        self.retry_count += 1
        return self.retry_count <= self.max_retries


class TradingEngine:
    """
    Modern trading engine wrapper with proper error handling
    and clean interfaces for API integration
    """

    def __init__(
        self,
        exchange_name: str = None,
        api_key: str = None,
        secret_key: str = None,
        paper_trading: bool = True,
    ):
        self.exchange_name = exchange_name or os.getenv("DEFAULT_EXCHANGE", "binanceus")
        self.api_key = api_key or os.getenv("EXCHANGE_API_KEY", "")
        self.secret_key = secret_key or os.getenv("EXCHANGE_SECRET_KEY", "")
        self.paper_trading = paper_trading if paper_trading is not None else os.getenv("PAPER_TRADING", "true").lower() == "true"

        self.exchange = None
        self.rate_limiter = RateLimiter()
        self.trade_repo = TradeRepository()
        self.portfolio_engine = PortfolioEngine()
        self.paper_account = PaperAccount() if self.paper_trading else None

        # Initialize exchange connection
        self._init_exchange()

    def _init_exchange(self):
        """Initialize CCXT exchange connection"""
        try:
            exchange_class = getattr(ccxt, self.exchange_name)
            config = {
                "enableRateLimit": True,
                "verbose": False,
            }

            # Only add API keys if provided and not empty
            if self.api_key and self.secret_key and self.api_key != "your_api_key_here":
                config["apiKey"] = self.api_key
                config["secret"] = self.secret_key

            self.exchange = exchange_class(config)
            logger.info(f"Connected to {self.exchange_name}")

            if self.paper_trading:
                logger.info("*** PAPER TRADING MODE ENABLED ***")

        except Exception as e:
            logger.error(f"Failed to initialize exchange: {e}")
            raise

    def _api_call_with_retry(self, func, *args, **kwargs) -> Any:
        """Execute API call with retry logic and exponential backoff"""
        self.rate_limiter.retry_count = 0  # Reset on new call
        while True:
            try:
                self.rate_limiter.wait()
                result = func(*args, **kwargs)
                self.rate_limiter.success()
                return result
            except ccxt.RateLimitExceeded as e:
                logger.warning(f"Rate limit exceeded: {e}")
                if not self.rate_limiter.failure():
                    raise
            except ccxt.NetworkError as e:
                logger.warning(f"Network error: {e}")
                if not self.rate_limiter.failure():
                    raise
            except ccxt.ExchangeError as e:
                logger.error(f"Exchange error: {e}")
                raise

    def fetch_ohlcv(
        self, symbol: str, timeframe: str = "1h", limit: int = 100
    ) -> pd.DataFrame:
        """Fetch OHLCV data with error handling (public endpoint - no auth needed)"""
        try:
            ohlcv = self._api_call_with_retry(
                self.exchange.fetch_ohlcv,
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
            )

            columns = ["timestamp", "open", "high", "low", "close", "volume"]
            df = pd.DataFrame(ohlcv, columns=columns, dtype=np.float64)
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            return df

        except Exception as e:
            logger.error(f"Failed to fetch OHLCV for {symbol}: {e}")
            raise

    def fetch_balance(self) -> Dict[str, Any]:
        """Fetch account balance"""
        if self.paper_trading:
            return self.paper_account.get_balances()

        try:
            return self._api_call_with_retry(self.exchange.fetch_balance)
        except Exception as e:
            logger.error(f"Failed to fetch balance: {e}")
            raise

    def fetch_open_orders(self, symbol: str = None) -> List[Dict]:
        """Fetch open orders

        For paper trading, returns trades with pending SL/TP targets as "open orders".
        """
        if self.paper_trading:
            # Get paper trades with active SL/TP from positions
            try:
                from api.database import get_db_connection
                conn = get_db_connection()
                cursor = conn.cursor()

                # Find trades with pending SL/TP targets
                if symbol:
                    rows = cursor.execute("""
                        SELECT * FROM trades
                        WHERE paper = 1
                        AND (stop_price IS NOT NULL OR target_price IS NOT NULL)
                        AND symbol = ?
                        ORDER BY timestamp DESC
                    """, (symbol,)).fetchall()
                else:
                    rows = cursor.execute("""
                        SELECT * FROM trades
                        WHERE paper = 1
                        AND (stop_price IS NOT NULL OR target_price IS NOT NULL)
                        ORDER BY timestamp DESC
                    """).fetchall()

                orders = []
                for row in rows:
                    orders.append({
                        "id": row["id"],
                        "symbol": row["symbol"],
                        "side": row["side"],
                        "amount": row["amount"],
                        "price": row["price"],
                        "stop_price": row["stop_price"],
                        "target_price": row["target_price"],
                        "status": "monitoring",
                        "timestamp": row["timestamp"],
                        "paper": True
                    })
                return orders
            except Exception as e:
                logger.warning(f"Failed to fetch paper orders: {e}")
                return []

        try:
            return self._api_call_with_retry(
                self.exchange.fetch_open_orders, symbol=symbol
            )
        except Exception as e:
            logger.error(f"Failed to fetch open orders: {e}")
            raise

    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """Get current ticker for a symbol (public endpoint - no auth needed)"""
        try:
            return self._api_call_with_retry(self.exchange.fetch_ticker, symbol)
        except Exception as e:
            logger.error(f"Failed to fetch ticker: {e}")
            raise

    def get_markets(self) -> List[Dict[str, Any]]:
        """Get available markets (public endpoint - no auth needed)"""
        try:
            self.exchange.load_markets()
            return list(self.exchange.markets.values())
        except Exception as e:
            logger.error(f"Failed to fetch markets: {e}")
            raise

    def _get_execution_price(self, symbol: str, price: Optional[float]) -> float:
        if price is not None and price > 0:
            return float(price)
        ticker = self.get_ticker(symbol)
        last = ticker.get("last")
        if last is None:
            raise ValueError("Unable to determine execution price")
        return float(last)

    def _execute_paper_trade(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: Optional[float],
        order_type: str,
    ) -> Dict[str, Any]:
        exec_price = self._get_execution_price(symbol, price)
        fee_rate = float(os.getenv("PAPER_FEE_RATE", "0.001"))
        fee = exec_price * amount * fee_rate
        fee_currency = symbol.split("/")[1]

        self.paper_account.apply_trade(symbol, side, amount, exec_price, fee)

        trade = Trade(
            id=f"paper_{uuid.uuid4().hex}",
            timestamp=int(time.time() * 1000),
            symbol=symbol,
            side=side.lower(),
            amount=amount,
            price=exec_price,
            fee=fee,
            fee_currency=fee_currency,
            status="closed",
            paper=True,
            strategy="manual",
            notes=order_type,
        )
        self.trade_repo.create(trade)
        self.portfolio_engine.update_positions_from_trade(trade)

        return {
            "id": trade.id,
            "symbol": symbol,
            "side": trade.side,
            "type": order_type,
            "amount": amount,
            "price": exec_price,
            "status": "closed",
            "paper_trade": True,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _enforce_risk_limits(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: Optional[float],
    ) -> None:
        repo = RiskLimitsRepository()
        limits = repo.get()
        risk_manager = RiskManager(limits)

        side_lower = side.lower()
        position = self.portfolio_engine.position_repo.get_by_symbol(symbol)
        allow_shorts = os.getenv("ALLOW_SHORT_POSITIONS", "false").lower() == "true"

        # Allow risk-reducing exits (sell on existing long)
        if side_lower == "sell" and position is not None:
            return

        # For sell without position, only enforce if shorts are allowed
        if side_lower == "sell" and position is None and not allow_shorts:
            return

        exec_price = self._get_execution_price(symbol, price)
        position_value = exec_price * amount

        # Compute portfolio value and exposure
        balances = self.fetch_balance()
        base_currency = self.paper_account.base_currency if self.paper_trading else "USDT"
        cash_balance = balances.get("free", {}).get(base_currency, 0.0)

        positions = self.portfolio_engine.position_repo.get_all()
        total_exposure = 0.0
        current_prices: Dict[str, float] = {}
        for pos in positions:
            try:
                ticker = self.get_ticker(pos.symbol)
                current_price = ticker.get("last") or pos.avg_entry_price
            except Exception:
                current_price = pos.avg_entry_price
            current_prices[pos.symbol] = float(current_price)
            total_exposure += current_price * pos.amount

        # Include proposed position in exposure for new entries
        if side_lower == "buy" or (side_lower == "sell" and allow_shorts and position is None):
            total_exposure += position_value

        portfolio_value = (
            self.portfolio_engine.get_portfolio_value(cash_balance, current_prices)
            if positions
            else cash_balance
        )

        # Position size check should consider existing position value
        if position is not None:
            try:
                existing_price = current_prices.get(symbol, exec_price)
            except Exception:
                existing_price = exec_price
            existing_value = existing_price * position.amount
        else:
            existing_value = 0.0

        position_size = position_value + existing_value if side_lower == "buy" else position_value

        # Daily P&L (UTC)
        now = datetime.utcnow()
        start_of_today = datetime(now.year, now.month, now.day)
        start_ts = int(start_of_today.timestamp() * 1000)
        end_ts = int(now.timestamp() * 1000)
        today_trades = self.trade_repo.get_between(start_ts, end_ts)
        today_pnl = self.portfolio_engine.calculate_realized_pnl_from_trades(today_trades)

        peak_equity = self.portfolio_engine.get_peak_equity()
        if peak_equity <= 0:
            peak_equity = portfolio_value

        result = risk_manager.check_can_trade(
            today_pnl=today_pnl,
            position_size=position_size,
            portfolio_value=portfolio_value,
            total_exposure=total_exposure,
            peak_equity=peak_equity,
        )

        if not result.get("can_trade", True):
            raise ValueError(result.get("reason", "Risk limits exceeded"))

    def scan_market(self, symbol: str, timeframe: str = "1h", df: pd.DataFrame = None) -> ScanResult:
        """
        Run comprehensive market scan using all technical indicators
        Returns aggregated signals and individual indicator results

        Args:
            symbol: Trading pair symbol
            timeframe: Candle timeframe (e.g., "1h", "4h", "1d")
            df: Optional DataFrame with OHLCV data. If not provided, fetches from exchange.
        """
        # Fetch OHLCV data if not provided
        if df is None:
            df = self.fetch_ohlcv(symbol, timeframe)

        open_prices = df["open"].values
        high = df["high"].values
        low = df["low"].values
        close = df["close"].values
        volume = df["volume"].values

        indicators = []
        score_total = 0.0

        # RSI
        try:
            rsi = ta.RSI(close, timeperiod=14)
            rsi_value = rsi[-1]
            rsi_prev = float(rsi[-2]) if len(rsi) > 1 and not np.isnan(rsi[-2]) else None
            rsi_score = 0
            rsi_signal = "neutral"

            if rsi_value < 30:
                rsi_score = 2
                rsi_signal = "oversold"
            elif rsi_value < 40:
                rsi_score = 1
                rsi_signal = "weak"
            elif rsi_value > 70:
                rsi_score = -2
                rsi_signal = "overbought"
            elif rsi_value > 60:
                rsi_score = -1
                rsi_signal = "strong"

            score_total += rsi_score
            indicators.append(
                IndicatorResult(
                    name="RSI",
                    value=float(rsi_value),
                    score=float(rsi_score),
                    signal=rsi_signal,
                    prev_value=rsi_prev,
                )
            )
        except Exception as e:
            logger.warning(f"RSI calculation failed: {e}")

        # MACD
        try:
            macd, macd_signal, macd_hist = ta.MACD(
                close, fastperiod=12, slowperiod=26, signalperiod=9
            )
            macd_prev = float(macd[-2]) if len(macd) > 1 and not np.isnan(macd[-2]) else None
            macd_score = 0
            macd_trend = "neutral"

            if macd[-1] > macd_signal[-1]:
                macd_score = 1
                macd_trend = "bullish"
                if macd[-1] > macd[-2]:
                    macd_score = 2
                    macd_trend = "bullish_rising"
            else:
                macd_score = -1
                macd_trend = "bearish"
                if macd[-1] < macd[-2]:
                    macd_score = -2
                    macd_trend = "bearish_falling"

            score_total += macd_score
            indicators.append(
                IndicatorResult(
                    name="MACD",
                    value=float(macd[-1]),
                    score=float(macd_score),
                    signal=macd_trend,
                    details={
                        "signal_line": float(macd_signal[-1]),
                        "histogram": float(macd_hist[-1]),
                    },
                    prev_value=macd_prev,
                )
            )
        except Exception as e:
            logger.warning(f"MACD calculation failed: {e}")

        # EMA (20 vs 50)
        try:
            ema20 = ta.EMA(close, timeperiod=20)
            ema50 = ta.EMA(close, timeperiod=50)
            ema_prev = float(ema20[-2]) if len(ema20) > 1 and not np.isnan(ema20[-2]) else None
            ema_score = 0
            ema_signal = "neutral"

            if ema20[-1] > ema50[-1]:
                ema_score = 1
                ema_signal = "bullish"
                if ema20[-1] > ema20[-2]:
                    ema_score = 2
                    ema_signal = "bullish_rising"
            else:
                ema_score = -1
                ema_signal = "bearish"

            score_total += ema_score
            indicators.append(
                IndicatorResult(
                    name="EMA",
                    value=float(ema20[-1]),
                    score=float(ema_score),
                    signal=ema_signal,
                    details={"ema20": float(ema20[-1]), "ema50": float(ema50[-1])},
                    prev_value=ema_prev,
                )
            )
        except Exception as e:
            logger.warning(f"EMA calculation failed: {e}")

        # SMA
        try:
            sma20 = ta.SMA(close, timeperiod=20)
            sma50 = ta.SMA(close, timeperiod=50)
            sma_prev = float(sma20[-2]) if len(sma20) > 1 and not np.isnan(sma20[-2]) else None
            sma_score = 0
            sma_signal = "neutral"

            if sma20[-1] > sma50[-1]:
                sma_score = 1
                sma_signal = "bullish"
            else:
                sma_score = -1
                sma_signal = "bearish"

            score_total += sma_score
            indicators.append(
                IndicatorResult(
                    name="SMA",
                    value=float(sma20[-1]),
                    score=float(sma_score),
                    signal=sma_signal,
                    prev_value=sma_prev,
                )
            )
        except Exception as e:
            logger.warning(f"SMA calculation failed: {e}")

        # ADX
        try:
            adx = ta.ADX(high, low, close, timeperiod=14)
            adx_value = adx[-1]
            adx_prev = float(adx[-2]) if len(adx) > 1 and not np.isnan(adx[-2]) else None
            adx_score = 0
            adx_signal = "weak_trend"

            if adx_value > 25:
                adx_signal = "strong_trend"
                adx_score = 1
            if adx_value > 50:
                adx_signal = "very_strong_trend"
                adx_score = 2

            score_total += adx_score
            indicators.append(
                IndicatorResult(
                    name="ADX",
                    value=float(adx_value),
                    score=float(adx_score),
                    signal=adx_signal,
                    prev_value=adx_prev,
                )
            )
        except Exception as e:
            logger.warning(f"ADX calculation failed: {e}")

        # Bollinger Bands
        try:
            upper, middle, lower = ta.BBANDS(close, timeperiod=20)
            bb_prev = float(close[-2]) if len(close) > 1 else None
            bb_score = 0
            bb_signal = "neutral"

            if close[-1] < lower[-1]:
                bb_score = 2
                bb_signal = "oversold"
            elif close[-1] > upper[-1]:
                bb_score = -2
                bb_signal = "overbought"

            score_total += bb_score
            indicators.append(
                IndicatorResult(
                    name="Bollinger Bands",
                    value=float(close[-1]),
                    score=float(bb_score),
                    signal=bb_signal,
                    details={
                        "upper": float(upper[-1]),
                        "middle": float(middle[-1]),
                        "lower": float(lower[-1]),
                    },
                    prev_value=bb_prev,
                )
            )
        except Exception as e:
            logger.warning(f"Bollinger Bands calculation failed: {e}")

        # Stochastic
        try:
            slowk, slowd = ta.STOCH(
                high,
                low,
                close,
                fastk_period=14,
                slowk_period=3,
                slowk_matype=0,
                slowd_period=3,
                slowd_matype=0,
            )
            stoch_prev = float(slowk[-2]) if len(slowk) > 1 and not np.isnan(slowk[-2]) else None
            stoch_score = 0
            stoch_signal = "neutral"

            if slowk[-1] < 20:
                stoch_score = 2
                stoch_signal = "oversold"
            elif slowk[-1] > 80:
                stoch_score = -2
                stoch_signal = "overbought"

            score_total += stoch_score
            indicators.append(
                IndicatorResult(
                    name="Stochastic",
                    value=float(slowk[-1]),
                    score=float(stoch_score),
                    signal=stoch_signal,
                    details={"slowk": float(slowk[-1]), "slowd": float(slowd[-1])},
                    prev_value=stoch_prev,
                )
            )
        except Exception as e:
            logger.warning(f"Stochastic calculation failed: {e}")

        # CCI
        try:
            cci = ta.CCI(high, low, close, timeperiod=20)
            cci_value = cci[-1]
            cci_prev = float(cci[-2]) if len(cci) > 1 and not np.isnan(cci[-2]) else None
            cci_score = 0
            cci_signal = "neutral"

            if cci_value < -100:
                cci_score = 2
                cci_signal = "oversold"
            elif cci_value > 100:
                cci_score = -2
                cci_signal = "overbought"

            score_total += cci_score
            indicators.append(
                IndicatorResult(
                    name="CCI",
                    value=float(cci_value),
                    score=float(cci_score),
                    signal=cci_signal,
                    prev_value=cci_prev,
                )
            )
        except Exception as e:
            logger.warning(f"CCI calculation failed: {e}")

        # MFI (Money Flow Index)
        try:
            mfi = ta.MFI(high, low, close, volume, timeperiod=14)
            mfi_value = mfi[-1]
            mfi_prev = float(mfi[-2]) if len(mfi) > 1 and not np.isnan(mfi[-2]) else None
            mfi_score = 0
            mfi_signal = "neutral"

            if mfi_value < 20:
                mfi_score = 2
                mfi_signal = "oversold"
            elif mfi_value > 80:
                mfi_score = -2
                mfi_signal = "overbought"

            score_total += mfi_score
            indicators.append(
                IndicatorResult(
                    name="MFI",
                    value=float(mfi_value),
                    score=float(mfi_score),
                    signal=mfi_signal,
                    prev_value=mfi_prev,
                )
            )
        except Exception as e:
            logger.warning(f"MFI calculation failed: {e}")

        # Aroon
        try:
            aroon_down, aroon_up = ta.AROON(high, low, timeperiod=25)
            aroon_prev = float(aroon_up[-2] - aroon_down[-2]) if len(aroon_up) > 1 and not np.isnan(aroon_up[-2]) else None
            aroon_score = 0
            aroon_signal = "neutral"

            if aroon_up[-1] > 70 and aroon_down[-1] < 30:
                aroon_score = 2
                aroon_signal = "bullish"
            elif aroon_down[-1] > 70 and aroon_up[-1] < 30:
                aroon_score = -2
                aroon_signal = "bearish"

            score_total += aroon_score
            indicators.append(
                IndicatorResult(
                    name="Aroon",
                    value=float(aroon_up[-1] - aroon_down[-1]),
                    score=float(aroon_score),
                    signal=aroon_signal,
                    details={
                        "aroon_up": float(aroon_up[-1]),
                        "aroon_down": float(aroon_down[-1]),
                    },
                    prev_value=aroon_prev,
                )
            )
        except Exception as e:
            logger.warning(f"Aroon calculation failed: {e}")

        # APO (Absolute Price Oscillator)
        try:
            apo = ta.APO(close, fastperiod=12, slowperiod=26, matype=0)
            apo_value = apo[-1]
            apo_prev = float(apo[-2]) if len(apo) > 1 and not np.isnan(apo[-2]) else None
            apo_score = 0
            apo_signal = "neutral"

            if apo_value > 0:
                apo_score = 1
                apo_signal = "bullish"
                if apo_value > apo[-2]:
                    apo_score = 2
                    apo_signal = "bullish_rising"
            else:
                apo_score = -1
                apo_signal = "bearish"
                if apo_value < apo[-2]:
                    apo_score = -2
                    apo_signal = "bearish_falling"

            score_total += apo_score
            indicators.append(
                IndicatorResult(
                    name="APO",
                    value=float(apo_value),
                    score=float(apo_score),
                    signal=apo_signal,
                    prev_value=apo_prev,
                )
            )
        except Exception as e:
            logger.warning(f"APO calculation failed: {e}")

        # CMO (Chande Momentum Oscillator)
        try:
            cmo = ta.CMO(close, timeperiod=14)
            cmo_value = cmo[-1]
            cmo_prev = float(cmo[-2]) if len(cmo) > 1 and not np.isnan(cmo[-2]) else None
            cmo_score = 0
            cmo_signal = "neutral"

            if cmo_value < -50:
                cmo_score = 2
                cmo_signal = "oversold"
            elif cmo_value < 0:
                cmo_score = 1
                cmo_signal = "weak"
            elif cmo_value > 50:
                cmo_score = -2
                cmo_signal = "overbought"
            elif cmo_value > 0:
                cmo_score = -1
                cmo_signal = "strong"

            score_total += cmo_score
            indicators.append(
                IndicatorResult(
                    name="CMO",
                    value=float(cmo_value),
                    score=float(cmo_score),
                    signal=cmo_signal,
                    prev_value=cmo_prev,
                )
            )
        except Exception as e:
            logger.warning(f"CMO calculation failed: {e}")

        # DEMA (Double Exponential Moving Average)
        try:
            dema20 = ta.DEMA(close, timeperiod=20)
            dema50 = ta.DEMA(close, timeperiod=50)
            dema_prev = float(dema20[-2]) if len(dema20) > 1 and not np.isnan(dema20[-2]) else None
            dema_score = 0
            dema_signal = "neutral"

            if dema20[-1] > dema50[-1]:
                dema_score = 1
                dema_signal = "bullish"
                if close[-1] > dema20[-1]:
                    dema_score = 2
                    dema_signal = "bullish_above"
            else:
                dema_score = -1
                dema_signal = "bearish"
                if close[-1] < dema20[-1]:
                    dema_score = -2
                    dema_signal = "bearish_below"

            score_total += dema_score
            indicators.append(
                IndicatorResult(
                    name="DEMA",
                    value=float(dema20[-1]),
                    score=float(dema_score),
                    signal=dema_signal,
                    details={"dema20": float(dema20[-1]), "dema50": float(dema50[-1])},
                    prev_value=dema_prev,
                )
            )
        except Exception as e:
            logger.warning(f"DEMA calculation failed: {e}")

        # MESA (MAMA - MESA Adaptive Moving Average)
        try:
            mama, fama = ta.MAMA(close, fastlimit=0.5, slowlimit=0.05)
            mama_prev = float(mama[-2]) if len(mama) > 1 and not np.isnan(mama[-2]) else None
            mesa_score = 0
            mesa_signal = "neutral"

            if mama[-1] > fama[-1]:
                mesa_score = 1
                mesa_signal = "bullish"
                if close[-1] > mama[-1]:
                    mesa_score = 2
                    mesa_signal = "bullish_strong"
            else:
                mesa_score = -1
                mesa_signal = "bearish"
                if close[-1] < mama[-1]:
                    mesa_score = -2
                    mesa_signal = "bearish_strong"

            score_total += mesa_score
            indicators.append(
                IndicatorResult(
                    name="MESA",
                    value=float(mama[-1]),
                    score=float(mesa_score),
                    signal=mesa_signal,
                    details={"mama": float(mama[-1]), "fama": float(fama[-1])},
                    prev_value=mama_prev,
                )
            )
        except Exception as e:
            logger.warning(f"MESA calculation failed: {e}")

        # KAMA (Kaufman Adaptive Moving Average)
        try:
            kama = ta.KAMA(close, timeperiod=30)
            kama_value = kama[-1]
            kama_prev = float(kama[-2]) if len(kama) > 1 and not np.isnan(kama[-2]) else None
            kama_score = 0
            kama_signal = "neutral"

            if close[-1] > kama_value:
                kama_score = 1
                kama_signal = "bullish"
                if kama_value > kama[-2]:
                    kama_score = 2
                    kama_signal = "bullish_rising"
            else:
                kama_score = -1
                kama_signal = "bearish"
                if kama_value < kama[-2]:
                    kama_score = -2
                    kama_signal = "bearish_falling"

            score_total += kama_score
            indicators.append(
                IndicatorResult(
                    name="KAMA",
                    value=float(kama_value),
                    score=float(kama_score),
                    signal=kama_signal,
                    prev_value=kama_prev,
                )
            )
        except Exception as e:
            logger.warning(f"KAMA calculation failed: {e}")

        # MOM (Momentum)
        try:
            mom = ta.MOM(close, timeperiod=10)
            mom_value = mom[-1]
            mom_prev = float(mom[-2]) if len(mom) > 1 and not np.isnan(mom[-2]) else None
            mom_score = 0
            mom_signal = "neutral"

            if mom_value > 0:
                mom_score = 1
                mom_signal = "bullish"
                if mom_value > mom[-2]:
                    mom_score = 2
                    mom_signal = "bullish_accelerating"
            else:
                mom_score = -1
                mom_signal = "bearish"
                if mom_value < mom[-2]:
                    mom_score = -2
                    mom_signal = "bearish_accelerating"

            score_total += mom_score
            indicators.append(
                IndicatorResult(
                    name="MOM",
                    value=float(mom_value),
                    score=float(mom_score),
                    signal=mom_signal,
                    prev_value=mom_prev,
                )
            )
        except Exception as e:
            logger.warning(f"MOM calculation failed: {e}")

        # PPO (Percentage Price Oscillator)
        try:
            ppo = ta.PPO(close, fastperiod=12, slowperiod=26, matype=0)
            ppo_value = ppo[-1]
            ppo_prev = float(ppo[-2]) if len(ppo) > 1 and not np.isnan(ppo[-2]) else None
            ppo_score = 0
            ppo_signal = "neutral"

            if ppo_value > 0:
                ppo_score = 1
                ppo_signal = "bullish"
                if ppo_value > ppo[-2]:
                    ppo_score = 2
                    ppo_signal = "bullish_rising"
            else:
                ppo_score = -1
                ppo_signal = "bearish"
                if ppo_value < ppo[-2]:
                    ppo_score = -2
                    ppo_signal = "bearish_falling"

            score_total += ppo_score
            indicators.append(
                IndicatorResult(
                    name="PPO",
                    value=float(ppo_value),
                    score=float(ppo_score),
                    signal=ppo_signal,
                    prev_value=ppo_prev,
                )
            )
        except Exception as e:
            logger.warning(f"PPO calculation failed: {e}")

        # SAR (Parabolic SAR)
        try:
            sar = ta.SAR(high, low, acceleration=0.02, maximum=0.2)
            sar_value = sar[-1]
            sar_prev = float(sar[-2]) if len(sar) > 1 and not np.isnan(sar[-2]) else None
            sar_score = 0
            sar_signal = "neutral"

            if close[-1] > sar_value:
                sar_score = 2
                sar_signal = "bullish"
            else:
                sar_score = -2
                sar_signal = "bearish"

            score_total += sar_score
            indicators.append(
                IndicatorResult(
                    name="SAR",
                    value=float(sar_value),
                    score=float(sar_score),
                    signal=sar_signal,
                    prev_value=sar_prev,
                )
            )
        except Exception as e:
            logger.warning(f"SAR calculation failed: {e}")

        # TRIMA (Triangular Moving Average)
        try:
            trima = ta.TRIMA(close, timeperiod=30)
            trima_value = trima[-1]
            trima_prev = float(trima[-2]) if len(trima) > 1 and not np.isnan(trima[-2]) else None
            trima_score = 0
            trima_signal = "neutral"

            if close[-1] > trima_value:
                trima_score = 1
                trima_signal = "bullish"
                if trima_value > trima[-2]:
                    trima_score = 2
                    trima_signal = "bullish_rising"
            else:
                trima_score = -1
                trima_signal = "bearish"
                if trima_value < trima[-2]:
                    trima_score = -2
                    trima_signal = "bearish_falling"

            score_total += trima_score
            indicators.append(
                IndicatorResult(
                    name="TRIMA",
                    value=float(trima_value),
                    score=float(trima_score),
                    signal=trima_signal,
                    prev_value=trima_prev,
                )
            )
        except Exception as e:
            logger.warning(f"TRIMA calculation failed: {e}")

        # TRIX (Triple Exponential Average)
        try:
            trix = ta.TRIX(close, timeperiod=30)
            trix_value = trix[-1]
            trix_prev = float(trix[-2]) if len(trix) > 1 and not np.isnan(trix[-2]) else None
            trix_score = 0
            trix_signal = "neutral"

            if trix_value > 0:
                trix_score = 1
                trix_signal = "bullish"
                if trix_value > trix[-2]:
                    trix_score = 2
                    trix_signal = "bullish_rising"
            else:
                trix_score = -1
                trix_signal = "bearish"
                if trix_value < trix[-2]:
                    trix_score = -2
                    trix_signal = "bearish_falling"

            score_total += trix_score
            indicators.append(
                IndicatorResult(
                    name="TRIX",
                    value=float(trix_value),
                    score=float(trix_score),
                    signal=trix_signal,
                    prev_value=trix_prev,
                )
            )
        except Exception as e:
            logger.warning(f"TRIX calculation failed: {e}")

        # T3 (Triple Exponential Moving Average)
        try:
            t3 = ta.T3(close, timeperiod=5, vfactor=0.7)
            t3_value = t3[-1]
            t3_prev = float(t3[-2]) if len(t3) > 1 and not np.isnan(t3[-2]) else None
            t3_score = 0
            t3_signal = "neutral"

            if close[-1] > t3_value:
                t3_score = 1
                t3_signal = "bullish"
                if t3_value > t3[-2]:
                    t3_score = 2
                    t3_signal = "bullish_rising"
            else:
                t3_score = -1
                t3_signal = "bearish"
                if t3_value < t3[-2]:
                    t3_score = -2
                    t3_signal = "bearish_falling"

            score_total += t3_score
            indicators.append(
                IndicatorResult(
                    name="T3",
                    value=float(t3_value),
                    score=float(t3_score),
                    signal=t3_signal,
                    prev_value=t3_prev,
                )
            )
        except Exception as e:
            logger.warning(f"T3 calculation failed: {e}")

        # ROC (Rate of Change)
        try:
            roc = ta.ROC(close, timeperiod=10)
            roc_value = roc[-1]
            roc_prev = float(roc[-2]) if len(roc) > 1 and not np.isnan(roc[-2]) else None
            roc_score = 0
            roc_signal = "neutral"

            if roc_value > 5:
                roc_score = 2
                roc_signal = "strong_bullish"
            elif roc_value > 0:
                roc_score = 1
                roc_signal = "bullish"
            elif roc_value < -5:
                roc_score = -2
                roc_signal = "strong_bearish"
            else:
                roc_score = -1
                roc_signal = "bearish"

            score_total += roc_score
            indicators.append(
                IndicatorResult(
                    name="ROC",
                    value=float(roc_value),
                    score=float(roc_score),
                    signal=roc_signal,
                    prev_value=roc_prev,
                )
            )
        except Exception as e:
            logger.warning(f"ROC calculation failed: {e}")

        # WMA (Weighted Moving Average)
        try:
            wma20 = ta.WMA(close, timeperiod=20)
            wma50 = ta.WMA(close, timeperiod=50)
            wma_prev = float(wma20[-2]) if len(wma20) > 1 and not np.isnan(wma20[-2]) else None
            wma_score = 0
            wma_signal = "neutral"

            if wma20[-1] > wma50[-1]:
                wma_score = 1
                wma_signal = "bullish"
                if close[-1] > wma20[-1]:
                    wma_score = 2
                    wma_signal = "bullish_above"
            else:
                wma_score = -1
                wma_signal = "bearish"
                if close[-1] < wma20[-1]:
                    wma_score = -2
                    wma_signal = "bearish_below"

            score_total += wma_score
            indicators.append(
                IndicatorResult(
                    name="WMA",
                    value=float(wma20[-1]),
                    score=float(wma_score),
                    signal=wma_signal,
                    details={"wma20": float(wma20[-1]), "wma50": float(wma50[-1])},
                    prev_value=wma_prev,
                )
            )
        except Exception as e:
            logger.warning(f"WMA calculation failed: {e}")

        # ATR (Average True Range) - volatility indicator
        try:
            atr = ta.ATR(high, low, close, timeperiod=14)
            atr_value = atr[-1]
            atr_prev = float(atr[-2]) if len(atr) > 1 and not np.isnan(atr[-2]) else None
            atr_pct = (atr_value / close[-1]) * 100  # As percentage of price
            atr_score = 0
            atr_signal = "low_volatility"

            if atr_pct > 5:
                atr_score = 0  # High volatility - neutral but informative
                atr_signal = "high_volatility"
            elif atr_pct > 2:
                atr_score = 1  # Moderate volatility - good for trading
                atr_signal = "moderate_volatility"

            score_total += atr_score
            indicators.append(
                IndicatorResult(
                    name="ATR",
                    value=float(atr_value),
                    score=float(atr_score),
                    signal=atr_signal,
                    details={"atr_pct": float(atr_pct)},
                    prev_value=atr_prev,
                )
            )
        except Exception as e:
            logger.warning(f"ATR calculation failed: {e}")

        # OBV (On Balance Volume)
        try:
            obv = ta.OBV(close, volume)
            obv_value = obv[-1]
            obv_prev = float(obv[-2]) if len(obv) > 1 and not np.isnan(obv[-2]) else None
            obv_score = 0
            obv_signal = "neutral"

            # Compare OBV trend with price trend
            obv_trend = obv[-1] > obv[-5] if len(obv) > 5 else obv[-1] > obv[-2]
            price_trend = close[-1] > close[-5] if len(close) > 5 else close[-1] > close[-2]

            if obv_trend and price_trend:
                obv_score = 2
                obv_signal = "bullish_confirmed"
            elif obv_trend and not price_trend:
                obv_score = 1
                obv_signal = "bullish_divergence"
            elif not obv_trend and not price_trend:
                obv_score = -2
                obv_signal = "bearish_confirmed"
            else:
                obv_score = -1
                obv_signal = "bearish_divergence"

            score_total += obv_score
            indicators.append(
                IndicatorResult(
                    name="OBV",
                    value=float(obv_value),
                    score=float(obv_score),
                    signal=obv_signal,
                    prev_value=obv_prev,
                )
            )
        except Exception as e:
            logger.warning(f"OBV calculation failed: {e}")

        # WILLR (Williams %R)
        try:
            willr = ta.WILLR(high, low, close, timeperiod=14)
            willr_value = willr[-1]
            willr_prev = float(willr[-2]) if len(willr) > 1 and not np.isnan(willr[-2]) else None
            willr_score = 0
            willr_signal = "neutral"

            if willr_value < -80:
                willr_score = 2
                willr_signal = "oversold"
            elif willr_value < -50:
                willr_score = 1
                willr_signal = "weak"
            elif willr_value > -20:
                willr_score = -2
                willr_signal = "overbought"
            elif willr_value > -50:
                willr_score = -1
                willr_signal = "strong"

            score_total += willr_score
            indicators.append(
                IndicatorResult(
                    name="WILLR",
                    value=float(willr_value),
                    score=float(willr_score),
                    signal=willr_signal,
                    prev_value=willr_prev,
                )
            )
        except Exception as e:
            logger.warning(f"WILLR calculation failed: {e}")

        # ULTOSC (Ultimate Oscillator)
        try:
            ultosc = ta.ULTOSC(high, low, close, timeperiod1=7, timeperiod2=14, timeperiod3=28)
            ultosc_value = ultosc[-1]
            ultosc_prev = float(ultosc[-2]) if len(ultosc) > 1 and not np.isnan(ultosc[-2]) else None
            ultosc_score = 0
            ultosc_signal = "neutral"

            if ultosc_value < 30:
                ultosc_score = 2
                ultosc_signal = "oversold"
            elif ultosc_value < 50:
                ultosc_score = 1
                ultosc_signal = "weak"
            elif ultosc_value > 70:
                ultosc_score = -2
                ultosc_signal = "overbought"
            elif ultosc_value > 50:
                ultosc_score = -1
                ultosc_signal = "strong"

            score_total += ultosc_score
            indicators.append(
                IndicatorResult(
                    name="ULTOSC",
                    value=float(ultosc_value),
                    score=float(ultosc_score),
                    signal=ultosc_signal,
                    prev_value=ultosc_prev,
                )
            )
        except Exception as e:
            logger.warning(f"ULTOSC calculation failed: {e}")

        # Determine overall signal (adjusted for 27 indicators)
        if score_total >= 27:
            trade_signal = TrendSignal.STRONG_BUY
        elif score_total >= 13:
            trade_signal = TrendSignal.BUY
        elif score_total <= -27:
            trade_signal = TrendSignal.STRONG_SELL
        elif score_total <= -13:
            trade_signal = TrendSignal.SELL
        else:
            trade_signal = TrendSignal.HOLD

        return ScanResult(
            symbol=symbol,
            exchange=self.exchange_name,
            timeframe=timeframe,
            timestamp=datetime.utcnow(),
            score_total=score_total,
            trade_signal=trade_signal,
            indicators=indicators,
            ohlcv={
                "open": float(open_prices[-1]),
                "high": float(high[-1]),
                "low": float(low[-1]),
                "close": float(close[-1]),
                "volume": float(volume[-1]),
            },
        )

    def place_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
        order_type: str = "market",
    ) -> Dict[str, Any]:
        """
        Place an order (market or limit)
        In paper trading mode, returns a simulated order
        """
        # Enforce risk limits before placing the order
        self._enforce_risk_limits(symbol, side, amount, price)

        if self.paper_trading:
            logger.info(
                f"PAPER TRADE: {side.upper()} {amount} {symbol} @ {price or 'market'}"
            )
            return self._execute_paper_trade(symbol, side, amount, price, order_type)

        try:
            if order_type == "market":
                if side.lower() == "buy":
                    return self._api_call_with_retry(
                        self.exchange.create_market_buy_order, symbol, amount
                    )
                else:
                    return self._api_call_with_retry(
                        self.exchange.create_market_sell_order, symbol, amount
                    )
            else:
                if side.lower() == "buy":
                    return self._api_call_with_retry(
                        self.exchange.create_limit_buy_order, symbol, amount, price
                    )
                else:
                    return self._api_call_with_retry(
                        self.exchange.create_limit_sell_order, symbol, amount, price
                    )
        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            raise

    def cancel_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """Cancel an open order"""
        if self.paper_trading:
            return {"id": order_id, "status": "canceled", "paper_trade": True}

        try:
            return self._api_call_with_retry(
                self.exchange.cancel_order, order_id, symbol
            )
        except Exception as e:
            logger.error(f"Failed to cancel order: {e}")
            raise
