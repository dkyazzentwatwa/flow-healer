import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

from api.backtest.downloader import DataDownloader
from api.backtest.engine import BacktestEngine
from api.models import AutomationRule, AutomationRuleRepository
from api.trading_engine import TradingEngine
from api.logger import nobi_logger

# Disable noisy logging during tuning
nobi_logger._log = lambda *args, **kwargs: None

DAYS_BY_TIMEFRAME = {
    "1m": 7,
    "5m": 30,
    "15m": 60,
    "1h": 180,
    "4h": 365,
    "1d": 1000,
}

if os.getenv("FAST") == "1":
    DAYS_BY_TIMEFRAME = {
        "1m": 3,
        "5m": 14,
        "15m": 30,
        "1h": 90,
        "4h": 180,
        "1d": 365,
    }

INITIAL_BALANCE = 100000.0
TOP_K = 5
ENTRY_CANDIDATES_LIMIT = 12
EXIT_CANDIDATES_LIMIT = 18


def clone_rule(rule: AutomationRule, **updates) -> AutomationRule:
    data = rule.__dict__.copy()
    data.update(updates)
    return AutomationRule(**data)


def clamp_min(value: float, minimum: float = 0.1) -> float:
    return max(minimum, value)


def return_pct(result: Dict) -> float:
    return (result["final_balance"] - result["initial_balance"]) / result["initial_balance"] * 100


def run_pair(engine: BacktestEngine, entry: AutomationRule, exit_rule: AutomationRule, start_dt, end_dt):
    return engine.run_pair(entry, exit_rule, start_dt, end_dt, INITIAL_BALANCE)


def generate_entry_candidates(entry_rule: AutomationRule) -> List[AutomationRule]:
    candidates = []
    base_min_score = entry_rule.min_score or 0
    min_score_offsets = [-2, 0, 2]

    sl_base = entry_rule.stop_loss_pct or 0
    tp_base = entry_rule.take_profit_pct or 0

    sl_offsets = [-1, 0, 1] if sl_base else [0]
    tp_offsets = [-2, 0, 2] if tp_base else [0]

    for d in min_score_offsets:
        for sl in sl_offsets:
            for tp in tp_offsets:
                updates = {
                    "min_score": base_min_score + d,
                    "stop_loss_pct": clamp_min(sl_base + sl) if sl_base else None,
                    "take_profit_pct": clamp_min(tp_base + tp) if tp_base else None,
                }
                candidates.append(clone_rule(entry_rule, **updates))
    return candidates[:ENTRY_CANDIDATES_LIMIT]


def generate_exit_candidates(exit_rule: AutomationRule) -> List[AutomationRule]:
    candidates = []
    base_min_score = exit_rule.min_score or 0
    min_score_offsets = [-2, 0, 2]

    min_profit_vals = [0.25, 0.5, 1.0]
    break_even_vals = [0.5, 1.0, 1.5]
    max_hold = exit_rule.max_hold_bars or 0
    max_hold_vals = [max_hold] if max_hold else [0]

    for d in min_score_offsets:
        for mp in min_profit_vals:
            for be in break_even_vals:
                for mh in max_hold_vals:
                    updates = {
                        "min_score": base_min_score + d,
                        "min_profit_pct": mp,
                        "break_even_after_pct": be,
                        "max_hold_bars": mh or None,
                    }
                    candidates.append(clone_rule(exit_rule, **updates))
    return candidates[:EXIT_CANDIDATES_LIMIT]


def load_existing_symbols(db_path: str) -> Dict[str, int]:
    if not os.path.exists(db_path):
        return {}
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    rows = cursor.execute(
        "SELECT symbol, COUNT(*) FROM ohlcv_data GROUP BY symbol"
    ).fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}


