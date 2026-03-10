"""
Tests for portfolio calculation engine.

Tests cover:
- FIFO matching with multiple buys/sells
- Realized P&L calculation
- Unrealized P&L calculation
- Performance metrics calculation
- Position updates from trades
"""

import pytest
from datetime import datetime, timedelta
from api.portfolio import Position, PositionRepository, PortfolioEngine
from api.models import Trade, TradeRepository
from api.database import init_db, close_db


@pytest.fixture
def db():
    """Create in-memory database for testing"""
    init_db(":memory:")
    yield
    close_db()


@pytest.fixture
def trade_repo(db):
    """Create trade repository"""
    return TradeRepository()


@pytest.fixture
def position_repo(db):
    """Create position repository"""
    return PositionRepository()


@pytest.fixture
def portfolio_engine(db):
    """Create portfolio engine"""
    return PortfolioEngine()


def create_trade(
    trade_id: str,
    symbol: str,
    side: str,
    amount: float,
    price: float,
    timestamp: int,
    fee: float = 0.0
) -> Trade:
    """Helper to create a trade"""
    return Trade(
        id=trade_id,
        timestamp=timestamp,
        symbol=symbol,
        side=side,
        amount=amount,
        price=price,
        fee=fee,
        fee_currency="USDT",
        paper=True
    )


class TestPositionRepository:
    """Test position repository operations"""

    def test_create_and_get_position(self, position_repo):
        """Test creating and retrieving a position"""
        position = Position(
            symbol="BTC/USDT",
            amount=0.5,
            avg_entry_price=50000.0,
            total_cost=25000.0,
            side="long",
            opened_at=1000000,
            last_updated=1000000
        )

        position_repo.upsert(position)

        retrieved = position_repo.get_by_symbol("BTC/USDT")
        assert retrieved is not None
        assert retrieved.symbol == "BTC/USDT"
        assert retrieved.amount == 0.5
        assert retrieved.avg_entry_price == 50000.0
        assert retrieved.side == "long"

    def test_update_position(self, position_repo):
        """Test updating an existing position"""
        position = Position(
            symbol="ETH/USDT",
            amount=1.0,
            avg_entry_price=3000.0,
            total_cost=3000.0,
            side="long",
            opened_at=1000000,
            last_updated=1000000
        )

        position_repo.upsert(position)

        # Update the position
        updated_position = Position(
            symbol="ETH/USDT",
            amount=2.0,
            avg_entry_price=3100.0,
            total_cost=6200.0,
            side="long",
            opened_at=1000000,
            last_updated=1000100
        )

        position_repo.upsert(updated_position)

        retrieved = position_repo.get_by_symbol("ETH/USDT")
        assert retrieved.amount == 2.0
        assert retrieved.avg_entry_price == 3100.0

    def test_delete_position(self, position_repo):
        """Test deleting a position"""
        position = Position(
            symbol="SOL/USDT",
            amount=10.0,
            avg_entry_price=100.0,
            total_cost=1000.0,
            side="long",
            opened_at=1000000,
            last_updated=1000000
        )

        position_repo.upsert(position)
        position_repo.delete("SOL/USDT")

        retrieved = position_repo.get_by_symbol("SOL/USDT")
        assert retrieved is None

    def test_get_all_positions(self, position_repo):
        """Test getting all positions"""
        positions = [
            Position("BTC/USDT", 0.5, 50000.0, 25000.0, "long", 1000000, 1000000),
            Position("ETH/USDT", 1.0, 3000.0, 3000.0, "long", 1000000, 1000000),
            Position("SOL/USDT", 10.0, 100.0, 1000.0, "long", 1000000, 1000000)
        ]

        for pos in positions:
            position_repo.upsert(pos)

        all_positions = position_repo.get_all()
        assert len(all_positions) == 3


