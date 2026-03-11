"""
Tests for portfolio API endpoints.

Tests all portfolio endpoints:
- GET /api/portfolio/summary
- GET /api/portfolio/positions
- GET /api/portfolio/metrics
- GET /api/portfolio/history
"""

import pytest
from fastapi.testclient import TestClient
from api.main import app
from api.database import init_db, close_db
from api.models import Trade, TradeRepository
from api.portfolio import PortfolioEngine
from api.routes import portfolio as portfolio_routes
import time
import tempfile
import os


@pytest.fixture
def client():
    """Create a test client with a temporary database"""
    # Create temporary database
    fd, temp_db = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    # Initialize database
    init_db(temp_db)

    # Create client
    test_client = TestClient(app)

    yield test_client

    # Cleanup
    close_db()
    os.unlink(temp_db)


@pytest.fixture
def setup_test_data():
    """Setup test data: trades and positions"""
    trade_repo = TradeRepository()
    engine = PortfolioEngine()

    # Create some test trades
    timestamp = int(time.time() * 1000)

    # Buy trade
    buy_trade = Trade(
        id="test-buy-1",
        timestamp=timestamp - 1000,
        symbol="BTC/USDT",
        side="buy",
        amount=1.0,
        price=50000.0,
        fee=10.0
    )
    trade_repo.create(buy_trade)
    engine.update_positions_from_trade(buy_trade)

    # Sell trade (partial close)
    sell_trade = Trade(
        id="test-sell-1",
        timestamp=timestamp,
        symbol="BTC/USDT",
        side="sell",
        amount=0.5,
        price=52000.0,
        fee=5.0
    )
    trade_repo.create(sell_trade)
    engine.update_positions_from_trade(sell_trade)

    return {
        "buy_trade": buy_trade,
        "sell_trade": sell_trade
    }


def test_get_portfolio_summary(client):
    """Test GET /api/portfolio/summary endpoint"""
    response = client.get("/api/portfolio/summary")

    assert response.status_code == 200
    data = response.json()
    portfolio = data["portfolio"]

    # Check response structure
    assert "totalValue" in portfolio
    assert "cash" in portfolio
    assert "unrealizedPnl" in portfolio
    assert "realizedPnl" in portfolio
    assert "timestamp" in portfolio

    # Check data types
    assert isinstance(portfolio["totalValue"], (int, float))
    assert isinstance(portfolio["cash"], (int, float))
    assert isinstance(portfolio["unrealizedPnl"], (int, float))
    assert isinstance(portfolio["realizedPnl"], (int, float))
    assert isinstance(portfolio["timestamp"], int)

    # With no data, cash balance should be 10000.0
    assert portfolio["cash"] == 10000.0


def test_get_portfolio_summary_with_data(client, setup_test_data, monkeypatch):
    """Test portfolio summary with actual trades"""
    monkeypatch.setattr(
        portfolio_routes,
        "_get_current_prices",
        lambda symbols: {"BTC/USDT": 50000.0},
    )

    response = client.get("/api/portfolio/summary")

    assert response.status_code == 200
    data = response.json()

    # Should have realized P&L from the sell trade
    # Profit = (52000 - 50000) * 0.5 - fees = 1000 - 15 = 985
    assert data["portfolio"]["realizedPnl"] > 0


def test_get_positions_empty(client):
    """Test GET /api/portfolio/positions with no positions"""
    response = client.get("/api/portfolio/positions")

    assert response.status_code == 200
    data = response.json()

    assert "positions" in data
    assert isinstance(data["positions"], list)
    assert len(data["positions"]) == 0


