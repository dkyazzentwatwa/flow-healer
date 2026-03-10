# NobiBot (Nobi Owl Trader) Context

## Project Overview
NobiBot is a professional cryptocurrency trading bot featuring a **hybrid architecture**:
- **Backend:** Python (FastAPI) trading engine with 22 technical indicators and CCXT for exchange integration.
- **Frontend:** Next.js (TypeScript) modern dashboard for real-time monitoring, manual trading, and analysis.

The project is currently undergoing a "Revival Plan" to modernize legacy scripts into this robust, API-driven architecture.

## Architecture
```
┌───────────────────────┐      WebSocket/REST      ┌───────────────────────┐
│   Next.js Dashboard   │ <──────────────────────> │    FastAPI Backend    │
│ (localhost:3000)      │                          │ (localhost:8000)      │
└───────────────────────┘                          └───────────┬───────────┘
                                                               │
                                                               ▼
                                                     ┌───────────────────┐
                                                     │   Exchange APIs   │
                                                     │ (Binance, etc.)   │
                                                     └───────────────────┘
```

## Getting Started

### Prerequisites
- **Python:** 3.12+ (Recommended)
- **Node.js:** 18+
- **System Libs:** TA-Lib (Required for technical indicators)

### Setup
1.  **Backend:**
    ```bash
    python3.12 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env  # Configure API keys
    ```

2.  **Frontend:**
    ```bash
    cd dashboard
    npm install
    cp .env.example .env
    ```

### Running the Application
**Terminal 1 (Backend):**
```bash
source .venv/bin/activate
# Run from project root
python -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 (Frontend):**
```bash
cd dashboard
npm run dev
# Access at http://localhost:3000
```

## Key Directories & Files

### Backend (`/`)
- **`api/`**: Main FastAPI application.
    - `main.py`: Entry point, app configuration, and WebSocket manager.
    - `routes/`: API endpoint definitions (portfolio, risk, etc.).
    - `trading_engine.py`: Core logic wrapping CCXT and indicators.
- **`tests/`**: Pytest suite for the backend.
- **`requirements.txt`**: Python dependencies.

### Frontend (`dashboard/`)
- **`app/`**: Next.js App Router pages (`portfolio/`, `scan/`, etc.).
- **`components/`**: Reusable React components (Charts, SignalCards).
- **`lib/`**: Utilities, types, and Zustand store (`store.ts`).
- **`package.json`**: Frontend dependencies and scripts.

### Documentation (`docs/`)
- **`docs/plans/`**: Detailed design documents for development phases.
    - *Key Doc:* `2026-01-25-phase5-pnl-analytics-design.md`

### Legacy/Scripts
- **`nalgo*.py`**: Older standalone bot scripts (reference).
- **`scripts/`**: Utility scripts (e.g., startup).

## Current Development Focus
**Phase 5: P&L Analytics & Risk Management**
- **Goal:** Implement real-time P&L tracking, portfolio analytics, and strict risk management rules.
- **Status:** In progress (Design approved).
- **Next Steps:**
    1.  Implement SQLite database for trade/position persistence.
    2.  Build Backend P&L calculation logic and endpoints (`api/routes/portfolio.py`).
    3.  Update Frontend to display Portfolio Analytics (`dashboard/app/portfolio/page.tsx`).

## Development Conventions

- **Code Style:**
    - **Python:** PEP 8. Use type hints (`typing` module) extensively. Pydantic models for data validation.
    - **TypeScript:** Strict type checking. Functional components with Hooks.
- **State Management:** Zustand (Frontend) for global state (portfolio, settings).
- **Testing:** `pytest` for backend logic. Ensure tests pass before committing.
- **Safety:**
    - **NEVER** commit real API keys. Use `.env`.
    - **Paper Trading:** Default mode for development. Ensure logic respects the `paper_trading` flag.
    - **Risk:** Always respect `daily_loss_limit` and stop-loss logic when implementing trading execution.
