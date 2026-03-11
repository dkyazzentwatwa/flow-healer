import pytest
from api.risk import RiskManager, RiskLimits
from api.database import init_db, close_db


@pytest.fixture
def db():
    init_db(":memory:")
    yield
    close_db()


def make_limits() -> RiskLimits:
    return RiskLimits(
        max_daily_loss=500.0,
        max_drawdown_pct=20.0,
        max_position_size_pct=20.0,
        max_exposure_pct=80.0,
    )


def test_check_daily_loss_limit(db):
    """Test daily loss limit enforcement"""
    risk_mgr = RiskManager(make_limits())

    # Mock today's P&L as -$450 (approaching limit)
    result = risk_mgr.check_can_trade(today_pnl=-450.0)
    assert result["can_trade"] is True
    assert result["warning"] is not None

    # Mock today's P&L as -$600 (exceeded limit)
    result = risk_mgr.check_can_trade(today_pnl=-600.0)
    assert result["can_trade"] is False
    assert "daily loss limit" in result["reason"].lower()


def test_position_size_limit(db):
    """Test position size limit enforcement"""
    risk_mgr = RiskManager(make_limits())

    # Test position within limit
    result = risk_mgr.check_can_trade(
        today_pnl=0.0,
        position_size=1500.0,
        portfolio_value=10000.0,
        total_exposure=0.0
    )
    assert result["can_trade"] is True

    # Test position exceeding limit (25% of 10k = 2500)
    result = risk_mgr.check_can_trade(
        today_pnl=0.0,
        position_size=2500.0,
        portfolio_value=10000.0,
        total_exposure=0.0
    )
    assert result["can_trade"] is False
    assert "position size" in result["reason"].lower()


def test_exposure_limit(db):
    """Test total exposure limit enforcement"""
    risk_mgr = RiskManager(make_limits())

    # Test exposure within limit
    result = risk_mgr.check_can_trade(
        today_pnl=0.0,
        position_size=0.0,
        portfolio_value=10000.0,
        total_exposure=7000.0
    )
    assert result["can_trade"] is True

    # Test exposure exceeding limit (85% of 10k = 8500)
    result = risk_mgr.check_can_trade(
        today_pnl=0.0,
        position_size=0.0,
        portfolio_value=10000.0,
        total_exposure=8500.0
    )
    assert result["can_trade"] is False
    assert "exposure" in result["reason"].lower()


def test_drawdown_limit_blocks_at_exact_threshold(db):
    """Test drawdown guardrail at the configured edge."""
    risk_mgr = RiskManager(make_limits())

    result = risk_mgr.check_can_trade(
        today_pnl=0.0,
        position_size=0.0,
        portfolio_value=8000.0,
        total_exposure=0.0,
        peak_equity=10000.0,
    )

    assert result["can_trade"] is False
    assert "drawdown" in result["reason"].lower()


@pytest.mark.parametrize(
    ("kwargs", "reason_fragment"),
    [
        (
            {"today_pnl": True, "position_size": 0.0, "portfolio_value": 10000.0, "total_exposure": 0.0},
            "today p&l",
        ),
        (
            {"today_pnl": 0.0, "position_size": -1.0, "portfolio_value": 10000.0, "total_exposure": 0.0},
            "position size",
        ),
        (
            {"today_pnl": 0.0, "position_size": True, "portfolio_value": 10000.0, "total_exposure": 0.0},
            "position size",
        ),
        (
            {"today_pnl": 0.0, "position_size": 0.0, "portfolio_value": 0.0, "total_exposure": 0.0},
            "portfolio value",
        ),
        (
            {"today_pnl": 0.0, "position_size": 0.0, "portfolio_value": True, "total_exposure": 0.0},
            "portfolio value",
        ),
        (
            {"today_pnl": 0.0, "position_size": 0.0, "portfolio_value": 10000.0, "total_exposure": -5.0},
            "total exposure",
        ),
        (
            {"today_pnl": 0.0, "position_size": 0.0, "portfolio_value": 10000.0, "total_exposure": True},
            "total exposure",
        ),
        (
            {
                "today_pnl": 0.0,
                "position_size": 0.0,
                "portfolio_value": 10000.0,
                "total_exposure": 0.0,
                "peak_equity": -100.0,
            },
            "peak equity",
        ),
        (
            {
                "today_pnl": 0.0,
                "position_size": 0.0,
                "portfolio_value": 10000.0,
                "total_exposure": 0.0,
                "peak_equity": True,
            },
            "peak equity",
        ),
    ],
)
def test_check_can_trade_rejects_invalid_inputs(db, kwargs, reason_fragment):
    """Test invalid risk inputs are rejected instead of silently passing."""
    risk_mgr = RiskManager(make_limits())

    result = risk_mgr.check_can_trade(**kwargs)

    assert result["can_trade"] is False
    assert reason_fragment in result["reason"].lower()


@pytest.mark.parametrize(
    ("portfolio_value", "risk_pct", "stop_loss_pct"),
    [
        (True, 2.0, 5.0),
        (10000.0, True, 5.0),
        (10000.0, 2.0, True),
    ],
)
def test_calculate_position_size_returns_zero_for_boolean_inputs(
    db, portfolio_value, risk_pct, stop_loss_pct
):
    """Test boolean values are rejected instead of being treated as numbers."""
    risk_mgr = RiskManager(make_limits())

    position_size = risk_mgr.calculate_position_size(
        portfolio_value=portfolio_value,
        risk_pct=risk_pct,
        stop_loss_pct=stop_loss_pct,
    )

    assert position_size == 0.0


def test_calculate_position_size(db):
    """Test position size calculation"""
    risk_mgr = RiskManager(make_limits())

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


@pytest.mark.parametrize(
    ("portfolio_value", "risk_pct", "stop_loss_pct"),
    [
        (0.0, 2.0, 5.0),
        (-1000.0, 2.0, 5.0),
        (10000.0, 0.0, 5.0),
        (10000.0, -1.0, 5.0),
        (10000.0, 2.0, -5.0),
    ],
)
def test_calculate_position_size_returns_zero_for_invalid_inputs(
    db, portfolio_value, risk_pct, stop_loss_pct
):
    """Test invalid sizing inputs are safely clamped to zero."""
    risk_mgr = RiskManager(make_limits())

    position_size = risk_mgr.calculate_position_size(
        portfolio_value=portfolio_value,
        risk_pct=risk_pct,
        stop_loss_pct=stop_loss_pct,
    )

    assert position_size == 0.0
