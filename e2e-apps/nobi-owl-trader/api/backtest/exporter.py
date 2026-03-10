import csv
import io
from typing import Any, Iterable, Mapping


SUMMARY_FIELDS = (
    "id",
    "timestamp",
    "rule_name",
    "symbol",
    "timeframe",
    "initial_balance",
    "final_balance",
    "total_trades",
    "win_rate",
    "max_drawdown",
    "max_drawdown_percent",
    "entry_rule",
    "exit_rule",
)

TRADE_FIELDS = (
    "entry_time",
    "exit_time",
    "symbol",
    "side",
    "entry_price",
    "exit_price",
    "amount",
    "pnl",
    "pnl_pct",
    "reason",
)

EQUITY_FIELDS = ("timestamp", "equity")


def export_backtest_csv(result: Mapping[str, Any]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")

    writer.writerow(("section", "field", "value"))
    for field in SUMMARY_FIELDS:
        if field in result and result[field] is not None:
            writer.writerow(("summary", field, result[field]))

    _write_rows(
        writer=writer,
        field_names=TRADE_FIELDS,
        row_type="trade",
        rows=result.get("trades", ()),
    )
    _write_rows(
        writer=writer,
        field_names=EQUITY_FIELDS,
        row_type="equity",
        rows=result.get("equity_curve", ()),
    )

    return buffer.getvalue()


def _write_rows(
    *,
    writer: Any,
    field_names: Iterable[str],
    row_type: str,
    rows: Iterable[Mapping[str, Any]],
) -> None:
    materialized_rows = list(rows)
    if not materialized_rows:
        return

    headers = tuple(field_names)
    writer.writerow(("section", *headers))
    for row in materialized_rows:
        writer.writerow((row_type, *(row.get(field, "") for field in headers)))
