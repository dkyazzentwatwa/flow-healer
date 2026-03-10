# NobiBot Pro Roadmap

## Phase 1: Observability & Communication
*Goal: Know exactly what the bot is doing in real-time.*

- [ ] **1.1 Live Execution Log (Backend)**
  - [ ] Create `logs` table in SQLite: `id`, `timestamp`, `level`, `message`, `rule_id`, `symbol`.
  - [ ] Create `LogRepository` in `api/models.py`.
  - [ ] Implement a centralized logging utility that writes to both the database and the console.
  - [ ] Create `GET /api/logs` endpoint with pagination.
- [ ] **1.2 Live Log Component (Frontend)**
  - [ ] Create `LogViewer.tsx` (terminal-style UI).
  - [ ] Integrate into Dashboard and Automation pages.
  - [ ] Implement auto-scroll and level filtering (Info, Warning, Error, Trade).
- [ ] **1.3 Webhook Notifications**
  - [ ] Add Discord/Telegram webhook support in `.env`.
  - [ ] Create notification service to alert on trades and errors.

## Phase 2: Advanced Execution
*Goal: Protect capital with automated exits and smart sizing.*

- [ ] **2.1 Risk-Based Position Sizing**
  - [ ] Support "Percent of Balance" trade amounts.
- [ ] **2.2 Automated Stop-Loss (SL) & Take-Profit (TP)**
  - [ ] Add `stop_loss_pct` and `take_profit_pct` to rules.
  - [ ] Track target and stop prices in the `trades` table.
- [ ] **2.3 Position Monitor Service**
  - [ ] Background job to check open positions every 30s.
  - [ ] Auto-close positions when SL or TP is hit.
- [ ] **2.4 Trailing Stop-Loss**
  - [ ] Implement logic to move stop-loss up as price rises.

## Phase 3: Strategy Verification
*Goal: Prove a strategy works before risking funds.*

- [x] **3.1 Historical Data Downloader**
  - [x] Fetch and cache large OHLCV batches for testing.
- [x] **3.2 Backtest Engine**
  - [x] Simulate rules against historical data.
  - [x] Calculate Net Profit, Win Rate, and Max Drawdown.
- [x] **3.3 Backtest UI**
  - [x] Create dedicated Backtesting interface.

## Phase 4: Professional Visualization
*Goal: Visual analysis of signals and trades.*

- [x] **4.1 Chart Marker Integration**
  - [x] Show Buy/Sell markers on charts at trade execution points.
- [x] **4.2 Indicator Overlays**
  - [x] Add visual overlays for Bollinger Bands, EMAs, etc. (Implemented SMA20 and EMA50).

## Phase 5: The Strategy Builder
*Goal: No-code logic for complex triggers.*

- [x] **5.1 Logical Rule Schema**
  - [x] Support multi-condition logic (e.g., RSI < 30 AND Price > EMA200).
- [x] **5.2 Visual Rule Builder**
  - [x] UI for stacking conditions without writing code.
