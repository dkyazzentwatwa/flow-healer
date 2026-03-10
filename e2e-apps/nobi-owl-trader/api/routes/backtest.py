from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import json

from api.backtest.downloader import DataDownloader
from api.backtest.engine import BacktestEngine
from api.trading_engine import TradingEngine
from api.models import AutomationRuleRepository
from api.database import get_db_connection

router = APIRouter(prefix="/api/backtest", tags=["Backtest"])
rule_repo = AutomationRuleRepository()

class DownloadRequest(BaseModel):
    symbol: str
    timeframe: str
    days: int = 30

class BacktestRequest(BaseModel):
    rule_id: str
    exit_rule_id: Optional[str] = None
    start_days_ago: int = 30
    initial_balance: float = 10000.0

@router.post("/download")
async def download_data(req: DownloadRequest):
    """Download historical data for a symbol/timeframe"""
    engine = TradingEngine()
    downloader = DataDownloader(engine)
    try:
        downloader.sync_data(req.symbol, req.timeframe, days=req.days)
        return {"status": "success", "message": f"Data sync started for {req.symbol}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/run")
async def run_backtest(req: BacktestRequest):
    """Run a backtest using an existing automation rule"""
    # 1. Fetch rule
    rules = rule_repo.get_all()
    rule = next((r for r in rules if r.id == req.rule_id), None)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    exit_rule = None
    if req.exit_rule_id:
        exit_rule = next((r for r in rules if r.id == req.exit_rule_id), None)
        if not exit_rule:
            raise HTTPException(status_code=404, detail="Exit rule not found")

    # 2. Setup dates
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=req.start_days_ago)

    # 3. Run engine
    engine = TradingEngine()
    bt_engine = BacktestEngine(engine)
    
    try:
        if exit_rule:
            results = bt_engine.run_pair(rule, exit_rule, start_dt, end_dt, req.initial_balance)
        else:
            results = bt_engine.run(rule, start_dt, end_dt, req.initial_balance)
        if "error" in results:
            raise HTTPException(status_code=400, detail=results["error"])

        # Save results to DB
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO backtest_results (
                id, timestamp, rule_id, symbol, timeframe, start_date, end_date,
                initial_balance, final_balance, total_trades, win_rate, max_drawdown, details
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                results["id"],
                results["timestamp"],
                rule.id,
                results["symbol"],
                results["timeframe"],
                start_dt.isoformat(),
                end_dt.isoformat(),
                results["initial_balance"],
                results["final_balance"],
                results["total_trades"],
                results["win_rate"],
                results.get("max_drawdown", 0.0),
                json.dumps(results["trades"]),
            ),
        )
        conn.commit()

        return results
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/results")
async def get_backtest_results():
    """Fetch previous backtest results"""
    conn = get_db_connection()
    cursor = conn.cursor()
    rows = cursor.execute("SELECT * FROM backtest_results ORDER BY timestamp DESC").fetchall()
    return [dict(row) for row in rows]
