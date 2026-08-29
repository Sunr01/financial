"""多股票回测引擎：按因子排序选股，持仓N只，每日换仓（支持多因子）。"""

from finagent.agents.tools import get_kline_df
from finagent.backtest.factor import FACTORS, momentum_factor


def run_multi_backtest(stocks: list, hold_num: int = 5, change_num: int = 1,
                       days: int = 250, capital: float = 1_000_000.0,
                       commission_rate: float = 0.0003,
                       slippage: float = 0.001,
                       factor: str = "momentum") -> dict:
    """多股票回测。stocks 为股票代码列表。

    参数：
      factor: 因子名（momentum 动量 / growth 成长 / volatility 波动率）
    企业级特性：计入手续费与滑点；因子模块化（factor.py）。
    """
    # 1. 拉每只股票K线（对齐日期）
    data = {}
    all_dates = None
    for symbol in stocks:
        df = get_kline_df(symbol, days).reset_index(drop=True)
        data[symbol] = df
        if all_dates is None or len(df) > len(all_dates):
            all_dates = df["date"].tolist()

    # 因子函数（从注册表取，默认动量）
    factor_fn = FACTORS.get(factor, momentum_factor)

    # 2. 逐日模拟
    cash = capital
    holdings = {}          # symbol -> 股数
    nav = []               # 每日净值
    trades = []

    for i, date in enumerate(all_dates):
        # 每日因子分（用指定因子）
        scores = {}
        for symbol, df in data.items():
            drow = df[df["date"] == date]
            if drow.empty:
                continue
            idx = drow.index[0]
            if idx >= 20:
                scores[symbol] = factor_fn(df.iloc[:idx + 1], 20)
            else:
                scores[symbol] = 0.0
        # 排序选前 N 只
        ranked = sorted(scores, key=scores.get, reverse=True)[:hold_num]

        # 卖出不在前 N 的持仓
        for sym in list(holdings):
            if sym not in ranked:
                sell_price = _price(data, sym, date) * (1 - slippage)
                proceeds = holdings[sym] * sell_price
                fee = proceeds * commission_rate
                cash += proceeds - fee
                trades.append({"date": str(date), "side": "sell", "symbol": sym,
                               "price": round(sell_price, 2), "qty": holdings[sym],
                               "fee": round(fee, 2)})
                del holdings[sym]
        # 买入新进前 N 的
        for sym in ranked:
            if sym not in holdings:
                buy_price = _price(data, sym, date) * (1 + slippage)
                if buy_price <= 0:
                    continue
                qty = int((cash / len(ranked)) / buy_price / 100) * 100
                if qty > 0:
                    cost = qty * buy_price
                    fee = cost * commission_rate
                    cash -= cost + fee
                    holdings[sym] = qty
                    trades.append({"date": str(date), "side": "buy", "symbol": sym,
                                   "price": round(buy_price, 2), "qty": qty,
                                   "fee": round(fee, 2)})

        # 记录净值
        total = cash + sum(holdings[s] * _price(data, s, date) for s in holdings)
        nav.append({"date": date, "nav": round(total, 2)})

    return {"nav": nav, "trades": trades,
            "final_value": nav[-1]["nav"] if nav else capital}


def _price(data, symbol, date):
    """取某日收盘价。"""
    drow = data[symbol][data[symbol]["date"] == date]
    return float(drow["close"].iloc[0]) if not drow.empty else 0.0
