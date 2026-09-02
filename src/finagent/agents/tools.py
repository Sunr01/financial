"""Agent 工具层：行情/K线/财务/新闻 获取函数，供 Agent 调用。

数据源策略（保证沪深京全部 A 股，输入 6 位代码即可获取）：
- 行情：东财单股盘口（全市场含北交所，快）→ 新浪全市场快照兜底
- K线：腾讯源 → 东财历史行情兜底（腾讯对北交所覆盖不全）
- 财务/新闻：东方财富（全市场含北交所）
新浪/腾讯代码带前缀（sh600519/sz000001/bj430047），东财不带（600519）。
"""

import time
import akshare as ak


def _with_prefix(symbol: str) -> str:
    """给 6 位代码加交易所前缀：6开头→sh（沪），0/3开头→sz（深），4/8/9开头→bj（北交所）。"""
    if symbol.startswith("6"):
        return f"sh{symbol}"
    if symbol.startswith(("4", "8", "9")):
        return f"bj{symbol}"
    return f"sz{symbol}"


def _retry(fn, retries: int = 2):
    """简单重试：失败后等待1秒再试，最多重试 retries 次。"""
    for i in range(retries + 1):
        try:
            return fn()
        except Exception:
            if i == retries:
                raise
            time.sleep(1)


def _em_name(symbol: str) -> str:
    """东财查询股票简称（失败返回代码本身）。"""
    try:
        info = ak.stock_individual_info_em(symbol=symbol)
        return str(info.loc[info["item"] == "股票简称", "value"].iloc[0])
    except Exception:
        return symbol


def get_realtime_quote(symbol: str) -> str:
    """获取股票实时行情。优先东财单股盘口（沪深京全部 A 股，快），
    新浪全市场快照兜底（不含北交所）。symbol 为 6 位股票代码。"""
    def _fetch_em():
        bid = ak.stock_bid_ask_em(symbol=symbol)
        if bid is None or bid.empty:
            raise ValueError("东财无该股票数据")
        latest = str(bid.loc[bid["item"] == "最新", "value"].iloc[0])
        pct = str(bid.loc[bid["item"] == "涨幅", "value"].iloc[0])
        return f"{_em_name(symbol)}({symbol}) 最新价 {latest} 元，涨跌幅 {pct}%"

    def _fetch_sina():
        df = ak.stock_zh_a_spot()
        matched = df[df["代码"] == _with_prefix(symbol)]
        if matched.empty:
            return f"未找到股票 {symbol}，请确认股票代码"
        row = matched.iloc[0]
        return (f"{row['名称']}({symbol}) 最新价 {row['最新价']} 元，"
                f"涨跌幅 {row['涨跌幅']}%")

    try:
        return _retry(_fetch_em)
    except Exception:
        return _retry(_fetch_sina)


def get_kline_data(symbol: str, days: int = 250) -> str:
    """获取股票历史K线摘要。优先腾讯源，失败（如北交所）用东财源兜底。
    symbol 为 6 位股票代码。"""
    def _fetch_tx():
        df = ak.stock_zh_a_hist_tx(symbol=_with_prefix(symbol)).tail(days)
        return (f"{symbol} 近{days}日K线：最新收盘 {df['close'].iloc[-1]}，"
                f"期间最高 {df['high'].max()}，最低 {df['low'].min()}")

    def _fetch_em():
        df = ak.stock_zh_a_hist(symbol=symbol, period="daily", adjust="qfq").tail(days)
        return (f"{symbol} 近{days}日K线：最新收盘 {df['收盘'].iloc[-1]}，"
                f"期间最高 {df['最高'].max()}，最低 {df['最低'].min()}")

    try:
        return _retry(_fetch_tx)
    except Exception:
        return _retry(_fetch_em)


# K线数据缓存（内存级，避免重复请求外部接口）
_kline_cache: dict = {}


def get_kline_df(symbol: str, days: int = 120):
    """获取K线数据（DataFrame），带内存缓存。优先腾讯源，失败用东财源兜底。
    symbol 为 6 位股票代码。"""
    cache_key = symbol
    if cache_key in _kline_cache:
        return _kline_cache[cache_key].tail(days)
    try:
        df = ak.stock_zh_a_hist_tx(symbol=_with_prefix(symbol))
        df = df[["date", "open", "close", "high", "low", "volume"]]
    except Exception:
        # 兜底：东财历史行情（列名中文，需映射）
        df = ak.stock_zh_a_hist(symbol=symbol, period="daily", adjust="qfq")
        df = df.rename(columns={"日期": "date", "开盘": "open", "收盘": "close",
                                "最高": "high", "最低": "low", "成交量": "volume"})
        df = df[["date", "open", "close", "high", "low", "volume"]]
    _kline_cache[cache_key] = df
    return df.tail(days)


def get_financial_indicators(symbol: str) -> str:
    """获取股票财务摘要（东方财富源，全市场含北交所），返回最新报告期关键指标。
    symbol 为 6 位股票代码。"""
    def _fetch():
        df = ak.stock_financial_abstract(symbol=symbol)
        if df is None or df.empty:
            return f"{symbol} 暂无财务数据"
        cols = list(df.columns)
        latest = str(cols[0])  # 第一列通常是最新报告期
        keys = ["每股收益", "营业总收入", "营业收入", "归母净利润", "净利润",
                "净资产收益率", "每股净资产", "毛利率"]
        found = []
        for idx in df.index:
            name = str(idx)
            for k in keys:
                if k in name:
                    try:
                        v = df.loc[idx, cols[0]]
                        if v is not None and str(v) != "nan":
                            found.append(f"{name}: {v}")
                    except Exception:
                        pass
                    break
        if not found:
            return (f"{symbol} 财务数据已获取（最新报告期 {latest}，"
                    f"共 {df.shape[0]} 项指标）")
        return (f"{symbol} 最新报告期 {latest}：\n"
                + "\n".join(found[:6]))
    return _retry(_fetch)


def search_news(keyword: str) -> str:
    """搜索股票相关新闻（东方财富源，全市场含北交所），返回标题列表。
    keyword 为搜索关键词/股票代码。"""
    def _fetch():
        df = ak.stock_news_em(symbol=keyword)
        return "\n".join(f"- {t}" for t in df["新闻标题"].head(5).tolist())
    return _retry(_fetch)
