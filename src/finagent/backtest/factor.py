"""因子计算模块：独立封装，支持扩展多因子。

企业级设计：因子计算与回测引擎解耦，新增因子只需在此模块加函数。
"""


def momentum_factor(df, window: int = 20) -> float:
    """动量因子：近 window 日涨幅（最新收盘 / window日前收盘 - 1）。"""
    if len(df) < window + 1:
        return 0.0
    last = float(df["close"].iloc[-1])
    base = float(df["close"].iloc[-window - 1])
    if base == 0:
        return 0.0
    return last / base - 1


def volatility_factor(df, window: int = 20) -> float:
    """波动率因子：近 window 日日收益标准差（越低分越高，取负）。"""
    if len(df) < window + 1:
        return 0.0
    rets = df["close"].pct_change().dropna().tail(window)
    if len(rets) < 2:
        return 0.0
    std = float(rets.std())
    return -std  # 低波动得分更高


def growth_factor(df, window: int = 20) -> float:
    """成长因子：最近两期营收同比增速（越高分越高）。"""
    if len(df) < 2:
        return 0.0
    cur = float(df["close"].iloc[-1])
    prev = float(df["close"].iloc[-window - 1]) if len(df) > window else float(df["close"].iloc[0])
    if prev == 0:
        return 0.0
    return cur / prev - 1  # 简化：用价格涨幅近似成长（真实应用用财务营收增速）


# 因子注册表：可扩展新增因子
FACTORS = {
    "momentum": momentum_factor,
    "volatility": volatility_factor,
    "growth": growth_factor,
}


def compute_factor_scores(df_map: dict, factor: str = "momentum",
                          window: int = 20) -> dict:
    """对每只股票计算指定因子的得分。df_map: {symbol: DataFrame}。"""
    fn = FACTORS.get(factor, momentum_factor)
    return {symbol: fn(df, window) for symbol, df in df_map.items()}
