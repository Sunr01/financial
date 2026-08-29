"""单股票回测引擎：用历史K线模拟执行策略规则，产出净值与交易记录。

企业级特性：计入手续费与滑点；参数可配置。
"""

import pandas as pd
import akshare as ak
from finagent.agents.tools import get_kline_df


def run_backtest(symbol: str, rule: dict, days: int = 250,
                 initial_capital: float = 1_000_000.0,
                 commission_rate: float = 0.0003,
                 slippage: float = 0.001) -> dict:
    """跑单股票回测。

    参数：
      initial_capital: 初始资金
      commission_rate: 手续费率（如 0.0003 = 万3）
      slippage: 滑点比例（成交价偏移，如 0.001 = 0.1%）
    """
    df = get_kline_df(symbol, days)
    df = df.reset_index(drop=True)
    cash = initial_capital
    shares = 0
    buy_cost = 0.0
    nav, trades = [], []

    for _, row in df.iterrows():
        price = float(row["close"])
        if shares == 0 and _should_buy(rule, df, row, price, buy_cost):
            buy_price = price * (1 + slippage)  # 买入加滑点
            shares = int(cash / buy_price / 100) * 100
            if shares > 0:
                buy_cost = price
                cost = shares * buy_price
                fee = cost * commission_rate  # 手续费
                cash -= cost + fee
                trades.append({"date": str(row["date"]), "side": "buy",
                               "price": round(buy_price, 2), "qty": shares,
                               "fee": round(fee, 2)})
        elif shares > 0 and _should_sell(rule, df, row, price, buy_cost):
            sell_price = price * (1 - slippage)  # 卖出减滑点
            proceeds = shares * sell_price
            fee = proceeds * commission_rate
            cash += proceeds - fee
            trades.append({"date": str(row["date"]), "side": "sell",
                           "price": round(sell_price, 2), "qty": shares,
                           "fee": round(fee, 2)})
            shares = 0
        nav.append({"date": str(row["date"]), "nav": round(cash + shares * price, 2)})

    return {"nav": nav, "trades": trades,
            "final_value": cash + shares * float(df["close"].iloc[-1])}


def calc_returns(nav: list, initial: float = 1_000_000.0) -> list:
    """把净值序列转成收益率百分比序列。"""
    return [round((n / initial - 1) * 100, 2) for n in nav]


def get_benchmark(dates: list, benchmark_code: str = "sh000300") -> list:
    """获取指定指数同期收益率（对齐日期）。code 如 sh000300/sh000001。"""
    idx = ak.stock_zh_index_daily(symbol=benchmark_code)
    idx = idx[idx["date"].astype(str).isin(dates)]
    idx = idx.reset_index(drop=True)
    base = float(idx["close"].iloc[0])
    return [round((float(c) / base - 1) * 100, 2) for c in idx["close"]]


def _should_buy(rule, df, row, price, cost) -> bool:
    """判断是否买入（根据规则关键词识别策略类型）。"""
    desc = str(rule.get("buy_trigger", "")) + str(rule.get("description", ""))
    if "均线" in desc or "上穿" in desc:
        ma = df["close"].rolling(int(rule.get("window", 20))).mean()
        idx = int(row.name)
        if idx < 1 or pd.isna(ma.iloc[idx]) or pd.isna(ma.iloc[idx - 1]):
            return False
        return df["close"].iloc[idx - 1] <= ma.iloc[idx - 1] and price > ma.iloc[idx]
    return False


def _should_sell(rule, df, row, price, cost) -> bool:
    """判断是否卖出（根据规则关键词识别策略类型）。"""
    desc = str(rule.get("sell_trigger", "")) + str(rule.get("description", ""))
    if "均线" in desc or "下穿" in desc:
        ma = df["close"].rolling(int(rule.get("window", 20))).mean()
        idx = int(row.name)
        if idx < 1 or pd.isna(ma.iloc[idx]) or pd.isna(ma.iloc[idx - 1]):
            return False
        return df["close"].iloc[idx - 1] >= ma.iloc[idx - 1] and price < ma.iloc[idx]
    return False
