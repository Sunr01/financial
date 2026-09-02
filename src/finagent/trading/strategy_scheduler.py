"""策略后台调度器：定时轮询所有运行中的用户策略并执行检查。

相比之前"前端轮询才执行一次"的半成品，这里由后台线程按固定间隔
主动执行；运行状态持久化在 PG（data_store.set_strategy_running），
容器重启后调度器会自动恢复运行中的策略。
"""

import threading
import time

from finagent.data_store import (
    get_all_running_users,
    get_account_data,
    save_account_data,
    get_current_strategy,
)
from finagent.trading.account import Account
from finagent.trading.strategy_runner import run_strategy

INTERVAL_SECONDS = 60  # 每 60 秒检查一次
_stop = False
_thread: threading.Thread | None = None


def _load_account(username: str) -> Account:
    """从 PG 加载用户账户（兼容旧 JSON 结构）。"""
    data = get_account_data(username)
    if data and "account" in data:
        return Account.from_dict(data["account"])
    return Account()


def _save_account(username: str, acc: Account) -> None:
    """持久化用户账户到 PG（合并保存，避免覆盖 current_strategy/strategy_running）。"""
    data = get_account_data(username) or {}
    data["account"] = acc.to_dict()
    save_account_data(username, data)
    # 交易流水持久化（只在有交易时写库）
    if acc.trade_log:
        from finagent.data_store import record_trades
        record_trades(username, acc.trade_log)
        acc.trade_log.clear()


def execute_for_user(username: str) -> str:
    """为用户执行一次策略检查，返回结果消息。"""
    cur = get_current_strategy(username)
    if not cur.get("name"):
        return "尚未设置策略"
    symbol = cur.get("symbol", "600519")
    rule = {"description": cur.get("description", ""), "window": 20}
    acc = _load_account(username)
    msg = run_strategy(acc, symbol, rule)
    _save_account(username, acc)
    return msg


def _loop() -> None:
    """后台循环：轮询运行中的用户并执行。"""
    global _stop
    print("[scheduler] 策略调度器已启动（每 60s 检查一次）")
    while not _stop:
        try:
            users = get_all_running_users()
            for username in users:
                try:
                    msg = execute_for_user(username)
                    if msg and "无操作" not in msg:
                        print(f"[scheduler] {username}: {msg}")
                except Exception as e:
                    print(f"[scheduler] {username} 执行失败: {type(e).__name__}: {e}")
        except Exception as e:
            print(f"[scheduler] 轮询失败: {type(e).__name__}: {e}")
        # 分片睡眠，便于快速停止
        for _ in range(INTERVAL_SECONDS):
            if _stop:
                break
            time.sleep(1)


def start() -> None:
    """启动后台调度线程（幂等）。"""
    global _thread, _stop
    if _thread and _thread.is_alive():
        return
    _stop = False
    _thread = threading.Thread(target=_loop, daemon=True)
    _thread.start()


def stop() -> None:
    """停止调度线程。"""
    global _stop
    _stop = True
