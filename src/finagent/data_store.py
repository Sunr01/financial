"""用户数据存储：策略、账户、当前策略（按用户隔离，PostgreSQL）。"""

import json
from finagent.auth.db import get_conn


# ---------- 用户策略 ----------
def save_strategy(username: str, strategy: dict) -> None:
    """保存用户策略。"""
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO user_strategies (username, name, symbol, capital, code, rule)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (username, strategy.get("name", ""), strategy.get("symbol", ""),
             strategy.get("capital", ""), strategy.get("code", ""),
             json.dumps(strategy.get("rule", {}), ensure_ascii=False)),
        )


def list_strategies(username: str) -> list:
    """获取用户策略列表。"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM user_strategies WHERE username = %s ORDER BY id DESC",
            (username,),
        ).fetchall()
        return [
            {"id": r["id"], "name": r["name"], "symbol": r["symbol"],
             "capital": r["capital"], "code": r["code"], "rule": r["rule"]}
            for r in rows
        ]


# ---------- 用户账户 ----------
def get_account_data(username: str) -> dict:
    """获取用户账户数据（JSON）。"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT data FROM user_accounts WHERE username = %s", (username,)
        ).fetchone()
        return row["data"] if row else None


def save_account_data(username: str, data: dict) -> None:
    """保存用户账户数据（JSON）。"""
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO user_accounts (username, data) VALUES (%s, %s)
               ON CONFLICT (username) DO UPDATE SET data = EXCLUDED.data,
                   updated_at = NOW()""",
            (username, json.dumps(data, ensure_ascii=False)),
        )


# ---------- 当前策略 ----------
def get_current_strategy(username: str) -> dict:
    """获取用户当前策略。"""
    data = get_account_data(username)
    if data and "current_strategy" in data:
        return data["current_strategy"]
    return {"name": "", "symbol": "600519", "description": ""}


def set_current_strategy(username: str, strategy: dict) -> None:
    """设置用户当前策略（存账户 JSON 里）。"""
    data = get_account_data(username) or {}
    data["current_strategy"] = strategy
    save_account_data(username, data)


# ---------- 策略运行状态（持久化，容器重启可恢复） ----------
def set_strategy_running(username: str, running: bool) -> None:
    """设置策略运行状态（存入 PG，不再依赖内存）。"""
    data = get_account_data(username) or {}
    data["strategy_running"] = running
    save_account_data(username, data)


def get_strategy_running(username: str) -> bool:
    """获取策略运行状态。"""
    data = get_account_data(username)
    return bool(data and data.get("strategy_running"))


def get_all_running_users() -> list:
    """获取所有策略运行中的用户（供后台调度器轮询）。"""
    with get_conn() as conn:
        rows = conn.execute("SELECT username, data FROM user_accounts").fetchall()
        return [
            r["username"] for r in rows
            if r["data"] and r["data"].get("strategy_running")
        ]


# ---------- 交易流水 ----------
def record_trades(username: str, trades: list) -> None:
    """批量写入交易流水（每笔: symbol/name/side/qty/price/fee）。"""
    if not trades:
        return
    with get_conn() as conn:
        for t in trades:
            conn.execute(
                """INSERT INTO trades (username, symbol, name, side, qty, price, fee)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (username, t["symbol"], t.get("name", ""), t["side"],
                 t["qty"], t["price"], t.get("fee", 0)),
            )


def list_trades(username: str, limit: int = 50) -> list:
    """获取用户交易流水（按时间倒序）。"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, symbol, name, side, qty, price, fee, created_at "
            "FROM trades WHERE username = %s ORDER BY id DESC LIMIT %s",
            (username, limit),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------- 知识库同步状态（自动刷新用） ----------
def get_knowledge_signature() -> str | None:
    """获取已入库的知识库指纹（文档签名）。"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT docs_signature FROM knowledge_sync ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row["docs_signature"] if row else None


