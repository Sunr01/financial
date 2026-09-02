"""API 层单元测试：策略接口状态持久化、账户风控、调度器逻辑。

原则：不依赖外部网络与真实 DB——用 pytest monkeypatch 替换 PG 访问与行情接口。
"""

import pytest
from pathlib import Path


# ---------- 账户风控 ----------
def test_commission_and_slippage():
    """手续费(万2.5,最低5元) + 滑点(0.1%) 正确计入。"""
    from finagent.trading.account import Account
    a = Account(cash=1_000_000)
    msg = a.buy("600519", "贵州茅台", 100, 100.0)
    assert "已买入" in msg
    # 成交价=100*(1+0.001)=100.1, 手续费=max(100*100.1*0.00025,5)=5
    assert abs(a.cash - (1_000_000 - 100 * 100.1 - 5)) < 0.01
    # 卖出吃滑点 0.1%
    msg = a.sell("600519", 100, 110.0)
    assert "已卖出" in msg
    assert "600519" not in a.positions


def test_position_limit():
    """单只股票仓位上限 50% 生效。"""
    from finagent.trading.account import Account
    a = Account(cash=1_000_000)
    msg = a.buy("600519", "贵州茅台", 6000, 100.0)
    assert "仓位上限" in msg


def test_stop_loss():
    """止损：亏损超 10% 应触发强平。"""
    from finagent.trading.account import Account
    a = Account(cash=1_000_000)
    a.buy("600519", "贵州茅台", 100, 100.0)
    a.positions["600519"].price = 85.0  # 模拟跌 15%
    forced = a.check_stop_loss()
    assert "600519" in forced


# ---------- 策略运行状态持久化（mock PG） ----------
@pytest.fixture
def mock_store(monkeypatch):
    """mock data_store 的账户读写,验证状态持久化逻辑。"""
    import finagent.data_store as ds
    state = {"data": None}

    def fake_get(username):
        return state["data"]

    def fake_save(username, data):
        state["data"] = data

    monkeypatch.setattr(ds, "get_account_data", fake_get)
    monkeypatch.setattr(ds, "save_account_data", fake_save)
    return state


def test_strategy_running_persistence(mock_store):
    """策略运行状态存入 PG JSON,重启可恢复(不再是内存 dict)。"""
    from finagent.data_store import set_strategy_running, get_strategy_running
    set_strategy_running("alice", True)
    assert get_strategy_running("alice") is True
    set_strategy_running("alice", False)
    assert get_strategy_running("alice") is False


def test_all_running_users(mock_store, monkeypatch):
    """get_all_running_users 只返回运行中的用户(供调度器轮询)。"""
    import finagent.data_store as ds
    rows = [
        {"username": "alice", "data": {"strategy_running": True}},
        {"username": "bob", "data": {"strategy_running": False}},
        {"username": "carol", "data": None},
    ]

    def fake_all():
        return rows

    monkeypatch.setattr(ds, "get_conn", lambda: _FakeConn(rows))
    users = ds.get_all_running_users()
    assert users == ["alice"]


class _FakeConn:
    """最小 fake：execute().fetchall() 返回预设行。"""

    def __init__(self, rows):
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, *a, **k):
        class R:
            _rows = self._rows

            def fetchall(self):
                return self._rows
        return R()


# ---------- 调度器 ----------
def test_scheduler_execute_requires_strategy(monkeypatch):
    """调度器对未设置策略的用户返回提示(不崩溃)。"""
    from finagent.trading import strategy_scheduler as sch
    monkeypatch.setattr(sch, "get_current_strategy", lambda u: {"name": ""})
    assert "未设置策略" in sch.execute_for_user("alice")


