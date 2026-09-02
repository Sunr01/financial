"""股市行情分页接口测试：过滤/分页/JSON 序列化。不依赖网络与 PG。"""

import pandas as pd
import pytest


def _load_server(monkeypatch):
    """加载 server 模块，但屏蔽模块级 DB 初始化（避免连 PG）。"""
    import finagent.auth.db as db
    import finagent.agents.checkpointer as cp
    monkeypatch.setattr(db, "init_db", lambda: None)
    monkeypatch.setattr(cp, "get_checkpointer", lambda: None)
    from finagent.api import server
    return server


def _fake_snapshot():
    """30 只假股票。"""
    return pd.DataFrame({
        "代码": [f"6005{i:02d}" for i in range(30)],
        "名称": [f"测试股{i}" for i in range(30)],
        "最新价": [10.0 + i for i in range(30)],
        "涨跌幅": [float(i) for i in range(30)],
        "换手率": [2.0] * 30,
        "成交额": [3e8] * 30,
        "总市值": [4e9] * 30,
        "市盈率-动态": [15.0] * 30,
    })


def test_stocks_pagination(monkeypatch):
    """分页：总数/页数/第 2 页内容正确。"""
    server = _load_server(monkeypatch)
    monkeypatch.setattr(server, "_get_stock_snapshot", lambda refresh=False: _fake_snapshot())
    data = server.api_stocks(page=2, page_size=10, keyword="", user="t")
    assert data["total"] == 30
    assert data["pages"] == 3
    assert data["page"] == 2
    assert len(data["items"]) == 10
    assert data["items"][0]["代码"] == "600510"  # 第 2 页第一行


def test_stocks_keyword_filter(monkeypatch):
    """代码/名称筛选。"""
    server = _load_server(monkeypatch)
    monkeypatch.setattr(server, "_get_stock_snapshot", lambda refresh=False: _fake_snapshot())
    by_code = server.api_stocks(page=1, page_size=20, keyword="60051", user="t")
    assert by_code["total"] == 10  # 600510~600519
    by_name = server.api_stocks(page=1, page_size=20, keyword="测试股1", user="t")
    assert by_name["total"] == 11  # 测试股1 + 测试股10~19
    assert by_name["pages"] == 1


def test_stocks_out_of_range_page(monkeypatch):
    """超范围页码：返回空 items，页码不崩。"""
    server = _load_server(monkeypatch)
    monkeypatch.setattr(server, "_get_stock_snapshot", lambda refresh=False: _fake_snapshot())
    data = server.api_stocks(page=99, page_size=20, user="t")
    assert data["items"] == [] and data["page"] == 99


def test_stocks_source_error(monkeypatch):
    """数据源失败：返回 error 信息而非崩溃。"""
    server = _load_server(monkeypatch)
    def boom(refresh=False):
        raise ConnectionError("no net")
    monkeypatch.setattr(server, "_get_stock_snapshot", boom)
    data = server.api_stocks(page=1, page_size=20, user="t")
    assert "error" in data


def test_stocks_sort(monkeypatch):
    """按列排序：降序/升序对全市场生效（先排序后分页）。"""
    server = _load_server(monkeypatch)
    monkeypatch.setattr(server, "_get_stock_snapshot", lambda refresh=False: _fake_snapshot())
    # 涨跌幅 = i（0..29），降序第一页第一条应为 29
    data = server.api_stocks(page=1, page_size=10, sort_by="涨跌幅", sort_order="desc", user="t")
    assert data["items"][0]["涨跌幅"] == 29.0
    assert data["items"][0]["代码"] == "600529"
    # 升序第一页第一条应为 0
    data2 = server.api_stocks(page=1, page_size=10, sort_by="涨跌幅", sort_order="asc", user="t")
    assert data2["items"][0]["涨跌幅"] == 0.0
    # 非法列名不崩（保持原顺序）
    data3 = server.api_stocks(page=1, page_size=10, sort_by="不存在列", user="t")
    assert data3["items"][0]["代码"] == "600500"