def save_knowledge_signature(signature: str) -> None:
    """记录知识库已入库的指纹（新指纹插入）。"""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO knowledge_sync (docs_signature) VALUES (%s)",
            (signature,),
        )


# ---------- 用户数据导出/删除（合规） ----------
def export_user_data(username: str) -> dict:
    """导出用户全部数据（账户/策略/会话/交易流水）。"""
    with get_conn() as conn:
        user = conn.execute(
            "SELECT username, created_at FROM users WHERE username = %s",
            (username,),
        ).fetchone()
        account = conn.execute(
            "SELECT data FROM user_accounts WHERE username = %s",
            (username,),
        ).fetchone()
        strategies = conn.execute(
            "SELECT id, name, symbol, capital, code, rule, created_at "
            "FROM user_strategies WHERE username = %s ORDER BY id",
            (username,),
        ).fetchall()
        convs = conn.execute(
            "SELECT id, thread_id, title, messages, created_at, updated_at "
            "FROM conversations WHERE username = %s ORDER BY id",
            (username,),
        ).fetchall()
        trades = conn.execute(
            "SELECT id, symbol, name, side, qty, price, fee, created_at "
            "FROM trades WHERE username = %s ORDER BY id",
            (username,),
        ).fetchall()
        return {
            "user": dict(user) if user else None,
            "account": account["data"] if account else None,
            "strategies": [dict(r) for r in strategies],
            "conversations": [dict(r) for r in convs],
            "trades": [dict(r) for r in trades],
        }


def delete_user_data(username: str) -> None:
    """删除用户全部数据（用户/账户/策略/会话/交易流水，级联）。"""
    with get_conn() as conn:
        for table in ("trades", "conversations", "user_strategies",
                      "user_accounts", "users"):
            conn.execute(f"DELETE FROM {table} WHERE username = %s", (username,))


# ---------- 会话管理 ----------
def list_conversations(username: str) -> list:
    """获取用户会话列表（按更新时间倒序）。"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, thread_id, title, updated_at FROM conversations "
            "WHERE username = %s ORDER BY updated_at DESC",
            (username,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_conversation(username: str, thread_id: str) -> dict | None:
    """获取会话（含消息）。"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM conversations WHERE username = %s AND thread_id = %s",
            (username, thread_id),
        ).fetchone()
        return dict(row) if row else None


def create_conversation(username: str, thread_id: str, title: str = "新对话") -> None:
    """新建会话。"""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO conversations (username, thread_id, title) VALUES (%s, %s, %s) "
            "ON CONFLICT (username, thread_id) DO NOTHING",
            (username, thread_id, title),
        )


def append_message(username: str, thread_id: str, role: str, content: str) -> None:
    """向会话追加一条消息（user/assistant）。"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT messages FROM conversations WHERE username = %s AND thread_id = %s",
            (username, thread_id),
        ).fetchone()
        msgs = row["messages"] if row and row["messages"] else []
        msgs.append({"role": role, "content": content})
        # 标题：第一条用户消息截断
        title = conn.execute(
            "SELECT title FROM conversations WHERE username = %s AND thread_id = %s",
            (username, thread_id),
        ).fetchone()["title"]
        if title == "新对话" and role == "user":
            title = content[:20]
        conn.execute(
            "UPDATE conversations SET messages = %s, title = %s, updated_at = NOW() "
            "WHERE username = %s AND thread_id = %s",
            (json.dumps(msgs, ensure_ascii=False), title, username, thread_id),
        )


def rename_conversation(username: str, thread_id: str, title: str) -> None:
    """重命名会话。"""
    with get_conn() as conn:
        conn.execute(
            "UPDATE conversations SET title = %s, updated_at = NOW() "
            "WHERE username = %s AND thread_id = %s",
            (title, username, thread_id),
        )


def delete_conversation(username: str, thread_id: str) -> None:
    """删除会话。"""
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM conversations WHERE username = %s AND thread_id = %s",
            (username, thread_id),
        )