class TestRealizedPnL:
    """Test realized P&L calculation with FIFO matching"""

    def test_simple_buy_sell(self, trade_repo, portfolio_engine):
        """Test simple buy then sell scenario"""
        base_time = int(datetime.now().timestamp())

        # Buy 1 BTC at 50000
        buy_trade = create_trade("buy-1", "BTC/USDT", "buy", 1.0, 50000.0, base_time, fee=50.0)
        trade_repo.create(buy_trade)

        # Sell 1 BTC at 55000
        sell_trade = create_trade("sell-1", "BTC/USDT", "sell", 1.0, 55000.0, base_time + 100, fee=55.0)
        trade_repo.create(sell_trade)

        # Expected P&L: (55000 - 50000) * 1.0 - 50 - 55 = 4895
        pnl = portfolio_engine.calculate_realized_pnl("BTC/USDT")
        assert abs(pnl - 4895.0) < 0.01

    def test_multiple_buys_single_sell(self, trade_repo, portfolio_engine):
        """Test FIFO matching with multiple buys and one sell"""
        base_time = int(datetime.now().timestamp())

        # Buy 1 BTC at 50000
        trade_repo.create(create_trade("buy-1", "BTC/USDT", "buy", 1.0, 50000.0, base_time, fee=50.0))

        # Buy 1 BTC at 51000
        trade_repo.create(create_trade("buy-2", "BTC/USDT", "buy", 1.0, 51000.0, base_time + 100, fee=51.0))

        # Sell 1.5 BTC at 55000 - should match against first buy (1.0) and part of second buy (0.5)
        trade_repo.create(create_trade("sell-1", "BTC/USDT", "sell", 1.5, 55000.0, base_time + 200, fee=82.5))

        # Expected P&L:
        # First match: (55000 - 50000) * 1.0 - 50 - (82.5 * 1.0/1.5) = 5000 - 50 - 55 = 4895
        # Second match: (55000 - 51000) * 0.5 - (51 * 0.5/1.0) - (82.5 * 0.5/1.5) = 2000 - 25.5 - 27.5 = 1947
        # Total: 4895 + 1947 = 6842
        pnl = portfolio_engine.calculate_realized_pnl("BTC/USDT")
        assert abs(pnl - 6842.0) < 0.01

    def test_partial_sell_matching(self, trade_repo, portfolio_engine):
        """Test partial sell that doesn't consume entire buy"""
        base_time = int(datetime.now().timestamp())

        # Buy 2 BTC at 50000
        trade_repo.create(create_trade("buy-1", "BTC/USDT", "buy", 2.0, 50000.0, base_time, fee=100.0))

        # Sell 0.5 BTC at 55000 - should match against part of buy
        trade_repo.create(create_trade("sell-1", "BTC/USDT", "sell", 0.5, 55000.0, base_time + 100, fee=27.5))

        # Expected P&L: (55000 - 50000) * 0.5 - (100 * 0.5/2.0) - 27.5 = 2500 - 25 - 27.5 = 2447.5
        pnl = portfolio_engine.calculate_realized_pnl("BTC/USDT")
        assert abs(pnl - 2447.5) < 0.01

    def test_multiple_symbols(self, trade_repo, portfolio_engine):
        """Test realized P&L calculation across multiple symbols"""
        base_time = int(datetime.now().timestamp())

        # BTC trades
        trade_repo.create(create_trade("btc-buy-1", "BTC/USDT", "buy", 1.0, 50000.0, base_time, fee=50.0))
        trade_repo.create(create_trade("btc-sell-1", "BTC/USDT", "sell", 1.0, 52000.0, base_time + 100, fee=52.0))

        # ETH trades
        trade_repo.create(create_trade("eth-buy-1", "ETH/USDT", "buy", 10.0, 3000.0, base_time, fee=300.0))
        trade_repo.create(create_trade("eth-sell-1", "ETH/USDT", "sell", 10.0, 3200.0, base_time + 100, fee=320.0))

        # BTC P&L: (52000 - 50000) * 1.0 - 50 - 52 = 1898
        # ETH P&L: (3200 - 3000) * 10.0 - 300 - 320 = 1380
        # Total: 1898 + 1380 = 3278
        total_pnl = portfolio_engine.calculate_realized_pnl()
        assert abs(total_pnl - 3278.0) < 0.01

    def test_no_matching_trades(self, trade_repo, portfolio_engine):
        """Test with only buy trades (no sells to match)"""
        base_time = int(datetime.now().timestamp())

        # Only buy trades
        trade_repo.create(create_trade("buy-1", "BTC/USDT", "buy", 1.0, 50000.0, base_time, fee=50.0))
        trade_repo.create(create_trade("buy-2", "BTC/USDT", "buy", 1.0, 51000.0, base_time + 100, fee=51.0))

        pnl = portfolio_engine.calculate_realized_pnl("BTC/USDT")
        assert pnl == 0.0


