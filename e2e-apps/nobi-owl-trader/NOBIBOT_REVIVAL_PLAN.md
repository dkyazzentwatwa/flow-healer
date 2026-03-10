# NobiBot Revival Plan - Modern Hybrid Architecture

## Project Summary

**What You Built:** A crypto trading bot with 22 technical indicators and multi-exchange support
**Goal:** Revive for live trading, paper trading, and market analysis with a modern Next.js dashboard

---

## Architecture Decision: Hybrid Approach (Recommended)

After research, a **hybrid approach** is the best path forward:

```
┌─────────────────────────────────────────────────────────┐
│                    Next.js Frontend                      │
│         (Dashboard, Charts, Real-time Updates)          │
└─────────────────────┬───────────────────────────────────┘
                      │ WebSocket + REST API
┌─────────────────────▼───────────────────────────────────┐
│                   Node.js Bridge                         │
│        (Express/Fastify, Socket.IO, CCXT for data)      │
└─────────────────────┬───────────────────────────────────┘
                      │ HTTP/Process Communication
┌─────────────────────▼───────────────────────────────────┐
│                 Python Trading Engine                    │
│    (Your existing bot logic, talib, indicators)         │
└─────────────────────┬───────────────────────────────────┘
                      │ CCXT
┌─────────────────────▼───────────────────────────────────┐
│                    Binance API                           │
│            (Most reliable, best documented)             │
└─────────────────────────────────────────────────────────┘
```

**Why Hybrid?**
- Keep your battle-tested Python trading logic (22 indicators, years of refinement)
- Modern real-time dashboard with Next.js
- Best of both: Python for computation, Node.js for real-time delivery
- Path to full JS migration later if desired

**Exchange Choice: Binance**
- Best documentation and reliability
- Highest liquidity
- Well-supported by CCXT in both Python and JS

---

## Implementation Plan

### Phase 1: Security & Cleanup ✅ COMPLETED
**CRITICAL - Must complete before any trading**

- [x] Remove hardcoded API keys from `extra/asyncnobiV2.py`
- [x] Remove hardcoded MongoDB credentials from `nalgoV2SCAN.py`
- [x] Create `.env.example` with required variables
- [x] Add `python-dotenv` support to Python files
- [x] Create `.gitignore` (exclude .env, credentials, node_modules)
- [x] Archive `extra/` folder to `archive/legacy-bots/`
- [x] Archive `myExpressApp/` to `archive/old-express/`
- [x] Archive `webapp/` to `archive/old-webapp/`

### Phase 2: Python Engine Hardening ✅ COMPLETED
**Fix bugs and wrap in API**

- [x] Fix logic bugs (`if 'open' or 'NEW'` → proper condition)
- [x] Add try/except around all CCXT API calls
- [x] Add timeout handling for order monitoring loops
- [x] Implement exponential backoff for rate limiting
- [x] Create FastAPI wrapper around trading engine
  - `POST /api/scan` - Run market scan
  - `POST /api/trade` - Execute trade
  - `GET /api/balance` - Get account balance
  - `GET /api/orders` - Get open orders
  - `WS /api/signals` - Stream trading signals
- [x] Add paper trading mode flag

### Phase 3: Next.js Dashboard ✅ COMPLETED
**Modern frontend with real-time updates**

- [x] Dashboard home with quick stats
- [x] Market scanner page
- [x] Trade history with CSV export
- [x] Settings page
- [x] Local storage persistence (trades, scans, watchlist)
- [x] Zustand state management
- [x] US-only exchanges configured (binanceus, kraken, coinbase, gemini)

### Phase 4: Integration & Testing ✅ COMPLETED

- [x] Connect Next.js to Python API
- [x] Test paper trading flow end-to-end
- [x] Test market scanning and signal display

---

## Files to Modify/Create

**Python (Existing - Modify):**
| File | Changes |
|------|---------|
| `nalgoV2SCAN.py` | Remove hardcoded creds, add .env support |
| `nalgoV2livetrade.py` | Fix bugs, add API wrapper, paper trade mode |

