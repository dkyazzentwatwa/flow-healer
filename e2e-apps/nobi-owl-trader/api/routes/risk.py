from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from datetime import datetime
from api.risk import RiskManager, RiskLimitsRepository

router = APIRouter(prefix="/api/risk", tags=["risk"])

class RiskLimitsUpdate(BaseModel):
    max_daily_loss: Optional[float] = Field(default=None, alias="maxDailyLoss")
    max_drawdown_pct: Optional[float] = Field(default=None, alias="maxDrawdownPercent")
    max_position_size_pct: Optional[float] = Field(default=None, alias="maxPositionSizePercent")
    max_exposure_pct: Optional[float] = Field(default=None, alias="maxExposurePercent")
    stop_loss_pct: Optional[float] = Field(default=None, alias="stopLossPercent")
    take_profit_pct: Optional[float] = Field(default=None, alias="takeProfitPercent")
    trailing_stop_pct: Optional[float] = Field(default=None, alias="trailingStopPercent")

    class Config:
        allow_population_by_field_name = True

class PositionSizeRequest(BaseModel):
    portfolio_value: float
    risk_pct: float
    stop_loss_pct: float

@router.get("/limits")
async def get_risk_limits() -> Dict[str, Any]:
    """Get current risk limits"""
    repo = RiskLimitsRepository()
    limits = repo.get()
    return {
        "max_daily_loss": limits.max_daily_loss,
        "max_drawdown_percent": limits.max_drawdown_pct,
        "max_position_size_percent": limits.max_position_size_pct,
        "max_exposure_percent": limits.max_exposure_pct,
        "stop_loss_percent": limits.stop_loss_pct,
        "take_profit_percent": limits.take_profit_pct,
        "trailing_stop_percent": limits.trailing_stop_pct,
    }

@router.post("/limits")
async def update_risk_limits(limits: RiskLimitsUpdate) -> Dict[str, Any]:
    """Update risk limits"""
    repo = RiskLimitsRepository()
    current = repo.get()
    updates = limits.dict(exclude_unset=True, by_alias=False)
    for key, value in updates.items():
        setattr(current, key, value)
    updated = repo.save(current)
    return {
        "max_daily_loss": updated.max_daily_loss,
        "max_drawdown_percent": updated.max_drawdown_pct,
        "max_position_size_percent": updated.max_position_size_pct,
        "max_exposure_percent": updated.max_exposure_pct,
        "stop_loss_percent": updated.stop_loss_pct,
        "take_profit_percent": updated.take_profit_pct,
        "trailing_stop_percent": updated.trailing_stop_pct,
    }

@router.get("/check")
async def check_risk_status() -> Dict[str, Any]:
    """Check if trading is allowed based on current risk status"""
    from api.portfolio import PortfolioEngine, PositionRepository
    from api.paper import PaperAccount
    from api.routes.portfolio import _get_current_prices
    from api.models import TradeRepository
    
    repo = RiskLimitsRepository()
    limits = repo.get()
    risk_manager = RiskManager(limits)

    engine = PortfolioEngine()
    paper_account = PaperAccount()
    position_repo = PositionRepository()
    
    balances = paper_account.get_balances()
    cash_balance = balances["free"].get(paper_account.base_currency, 0.0)
    
    positions = position_repo.get_all()
    current_prices = _get_current_prices([p.symbol for p in positions])
    
    portfolio_value = engine.get_portfolio_value(cash_balance, current_prices)
    total_exposure = sum(current_prices.get(p.symbol, p.avg_entry_price) * p.amount for p in positions)
    
    # Realized P&L today (UTC)
    now = datetime.utcnow()
    start_of_today = datetime(now.year, now.month, now.day)
    start_ts = int(start_of_today.timestamp() * 1000)
    end_ts = int(now.timestamp() * 1000)
    trades = TradeRepository().get_between(start_ts, end_ts)
    today_pnl = engine.calculate_realized_pnl_from_trades(trades)

    # Peak equity from snapshots (fallback to current value)
    peak_equity = engine.get_peak_equity()
    if peak_equity <= 0:
        peak_equity = portfolio_value

    result = risk_manager.check_can_trade(
        today_pnl=today_pnl,
        portfolio_value=portfolio_value,
        total_exposure=total_exposure,
        peak_equity=peak_equity
    )
    exposure_pct = (total_exposure / portfolio_value * 100) if portfolio_value > 0 else 0.0
    drawdown = max(peak_equity - portfolio_value, 0.0) if peak_equity > 0 else 0.0
    drawdown_pct = (drawdown / peak_equity) if peak_equity > 0 else 0.0

    return {
        **result,
        "today_pnl": round(today_pnl, 2),
        "portfolio_value": round(portfolio_value, 2),
        "total_exposure": round(total_exposure, 2),
        "exposure_percent": round(exposure_pct, 2),
        "peak_equity": round(peak_equity, 2),
        "drawdown": round(drawdown, 2),
        "drawdown_percent": round(drawdown_pct * 100, 2),
    }

@router.post("/calculate-position-size")
async def calculate_position_size(request: PositionSizeRequest) -> Dict[str, float]:
    """Calculate safe position size based on risk parameters"""
    repo = RiskLimitsRepository()
    limits = repo.get()
    risk_manager = RiskManager(limits)
    position_size = risk_manager.calculate_position_size(
        request.portfolio_value,
        request.risk_pct,
        request.stop_loss_pct
    )

    return {
        "position_size": position_size,
        "position_pct": (position_size / request.portfolio_value * 100) if request.portfolio_value > 0 else 0
    }
