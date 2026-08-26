"""K线图表：用 mplfinance 生成K线图（当前用模拟数据，接口恢复后换真实）。"""

from pathlib import Path
import pandas as pd
import numpy as np
import mplfinance as mpf

# 基于项目根目录的绝对路径，避免相对路径乱跑
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CHART_DIR = PROJECT_ROOT / "output" / "charts"


def _mock_kline(symbol: str, days: int = 60) -> pd.DataFrame:
    """生成模拟K线数据（OHLCV），用于演示图表功能。"""
    dates = pd.date_range(end=pd.Timestamp.today(), periods=days, freq="D")
    base = 100.0
    rng = np.random.default_rng(42)
    close = base + np.cumsum(rng.normal(0, 1.5, days))
    open_ = np.roll(close, 1) * (1 + rng.normal(0, 0.005, days))
    high = np.maximum(open_, close) * 1.02
    low = np.minimum(open_, close) * 0.98
    volume = rng.integers(10000, 50000, days)
    df = pd.DataFrame({"Open": open_, "High": high, "Low": low,
                       "Close": close, "Volume": volume}, index=dates)
    df.index.name = "Date"
    return df


def generate_kline_chart(symbol: str, days: int = 60) -> str:
    """生成K线图，返回图片路径。"""
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    df = _mock_kline(symbol, days)
    file_path = CHART_DIR / f"{symbol}_kline.png"
    mpf.plot(df, type="candle", volume=True, mav=(5, 10),
             style="yahoo", savefig=dict(fname=file_path, dpi=120))
    return str(file_path)
