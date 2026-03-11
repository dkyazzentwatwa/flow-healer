from api.backtest.exporter import export_backtest_csv


def test_export_backtest_csv_includes_summary_trade_and_equity_sections():
    result = {
        "id": "bt-001",
        "timestamp": 1700000000000,
        "rule_name": "Momentum Rider",
        "symbol": "BTC/USDT",
        "timeframe": "1h",
        "initial_balance": 10000.0,
        "final_balance": 11250.5,
        "total_trades": 2,
        "win_rate": 50.0,
        "max_drawdown": 350.25,
        "max_drawdown_percent": 3.5,
        "trades": [
            {
                "entry_time": 1700000000000,
                "exit_time": 1700003600000,
                "symbol": "BTC/USDT",
                "side": "buy",
                "entry_price": 40000.0,
                "exit_price": 40500.0,
                "amount": 0.1,
                "pnl": 50.0,
                "pnl_pct": 1.25,
                "reason": "Sell Signal",
            }
        ],
        "equity_curve": [
            {"timestamp": 1700000000000, "equity": 10000.0},
            {"timestamp": 1700003600000, "equity": 11250.5},
        ],
    }

    exported = export_backtest_csv(result)

    assert exported.splitlines()[0] == "section,field,value"
    assert "summary,rule_name,Momentum Rider" in exported
    assert "summary,final_balance,11250.5" in exported
    assert "section,entry_time,exit_time,symbol,side,entry_price,exit_price,amount,pnl,pnl_pct,reason" in exported
    assert "trade,1700000000000,1700003600000,BTC/USDT,buy,40000.0,40500.0,0.1,50.0,1.25,Sell Signal" in exported
    assert "section,timestamp,equity" in exported
    assert "equity,1700003600000,11250.5" in exported


def test_export_backtest_csv_skips_empty_trade_and_equity_rows():
    exported = export_backtest_csv(
        {
            "rule_name": "No Trades",
            "symbol": "ETH/USDT",
            "trades": [],
            "equity_curve": [],
        }
    )

    assert "summary,rule_name,No Trades" in exported
    assert "summary,symbol,ETH/USDT" in exported
    assert "trade," not in exported
    assert "equity," not in exported


def test_export_backtest_csv_includes_paired_rule_summary_fields_with_missing_rows():
    exported = export_backtest_csv(
        {
            "id": "bt-pair-001",
            "rule_name": "Momentum Rider + Safety Exit",
            "symbol": "BTC/USDT",
            "timeframe": "4h",
            "entry_rule": "entry-42",
            "exit_rule": "exit-99",
            "trades": None,
            "equity_curve": None,
        }
    )

    assert "summary,rule_name,Momentum Rider + Safety Exit" in exported
    assert "summary,entry_rule,entry-42" in exported
    assert "summary,exit_rule,exit-99" in exported
    assert "trade," not in exported
    assert "equity," not in exported
