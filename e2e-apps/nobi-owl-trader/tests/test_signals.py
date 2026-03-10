import math

import pytest

from api.strategy.signals import build_strategy_signal, resolve_trade_signal


@pytest.mark.parametrize(
    ("score_total", "expected_signal"),
    [
        (27.0, "strong_buy"),
        (13.0, "buy"),
        (12.99, "hold"),
        (-12.99, "hold"),
        (-13.0, "sell"),
        (-27.0, "strong_sell"),
    ],
)
def test_resolve_trade_signal_uses_strategy_thresholds(score_total, expected_signal):
    assert resolve_trade_signal(score_total) == expected_signal


@pytest.mark.parametrize("score_total", [math.nan, math.inf, -math.inf])
def test_resolve_trade_signal_rejects_non_finite_scores(score_total):
    with pytest.raises(ValueError, match="finite"):
        resolve_trade_signal(score_total)


def test_build_strategy_signal_summarizes_indicator_bias():
    snapshot = build_strategy_signal(
        [
            {"name": "RSI", "score": 2.0, "signal": "oversold"},
            {"name": "MACD", "score": 1.0, "signal": "bullish"},
            {"name": "ADX", "score": 0.0, "signal": "neutral"},
            {"name": "CCI", "score": -2.0, "signal": "strong"},
        ]
    )

    assert snapshot.score_total == 1.0
    assert snapshot.trade_signal == "hold"
    assert snapshot.bullish_count == 2
    assert snapshot.bearish_count == 1
    assert snapshot.neutral_count == 1
    assert snapshot.strongest_bullish == "RSI"
    assert snapshot.strongest_bearish == "CCI"
    assert snapshot.indicator_count == 4


def test_build_strategy_signal_uses_explicit_score_total_when_provided():
    snapshot = build_strategy_signal(
        [
            {"name": "RSI", "score": 2.0},
            {"name": "MACD", "score": 1.0},
        ],
        score_total=-13.0,
    )

    assert snapshot.score_total == -13.0
    assert snapshot.trade_signal == "sell"
    assert snapshot.bullish_count == 2
    assert snapshot.bearish_count == 0
    assert snapshot.neutral_count == 0
