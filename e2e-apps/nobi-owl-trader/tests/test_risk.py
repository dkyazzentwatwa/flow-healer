import pytest
from api.risk import RiskManager, RiskLimits
from api.database import init_db, close_db

@pytest.fixture
def db():
    init_db(":memory:")
    yield
    close_db()

def test_check_daily_loss_limit(db):
    """Test daily loss limit enforcement"""
    limits = RiskLimits(
        daily_loss_limit=500.0,
        max_position_size_pct=20.0,
        max_exposure_pct=80.0
    )

    risk_mgr = RiskManager(limits)

    # Mock today's P&L as -$450 (approaching limit)
    result = risk_mgr.check_can_trade(today_pnl=-450.0)
    assert result["can_trade"] == True
    assert result["warning"] is not None

    # Mock today's P&L as -$600 (exceeded limit)
    result = risk_mgr.check_can_trade(today_pnl=-600.0)
    assert result["can_trade"] == False
    assert "daily loss limit" in result["reason"].lower()

def test_position_size_limit(db):
    """Test position size limit enforcement"""
    limits = RiskLimits(
        daily_loss_limit=500.0,
        max_position_size_pct=20.0,
        max_exposure_pct=80.0
    )

    risk_mgr = RiskManager(limits)

    # Test position within limit
    result = risk_mgr.check_can_trade(
        today_pnl=0.0,
        position_size=1500.0,
        portfolio_value=10000.0,
        total_exposure=0.0
    )
    assert result["can_trade"] == True

    # Test position exceeding limit (25% of 10k = 2500)
    result = risk_mgr.check_can_trade(
        today_pnl=0.0,
        position_size=2500.0,
        portfolio_value=10000.0,
        total_exposure=0.0
    )
    assert result["can_trade"] == False
    assert "position size" in result["reason"].lower()

def test_exposure_limit(db):
    """Test total exposure limit enforcement"""
    limits = RiskLimits(
        daily_loss_limit=500.0,
        max_position_size_pct=20.0,
        max_exposure_pct=80.0
    )

    risk_mgr = RiskManager(limits)

    # Test exposure within limit
    result = risk_mgr.check_can_trade(
        today_pnl=0.0,
        position_size=0.0,
        portfolio_value=10000.0,
        total_exposure=7000.0
    )
    assert result["can_trade"] == True

    # Test exposure exceeding limit (85% of 10k = 8500)
    result = risk_mgr.check_can_trade(
        today_pnl=0.0,
        position_size=0.0,
        portfolio_value=10000.0,
        total_exposure=8500.0
    )
    assert result["can_trade"] == False
    assert "exposure" in result["reason"].lower()

def test_calculate_position_size(db):
    """Test position size calculation"""
    limits = RiskLimits(
        daily_loss_limit=500.0,
        max_position_size_pct=20.0,
        max_exposure_pct=80.0
    )

    risk_mgr = RiskManager(limits)

    # Risk 2% of $10k with 5% stop loss
    # Risk amount = $200, Position = $200 / 5% = $4000
    # But capped at 20% = $2000
    position_size = risk_mgr.calculate_position_size(
        portfolio_value=10000.0,
        risk_pct=2.0,
        stop_loss_pct=5.0
    )
    assert position_size == 2000.0  # Capped at max_position_size_pct

    # Risk 1% of $10k with 10% stop loss = $1000 (under cap)
    position_size = risk_mgr.calculate_position_size(
        portfolio_value=10000.0,
        risk_pct=1.0,
        stop_loss_pct=10.0
    )
    assert position_size == 1000.0

    # Test with zero stop loss
    position_size = risk_mgr.calculate_position_size(
        portfolio_value=10000.0,
        risk_pct=2.0,
        stop_loss_pct=0.0
    )
    assert position_size == 0.0

    # Test max position size capping (would be $10k but capped at 20% = $2k)
    position_size = risk_mgr.calculate_position_size(
        portfolio_value=10000.0,
        risk_pct=5.0,
        stop_loss_pct=0.5
    )
    assert position_size == 2000.0  # Capped at max_position_size_pct