**Python (New):**
| File | Purpose |
|------|---------|
| `api/main.py` | FastAPI application entry |
| `api/routes/` | API route handlers |
| `api/websocket.py` | WebSocket signal streaming |
| `.env.example` | Environment variable template |
| `requirements.txt` | Updated Python dependencies |

**Next.js (New):**
| Directory | Purpose |
|-----------|---------|
| `dashboard/` | Complete Next.js application |

**Archive (Move):**
| From | To |
|------|-----|
| `extra/` | `archive/legacy-bots/` |
| `myExpressApp/` | `archive/old-express/` |
| `webapp/` | `archive/old-webapp/` |

---

## Tech Stack Summary

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 15, TypeScript, Tailwind, shadcn/ui |
| Real-time | Socket.IO |
| Charts | Lightweight Charts (TradingView) |
| API Layer | FastAPI (Python) |
| Trading Engine | Existing Python bot (cleaned up) |
| Technical Analysis | talib (Python) |
| Exchange | Binance via CCXT |
| Database | SQLite (local) or PostgreSQL (production) |

---

## Local Development Setup

```
Your Machine
├── Python trading engine (terminal 1)
│   └── FastAPI on localhost:8000
├── Next.js dashboard (terminal 2)
│   └── localhost:3000
└── Connects to Binance API
```

**Requirements:**
- Python 3.9+
- Node.js 18+
- Binance account (for API keys)

---

## Verification Plan

1. **Security Check**
   - Grep codebase for any remaining hardcoded credentials
   - Verify .env is in .gitignore

2. **Paper Trading Test**
   - Run scan on BTC/USDT 1h timeframe
   - Verify signals display in dashboard
   - Execute paper trade and verify balance updates

3. **Live Trading Test (Small Amount)**
   - Connect to Binance testnet first
   - Execute small trade ($10-20)
   - Verify order execution and logging

4. **Dashboard Verification**
   - Real-time price updates working
   - Signal cards updating on new data
   - Trade history displaying correctly

---

## Professional Trading Features Roadmap

### Phase 5: P&L Analytics & Risk Management (NEXT)
**Essential features that separate casual traders from profitable ones**

- [ ] Real-time portfolio value tracking
- [ ] Unrealized P&L display per position
- [ ] Daily/weekly/monthly performance charts
- [ ] Win rate, average win/loss, profit factor stats
- [ ] Max drawdown tracking
- [ ] Sharpe ratio calculation
- [ ] Position sizing calculator (% of portfolio)
- [ ] Stop-loss / Take-profit automation
- [ ] Maximum daily loss limit (auto-stops trading)
- [ ] Risk/reward ratio calculator
- [ ] Exposure limits per asset

**Files to create/modify:**
- `dashboard/app/portfolio/page.tsx` - Portfolio analytics page
- `dashboard/components/PnLChart.tsx` - Performance chart component
- `dashboard/components/RiskCalculator.tsx` - Position sizing tool
- `dashboard/lib/analytics.ts` - P&L calculation utilities
- `api/routes/portfolio.py` - Portfolio data endpoints

### Phase 6: Alerts & Multi-Timeframe Analysis
**Stay informed and see the bigger picture**

- [ ] Price alerts (crosses above/below threshold)
- [ ] Indicator alerts (RSI > 70, MACD crossover, etc.)
- [ ] Volume spike detection alerts
- [ ] Telegram webhook integration
- [ ] Discord webhook integration
- [ ] Browser push notifications
- [ ] Multi-timeframe analysis panel (view 4 TFs at once)
- [ ] Confluence score (when multiple TFs agree on signal)
- [ ] Higher timeframe trend context display

**Files to create/modify:**
- `dashboard/app/alerts/page.tsx` - Alert management page
- `dashboard/components/AlertBuilder.tsx` - Create/edit alerts
- `dashboard/components/MultiTimeframe.tsx` - MTF analysis panel
- `api/alerts.py` - Alert processing and webhook sending
- `dashboard/lib/notifications.ts` - Browser notification handler