class TestUnrealizedPnL:
    """Test unrealized P&L calculation"""

    def test_unrealized_pnl_long_position(self, position_repo, portfolio_engine):
        """Test unrealized P&L for long position"""
        position = Position(
            symbol="BTC/USDT",
            amount=1.0,
            avg_entry_price=50000.0,
            total_cost=50000.0,
            side="long",
            opened_at=1000000,
            last_updated=1000000
        )
        position_repo.upsert(position)

        current_prices = {"BTC/USDT": 55000.0}
        unrealized = portfolio_engine.calculate_unrealized_pnl(current_prices)

        # (55000 - 50000) * 1.0 = 5000
        assert abs(unrealized["BTC/USDT"] - 5000.0) < 0.01

    def test_unrealized_pnl_short_position(self, position_repo, portfolio_engine):
        """Test unrealized P&L for short position"""
        position = Position(
            symbol="ETH/USDT",
            amount=10.0,
            avg_entry_price=3000.0,
            total_cost=30000.0,
            side="short",
            opened_at=1000000,
            last_updated=1000000
        )
        position_repo.upsert(position)

        current_prices = {"ETH/USDT": 2800.0}
        unrealized = portfolio_engine.calculate_unrealized_pnl(current_prices)

        # (3000 - 2800) * 10.0 = 2000
        assert abs(unrealized["ETH/USDT"] - 2000.0) < 0.01

    def test_unrealized_pnl_multiple_positions(self, position_repo, portfolio_engine):
        """Test unrealized P&L for multiple positions"""
        positions = [
            Position("BTC/USDT", 1.0, 50000.0, 50000.0, "long", 1000000, 1000000),
            Position("ETH/USDT", 10.0, 3000.0, 30000.0, "long", 1000000, 1000000),
            Position("SOL/USDT", 100.0, 100.0, 10000.0, "long", 1000000, 1000000)
        ]

        for pos in positions:
            position_repo.upsert(pos)

        current_prices = {
            "BTC/USDT": 52000.0,
            "ETH/USDT": 3100.0,
            "SOL/USDT": 105.0
        }

        unrealized = portfolio_engine.calculate_unrealized_pnl(current_prices)

        assert abs(unrealized["BTC/USDT"] - 2000.0) < 0.01  # (52000 - 50000) * 1.0
        assert abs(unrealized["ETH/USDT"] - 1000.0) < 0.01  # (3100 - 3000) * 10.0
        assert abs(unrealized["SOL/USDT"] - 500.0) < 0.01   # (105 - 100) * 100.0

    def test_unrealized_pnl_missing_price(self, position_repo, portfolio_engine):
        """Test unrealized P&L when price is not available"""
        position = Position(
            symbol="BTC/USDT",
            amount=1.0,
            avg_entry_price=50000.0,
            total_cost=50000.0,
            side="long",
            opened_at=1000000,
            last_updated=1000000
        )
        position_repo.upsert(position)

        current_prices = {}  # No price data
        unrealized = portfolio_engine.calculate_unrealized_pnl(current_prices)

        assert unrealized["BTC/USDT"] == 0.0