def test_get_positions_with_data(client, setup_test_data, monkeypatch):
    """Test GET /api/portfolio/positions with open positions"""
    monkeypatch.setattr(
        portfolio_routes,
        "_get_current_prices",
        lambda symbols: {"BTC/USDT": 50000.0},
    )

    response = client.get("/api/portfolio/positions")

    assert response.status_code == 200
    data = response.json()

    assert "positions" in data
    positions = data["positions"]
    assert len(positions) == 1

    # Check first position
    position = positions[0]
    assert position["symbol"] == "BTC/USDT"
    assert position["quantity"] == 0.5  # Remaining after partial sell
    assert position["avgCost"] == 50000.0
    assert position["currentPrice"] == 50000.0
    assert position["marketValue"] == 25000.0
    assert position["unrealizedPnl"] == 0.0
    assert position["totalPnl"] == 0.0
    assert position["firstBuyDate"] == setup_test_data["buy_trade"].timestamp
    assert position["lastBuyDate"] == setup_test_data["sell_trade"].timestamp


def test_portfolio_routes_tolerate_exchange_failures(client, setup_test_data, monkeypatch):
    """Test summary and positions fall back safely when exchange lookup fails"""
    monkeypatch.setattr(
        portfolio_routes,
        "_get_exchange",
        lambda: (_ for _ in ()).throw(RuntimeError("exchange unavailable")),
    )

    summary_response = client.get("/api/portfolio/summary")
    assert summary_response.status_code == 200
    assert summary_response.json()["portfolio"]["unrealizedPnl"] == 0.0

    positions_response = client.get("/api/portfolio/positions")
    assert positions_response.status_code == 200
    positions = positions_response.json()["positions"]
    assert len(positions) == 1
    assert positions[0]["currentPrice"] == 50000.0
    assert positions[0]["unrealizedPnl"] == 0.0


def test_get_performance_metrics_empty(client):
    """Test GET /api/portfolio/metrics with no trades"""
    response = client.get("/api/portfolio/metrics")

    assert response.status_code == 200
    data = response.json()

    # Check all required metrics are present
    required_metrics = [
        "total_trades",
        "winning_trades",
        "losing_trades",
        "win_rate",
        "total_profit",
        "total_loss",
        "profit_factor",
        "avg_win",
        "avg_loss",
        "sharpe_ratio",
        "max_drawdown"
    ]

    for metric in required_metrics:
        assert metric in data

    # With no trades, most metrics should be 0
    assert data["total_trades"] == 0
    assert data["winning_trades"] == 0
    assert data["losing_trades"] == 0
    assert data["win_rate"] == 0.0


def test_get_performance_metrics_with_data(client, setup_test_data):
    """Test GET /api/portfolio/metrics with actual trades"""
    response = client.get("/api/portfolio/metrics")

    assert response.status_code == 200
    data = response.json()

    # Should have at least one completed trade
    assert data["total_trades"] > 0
    assert data["winning_trades"] > 0

    # Win rate should be positive
    assert data["win_rate"] > 0


def test_get_portfolio_history_empty(client):
    """Test GET /api/portfolio/history with no snapshots"""
    response = client.get("/api/portfolio/history")

    assert response.status_code == 200
    data = response.json()

    assert "history" in data
    assert isinstance(data["history"], list)
    # Empty history is OK
    assert len(data["history"]) == 0


def test_get_portfolio_history_with_days_param(client):
    """Test GET /api/portfolio/history with days parameter"""
    # Test with different day values
    for days in [7, 30, 90]:
        response = client.get(f"/api/portfolio/history?days={days}")
        assert response.status_code == 200
        data = response.json()
        assert "history" in data


def test_get_portfolio_history_invalid_days(client):
    """Test GET /api/portfolio/history with invalid days parameter"""
    # Test with days = 0 (below minimum)
    response = client.get("/api/portfolio/history?days=0")
    assert response.status_code == 422  # Validation error

    # Test with days = 400 (above maximum)
    response = client.get("/api/portfolio/history?days=400")
    assert response.status_code == 422  # Validation error


def test_get_portfolio_history_default_days(client):
    """Test GET /api/portfolio/history with default days (30)"""
    response = client.get("/api/portfolio/history")

    assert response.status_code == 200
    data = response.json()

    assert "history" in data
    assert isinstance(data["history"], list)