### Phase 7: Advanced Charting
**Professional-grade visualization**

- [ ] TradingView Lightweight Charts integration
- [ ] Candlestick charts with indicator overlays
- [ ] Drawing tools (trend lines, horizontal lines, fibonacci)
- [ ] Support/resistance auto-detection
- [ ] Multiple chart layouts (1x1, 2x2, 3x1)
- [ ] Chart templates/presets (save indicator combos)
- [ ] Volume profile visualization

**Files to create/modify:**
- `dashboard/components/TradingChart.tsx` - Main chart component
- `dashboard/components/ChartToolbar.tsx` - Drawing tools
- `dashboard/lib/chartPresets.ts` - Saved chart configurations

### Phase 8: Strategy Builder & Backtesting
**Test before you trade**

- [ ] Visual condition builder UI
  - IF [indicator] [operator] [value] AND/OR...
  - THEN [buy/sell] [amount]
- [ ] Save/load strategies
- [ ] Strategy performance comparison
- [ ] Auto-execution toggle per strategy
- [ ] Backtesting engine with historical data
- [ ] Equity curve visualization
- [ ] Performance metrics (win rate, max drawdown, etc.)
- [ ] Parameter optimization (find best RSI period, etc.)

**Files to create/modify:**
- `dashboard/app/strategies/page.tsx` - Strategy management
- `dashboard/app/backtest/page.tsx` - Backtesting interface
- `dashboard/components/StrategyBuilder.tsx` - Visual builder
- `dashboard/components/BacktestResults.tsx` - Results display
- `api/backtest.py` - Backtesting engine
- `api/strategies.py` - Strategy storage and execution

### Phase 9: Trade Journal & Analysis
**Learn from every trade**

- [ ] Add notes to each trade
- [ ] Tag trades (scalp, swing, breakout, reversal)
- [ ] Screenshot attachment support
- [ ] Performance breakdown by strategy/tag
- [ ] Calendar view of trading activity
- [ ] Mistake tracking and patterns

**Files to create/modify:**
- `dashboard/app/journal/page.tsx` - Trade journal page
- `dashboard/components/TradeNotes.tsx` - Note editor
- `dashboard/lib/journal.ts` - Journal storage

### Phase 10: Market Intelligence (Future)
**Advanced market insights**

- [ ] Crypto fear & greed index display
- [ ] Exchange inflow/outflow tracking
- [ ] Funding rates for futures
- [ ] Liquidation heatmaps
- [ ] Correlation matrix between assets
- [ ] Sector/category performance
- [ ] News sentiment analysis

---

## Priority Implementation Order

```
┌─────────────────────────────────────────────────────────┐
│  Phase 5: P&L & Risk Management     ← START HERE       │
│  (Highest impact for profitability)                    │
├─────────────────────────────────────────────────────────┤
│  Phase 6: Alerts + Multi-Timeframe                     │
│  (Stay informed, better context)                       │
├─────────────────────────────────────────────────────────┤
│  Phase 7: Advanced Charting                            │
│  (Visual analysis upgrade)                             │
├─────────────────────────────────────────────────────────┤
│  Phase 8: Strategy Builder + Backtesting               │
│  (Systematic trading)                                  │
├─────────────────────────────────────────────────────────┤
│  Phase 9: Trade Journal                                │
│  (Learn and improve)                                   │
├─────────────────────────────────────────────────────────┤
│  Phase 10: Market Intelligence                         │
│  (Advanced insights)                                   │
└─────────────────────────────────────────────────────────┘
```

---

## Current Status

**Completed:**
- ✅ Phase 1: Security & Cleanup
- ✅ Phase 2: Python Engine Hardening
- ✅ Phase 3: Next.js Dashboard (MVP)
- ✅ Phase 4: Integration & Testing

**Next Up:**
- 🔲 Phase 5: P&L Analytics & Risk Management
