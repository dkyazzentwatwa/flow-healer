from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from pydantic import BaseModel, Field
import uuid
from api.models import AutomationRule, AutomationRuleRepository
from api.paper import PaperAccount

router = APIRouter(prefix="/api/automation", tags=["Automation"])
rule_repo = AutomationRuleRepository()
paper_account = PaperAccount()

class RuleCreate(BaseModel):
    name: str
    symbol: str
    timeframe: str
    side: str  # "buy" or "sell"
    signal_type: str = Field(..., alias="signalType")
    amount: float
    amount_type: str = Field(default="fixed", alias="amountType")  # "fixed" or "percent"
    trigger_type: str = Field(default="signal", alias="triggerType")
    min_score: Optional[float] = Field(default=None, alias="minScore")
    stop_loss_pct: Optional[float] = Field(default=None, alias="stopLossPct")
    take_profit_pct: Optional[float] = Field(default=None, alias="takeProfitPct")
    trailing_stop_pct: Optional[float] = Field(default=None, alias="trailingStopPct")
    only_if_in_position: bool = Field(default=True, alias="onlyIfInPosition")
    reduce_only: bool = Field(default=True, alias="reduceOnly")
    min_profit_pct: Optional[float] = Field(default=None, alias="minProfitPct")
    break_even_after_pct: Optional[float] = Field(default=None, alias="breakEvenAfterPct")
    max_hold_bars: Optional[int] = Field(default=None, alias="maxHoldBars")
    cooldown_minutes: int = Field(default=60, alias="cooldownMinutes")
    conditions: Optional[str] = None

    class Config:
        allow_population_by_field_name = True

class RuleUpdate(BaseModel):
    name: Optional[str] = None
    symbol: Optional[str] = None
    timeframe: Optional[str] = None
    side: Optional[str] = None
    signal_type: Optional[str] = Field(default=None, alias="signalType")
    amount: Optional[float] = None
    amount_type: Optional[str] = Field(default=None, alias="amountType")
    trigger_type: Optional[str] = Field(default=None, alias="triggerType")
    min_score: Optional[float] = Field(default=None, alias="minScore")
    stop_loss_pct: Optional[float] = Field(default=None, alias="stopLossPct")
    take_profit_pct: Optional[float] = Field(default=None, alias="takeProfitPct")
    trailing_stop_pct: Optional[float] = Field(default=None, alias="trailingStopPct")
    only_if_in_position: Optional[bool] = Field(default=None, alias="onlyIfInPosition")
    reduce_only: Optional[bool] = Field(default=None, alias="reduceOnly")
    min_profit_pct: Optional[float] = Field(default=None, alias="minProfitPct")
    break_even_after_pct: Optional[float] = Field(default=None, alias="breakEvenAfterPct")
    max_hold_bars: Optional[int] = Field(default=None, alias="maxHoldBars")
    cooldown_minutes: Optional[int] = Field(default=None, alias="cooldownMinutes")
    conditions: Optional[str] = None

    class Config:
        allow_population_by_field_name = True

class RuleToggle(BaseModel):
    is_active: bool = Field(..., alias="isActive")

    class Config:
        allow_population_by_field_name = True

class BalanceSet(BaseModel):
    currency: str
    amount: float

@router.get("/rules", response_model=List[AutomationRule])
async def get_rules():
    return rule_repo.get_all()

@router.post("/rules", response_model=AutomationRule)
async def create_rule(rule: RuleCreate):
    new_rule = AutomationRule(
        id=str(uuid.uuid4()),
        name=rule.name,
        symbol=rule.symbol,
        timeframe=rule.timeframe,
        side=rule.side.lower(),
        trigger_type=rule.trigger_type.lower(),
        signal_type=rule.signal_type.upper(),
        amount=rule.amount,
        amount_type=rule.amount_type.lower(),
        min_score=rule.min_score,
        stop_loss_pct=rule.stop_loss_pct,
        take_profit_pct=rule.take_profit_pct,
        trailing_stop_pct=rule.trailing_stop_pct,
        only_if_in_position=rule.only_if_in_position,
        reduce_only=rule.reduce_only,
        min_profit_pct=rule.min_profit_pct,
        break_even_after_pct=rule.break_even_after_pct,
        max_hold_bars=rule.max_hold_bars,
        is_active=True,
        last_triggered=0,
        cooldown_minutes=rule.cooldown_minutes,
        conditions=rule.conditions
    )
    return rule_repo.create(new_rule)

@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str):
    rule_repo.delete(rule_id)
    return {"status": "deleted"}

@router.patch("/rules/{rule_id}/toggle")
async def toggle_rule(rule_id: str, toggle: RuleToggle):
    rule_repo.toggle_active(rule_id, toggle.is_active)
    return {"status": "updated", "is_active": toggle.is_active}

@router.patch("/rules/{rule_id}")
async def update_rule(rule_id: str, updates: RuleUpdate):
    existing = rule_repo.get_by_id(rule_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Rule not found")

    payload = updates.dict(exclude_unset=True, by_alias=False)
    updated = rule_repo.update(rule_id, payload)
    if not updated:
        raise HTTPException(status_code=400, detail="Failed to update rule")
    return updated

@router.post("/paper/balance")
async def set_paper_balance(balance: BalanceSet):
    """Set paper trading balance for a currency"""
    try:
        paper_account.set_balance(balance.currency, balance.amount)
        return {"status": "success", "currency": balance.currency, "amount": balance.amount}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/paper/reset")
async def reset_paper_account(start_balance: Optional[float] = None):
    """Reset all paper trading balances"""
    paper_account.reset(start_balance)
    return {"status": "reset", "start_balance": start_balance or 10000}