def test_portfolio_history_structure(client):
    """Test structure of portfolio history entries"""
    # Add a snapshot to the database
    from api.database import get_db_connection
    from datetime import datetime

    conn = get_db_connection()
    cursor = conn.cursor()

    today = datetime.now().strftime('%Y-%m-%d')
    cursor.execute("""
        INSERT INTO portfolio_snapshots (date, total_value, cash_balance, unrealized_pnl, realized_pnl_today)
        VALUES (?, ?, ?, ?, ?)
    """, (today, 11000.0, 10000.0, 500.0, 100.0))
    conn.commit()

    response = client.get("/api/portfolio/history?days=7")

    assert response.status_code == 200
    data = response.json()

    history = data["history"]
    if len(history) > 0:
        snapshot = history[0]
        assert "timestamp" in snapshot
        assert "totalValue" in snapshot
        assert "cash" in snapshot
        assert "positionsValue" in snapshot
        assert "totalPnl" in snapshot
        assert "totalPnlPercent" in snapshot
        assert "dayChange" in snapshot
        assert "dayChangePercent" in snapshot


def test_portfolio_summary_sanitizes_non_finite_values(client, monkeypatch):
    """Summary endpoint should normalize non-finite numeric values."""

    class StubPaperAccount:
        base_currency = "USDT"

        def get_balances(self):
            return {"free": {"USDT": float("nan")}}

    class StubPosition:
        symbol = "BTC/USDT"
        total_cost = float("inf")

    class StubPositionRepository:
        def get_all(self):
            return [StubPosition()]

    class StubPortfolioEngine:
        def calculate_unrealized_pnl(self, current_prices):
            return {"BTC/USDT": float("nan")}

        def calculate_realized_pnl(self):
            return float("inf")

        def calculate_realized_pnl_from_trades(self, trades):
            return float("-inf")

        def get_portfolio_value(self, cash_balance, current_prices):
            return float("nan")

    monkeypatch.setattr(portfolio_routes, "PaperAccount", StubPaperAccount)
    monkeypatch.setattr(portfolio_routes, "PositionRepository", StubPositionRepository)
    monkeypatch.setattr(portfolio_routes, "PortfolioEngine", StubPortfolioEngine)
    monkeypatch.setattr(
        portfolio_routes,
        "_get_current_prices",
        lambda symbols: {"BTC/USDT": float("nan")},
    )

    response = client.get("/api/portfolio/summary")

    assert response.status_code == 200
    portfolio = response.json()["portfolio"]
    assert portfolio["totalValue"] == 0.0
    assert portfolio["cash"] == 0.0
    assert portfolio["positions"] == 1
    assert portfolio["totalCost"] == 0.0
    assert portfolio["unrealizedPnl"] == 0.0
    assert portfolio["unrealizedPnlPercent"] == 0.0
    assert portfolio["realizedPnl"] == 0.0
    assert portfolio["totalPnl"] == 0.0
    assert portfolio["totalPnlPercent"] == 0.0
    assert isinstance(portfolio["timestamp"], int)


def test_all_endpoints_return_json(client):
    """Test that all endpoints return valid JSON"""
    endpoints = [
        "/api/portfolio/summary",
        "/api/portfolio/positions",
        "/api/portfolio/metrics",
        "/api/portfolio/history",
    ]

    for endpoint in endpoints:
        response = client.get(endpoint)
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        # Should be able to parse as JSON
        data = response.json()
        assert isinstance(data, dict)


def test_endpoints_handle_errors_gracefully(client):
    """Test that endpoints handle errors gracefully"""
    # All endpoints should return 200 even with empty data
    response = client.get("/api/portfolio/summary")
    assert response.status_code == 200

    response = client.get("/api/portfolio/positions")
    assert response.status_code == 200

    response = client.get("/api/portfolio/metrics")
    assert response.status_code == 200

    response = client.get("/api/portfolio/history")
    assert response.status_code == 200
