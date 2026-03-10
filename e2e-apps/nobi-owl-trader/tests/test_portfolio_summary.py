import json
import subprocess
import textwrap
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_ROOT = APP_ROOT / "dashboard"


def run_portfolio_summary(expression: str):
    script = textwrap.dedent(
        f"""
        import {{ buildPortfolioSummaryStats }} from "./lib/portfolio-summary.ts";

        const portfolio = {expression};
        console.log(JSON.stringify(buildPortfolioSummaryStats(portfolio)));
        """
    )
    result = subprocess.run(
        ["npx", "--yes", "tsx", "--eval", script],
        cwd=DASHBOARD_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_build_portfolio_summary_stats_uses_placeholder_values_without_portfolio():
    stats = run_portfolio_summary("null")

    assert stats == [
        {
            "label": "Total Portfolio Value",
            "value": "—",
            "tone": "neutral",
            "numericValue": None,
            "icon": "wallet",
        },
        {
            "label": "Cash Balance",
            "value": "—",
            "tone": "neutral",
            "numericValue": None,
            "icon": "cash",
        },
        {
            "label": "Unrealized P&L",
            "value": "—",
            "tone": "neutral",
            "numericValue": None,
            "icon": "unrealized",
        },
        {
            "label": "Realized P&L Today",
            "value": "—",
            "tone": "neutral",
            "numericValue": None,
            "icon": "realized",
        },
    ]


def test_build_portfolio_summary_stats_formats_portfolio_totals_and_pnl_direction():
    stats = run_portfolio_summary(
        """{
          totalValue: 12345.678,
          cash: 7890.12,
          unrealizedPnl: 245.5,
          realizedPnl: -50.25
        }"""
    )

    assert [stat["label"] for stat in stats] == [
        "Total Portfolio Value",
        "Cash Balance",
        "Unrealized P&L",
        "Realized P&L Today",
    ]
    assert [stat["value"] for stat in stats] == [
        "$12,345.68",
        "$7,890.12",
        "$245.50",
        "-$50.25",
    ]
    assert [stat["tone"] for stat in stats] == [
        "neutral",
        "neutral",
        "positive",
        "negative",
    ]
    assert [stat["numericValue"] for stat in stats] == [
        12345.678,
        7890.12,
        245.5,
        -50.25,
    ]


def test_build_portfolio_summary_stats_sanitizes_non_finite_values():
    stats = run_portfolio_summary(
        """{
          totalValue: Number.NaN,
          cash: Number.POSITIVE_INFINITY,
          unrealizedPnl: Number.NEGATIVE_INFINITY,
          realizedPnl: Number.NaN
        }"""
    )

    assert [stat["value"] for stat in stats] == ["—", "—", "—", "—"]
    assert [stat["tone"] for stat in stats] == [
        "neutral",
        "neutral",
        "neutral",
        "neutral",
    ]
    assert [stat["numericValue"] for stat in stats] == [None, None, None, None]