def test_industry_stocks_sort(monkeypatch):
    """行业成分股同样支持按列排序。"""
    server = _load_server(monkeypatch)
    import akshare
    import pandas as pd
    def fake_cons(symbol):
        return pd.DataFrame({
            "代码": ["600519", "000858", "600036"],
            "名称": ["贵州茅台", "五粮液", "招商银行"],
            "最新价": [1700.0, 150.0, 35.0],
            "涨跌幅": [1.2, -0.5, 0.3],
            "换手率": [0.5, 1.0, 0.2],
            "成交额": [8e9, 2e9, 3e9],
            "市盈率-动态": [28.0, 20.0, 6.0],
        })
    monkeypatch.setattr(akshare, "stock_board_industry_cons_em", fake_cons)
    data = server.api_stock_industry(name="酿酒行业", page=1, page_size=3,
                                     sort_by="最新价", sort_order="desc", user="t")
    assert [i["代码"] for i in data["items"]] == ["600519", "000858", "600036"]


def test_snapshot_em_primary(monkeypatch):
    """东财源正常时不调用新浪兜底。"""
    server = _load_server(monkeypatch)
    import akshare
    import pandas as pd
    calls = {"sina": 0}
    def fake_em():
        return pd.DataFrame({
            "代码": ["600519"], "名称": ["贵州茅台"], "最新价": [1700.0],
            "涨跌幅": [1.2], "换手率": [0.5], "成交额": [8e9],
            "总市值": [2e12], "市盈率-动态": [28.0],
        })
    def fake_sina():
        calls["sina"] += 1
        raise AssertionError("东财成功时不应调用新浪")
    monkeypatch.setattr(akshare, "stock_zh_a_spot_em", fake_em)
    monkeypatch.setattr(akshare, "stock_zh_a_spot", fake_sina)
    df = server._get_stock_snapshot(refresh=True)
    assert calls["sina"] == 0
    assert list(df["名称"]) == ["贵州茅台"]


def test_snapshot_fallback_to_sina(monkeypatch):
    """东财失败 → 新浪兜底，列映射正确（代码去前缀，缺字段置空）。"""
    server = _load_server(monkeypatch)
    import akshare
    import pandas as pd
    calls = {"em": 0, "sina": 0}
    def fake_em():
        calls["em"] += 1
        raise ConnectionError("eastmoney down")
    def fake_sina():
        calls["sina"] += 1
        return pd.DataFrame({
            "代码": ["sh600519", "sz000001"],
            "名称": ["贵州茅台", "平安银行"],
            "最新价": [1700.0, 11.0],
            "涨跌幅": [1.2, -0.5],
            "成交额": [8e9, 2e9],
        })
    monkeypatch.setattr(akshare, "stock_zh_a_spot_em", fake_em)
    monkeypatch.setattr(akshare, "stock_zh_a_spot", fake_sina)
    monkeypatch.setattr("time.sleep", lambda s: None)  # 去掉重试间隔
    df = server._get_stock_snapshot(refresh=True)
    assert calls["em"] == 3 and calls["sina"] == 1  # 东财重试 3 次失败后才切新浪
    assert list(df["代码"]) == ["600519", "000001"]
    assert list(df["名称"]) == ["贵州茅台", "平安银行"]
    assert df["换手率"].iloc[0] is None and df["总市值"].iloc[0] is None


def test_industries_em_primary(monkeypatch):
    """行业列表：东财优先，新浪兜底。"""
    server = _load_server(monkeypatch)
    import akshare
    import pandas as pd
    calls = {"sina": 0}
    def fake_em():
        return pd.DataFrame({"板块名称": ["酿酒行业", "银行行业"]})
    def fake_sina():
        calls["sina"] += 1
        raise AssertionError("东财成功时不应调用新浪")
    monkeypatch.setattr(akshare, "stock_board_industry_name_em", fake_em)
    monkeypatch.setattr(akshare, "stock_sector_spot", fake_sina)
    names = server._get_industries(refresh=True)
    assert names == ["酿酒行业", "银行行业"] and calls["sina"] == 0


def test_pick_chinese_names(monkeypatch):
    """新浪行业名提取：label 为英文/代码、板块为中文时，取中文。"""
    server = _load_server(monkeypatch)
    import pandas as pd
    df = pd.DataFrame({
        "label": ["NEW_BL", "NEW_YH", "MIX"],
        "板块": ["酿酒行业", "银行行业", ""],
    })
    names = server._pick_chinese_names(df)
    assert names == ["酿酒行业", "银行行业", "MIX"]  # 无中文时兜底 label


