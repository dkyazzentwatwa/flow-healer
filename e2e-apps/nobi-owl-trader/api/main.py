"""
NobiBot API - FastAPI Application
Modern REST API for the NobiBot trading engine
"""

import os
import asyncio
import json
from typing import Optional, List
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from .trading_engine import TradingEngine, ScanResult, TrendSignal
from .routes import risk, portfolio, automation, logs, backtest, tuning
from .routes import paper
from .scheduler import AutomationScheduler

load_dotenv()

# Global trading engine instance
engine: Optional[TradingEngine] = None
scheduler: Optional[AutomationScheduler] = None

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass


manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global engine, scheduler
    engine = TradingEngine()
    scheduler = AutomationScheduler(engine)
    scheduler.start()
    print("NobiBot API started (with Automation Scheduler)")
    yield
    # Shutdown
    if scheduler:
        scheduler.stop()
    print("NobiBot API shutting down")


app = FastAPI(
    title="NobiBot Trading API",
    description="Professional cryptocurrency trading bot API with 22 technical indicators",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS middleware for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(risk.router)
app.include_router(portfolio.router)
app.include_router(automation.router)
app.include_router(logs.router)
app.include_router(backtest.router)
app.include_router(tuning.router)
app.include_router(paper.router)


# Pydantic models for request/response
class ScanRequest(BaseModel):
    symbol: str = Field(..., example="BTC/USDT")
    timeframe: str = Field(default="1h", example="1h")


class TradeRequest(BaseModel):
    symbol: str = Field(..., example="BTC/USDT")
    side: str = Field(..., example="buy")
    amount: float = Field(..., example=0.001)
    price: Optional[float] = Field(default=None, example=50000.0)
    order_type: str = Field(default="market", example="market")


class CancelOrderRequest(BaseModel):
    order_id: str
    symbol: str


class IndicatorResponse(BaseModel):
    name: str
    value: float
    score: float
    signal: str
    details: dict = {}


class ScanResponse(BaseModel):
    symbol: str
    exchange: str
    timeframe: str
    timestamp: str
    score_total: float
    trade_signal: str
    indicators: List[IndicatorResponse]
    ohlcv: dict


class BalanceResponse(BaseModel):
    total: dict
    free: dict
    used: dict


class OrderResponse(BaseModel):
    id: str
    symbol: str
    side: str
    type: str
    amount: float
    price: Optional[float]
    status: str
    paper_trade: bool = False


class HealthResponse(BaseModel):
    status: str
    exchange: str
    paper_trading: bool
    timestamp: str


# API Endpoints
@app.get("/", tags=["Health"])
async def root():
    return {"message": "NobiBot Trading API v2.0", "docs": "/docs"}


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Check API health and connection status"""
    return HealthResponse(
        status="healthy",
        exchange=engine.exchange_name,
        paper_trading=engine.paper_trading,
        timestamp=datetime.utcnow().isoformat(),
    )


@app.post("/api/scan", response_model=ScanResponse, tags=["Scanning"])
async def run_scan(request: ScanRequest):
    """
    Run a market scan on the specified symbol
    Returns aggregated score and individual indicator signals
    """
    try:
        result = engine.scan_market(request.symbol, request.timeframe)
        return ScanResponse(
            symbol=result.symbol,
            exchange=result.exchange,
            timeframe=result.timeframe,
            timestamp=result.timestamp.isoformat(),
            score_total=result.score_total,
            trade_signal=result.trade_signal.value,
            indicators=[
                IndicatorResponse(
                    name=ind.name,
                    value=ind.value,
                    score=ind.score,
                    signal=ind.signal,
                    details=ind.details,
                )
                for ind in result.indicators
            ],
            ohlcv=result.ohlcv,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/balance", response_model=BalanceResponse, tags=["Account"])
async def get_balance():
    """Get account balance"""
    try:
        balance = engine.fetch_balance()
        return BalanceResponse(
            total=balance.get("total", {}),
            free=balance.get("free", {}),
            used=balance.get("used", {}),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/orders", tags=["Trading"])
async def get_open_orders(symbol: Optional[str] = Query(default=None)):
    """Get open orders"""
    try:
        orders = engine.fetch_open_orders(symbol)
        return {"orders": orders}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/trade", response_model=OrderResponse, tags=["Trading"])
async def place_trade(request: TradeRequest):
    """
    Place a trade order
    In paper trading mode, simulates the order
    """
    try:
        result = engine.place_order(
            symbol=request.symbol,
            side=request.side,
            amount=request.amount,
            price=request.price,
            order_type=request.order_type,
        )
        return OrderResponse(
            id=result.get("id", ""),
            symbol=result.get("symbol", request.symbol),
            side=result.get("side", request.side),
            type=result.get("type", request.order_type),
            amount=result.get("amount", request.amount),
            price=result.get("price"),
            status=result.get("status", "unknown"),
            paper_trade=result.get("paper_trade", False),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/cancel", tags=["Trading"])
async def cancel_order(request: CancelOrderRequest):
    """Cancel an open order"""
    try:
        result = engine.cancel_order(request.order_id, request.symbol)
        return {"success": True, "order": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ticker/{symbol:path}", tags=["Market Data"])
async def get_ticker(symbol: str):
    """Get current ticker for a symbol"""
    try:
        ticker = engine.get_ticker(symbol)
        pct = ticker.get("percentage")
        change = (float(pct) / 100) if pct is not None else None
        return {
            "symbol": symbol,
            "last": ticker.get("last"),
            "bid": ticker.get("bid"),
            "ask": ticker.get("ask"),
            "high": ticker.get("high"),
            "low": ticker.get("low"),
            "volume": ticker.get("baseVolume"),
            "change": change,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/markets", tags=["Market Data"])
async def get_markets():
    """Get available markets"""
    try:
        markets = engine.get_markets()
        # Return simplified market info
        return {
            "markets": [
                {
                    "symbol": m.get("symbol"),
                    "base": m.get("base"),
                    "quote": m.get("quote"),
                    "active": m.get("active"),
                }
                for m in markets
                if m.get("active")
            ][:100]  # Limit to first 100 active markets
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ohlcv/{symbol:path}", tags=["Market Data"])
async def get_ohlcv(
    symbol: str,
    timeframe: str = Query(default="1h"),
    limit: int = Query(default=100, le=500),
):
    """Get OHLCV data for charting"""
    try:
        df = engine.fetch_ohlcv(symbol, timeframe, limit)
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "data": df.to_dict(orient="records"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/market/ticker", tags=["Market Data"])
async def market_ticker(
    symbol: str = Query(..., min_length=1, example="BTC/USDT")
):
    """Ticker data for dashboard convenience routes"""
    try:
        ticker = engine.get_ticker(symbol)
        pct = ticker.get("percentage")
        change = (float(pct) / 100) if pct is not None else None
        return {
            "ticker": {
                "symbol": symbol,
                "last": ticker.get("last"),
                "bid": ticker.get("bid"),
                "ask": ticker.get("ask"),
                "high": ticker.get("high"),
                "low": ticker.get("low"),
                "volume": ticker.get("baseVolume"),
                "change": change,
                "changePercent": change,
                "timestamp": datetime.utcnow().timestamp(),
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/market/history", tags=["Market Data"])
async def market_history(
    symbol: str = Query(..., min_length=1, example="BTC/USDT"),
    interval: str = Query(default="1h"),
    limit: int = Query(default=100, le=500),
):
    """Historical candlesticks for the dashboard"""
    try:
        df = engine.fetch_ohlcv(symbol, interval, limit)
        candles = [
            {
                "time": int(row.timestamp.timestamp() * 1000),
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "volume": float(row.volume),
            }
            for row in df.itertuples(index=False)
        ]
        return {
            "symbol": symbol,
            "interval": interval,
            "candles": candles,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# WebSocket endpoint for real-time signals
@app.websocket("/ws/signals")
async def websocket_signals(websocket: WebSocket):
    """
    WebSocket endpoint for streaming trading signals
    Clients can subscribe to specific symbols
    """
    await manager.connect(websocket)
    try:
        while True:
            # Receive subscription message
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("action") == "subscribe":
                symbol = message.get("symbol", "BTC/USDT")
                timeframe = message.get("timeframe", "1h")

                # Run scan and send result
                try:
                    result = engine.scan_market(symbol, timeframe)
                    await websocket.send_json(
                        {
                            "type": "scan_result",
                            "symbol": result.symbol,
                            "score": result.score_total,
                            "signal": result.trade_signal.value,
                            "timestamp": result.timestamp.isoformat(),
                        }
                    )
                except Exception as e:
                    await websocket.send_json({"type": "error", "message": str(e)})

            elif message.get("action") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", 8000))
    uvicorn.run(app, host=host, port=port)
