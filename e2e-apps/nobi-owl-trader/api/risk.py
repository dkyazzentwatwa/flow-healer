from dataclasses import dataclass
from typing import Dict, Any, Optional
import math
import time
from api.database import get_db_connection

@dataclass
class RiskLimits:
    max_daily_loss: float = 500.0  # Max loss per day in USD
    max_drawdown_pct: float = 20.0  # Max drawdown vs peak equity (percent)
    max_position_size_pct: float = 20.0  # Max % of portfolio per position
    max_exposure_pct: float = 80.0  # Max % total exposure
    stop_loss_pct: float = 5.0  # Default stop loss % for paper trades
    take_profit_pct: float = 10.0  # Default take profit % for paper trades
    trailing_stop_pct: float = 3.0  # Default trailing stop %


class RiskLimitsRepository:
    def __init__(self):
        self.conn = get_db_connection()

    def get(self) -> RiskLimits:
        cursor = self.conn.cursor()
        row = cursor.execute("SELECT * FROM risk_limits WHERE id = 1").fetchone()
        if row:
            max_drawdown_pct = row["max_drawdown_pct"]
            # Normalize legacy fractional values (e.g. 0.2 => 20%)
            if max_drawdown_pct < 1:
                max_drawdown_pct *= 100
            stop_loss_pct = row["stop_loss_pct"]
            take_profit_pct = row["take_profit_pct"]
            trailing_stop_pct = row["trailing_stop_pct"]

            if stop_loss_pct < 1:
                stop_loss_pct *= 100
            if take_profit_pct < 1:
                take_profit_pct *= 100
            if trailing_stop_pct < 1:
                trailing_stop_pct *= 100

            max_position_size_pct = row["max_position_size_pct"]
            max_exposure_pct = row["max_exposure_pct"]

            if max_position_size_pct < 1:
                max_position_size_pct *= 100
            if max_exposure_pct < 1:
                max_exposure_pct *= 100

            return RiskLimits(
                max_daily_loss=row["max_daily_loss"],
                max_drawdown_pct=max_drawdown_pct,
                max_position_size_pct=max_position_size_pct,
                max_exposure_pct=max_exposure_pct,
                stop_loss_pct=stop_loss_pct,
                take_profit_pct=take_profit_pct,
                trailing_stop_pct=trailing_stop_pct,
            )

        # Seed defaults
        limits = RiskLimits()
        now = int(time.time() * 1000)
        cursor.execute(
            """
            INSERT INTO risk_limits (
                id, max_daily_loss, max_drawdown_pct, max_position_size_pct,
                max_exposure_pct, stop_loss_pct, take_profit_pct, trailing_stop_pct, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                limits.max_daily_loss,
                limits.max_drawdown_pct,
                limits.max_position_size_pct,
                limits.max_exposure_pct,
                limits.stop_loss_pct,
                limits.take_profit_pct,
                limits.trailing_stop_pct,
                now,
            ),
        )
        self.conn.commit()
        return limits

    def save(self, limits: RiskLimits) -> RiskLimits:
        now = int(time.time() * 1000)
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO risk_limits (
                id, max_daily_loss, max_drawdown_pct, max_position_size_pct,
                max_exposure_pct, stop_loss_pct, take_profit_pct, trailing_stop_pct, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                max_daily_loss = excluded.max_daily_loss,
                max_drawdown_pct = excluded.max_drawdown_pct,
                max_position_size_pct = excluded.max_position_size_pct,
                max_exposure_pct = excluded.max_exposure_pct,
                stop_loss_pct = excluded.stop_loss_pct,
                take_profit_pct = excluded.take_profit_pct,
                trailing_stop_pct = excluded.trailing_stop_pct,
                updated_at = excluded.updated_at
            """,
            (
                1,
                limits.max_daily_loss,
                limits.max_drawdown_pct,
                limits.max_position_size_pct,
                limits.max_exposure_pct,
                limits.stop_loss_pct,
                limits.take_profit_pct,
                limits.trailing_stop_pct,
                now,
            ),
        )
        self.conn.commit()
        return limits