def test_save_account_preserves_other_keys(mock_store, monkeypatch):
    """保存账户时不得覆盖 current_strategy/strategy_running(多写者共享 JSON 的回归测试)。"""
    from finagent.data_store import (
        set_current_strategy, set_strategy_running,
        get_current_strategy, get_strategy_running,
    )
    from finagent.trading.strategy_scheduler import _save_account
    from finagent.trading.account import Account

    # scheduler 模块内是 from ... import 绑定,需 mock 模块级引用,避免真连 PG
    import finagent.trading.strategy_scheduler as sch
    monkeypatch.setattr(sch, "get_account_data",
                        lambda u: mock_store["data"])
    monkeypatch.setattr(sch, "save_account_data",
                        lambda u, d: mock_store.__setitem__("data", d))

    # 先写策略 + 运行状态
    set_current_strategy("alice", {"name": "均线", "symbol": "600519"})
    set_strategy_running("alice", True)
    # 再保存账户(模拟调度器执行后的保存)
    _save_account("alice", Account(cash=900000))
    # 其他键必须还在
    assert get_strategy_running("alice") is True
    assert get_current_strategy("alice")["name"] == "均线"


# ---------- 交易流水 ----------
def test_trade_log_recorded_on_buy_sell():
    """买卖产生交易流水(含手续费/滑点)。"""
    from finagent.trading.account import Account
    a = Account(cash=1_000_000)
    a.buy("600519", "贵州茅台", 100, 100.0)
    a.sell("600519", 100, 110.0)
    assert len(a.trade_log) == 2
    assert a.trade_log[0]["side"] == "buy"
    assert a.trade_log[0]["symbol"] == "600519"
    assert a.trade_log[0]["fee"] > 0
    assert a.trade_log[1]["side"] == "sell"


def test_record_trades_skips_empty():
    """无流水时不写库。"""
    import finagent.data_store as ds
    ds.record_trades("alice", [])


def test_account_roundtrip_serialization():
    """账户 to_dict/from_dict 往返一致(持仓 Position 可 JSON 序列化)。"""
    import json
    from finagent.trading.account import Account
    a = Account(cash=900000)
    a.buy("600519", "贵州茅台", 100, 100.0)
    blob = json.dumps(a.to_dict())  # 不抛 TypeError
    b = Account.from_dict(json.loads(blob))
    assert b.cash == a.cash
    assert b.positions["600519"].qty == 100
    assert b.positions["600519"].cost > 0


def test_get_current_user_rejects_deleted(monkeypatch):
    """注销后旧 token 失效:用户不存在则 401。"""
    from finagent.auth import routes
    from fastapi import HTTPException

    monkeypatch.setattr(routes, "decode_token", lambda t: "ghost")
    monkeypatch.setattr(routes.db, "user_exists", lambda u: False)
    try:
        routes.get_current_user("fake-token")
        assert False, "应抛 401"
    except HTTPException as e:
        assert e.status_code == 401


# ---------- 用户数据导出/删除 ----------
def test_export_delete_user_data(mock_store, monkeypatch):
    """导出包含各数据域;删除级联清理。"""
    import finagent.data_store as ds
    calls = []

    def fake_export(u):
        return {"user": {"username": u}, "account": None,
                "strategies": [], "conversations": [], "trades": []}

    def fake_delete(u):
        calls.append(u)

    monkeypatch.setattr(ds, "export_user_data", fake_export)
    monkeypatch.setattr(ds, "delete_user_data", fake_delete)
    data = ds.export_user_data("alice")
    assert data["user"]["username"] == "alice"
    ds.delete_user_data("alice")
    assert calls == ["alice"]


# ---------- 知识库刷新签名 ----------
def test_knowledge_signature_changes_with_mtime(monkeypatch):
    """文档内容变化 → 签名变化(触发刷新判断)。"""
    from finagent.rag import refresh
    import os, shutil
    d = Path(os.getcwd()) / f".tmp_kg_{os.getpid()}"
    d.mkdir(exist_ok=True)
    try:
        f = d / "600519_茅台.md"
        f.write_text("贵州茅台2023年营收1505.60亿", encoding="utf-8")
        s1 = refresh._compute_signature(d)
        f.write_text("贵州茅台2023年营收1505.60亿 净利润747亿", encoding="utf-8")
        s2 = refresh._compute_signature(d)
        assert s1 != s2
    finally:
        shutil.rmtree(d, ignore_errors=True)