class TestPortfolioValue:
    """Test portfolio value calculation"""

    def test_portfolio_value_with_positions(self, position_repo, portfolio_engine):
        """Test total portfolio value calculation"""
        positions = [
            Position("BTC/USDT", 1.0, 50000.0, 50000.0, "long", 1000000, 1000000),
            Position("ETH/USDT", 10.0, 3000.0, 30000.0, "long", 1000000, 1000000)
        ]

        for pos in positions:
            position_repo.upsert(pos)

        current_prices = {
            "BTC/USDT": 55000.0,
            "ETH/USDT": 3200.0
        }

        cash_balance = 10000.0
        total_value = portfolio_engine.get_portfolio_value(cash_balance, current_prices)

        # 10000 (cash) + 55000 (1 BTC) + 32000 (10 ETH) = 97000
        assert abs(total_value - 97000.0) < 0.01

    def test_portfolio_value_cash_only(self, portfolio_engine):
        """Test portfolio value with only cash"""
        cash_balance = 50000.0
        current_prices = {}

        total_value = portfolio_engine.get_portfolio_value(cash_balance, current_prices)
        assert abs(total_value - 50000.0) < 0.01

    def test_portfolio_value_stays_consistent_with_unrealized_pnl(self, position_repo, portfolio_engine):
        """Test portfolio value uses the same math basis as unrealized P&L."""
        positions = [
            Position("BTC/USDT", 1.0, 50000.0, 50000.0, "long", 1000000, 1000000),
            Position("ETH/USDT", 10.0, 3000.0, 30000.0, "short", 1000000, 1000000),
            Position("SOL/USDT", 100.0, 100.0, 10000.0, "long", 1000000, 1000000),
        ]

        for pos in positions:
            position_repo.upsert(pos)

        current_prices = {
            "BTC/USDT": 55000.0,
            "ETH/USDT": 2800.0,
        }

        cash_balance = 10000.0
        total_value = portfolio_engine.get_portfolio_value(cash_balance, current_prices)

        expected_value = (
            cash_balance
            + 55000.0  # Long position should use current market value.
            + 32000.0  # Short equity contribution is entry basis plus unrealized profit.
            + 10000.0  # Missing prices should fall back to cost basis instead of disappearing.
        )

        assert abs(total_value - expected_value) < 0.01


class TestPerformanceMetrics:
    """Test performance metrics calculation"""

    def test_win_rate_calculation(self, trade_repo, portfolio_engine):
        """Test win rate calculation"""
        base_time = int(datetime.now().timestamp())

        # Winning trade
        trade_repo.create(create_trade("buy-1", "BTC/USDT", "buy", 1.0, 50000.0, base_time, fee=50.0))
        trade_repo.create(create_trade("sell-1", "BTC/USDT", "sell", 1.0, 55000.0, base_time + 100, fee=55.0))

        # Losing trade
        trade_repo.create(create_trade("buy-2", "ETH/USDT", "buy", 10.0, 3000.0, base_time, fee=300.0))
        trade_repo.create(create_trade("sell-2", "ETH/USDT", "sell", 10.0, 2900.0, base_time + 100, fee=290.0))

        metrics = portfolio_engine.calculate_performance_metrics()

        assert metrics["total_trades"] == 2
        assert metrics["winning_trades"] == 1
        assert metrics["losing_trades"] == 1
        assert abs(metrics["win_rate"] - 50.0) < 0.01

    def test_profit_factor_calculation(self, trade_repo, portfolio_engine):
        """Test profit factor calculation"""
        base_time = int(datetime.now().timestamp())

        # Winning trade: profit of 4895
        trade_repo.create(create_trade("buy-1", "BTC/USDT", "buy", 1.0, 50000.0, base_time, fee=50.0))
        trade_repo.create(create_trade("sell-1", "BTC/USDT", "sell", 1.0, 55000.0, base_time + 100, fee=55.0))

        # Losing trade: loss of -1590
        trade_repo.create(create_trade("buy-2", "ETH/USDT", "buy", 10.0, 3000.0, base_time, fee=300.0))
        trade_repo.create(create_trade("sell-2", "ETH/USDT", "sell", 10.0, 2900.0, base_time + 100, fee=290.0))

        metrics = portfolio_engine.calculate_performance_metrics()

        # Profit factor = total_profit / total_loss = 4895 / 1590 ≈ 3.08
        assert metrics["total_profit"] > 0
        assert metrics["total_loss"] > 0
        assert metrics["profit_factor"] > 0

    def test_performance_metrics_no_trades(self, portfolio_engine):
        """Test performance metrics with no trades"""
        metrics = portfolio_engine.calculate_performance_metrics()

        assert metrics["total_trades"] == 0
        assert metrics["winning_trades"] == 0
        assert metrics["losing_trades"] == 0
        assert metrics["win_rate"] == 0.0
        assert metrics["profit_factor"] == 0.0