class RiskManager:
    def __init__(self, limits: RiskLimits = None):
        self.limits = limits or RiskLimits()

    @staticmethod
    def _is_valid_number(value: float) -> bool:
        if isinstance(value, bool):
            return False
        return isinstance(value, (int, float)) and math.isfinite(value)

    def _invalid_input_result(self, field_name: str) -> Dict[str, Any]:
        return {
            "can_trade": False,
            "reason": f"Invalid {field_name}",
            "warning": None,
            "risk_metrics": {},
        }

    def check_can_trade(
        self,
        today_pnl: float = 0.0,
        position_size: float = 0.0,
        portfolio_value: float = 10000.0,
        total_exposure: float = 0.0,
        peak_equity: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Check if trading is allowed based on risk limits.

        Returns:
            Dict with can_trade (bool), reason (str), warning (str or None)
        """
        if not self._is_valid_number(today_pnl):
            return self._invalid_input_result("today P&L")
        if not self._is_valid_number(position_size) or position_size < 0:
            return self._invalid_input_result("position size")
        if not self._is_valid_number(portfolio_value) or portfolio_value <= 0:
            return self._invalid_input_result("portfolio value")
        if not self._is_valid_number(total_exposure) or total_exposure < 0:
            return self._invalid_input_result("total exposure")
        if peak_equity is not None and (
            not self._is_valid_number(peak_equity) or peak_equity <= 0
        ):
            return self._invalid_input_result("peak equity")

        # Check daily loss limit
        position_pct = 0.0
        exposure_pct = 0.0
        if portfolio_value > 0:
            position_pct = (position_size / portfolio_value) * 100
            exposure_pct = (total_exposure / portfolio_value) * 100

        drawdown = 0.0
        drawdown_pct = 0.0
        if peak_equity and peak_equity > 0:
            drawdown = max(peak_equity - portfolio_value, 0.0)
            drawdown_pct = drawdown / peak_equity

        daily_loss_pct = (
            (abs(today_pnl) / self.limits.max_daily_loss) * 100
            if self.limits.max_daily_loss > 0
            else 0.0
        )

        risk_metrics = {
            "today_pnl": today_pnl,
            "portfolio_value": portfolio_value,
            "position_size": position_size,
            "total_exposure": total_exposure,
            "position_pct": position_pct,
            "exposure_pct": exposure_pct,
            "peak_equity": peak_equity,
            "drawdown": drawdown,
            "drawdown_pct": drawdown_pct,
            "daily_loss_pct": daily_loss_pct,
            "max_daily_loss": self.limits.max_daily_loss,
            "max_drawdown_pct": self.limits.max_drawdown_pct,
            "max_position_size_pct": self.limits.max_position_size_pct,
            "max_exposure_pct": self.limits.max_exposure_pct,
        }

        if today_pnl <= -self.limits.max_daily_loss:
            return {
                "can_trade": False,
                "reason": f"Daily loss limit of ${self.limits.max_daily_loss} reached",
                "warning": None,
                "risk_metrics": risk_metrics,
            }

        # Warning if approaching limit (80%)
        warning = None
        if today_pnl <= -self.limits.max_daily_loss * 0.8:
            warning = f"Approaching daily loss limit ({abs(today_pnl):.2f} / {self.limits.max_daily_loss})"

        # Check position size limit
        if portfolio_value > 0:
            if position_pct > self.limits.max_position_size_pct:
                return {
                    "can_trade": False,
                    "reason": f"Position size {position_pct:.1f}% exceeds limit of {self.limits.max_position_size_pct}%",
                    "warning": warning,
                    "risk_metrics": risk_metrics,
                }

        # Check total exposure limit
        if portfolio_value > 0:
            if exposure_pct > self.limits.max_exposure_pct:
                return {
                    "can_trade": False,
                    "reason": f"Total exposure {exposure_pct:.1f}% exceeds limit of {self.limits.max_exposure_pct}%",
                    "warning": warning,
                    "risk_metrics": risk_metrics,
                }

        # Check max drawdown vs peak equity
        max_drawdown_fraction = self.limits.max_drawdown_pct / 100
        if peak_equity and peak_equity > 0:
            if drawdown_pct >= max_drawdown_fraction:
                return {
                    "can_trade": False,
                    "reason": f"Max drawdown limit reached ({drawdown_pct:.2%})",
                    "warning": warning,
                    "risk_metrics": risk_metrics
                }

        return {
            "can_trade": True,
            "reason": "All risk checks passed",
            "warning": warning,
            "risk_metrics": risk_metrics,
        }

    def calculate_position_size(
        self,
        portfolio_value: float,
        risk_pct: float,
        stop_loss_pct: float
    ) -> float:
        """
        Calculate safe position size based on risk tolerance.

        Args:
            portfolio_value: Total portfolio value
            risk_pct: % of portfolio willing to risk (e.g., 2.0 for 2%)
            stop_loss_pct: % stop loss distance (e.g., 5.0 for 5%)

        Returns:
            Position size in USD
        """
        if (
            not self._is_valid_number(portfolio_value)
            or portfolio_value <= 0
            or not self._is_valid_number(risk_pct)
            or risk_pct <= 0
            or not self._is_valid_number(stop_loss_pct)
            or stop_loss_pct <= 0
        ):
            return 0.0

        risk_amount = portfolio_value * (risk_pct / 100)
        position_size = risk_amount / (stop_loss_pct / 100)

        # Don't exceed max position size
        max_position = portfolio_value * (self.limits.max_position_size_pct / 100)
        return max(0.0, min(position_size, max_position))
