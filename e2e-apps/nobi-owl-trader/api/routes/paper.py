from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

from api.paper import PaperAccount

router = APIRouter(prefix="/api/paper", tags=["paper"])


class BalanceUpdate(BaseModel):
    currency: str = Field(..., example="USDT")
    total: float = Field(..., ge=0, alias="amount")
    available: Optional[float] = Field(default=None, ge=0)
    locked: Optional[float] = Field(default=None, ge=0)

    class Config:
        allow_population_by_field_name = True


class BalanceReset(BaseModel):
    start_balance: Optional[float] = Field(default=None, ge=0, alias="startBalance")

    class Config:
        allow_population_by_field_name = True


@router.get("/balance")
async def get_paper_balance() -> Dict[str, Any]:
    account = PaperAccount()
    return account.get_balances()


@router.post("/balance")
async def update_paper_balance(payload: BalanceUpdate) -> Dict[str, str]:
    try:
        account = PaperAccount()
        account.set_balance(
            payload.currency,
            payload.total,
            payload.available,
            payload.locked,
        )
        return {"status": "updated"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/reset")
async def reset_paper_balance(payload: BalanceReset) -> Dict[str, str]:
    try:
        account = PaperAccount()
        account.reset(payload.start_balance)
        return {"status": "reset"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
