from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


STRONG_BUY_THRESHOLD = 27.0
BUY_THRESHOLD = 13.0
SELL_THRESHOLD = -13.0
STRONG_SELL_THRESHOLD = -27.0
THRESHOLD_TOLERANCE = 1e-9


@dataclass(frozen=True, slots=True)
class StrategySignalSnapshot:
    score_total: float
    trade_signal: str
    bullish_count: int
    bearish_count: int
    neutral_count: int
    strongest_bullish: str | None
    strongest_bearish: str | None
    indicator_count: int


def resolve_trade_signal(score_total: float) -> str:
    if not math.isfinite(score_total):
        raise ValueError("score_total must be finite")

    if _meets_or_exceeds(score_total, STRONG_BUY_THRESHOLD):
        return "strong_buy"
    if _meets_or_exceeds(score_total, BUY_THRESHOLD):
        return "buy"
    if _meets_or_falls_below(score_total, STRONG_SELL_THRESHOLD):
        return "strong_sell"
    if _meets_or_falls_below(score_total, SELL_THRESHOLD):
        return "sell"
    return "hold"


def build_strategy_signal(
    indicators: Iterable[Mapping[str, Any]],
    *,
    score_total: float | None = None,
) -> StrategySignalSnapshot:
    indicator_items = list(indicators)
    resolved_score_total = _resolve_score_total(indicator_items, score_total)

    bullish_count = 0
    bearish_count = 0
    neutral_count = 0
    strongest_bullish: tuple[float, str] | None = None
    strongest_bearish: tuple[float, str] | None = None

    for indicator in indicator_items:
        score = _coerce_score(indicator.get("score", 0.0))
        name = str(indicator.get("name", "unknown"))

        if score > 0:
            bullish_count += 1
            if strongest_bullish is None or score > strongest_bullish[0]:
                strongest_bullish = (score, name)
        elif score < 0:
            bearish_count += 1
            if strongest_bearish is None or score < strongest_bearish[0]:
                strongest_bearish = (score, name)
        else:
            neutral_count += 1

    return StrategySignalSnapshot(
        score_total=resolved_score_total,
        trade_signal=resolve_trade_signal(resolved_score_total),
        bullish_count=bullish_count,
        bearish_count=bearish_count,
        neutral_count=neutral_count,
        strongest_bullish=strongest_bullish[1] if strongest_bullish else None,
        strongest_bearish=strongest_bearish[1] if strongest_bearish else None,
        indicator_count=len(indicator_items),
    )


def _resolve_score_total(
    indicators: list[Mapping[str, Any]],
    score_total: float | None,
) -> float:
    if score_total is None:
        return sum(_coerce_score(indicator.get("score", 0.0)) for indicator in indicators)

    return _coerce_score(score_total)


def _coerce_score(value: Any) -> float:
    score = float(value)
    if not math.isfinite(score):
        raise ValueError("score values must be finite")
    return score


def _meets_or_exceeds(score_total: float, threshold: float) -> bool:
    return score_total >= threshold or math.isclose(
        score_total,
        threshold,
        rel_tol=0.0,
        abs_tol=THRESHOLD_TOLERANCE,
    )


def _meets_or_falls_below(score_total: float, threshold: float) -> bool:
    return score_total <= threshold or math.isclose(
        score_total,
        threshold,
        rel_tol=0.0,
        abs_tol=THRESHOLD_TOLERANCE,
    )