def test_industries_sina_fallback_chinese(monkeypatch):
    """东财失败 → 新浪兜底：行业名必须为中文。"""
    server = _load_server(monkeypatch)
    import akshare
    import pandas as pd
    def fake_em():
        raise ConnectionError("eastmoney down")
    def fake_sina(indicator="新浪行业"):
        return pd.DataFrame({
            "label": ["NEW_BL", "NEW_YH"],
            "板块": ["酿酒行业", "银行行业"],
            "公司家数": [10, 20],
        })
    monkeypatch.setattr(akshare, "stock_board_industry_name_em", fake_em)
    monkeypatch.setattr(akshare, "stock_sector_spot", fake_sina)
    names = server._get_industries(refresh=True)
    assert names == ["酿酒行业", "银行行业"]
    assert all(any("\u4e00" <= c <= "\u9fff" for c in n) for n in names)


def test_industry_stocks_retry(monkeypatch):
    """行业成分：东财偶发断连时自动重试，重试成功返回数据。"""
    server = _load_server(monkeypatch)
    import akshare
    import pandas as pd
    monkeypatch.setattr("time.sleep", lambda s: None)  # 去掉重试间隔
    calls = {"n": 0}

    def fake_cons(symbol):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("intermittent")
        return pd.DataFrame({
            "代码": ["600519"], "名称": ["贵州茅台"], "最新价": [1700.0],
            "涨跌幅": [1.2], "换手率": [0.5], "成交额": [8e9], "市盈率-动态": [28.0],
        })

    monkeypatch.setattr(akshare, "stock_board_industry_cons_em", fake_cons)
    data = server.api_stock_industry(name="酿酒行业", page=1, page_size=20, user="t")
    assert data["total"] == 1 and data["items"][0]["名称"] == "贵州茅台"
    assert calls["n"] == 3  # 失败 2 次 + 成功 1 次


def test_industry_stocks_all_sources_fail(monkeypatch):
    """行业成分：东财重试后仍失败、新浪兜底也失败 → 返回友好 error。"""
    server = _load_server(monkeypatch)
    import akshare
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr(akshare, "stock_board_industry_cons_em",
                        lambda symbol: (_ for _ in ()).throw(ConnectionError("em down")))
    monkeypatch.setattr(akshare, "stock_sector_spot",
                        lambda indicator="新浪行业": (_ for _ in ()).throw(ValueError("sina parse")))
    data = server.api_stock_industry(name="酿酒行业", page=1, page_size=20, user="t")
    assert "error" in data and "新浪兜底也失败" in data["error"]


def test_industry_stocks_sina_label_mapping(monkeypatch):
    """新浪兜底：中文行业名 → label 反查 → 成分股列映射（去前缀、英文列转统一列）。"""
    server = _load_server(monkeypatch)
    import akshare
    import pandas as pd
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr(akshare, "stock_board_industry_cons_em",
                        lambda symbol: (_ for _ in ()).throw(ConnectionError("em down")))

    def fake_spot(indicator="新浪行业"):
        return pd.DataFrame({
            "label": ["new_blhy", "new_yhhy"],
            "板块": ["酿酒行业", "银行行业"],
        })

    def fake_detail(sector):
        assert sector == "new_blhy"  # 必须用新浪内部 label 查询
        return pd.DataFrame({
            "symbol": ["sh600519", "sz000858"],
            "name": ["贵州茅台", "五粮液"],
            "trade": [1700.0, 150.0],
            "changepercent": [1.2, -0.5],
            "turnoverratio": [0.5, 1.0],
            "amount": [8e9, 2e9],
            "mktcap": [2e12, 5e11],
            "per": [28.0, 20.0],
        })

    monkeypatch.setattr(akshare, "stock_sector_spot", fake_spot)
    monkeypatch.setattr(akshare, "stock_sector_detail", fake_detail)
    data = server.api_stock_industry(name="酿酒行业", page=1, page_size=20, user="t")
    assert data["total"] == 2
    assert data["items"][0]["代码"] == "600519"  # sh 前缀已去除
    assert data["items"][0]["名称"] == "贵州茅台"
    assert data["items"][0]["换手率"] == 0.5
    assert data["items"][0]["总市值"] == 2e12
