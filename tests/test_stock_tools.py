"""工具层测试：多源兜底（东财→新浪，腾讯→东财）与沪深京前缀。
原则：不依赖网络——用 monkeypatch 替换 akshare 接口，只测我方逻辑。"""

import pandas as pd
import pytest

import finagent.agents.tools as tools


def _fake_spot_df():
    return pd.DataFrame([
        {"代码": "sh600519", "名称": "贵州茅台", "最新价": 1700.0, "涨跌幅": 1.2},
    ])


def _fake_bid_df():
    return pd.DataFrame([
        {"item": "最新", "value": 1700.0},
        {"item": "涨幅", "value": 1.2},
        {"item": "最高", "value": 1710.0},
        {"item": "最低", "value": 1690.0},
    ])


def _fake_info_df():
    return pd.DataFrame([
        {"item": "股票简称", "value": "贵州茅台"},
        {"item": "行业", "value": "白酒"},
    ])


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """去掉重试间隔，测试跑得快。"""
    monkeypatch.setattr(tools.time, "sleep", lambda s: None)


def test_with_prefix_markets():
    """沪深京前缀：6→sh，0/3→sz，4/8/9→bj。"""
    assert tools._with_prefix("600519") == "sh600519"
    assert tools._with_prefix("688981") == "sh688981"
    assert tools._with_prefix("000001") == "sz000001"
    assert tools._with_prefix("300750") == "sz300750"
    assert tools._with_prefix("430047") == "bj430047"
    assert tools._with_prefix("832566") == "bj832566"
    assert tools._with_prefix("920001") == "bj920001"


def test_quote_em_primary(monkeypatch):
    """行情优先走东财单股接口（含名称），不落新浪。"""
    monkeypatch.setattr(tools.ak, "stock_bid_ask_em", lambda symbol: _fake_bid_df())
    monkeypatch.setattr(tools.ak, "stock_individual_info_em", lambda symbol: _fake_info_df())
    called = {"sina": False}
    def _sina():
        called["sina"] = True
        return _fake_spot_df()
    monkeypatch.setattr(tools.ak, "stock_zh_a_spot", _sina)
    out = tools.get_realtime_quote("600519")
    assert "贵州茅台" in out and "1700" in out and not called["sina"]


def test_quote_fallback_to_sina(monkeypatch):
    """东财挂了 → 新浪快照兜底。"""
    monkeypatch.setattr(tools.ak, "stock_bid_ask_em",
                        lambda symbol: (_ for _ in ()).throw(ConnectionError("down")))
    monkeypatch.setattr(tools.ak, "stock_zh_a_spot", lambda: _fake_spot_df())
    out = tools.get_realtime_quote("600519")
    assert "贵州茅台" in out and "1700" in out


def test_quote_not_found_message(monkeypatch):
    """代码不存在 → 明确提示。"""
    monkeypatch.setattr(tools.ak, "stock_bid_ask_em",
                        lambda symbol: (_ for _ in ()).throw(ValueError("empty")))
    monkeypatch.setattr(tools.ak, "stock_zh_a_spot", lambda: _fake_spot_df())
    out = tools.get_realtime_quote("999999")
    assert "未找到股票" in out


def test_kline_tx_primary(monkeypatch):
    """K线优先腾讯源。"""
    df = pd.DataFrame([{"date": "2024-01-01", "close": 100.0, "high": 105.0, "low": 95.0},
                       {"date": "2024-01-02", "close": 102.0, "high": 106.0, "low": 96.0}])
    monkeypatch.setattr(tools.ak, "stock_zh_a_hist_tx", lambda symbol: df)
    out = tools.get_kline_data("600519")
    assert "600519" in out and "102" in out


def test_kline_fallback_to_em(monkeypatch):
    """腾讯挂了（如北交所）→ 东财历史行情兜底。"""
    monkeypatch.setattr(tools.ak, "stock_zh_a_hist_tx",
                        lambda symbol: (_ for _ in ()).throw(ConnectionError("down")))
    em_df = pd.DataFrame([{"日期": "2024-01-01", "收盘": 100.0, "最高": 105.0, "最低": 95.0},
                          {"日期": "2024-01-02", "收盘": 102.0, "最高": 106.0, "最低": 96.0}])
    monkeypatch.setattr(tools.ak, "stock_zh_a_hist", lambda symbol, **kw: em_df)
    out = tools.get_kline_data("430047")
    assert "430047" in out and "102" in out


def test_financial_latest_period(monkeypatch):
    """财务摘要输出最新报告期关键指标。"""
    df = pd.DataFrame([
        {"2024-12-31": "59.49", "2023-12-31": "50.00"},
        {"2024-12-31": "1505.60亿", "2023-12-31": "1476.94亿"},
        {"2024-12-31": "862.28亿", "2023-12-31": "747.34亿"},
    ], index=["每股收益", "营业总收入", "归母净利润"])
    monkeypatch.setattr(tools.ak, "stock_financial_abstract", lambda symbol: df)
    out = tools.get_financial_indicators("600519")
    assert "2024-12-31" in out and "每股收益" in out and "59.49" in out


def test_news_headlines(monkeypatch):
    """新闻取前 5 条标题。"""
    df = pd.DataFrame({"新闻标题": ["茅台提价", "茅台发布年报", "a", "b", "c", "d"]})
    monkeypatch.setattr(tools.ak, "stock_news_em", lambda symbol: df)
    out = tools.search_news("600519")
    assert out.count("- ") == 5 and "茅台提价" in out


def test_kline_df_fallback_to_em(monkeypatch):
    """get_kline_df：腾讯失败 → 东财兜底，列映射为 date/open/close/high/low/volume。"""
    monkeypatch.setattr(tools.ak, "stock_zh_a_hist_tx",
                        lambda symbol: (_ for _ in ()).throw(ConnectionError("down")))
    em_df = pd.DataFrame([
        {"日期": "2024-01-01", "开盘": 99.0, "收盘": 100.0, "最高": 105.0, "最低": 95.0, "成交量": 10000},
        {"日期": "2024-01-02", "开盘": 100.0, "收盘": 102.0, "最高": 106.0, "最低": 96.0, "成交量": 12000},
    ])
    monkeypatch.setattr(tools.ak, "stock_zh_a_hist", lambda symbol, **kw: em_df)
    df = tools.get_kline_df("600519")
    assert list(df.columns) == ["date", "open", "close", "high", "low", "volume"]
    assert df["close"].iloc[-1] == 102.0


def test_stream_text_character_level():
    """组合文本按字符推送：每个字符一个队列事件，可还原原文。"""
    import queue
    from finagent.agents.supervisor import _stream_text

    class _FakeHandler:
        def __init__(self):
            self.q = queue.Queue()

    h = _FakeHandler()
    _stream_text(h, "你好，FinAgent")
    items = []
    while True:
        it = h.q.get()
        if it is None:
            break
        items.append(it)
    assert len(items) == 11  # "你好，FinAgent" 共 11 个字符，每个一个事件
    assert "".join(items) == "你好，FinAgent"
