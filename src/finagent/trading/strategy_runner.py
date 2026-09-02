"""策略执行器：按当前策略规则自动买卖，驱动模拟账户。"""

from finagent.agents.tools import get_kline_df
from finagent.backtest.engine import _should_buy, _should_sell
from finagent.trading.account import Account


def run_strategy(account: Account, symbol: str, rule: dict) -> str:
    """执行一次策略检查：先处理止损，再判断当前是否该买/卖，并执行到账户。"""
    df = get_kline_df(symbol, 60)
    df = df.reset_index(drop=True)
    row = df.iloc[-1]  # 最新一天
    price = float(row["close"])

    # 1) 止损优先：持仓亏损超阈值直接强平（含 account.sell 的手续费/滑点）
    pos = account.positions.get(symbol)
    holding = pos is not None and pos.qty > 0
    if holding and pos.cost > 0:
        loss_pct = (price - pos.cost) / pos.cost
        if loss_pct <= -account.stop_loss_pct:
            msg = account.sell(symbol, pos.qty, price)
            return f"[止损] {msg}（亏损 {loss_pct:.1%} 触发止损线）"

    if not holding and _should_buy(rule, df, row, price, 0.0):
        cash = account.cash
        qty = int(cash / price / 100) * 100
        if qty > 0:
            name = _get_name(symbol)
            msg = account.buy(symbol, name, qty, price)
            return f"[买入] {msg}（触发买入规则）"
        return "现金不足以买入"
    elif holding and _should_sell(rule, df, row, price, pos.cost):
        qty = pos.qty
        msg = account.sell(symbol, qty, price)
        return f"[卖出] {msg}（触发卖出规则）"
    return "无操作（未触发规则）"


def _get_name(symbol: str) -> str:
    """获取股票名称（简化：从行情接口取）。"""
    try:
        from finagent.agents.tools import get_realtime_quote
        return get_realtime_quote(symbol).split()[0]
    except Exception:
        return symbol
