# Phase 5: P&L Analytics & Risk Management - Design Document

**Date:** 2026-01-25
**Status:** Approved for Implementation
**Approach:** Bottom-Up (Data Foundation First)

---

## Overview

Build comprehensive portfolio tracking, P&L analytics, and risk management for NobiBot. This phase adds professional trading features that separate profitable traders from casual ones.

**Core Goals:**
1. Track profitability (realized P&L from closed trades)
2. Monitor risk (daily loss limits, position sizing, exposure tracking)
3. Analyze performance (win rate, profit factor, Sharpe ratio)
4. Manage open positions (unrealized P&L in real-time)

**Data Persistence:** SQLite database (`trading_data.db`) for persistent local storage

---

## Database Schema

### `trades` table
Every executed trade (buy or sell):
```sql
CREATE TABLE trades (
    id TEXT PRIMARY KEY,
    timestamp INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,              -- "buy" or "sell"
    amount REAL NOT NULL,
    price REAL NOT NULL,
    fee REAL DEFAULT 0,
    fee_currency TEXT,
    status TEXT DEFAULT 'closed',    -- 'open', 'closed', 'cancelled'
    paper BOOLEAN DEFAULT 0,
    strategy TEXT,
    notes TEXT
);
```

### `positions` table
Currently open positions (aggregate of open trades):
```sql
CREATE TABLE positions (
    symbol TEXT PRIMARY KEY,
    amount REAL NOT NULL,
    avg_entry_price REAL NOT NULL,
    total_cost REAL NOT NULL,
    side TEXT NOT NULL,              -- "long" or "short"
    opened_at INTEGER NOT NULL,
    last_updated INTEGER NOT NULL
);
```

### `portfolio_snapshots` table
Daily portfolio value for charts:
```sql
CREATE TABLE portfolio_snapshots (
    date TEXT PRIMARY KEY,           -- YYYY-MM-DD
    total_value REAL NOT NULL,
    cash_balance REAL NOT NULL,
    unrealized_pnl REAL NOT NULL,
    realized_pnl_today REAL NOT NULL
);
```

### `balances` table
Track cash balance changes:
```sql
CREATE TABLE balances (
    timestamp INTEGER PRIMARY KEY,
    currency TEXT NOT NULL,
    total REAL NOT NULL,
    available REAL NOT NULL,
    locked REAL NOT NULL
);
```

---

## P&L Calculation Logic

### Realized P&L
```python
realized_pnl = (sell_price - buy_price) * amount - total_fees

# Example:
# Buy: 0.1 BTC @ $50,000 = $5,000 (fee: $5)
# Sell: 0.1 BTC @ $52,000 = $5,200 (fee: $5.20)
# Realized P&L = ($52,000 - $50,000) * 0.1 - $10.20 = $189.80
```

### Unrealized P&L
```python
unrealized_pnl = (current_price - avg_entry_price) * amount - fees_paid

# Example:
# Open: 0.5 BTC @ $48,000, current: $50,000
# Unrealized P&L = ($50,000 - $48,000) * 0.5 = $1,000
```

### Position Tracking (FIFO)
```python
# Multiple buys, then sell:
# Buy #1: 0.3 BTC @ $45,000
# Buy #2: 0.2 BTC @ $48,000
# Average entry = (0.3*45000 + 0.2*48000) / 0.5 = $46,200

# Sell 0.2 BTC @ $50,000
# Remaining: 0.3 BTC @ $46,200
```

### Portfolio Value
```python
portfolio_value = cash_balance + sum(position_value for all positions)
position_value = amount * current_market_price
```

### Performance Metrics
```python
win_rate = (winning_trades / total_trades) * 100
profit_factor = total_profit / total_loss  # > 1.0 is good
avg_win = total_profit / winning_trades
avg_loss = total_loss / losing_trades
sharpe_ratio = (avg_return - risk_free_rate) / std_deviation_of_returns
```

---

## FastAPI Endpoints

