# NobiBot - Professional Cryptocurrency Trading Bot

A crypto trading bot with 22 technical indicators and multi-exchange support, featuring a modern Next.js dashboard.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Next.js Frontend                      │
│         (Dashboard, Charts, Real-time Updates)          │
│              http://localhost:3000                       │
└─────────────────────┬───────────────────────────────────┘
                      │ REST API + WebSocket
┌─────────────────────▼───────────────────────────────────┐
│                   FastAPI Backend                        │
│        (Trading Engine, Indicators, CCXT)               │
│              http://localhost:8000                       │
└─────────────────────┬───────────────────────────────────┘
                      │ CCXT
┌─────────────────────▼───────────────────────────────────┐
│                    Exchange API                          │
│            (Binance, Kraken, etc.)                      │
└─────────────────────────────────────────────────────────┘
```

## Features

- **22 Technical Indicators**: RSI, MACD, EMA, SMA, ADX, Bollinger Bands, Stochastic, CCI, MFI, Aroon, and more
- **Multi-Exchange Support**: Binance, Kraken, Coinbase Pro, and 100+ exchanges via CCXT
- **Paper Trading Mode**: Test strategies without risking real funds
- **Real-time Dashboard**: Modern Next.js frontend with live updates
- **RESTful API**: Clean FastAPI endpoints for integration
- **WebSocket Support**: Stream trading signals in real-time

## Quick Start

### Prerequisites

- **Python 3.12** (recommended - 3.14 has compatibility issues)
- Node.js 18+
- TA-Lib (for technical indicators)

### 1. Install Python 3.12 (if needed)

```bash
# macOS with Homebrew
brew install python@3.12

# Verify installation
python3.12 --version
```

### 2. Setup Environment

```bash
cd /path/to/ccxt1

# Copy environment files
cp .env.example .env
cp dashboard/.env.example dashboard/.env

# Edit .env with your API keys (optional for paper trading)
```

### 3. Install Python Dependencies

```bash
# Create virtual environment with Python 3.12
python3.12 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install TA-Lib system library first (macOS)
brew install ta-lib

# Install Python dependencies
pip install -r requirements.txt
```

**TA-Lib Installation:**
- macOS: `brew install ta-lib`
- Ubuntu: `sudo apt-get install libta-lib-dev`
- See [TA-Lib installation guide](https://github.com/mrjbq7/ta-lib#installation) for other systems

### 3. Install Dashboard Dependencies

```bash
cd dashboard
npm install
cd ..
```

### 4. Start the Services

**Terminal 1 - Python API:**
```bash
source venv/bin/activate
python -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 - Next.js Dashboard:**
```bash
cd dashboard
npm run dev
```

### 5. Access the Dashboard

Open http://localhost:3000 in your browser.

## Configuration

### Environment Variables (.env)

```bash
# Exchange API (leave empty for paper trading only)
EXCHANGE_API_KEY=your_api_key_here
EXCHANGE_SECRET_KEY=your_secret_key_here
DEFAULT_EXCHANGE=binance

# Paper Trading Mode (recommended for testing)
PAPER_TRADING=true

# MongoDB (optional - for storing scan results)
MONGODB_URI=mongodb://localhost:27017/nobi

# API Server
API_HOST=0.0.0.0
API_PORT=8000
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/scan` | POST | Run market scan |
| `/api/balance` | GET | Get account balance |
| `/api/orders` | GET | Get open orders |
| `/api/trade` | POST | Place trade order |
| `/api/ticker/{symbol}` | GET | Get ticker |
| `/api/ohlcv/{symbol}` | GET | Get OHLCV data |
| `/api/markets` | GET | Get available markets |
| `/ws/signals` | WS | WebSocket signals |

### Example: Run a Market Scan

```bash
curl -X POST http://localhost:8000/api/scan \
  -H "Content-Type: application/json" \
  -d '{"symbol": "BTC/USDT", "timeframe": "1h"}'
```

## Project Structure

```
ccxt1/
├── api/                      # FastAPI backend
│   ├── main.py              # API application
│   ├── trading_engine.py    # Trading engine wrapper
│   └── routes/              # API route handlers
├── dashboard/               # Next.js frontend
│   ├── app/                 # App router pages
│   ├── components/          # React components
│   └── lib/                 # Utilities and state
├── nalgoV2SCAN.py          # Original scanner (legacy)
├── nalgoV2livetrade.py     # Original trader (legacy)
├── archive/                 # Archived legacy code
├── .env.example            # Environment template
├── requirements.txt        # Python dependencies
└── README.md
```

## Technical Indicators

The bot analyzes markets using these indicators:

| Indicator | Type | Signal Logic |
|-----------|------|--------------|
| RSI | Momentum | Oversold < 30, Overbought > 70 |
| MACD | Trend | Cross above/below signal line |
| EMA | Trend | 20 EMA vs 50 EMA crossover |
| SMA | Trend | 20 SMA vs 50 SMA crossover |
| ADX | Trend Strength | Strong trend > 25 |
| Bollinger Bands | Volatility | Price vs bands |
| Stochastic | Momentum | Oversold < 20, Overbought > 80 |
| CCI | Momentum | Oversold < -100, Overbought > 100 |
| MFI | Volume | Oversold < 20, Overbought > 80 |
| Aroon | Trend | Aroon Up vs Aroon Down |

## Safety Features

- **Paper Trading Mode**: Enabled by default
- **Rate Limiting**: Exponential backoff for API calls
- **Environment Variables**: No hardcoded credentials
- **Error Handling**: Graceful error recovery

## Warning

Trading cryptocurrencies involves significant risk. This software is provided for educational purposes. Always:

1. Start with paper trading
2. Use only funds you can afford to lose
3. Never share your API keys
4. Review and understand the code before live trading

## License

MIT License - See LICENSE file for details.

## Author

NobiOwl (David Kyazze-Ntwatwa) - 2019-2024
