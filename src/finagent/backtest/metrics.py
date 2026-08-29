"""绩效指标计算：相对收益率、最大回撤、年化、夏普、胜率、盈亏比、波动率。"""

import math

TRADING_DAYS = 252  # 一年交易日数


def calc_relative_return(strategy_returns: list, benchmark_returns: list) -> float:
    """相对收益率 = 策略收益率 - 基准收益率。"""
    if not strategy_returns or not benchmark_returns:
        return 0.0
    return round(strategy_returns[-1] - benchmark_returns[-1], 2)


def calc_max_drawdown(nav: list) -> dict:
    """最大回撤 + 区间。nav 为净值序列。"""
    if not nav:
        return {"max_drawdown": 0.0, "start": "", "end": ""}
    peak = nav[0]["nav"]
    peak_date = nav[0]["date"]
    max_dd = 0.0
    dd_start = dd_end = nav[0]["date"]
    for point in nav:
        if point["nav"] > peak:
            peak = point["nav"]
            peak_date = point["date"]
        dd = (point["nav"] - peak) / peak * 100 if peak else 0
        if dd < max_dd:
            max_dd = dd
            dd_start = peak_date
            dd_end = point["date"]
    return {"max_drawdown": round(max_dd, 2), "start": str(dd_start), "end": str(dd_end)}


def calc_annualized_return(total_return_pct: float, days: int) -> float:
    """年化收益率。total_return_pct 为累计收益百分比。"""
    if days <= 0:
        return 0.0
    total = total_return_pct / 100 + 1
    if total <= 0:
        return -100.0
    return round((total ** (TRADING_DAYS / days) - 1) * 100, 2)


def calc_volatility(daily_returns: list) -> float:
    """年化波动率（日收益标准差 × √252）。"""
    if len(daily_returns) < 2:
        return 0.0
    mean = sum(daily_returns) / len(daily_returns)
    var = sum((r - mean) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
    return round(math.sqrt(var) * math.sqrt(TRADING_DAYS) * 100, 4)


def calc_sharpe(daily_returns: list, risk_free: float = 0.02) -> float:
    """夏普比率 = (年化收益 - 无风险利率) / 年化波动率。"""
    vol = calc_volatility(daily_returns)
    if vol == 0:
        return 0.0
    mean_daily = sum(daily_returns) / len(daily_returns) if daily_returns else 0
    annual_return = mean_daily * TRADING_DAYS
    return round((annual_return - risk_free) / (vol / 100), 2)


def calc_trade_stats(trades: list) -> dict:
    """交易统计：胜率、盈亏比。trades 为买卖配对后的交易记录。"""
    # 按买卖配对（buy 后跟 sell 算一笔完整交易）
    closed = []
    buy_price = None
    for t in trades:
        if t["side"] == "buy":
            buy_price = t["price"]
        elif t["side"] == "sell" and buy_price is not None:
            pnl_pct = (t["price"] - buy_price) / buy_price * 100
            closed.append(pnl_pct)
            buy_price = None
    if not closed:
        return {"win_rate": 0.0, "profit_loss_ratio": 0.0, "trade_count": 0}
    wins = [p for p in closed if p > 0]
    losses = [p for p in closed if p <= 0]
    win_rate = round(len(wins) / len(closed) * 100, 2)
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0
    plr = round(avg_win / avg_loss, 2) if avg_loss > 0 else 0.0
    return {"win_rate": win_rate, "profit_loss_ratio": plr, "trade_count": len(closed)}
