import pytest
from datetime import datetime
from api.models import Trade, TradeRepository
from api.database import init_db

@pytest.fixture
def db():
    """Create in-memory database for testing"""
    init_db(":memory:")
    yield
    from api.database import close_db
    close_db()

def test_create_trade(db):
    """Test creating a trade"""
    repo = TradeRepository()

    trade = Trade(
        id="test-001",
        timestamp=int(datetime.now().timestamp()),
        symbol="BTC/USDT",
        side="buy",
        amount=0.1,
        price=50000.0,
        fee=5.0,
        fee_currency="USDT",
        paper=True
    )

    repo.create(trade)

    # Retrieve and verify
    retrieved = repo.get_by_id("test-001")
    assert retrieved is not None
    assert retrieved.symbol == "BTC/USDT"
    assert retrieved.side == "buy"
    assert retrieved.amount == 0.1
    assert retrieved.price == 50000.0
