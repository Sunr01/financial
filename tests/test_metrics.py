"""绩效指标单元测试。"""

from finagent.backtest.metrics import (
    calc_relative_return,
    calc_max_drawdown,
    calc_annualized_return,
    calc_volatility,
    calc_sharpe,
    calc_trade_stats,
)


def test_relative_return():
    """相对收益率 = 策略收益 - 基准收益。"""
    assert calc_relative_return([0, 10, 30], [0, 5, 20]) == 10.0


def test_max_drawdown():
    """最大回撤：从高点 120 跌到 80 = -33.33%，区间从高点日到低点日。"""
    nav = [
        {"date": "2026-01-01", "nav": 100},
        {"date": "2026-01-02", "nav": 120},
        {"date": "2026-01-03", "nav": 90},
        {"date": "2026-01-04", "nav": 80},
    ]
    dd = calc_max_drawdown(nav)
    assert dd["max_drawdown"] == -33.33
    assert dd["start"] == "2026-01-02"
    assert dd["end"] == "2026-01-04"


def test_annualized_return():
    """100 天涨 10% → 年化约 27.15%。"""
    r = calc_annualized_return(10.0, 100)
    assert abs(r - 27.15) < 0.5


def test_volatility():
    """有波动的日收益 → 年化波动率 > 0。"""
    daily = [0.01, -0.005, 0.02, -0.01, 0.015] * 10
    assert calc_volatility(daily) > 0


def test_sharpe():
    """正收益波动 → 夏普 > 0。"""
    daily = [0.01, -0.005, 0.02, -0.01, 0.015] * 10
    assert calc_sharpe(daily) > 0


def test_trade_stats():
    """3 胜 1 亏 → 胜率 75%，盈亏比 1.5。"""
    trades = [
        {"side": "buy", "price": 100}, {"side": "sell", "price": 110},
        {"side": "buy", "price": 100}, {"side": "sell", "price": 120},
        {"side": "buy", "price": 100}, {"side": "sell", "price": 90},
        {"side": "buy", "price": 100}, {"side": "sell", "price": 115},
    ]
    ts = calc_trade_stats(trades)
    assert ts["win_rate"] == 75.0
    assert ts["profit_loss_ratio"] == 1.5
    assert ts["trade_count"] == 4
