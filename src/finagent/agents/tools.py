"""Agent 工具层：4 个函数，供 Agent 调用（行情/K线/财务/新闻）。

数据源：实时行情=新浪，K线=腾讯，财务/新闻=东方财富。
新浪/腾讯代码需带前缀（sh600519/sz000001），东财不带（600519）。
"""

import time
import requests
import akshare as ak


def _with_prefix(symbol: str) -> str:
    """给 6 位代码加交易所前缀：6开头→sh，其他→sz。"""
    return f"sh{symbol}" if symbol.startswith("6") else f"sz{symbol}"


def _retry(fn, retries: int = 2):
    """简单重试：失败后等待1秒再试，最多重试 retries 次。"""
    for i in range(retries + 1):
        try:
            return fn()
        except Exception:
            if i == retries:
                raise
            time.sleep(1)


def get_realtime_quote(symbol: str) -> str:
    """获取股票实时行情（新浪源），返回文本。symbol 为 6 位股票代码。"""
    def _fetch():
        df = ak.stock_zh_a_spot()
        matched = df[df["代码"] == _with_prefix(symbol)]
        if matched.empty:
            return f"未找到股票 {symbol}，请确认股票代码"
        row = matched.iloc[0]
        return f"{row['名称']} 最新价 {row['最新价']} 元，涨跌幅 {row['涨跌幅']}%"
    return _retry(_fetch)


def get_kline_data(symbol: str, days: int = 250) -> str:
    """获取股票历史K线（腾讯源），返回文本摘要。symbol 为 6 位股票代码。"""
    def _fetch():
        df = ak.stock_zh_a_hist_tx(symbol=_with_prefix(symbol)).tail(days)
        return (f"{symbol} 近{days}日K线：最新收盘 {df['close'].iloc[-1]}，"
                f"期间最高 {df['high'].max()}，最低 {df['low'].min()}")
    return _retry(_fetch)


# K线数据缓存（内存级，避免重复请求外部接口）
_kline_cache: dict = {}


def get_kline_df(symbol: str, days: int = 120):
    """获取K线数据（DataFrame），带内存缓存。symbol 为 6 位股票代码。"""
    cache_key = symbol
    if cache_key in _kline_cache:
        return _kline_cache[cache_key].tail(days)
    df = ak.stock_zh_a_hist_tx(symbol=_with_prefix(symbol))
    df = df[["date", "open", "close", "high", "low", "volume"]]
    _kline_cache[cache_key] = df
    return df.tail(days)


def get_financial_indicators(symbol: str) -> str:
    """获取股票财务摘要（东方财富源），返回文本。symbol 为 6 位股票代码。"""
    def _fetch():
        df = ak.stock_financial_abstract(symbol=symbol)
        return f"{symbol} 财务数据已获取，共 {df.shape[1]} 个报告期"
    return _retry(_fetch)


def search_news(keyword: str) -> str:
    """搜索股票相关新闻（东方财富源），返回标题列表。keyword 为搜索关键词。"""
    def _fetch():
        df = ak.stock_news_em(symbol=keyword)
        return "\n".join(f"- {t}" for t in df["新闻标题"].head(5).tolist())
    return _retry(_fetch)
