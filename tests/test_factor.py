"""因子计算单元测试。"""

import pandas as pd

from finagent.backtest.factor import (
    momentum_factor,
    volatility_factor,
    growth_factor,
    FACTORS,
)


def _make_df(closes):
    """构造简单 K 线 DataFrame（只用 close 列）。"""
    return pd.DataFrame({"close": closes, "open": closes, "high": closes,
                         "low": closes, "volume": [1000] * len(closes)})


def test_momentum_factor():
    """动量因子：上涨 → 正分，下跌 → 负分。"""
    up = _make_df([100] * 21 + [110])          # 20日涨10%
    down = _make_df([100] * 21 + [90])         # 20日跌10%
    assert momentum_factor(up, 20) > 0
    assert momentum_factor(down, 20) < 0


def test_growth_factor():
    """成长因子：涨幅大 → 分高。"""
    fast = _make_df([100] * 21 + [130])        # 涨30%
    slow = _make_df([100] * 21 + [105])        # 涨5%
    assert growth_factor(fast, 20) > growth_factor(slow, 20)


def test_volatility_factor():
    """波动率因子：波动大 → 分低（负分更小）。"""
    calm = _make_df([100 + i for i in range(25)])          # 平滑上涨
    wild = _make_df([100, 120, 90, 130, 80, 140, 70] * 4)  # 剧烈波动
    assert volatility_factor(calm, 20) > volatility_factor(wild, 20)


def test_factor_registry():
    """因子注册表包含 3 种因子。"""
    assert set(FACTORS.keys()) == {"momentum", "growth", "volatility"}