### Portfolio Endpoints
```
GET  /api/portfolio/summary
→ Returns: total_value, cash_balance, unrealized_pnl, realized_pnl_today

GET  /api/portfolio/positions
→ Returns: list of open positions with unrealized P&L

GET  /api/portfolio/history?days=30
→ Returns: daily portfolio snapshots for charts

GET  /api/portfolio/metrics
→ Returns: win_rate, profit_factor, sharpe_ratio, avg_win, avg_loss, max_drawdown
```

### Trade Management
```
POST /api/trades
→ Body: { symbol, side, amount, price, fee, paper }
→ Returns: created trade + updated position

GET  /api/trades?limit=100&offset=0
→ Returns: paginated trade history

GET  /api/trades/stats?period=day|week|month
→ Returns: P&L breakdown by time period
```

### Risk Management
```
GET  /api/risk/limits
→ Returns: current risk limits

POST /api/risk/limits
→ Body: { daily_loss_limit, max_position_size_pct }
→ Returns: updated limits

GET  /api/risk/check
→ Returns: { can_trade: bool, reason: string, risk_metrics: {...} }
```

### Background Tasks
```python
# Every minute
def update_unrealized_pnl():
    - Fetch current prices for open positions
    - Recalculate unrealized P&L
    - Check stop-loss/take-profit triggers
    - Update positions table

# Midnight UTC
def create_daily_snapshot():
    - Calculate total portfolio value
    - Save to portfolio_snapshots
    - Reset daily P&L counters
```

---

## Zustand Store Architecture

**File:** `dashboard/lib/store.ts`

```typescript
interface TradingStore {
  // Connection & Settings
  isConnected: boolean;
  apiUrl: string;
  selectedSymbol: string;
  selectedTimeframe: string;
  settings: UserSettings;

  // Market Data
  ticker: Ticker | null;
  scanResult: ScanResult | null;

  // Portfolio & P&L
  portfolio: {
    totalValue: number;
    cashBalance: number;
    unrealizedPnl: number;
    realizedPnlToday: number;
  };
  positions: Position[];

  // Performance Metrics
  metrics: {
    winRate: number;
    profitFactor: number;
    avgWin: number;
    avgLoss: number;
    sharpeRatio: number;
    maxDrawdown: number;
  };

  // Risk Management
  riskLimits: {
    dailyLossLimit: number;
    maxPositionSizePct: number;
    maxExposurePct: number;
  };
  canTrade: boolean;

  // History
  tradeHistory: Trade[];
  portfolioHistory: PortfolioSnapshot[];

  // Actions
  fetchPortfolio: () => Promise<void>;
  fetchPositions: () => Promise<void>;
  fetchMetrics: () => Promise<void>;
  fetchPortfolioHistory: (days: number) => Promise<void>;
  executeTrade: (trade: TradeRequest) => Promise<void>;
  updateRiskLimits: (limits: RiskLimits) => Promise<void>;
  checkRiskStatus: () => Promise<void>;
}
```

**Auto-refresh:** Poll `/api/portfolio/summary` and `/api/portfolio/positions` every 10 seconds

**LocalStorage Caching:** Save portfolio data to localStorage for offline viewing

---

## UI Components

### New Page: `dashboard/app/portfolio/page.tsx`

**Layout:**
```
┌─────────────────────────────────────────────┐
│  Portfolio Overview                          │
│  [Total Value] [Cash Balance] [Today P&L]   │
│                                              │
│  [Portfolio Value Chart - 30 days]          │
│                                              │
│  [Open Positions]    [Performance Metrics]  │
│                                              │
│  [Risk Status]                               │
└─────────────────────────────────────────────┘
```

### Components to Build

1. **`PortfolioSummary.tsx`** - Top stat cards
2. **`PnLChart.tsx`** - Line chart (Recharts or Lightweight Charts)
3. **`PositionsList.tsx`** - Open positions table with unrealized P&L
4. **`PerformanceMetrics.tsx`** - Win rate, profit factor, Sharpe ratio
5. **`RiskStatus.tsx`** - Visual risk gauge with limits
6. **`RiskCalculator.tsx`** - Position sizing calculator

