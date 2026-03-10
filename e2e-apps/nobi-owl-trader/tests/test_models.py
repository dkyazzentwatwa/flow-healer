import pytest
from datetime import datetime
from api.models import AutomationRule, AutomationRuleRepository, Trade, TradeRepository
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


def test_trade_round_trip_keeps_boolean_fields_and_stable_serialization(db):
    repo = TradeRepository()

    trade = Trade(
        id="test-bool-001",
        timestamp=int(datetime.now().timestamp()),
        symbol="ETH/USDT",
        side="buy",
        amount=1.5,
        price=2500.0,
        paper=True,
        is_trailing=True,
    )

    repo.create(trade)
    retrieved = repo.get_by_id("test-bool-001")

    assert retrieved is not None
    assert retrieved.paper is True
    assert isinstance(retrieved.paper, bool)
    assert retrieved.is_trailing is True
    assert isinstance(retrieved.is_trailing, bool)
    assert retrieved.to_dict()["paper"] is True
    assert retrieved.to_dict()["is_trailing"] is True


def test_automation_rule_serialization_preserves_boolean_defaults(db):
    repo = AutomationRuleRepository()

    rule = AutomationRule(
        id="rule-001",
        name="Momentum Long",
        symbol="BTC/USDT",
        timeframe="1h",
        side="buy",
        signal_type="RSI",
        amount=25.0,
    )

    repo.create(rule)
    retrieved = repo.get_by_id("rule-001")

    assert retrieved is not None
    assert retrieved.only_if_in_position is True
    assert isinstance(retrieved.only_if_in_position, bool)
    assert retrieved.reduce_only is True
    assert isinstance(retrieved.reduce_only, bool)
    assert retrieved.is_active is True
    assert isinstance(retrieved.is_active, bool)
    assert retrieved.to_dict()["cooldown_minutes"] == 60
    assert retrieved.to_dict()["only_if_in_position"] is True