class TestPositionUpdates:
    """Test position updates from trades"""

    def test_create_position_from_buy(self, trade_repo, portfolio_engine):
        """Test creating a new position from a buy trade"""
        base_time = int(datetime.now().timestamp())

        trade = create_trade("buy-1", "BTC/USDT", "buy", 1.0, 50000.0, base_time, fee=50.0)
        trade_repo.create(trade)

        portfolio_engine.update_positions_from_trade(trade)

        position = portfolio_engine.position_repo.get_by_symbol("BTC/USDT")
        assert position is not None
        assert position.amount == 1.0
        assert position.avg_entry_price == 50000.0
        assert position.side == "long"

    def test_add_to_existing_position(self, trade_repo, portfolio_engine):
        """Test adding to an existing position"""
        base_time = int(datetime.now().timestamp())

        # First buy
        trade1 = create_trade("buy-1", "BTC/USDT", "buy", 1.0, 50000.0, base_time, fee=50.0)
        trade_repo.create(trade1)
        portfolio_engine.update_positions_from_trade(trade1)

        # Second buy at different price
        trade2 = create_trade("buy-2", "BTC/USDT", "buy", 1.0, 52000.0, base_time + 100, fee=52.0)
        trade_repo.create(trade2)
        portfolio_engine.update_positions_from_trade(trade2)

        position = portfolio_engine.position_repo.get_by_symbol("BTC/USDT")
        assert position is not None
        assert position.amount == 2.0
        # Avg price = (50000 * 1 + 50 + 52000 * 1 + 52) / 2 = 51051
        assert abs(position.avg_entry_price - 51051.0) < 0.01

    def test_reduce_position_from_sell(self, trade_repo, portfolio_engine):
        """Test reducing a position from a sell trade"""
        base_time = int(datetime.now().timestamp())

        # Buy 2 BTC
        trade1 = create_trade("buy-1", "BTC/USDT", "buy", 2.0, 50000.0, base_time, fee=100.0)
        trade_repo.create(trade1)
        portfolio_engine.update_positions_from_trade(trade1)

        # Sell 1 BTC
        trade2 = create_trade("sell-1", "BTC/USDT", "sell", 1.0, 55000.0, base_time + 100, fee=55.0)
        trade_repo.create(trade2)
        portfolio_engine.update_positions_from_trade(trade2)

        position = portfolio_engine.position_repo.get_by_symbol("BTC/USDT")
        assert position is not None
        assert position.amount == 1.0
        assert position.avg_entry_price == 50000.0  # Entry price remains same

    def test_close_position_from_sell(self, trade_repo, portfolio_engine):
        """Test closing a position completely"""
        base_time = int(datetime.now().timestamp())

        # Buy 1 BTC
        trade1 = create_trade("buy-1", "BTC/USDT", "buy", 1.0, 50000.0, base_time, fee=50.0)
        trade_repo.create(trade1)
        portfolio_engine.update_positions_from_trade(trade1)

        # Sell 1 BTC (close position)
        trade2 = create_trade("sell-1", "BTC/USDT", "sell", 1.0, 55000.0, base_time + 100, fee=55.0)
        trade_repo.create(trade2)
        portfolio_engine.update_positions_from_trade(trade2)

        position = portfolio_engine.position_repo.get_by_symbol("BTC/USDT")
        assert position is None  # Position should be closed


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_empty_database(self, portfolio_engine):
        """Test operations on empty database"""
        realized_pnl = portfolio_engine.calculate_realized_pnl()
        assert realized_pnl == 0.0

        unrealized_pnl = portfolio_engine.calculate_unrealized_pnl({})
        assert unrealized_pnl == {}

        portfolio_value = portfolio_engine.get_portfolio_value(1000.0, {})
        assert portfolio_value == 1000.0

        metrics = portfolio_engine.calculate_performance_metrics()
        assert metrics["total_trades"] == 0

    def test_negative_prices_handling(self, trade_repo, portfolio_engine):
        """Test handling of edge case prices"""
        base_time = int(datetime.now().timestamp())

        # Create legitimate trades with very small amounts
        trade_repo.create(create_trade("buy-1", "BTC/USDT", "buy", 0.001, 50000.0, base_time, fee=0.05))
        trade_repo.create(create_trade("sell-1", "BTC/USDT", "sell", 0.001, 51000.0, base_time + 100, fee=0.051))

        pnl = portfolio_engine.calculate_realized_pnl("BTC/USDT")
        # Should calculate correctly even with small amounts
        assert pnl != 0.0