### Color Coding
- **Green:** Positive P&L, within risk limits
- **Red:** Negative P&L, exceeded limits
- **Yellow:** Warning (80% of limit)
- **Gray:** Neutral/no data

---

## Risk Management

### Risk Limits Configuration
```typescript
interface RiskLimits {
  dailyLossLimit: number;        // Max loss per day (USD)
  maxPositionSizePct: number;    // Max % of portfolio per position
  maxExposurePct: number;        // Total % in all positions
  stopLossEnabled: boolean;
  takeProfitEnabled: boolean;
}
```

### Pre-Trade Risk Check
```python
def check_risk_limits(trade_request):
    # 1. Check daily loss
    if today_pnl <= -daily_loss_limit:
        return False, "Daily loss limit reached"

    # 2. Check position size
    if position_size_pct > max_position_size_pct:
        return False, "Position size too large"

    # 3. Check exposure
    if total_exposure_pct > max_exposure_pct:
        return False, "Max exposure reached"

    return True, "OK"
```

### Position Sizing Calculator
```python
def calculate_position_size(risk_pct, stop_loss_pct):
    """
    Risk 2% with 5% stop loss:
    Position = (portfolio * 0.02) / 0.05
    """
    risk_amount = portfolio_value * (risk_pct / 100)
    position_size = risk_amount / (stop_loss_pct / 100)
    return position_size
```

### Auto-Stop Trading
When daily loss limit is reached:
- Set `can_trade = False`
- Display warning banner in UI
- Optionally close all positions
- Re-enable at midnight UTC

### Risk Indicators
- **0-50% used:** Green - Safe
- **50-80% used:** Yellow - Warning
- **80-100% used:** Red - Danger
- **100%+ used:** Black - Disabled

---

## Implementation Order

### Week 1: Database & Core API
1. Create SQLite database with schema
2. Build portfolio calculation engine
3. Implement `/api/portfolio/*` endpoints
4. Add background tasks (P&L updates, snapshots)

### Week 2: Risk Management
1. Implement risk limit checks
2. Add position sizing calculator
3. Build auto-stop trading logic
4. Create `/api/risk/*` endpoints

### Week 3: Frontend State & UI
1. Create Zustand store with portfolio state
2. Build `dashboard/lib/store.ts`
3. Create portfolio page layout
4. Build core components (summary, chart, positions)

### Week 4: Polish & Testing
1. Add performance metrics display
2. Build risk status dashboard
3. Test P&L calculations with sample trades
4. Verify risk limits prevent over-trading

---

## Success Criteria

- [ ] Can track realized P&L from trade history
- [ ] Can see unrealized P&L on open positions
- [ ] Portfolio value chart shows 30-day history
- [ ] Win rate and profit factor calculate correctly
- [ ] Daily loss limit prevents trading when exceeded
- [ ] Position sizing calculator helps determine safe trade size
- [ ] Risk status shows clear visual indicators
- [ ] All data persists in SQLite database

---

## Files to Create

**Python:**
- `api/database.py` - SQLite connection and models
- `api/portfolio.py` - Portfolio calculation engine
- `api/risk.py` - Risk management logic
- `api/routes/portfolio.py` - Portfolio endpoints
- `api/routes/risk.py` - Risk endpoints
- `api/tasks.py` - Background tasks (APScheduler)

**TypeScript:**
- `dashboard/lib/store.ts` - Zustand store
- `dashboard/lib/types.ts` - TypeScript interfaces
- `dashboard/app/portfolio/page.tsx` - Portfolio page
- `dashboard/components/PortfolioSummary.tsx`
- `dashboard/components/PnLChart.tsx`
- `dashboard/components/PositionsList.tsx`
- `dashboard/components/PerformanceMetrics.tsx`
- `dashboard/components/RiskStatus.tsx`
- `dashboard/components/RiskCalculator.tsx`

**Documentation:**
- Update `NOBIBOT_REVIVAL_PLAN.md` Phase 5 status
- Add P&L calculation examples to README