def resolve_focus_symbols(rule_symbols: List[str]) -> List[str]:
    env_symbols = os.getenv("FOCUS_SYMBOLS")
    if env_symbols:
        return [s.strip() for s in env_symbols.split(",") if s.strip()]

    if os.getenv("ALL_SYMBOLS") == "1":
        return sorted(set(rule_symbols))

    existing = load_existing_symbols("trading_data.db")
    return [s for s in sorted(set(rule_symbols)) if existing.get(s, 0) >= 200]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def main():
    engine = TradingEngine()
    downloader = DataDownloader(engine)
    bt_engine = BacktestEngine(engine)
    repo = AutomationRuleRepository()

    rules = repo.get_all()
    entry_rules = [r for r in rules if r.side.lower() == "buy"]
    exit_rules = [r for r in rules if r.side.lower() == "sell"]

    rule_symbols = [r.symbol for r in rules]
    focus_symbols = set(resolve_focus_symbols(rule_symbols))

    pairs: List[Tuple[AutomationRule, AutomationRule]] = []
    for entry in entry_rules:
        for exit_rule in exit_rules:
            if entry.symbol == exit_rule.symbol and entry.timeframe == exit_rule.timeframe:
                if focus_symbols and entry.symbol not in focus_symbols:
                    continue
                pairs.append((entry, exit_rule))

    results = {
        "generated_at": utc_now().isoformat(),
        "initial_balance": INITIAL_BALANCE,
        "focus_symbols": sorted(focus_symbols) if focus_symbols else [],
        "pairs": [],
    }

    skip_download = os.getenv("SKIP_DOWNLOAD") == "1"
    auto_apply = os.getenv("AUTO_APPLY") == "1"

    for entry, exit_rule in pairs:
        tf_days = DAYS_BY_TIMEFRAME.get(entry.timeframe, 60)
        start_dt = utc_now() - timedelta(days=tf_days)
        end_dt = utc_now()

        print(f"\n[PAIR] {entry.symbol} {entry.timeframe} | {entry.name} + {exit_rule.name}")
        if not skip_download:
            print(f"Downloading {tf_days} days of data...")
            downloader.sync_data(entry.symbol, entry.timeframe, days=tf_days)
        else:
            print("Using existing local data...")

        base_result = run_pair(bt_engine, entry, exit_rule, start_dt, end_dt)
        if "error" in base_result:
            print(f"  -> Skipped: {base_result['error']}")
            results["pairs"].append(
                {
                    "symbol": entry.symbol,
                    "timeframe": entry.timeframe,
                    "entry_rule": entry.id,
                    "exit_rule": exit_rule.id,
                    "error": base_result["error"],
                }
            )
            continue

        entry_candidates = generate_entry_candidates(entry)
        exit_candidates = generate_exit_candidates(exit_rule)

        candidate_results = []
        for entry_cand in entry_candidates:
            cand_result = run_pair(bt_engine, entry_cand, exit_rule, start_dt, end_dt)
            if "error" in cand_result:
                continue
            candidate_results.append((entry_cand, exit_rule, cand_result))

        candidate_results.sort(key=lambda x: return_pct(x[2]), reverse=True)
        top_entry = candidate_results[:5] if candidate_results else []

        tuned_results = []
        for entry_cand, _, _ in top_entry:
            for exit_cand in exit_candidates:
                cand_result = run_pair(bt_engine, entry_cand, exit_cand, start_dt, end_dt)
                if "error" in cand_result:
                    continue
                tuned_results.append((entry_cand, exit_cand, cand_result))

        tuned_results.sort(key=lambda x: return_pct(x[2]), reverse=True)
        top = tuned_results[:TOP_K] if tuned_results else []

        def summarize(entry_rule, exit_rule, result):
            return {
                "entry": {
                    "id": entry_rule.id,
                    "name": entry_rule.name,
                    "min_score": entry_rule.min_score,
                    "stop_loss_pct": entry_rule.stop_loss_pct,
                    "take_profit_pct": entry_rule.take_profit_pct,
                    "trailing_stop_pct": entry_rule.trailing_stop_pct,
                },
                "exit": {
                    "id": exit_rule.id,
                    "name": exit_rule.name,
                    "min_score": exit_rule.min_score,
                    "min_profit_pct": exit_rule.min_profit_pct,
                    "break_even_after_pct": exit_rule.break_even_after_pct,
                    "max_hold_bars": exit_rule.max_hold_bars,
                },
                "metrics": {
                    "final_balance": result["final_balance"],
                    "return_pct": round(return_pct(result), 2),
                    "win_rate": result["win_rate"],
                    "total_trades": result["total_trades"],
                    "max_drawdown_pct": result.get("max_drawdown_percent", 0.0),
                },
            }

        pair_summary = {
            "symbol": entry.symbol,
            "timeframe": entry.timeframe,
            "entry_rule": entry.id,
            "exit_rule": exit_rule.id,
            "base": summarize(entry, exit_rule, base_result),
            "top": [summarize(e, x, r) for e, x, r in top],
        }

        if top:
            best_entry, best_exit, _best_result = top[0]
            best_metrics = pair_summary["top"][0]["metrics"]
            print(
                f"  Best return: {best_metrics['return_pct']}% | trades={best_metrics['total_trades']} | drawdown={best_metrics['max_drawdown_pct']}%"
            )
            if auto_apply:
                repo.update(entry.id, {
                    "min_score": best_entry.min_score,
                    "stop_loss_pct": best_entry.stop_loss_pct,
                    "take_profit_pct": best_entry.take_profit_pct,
                })
                repo.update(exit_rule.id, {
                    "min_score": best_exit.min_score,
                    "min_profit_pct": best_exit.min_profit_pct,
                    "break_even_after_pct": best_exit.break_even_after_pct,
                    "max_hold_bars": best_exit.max_hold_bars,
                })
                pair_summary["auto_applied"] = True
        results["pairs"].append(pair_summary)

    report_path = "docs/backtest_tuning_report.json"
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2)
        f.write("\n")

    csv_lines = [
        "symbol,timeframe,entry_rule,exit_rule,entry_min_score,entry_sl,entry_tp,exit_min_score,min_profit,break_even,max_hold,return_pct,win_rate,total_trades,max_drawdown_pct"
    ]
    for pair in results["pairs"]:
        if "top" not in pair or not pair["top"]:
            continue
        best = pair["top"][0]
        csv_lines.append(
            f"{pair['symbol']},{pair['timeframe']},{best['entry']['name']},{best['exit']['name']},"
            f"{best['entry']['min_score']},{best['entry']['stop_loss_pct']},{best['entry']['take_profit_pct']},"
            f"{best['exit']['min_score']},{best['exit']['min_profit_pct']},{best['exit']['break_even_after_pct']},"
            f"{best['exit']['max_hold_bars']},{best['metrics']['return_pct']},{best['metrics']['win_rate']},"
            f"{best['metrics']['total_trades']},{best['metrics']['max_drawdown_pct']}"
        )

    with open("docs/backtest_tuning_report.csv", "w") as f:
        f.write("\n".join(csv_lines))
        f.write("\n")

    print(f"\nReport written to {report_path}")


if __name__ == "__main__":
    main()
