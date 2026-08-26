"""用 AkShare 拉取股票财务数据，转成中文叙述文本。"""

import akshare as ak
import pandas as pd

STOCKS = [
    {"symbol": "600519", "name": "贵州茅台"},
    {"symbol": "300750", "name": "宁德时代"},
    {"symbol": "600036", "name": "招商银行"},
]


def fetch_financial_abstract(symbol: str) -> pd.DataFrame:
    """拉取指定股票的财务摘要数据。"""
    return ak.stock_financial_abstract(symbol=symbol)


def fmt_yi(value: float) -> str:
    """把金额（元）转成亿元字符串，方便阅读。"""
    return f"{value / 1e8:.2f} 亿元"


def to_chinese_text(df: pd.DataFrame, stock_name: str) -> str:
    """把财务摘要宽表（指标在行、日期在列）转成中文叙述。"""
    revenue = df[df["指标"] == "营业总收入"].iloc[0]
    profit = df[df["指标"] == "归母净利润"].iloc[0]
    annual = [c for c in df.columns if c.endswith("1231")][:5]
    lines = []
    for d in annual:
        lines.append(f"{stock_name} {d}：营业总收入 {fmt_yi(revenue[d])}，归母净利润 {fmt_yi(profit[d])}。")
    return "\n".join(lines)
