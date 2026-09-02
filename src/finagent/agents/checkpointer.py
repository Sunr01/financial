"""LangGraph Checkpointer：Agent 会话状态持久化到 PostgreSQL（同步版）。"""

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from langgraph.checkpoint.postgres import PostgresSaver

from finagent.config import settings


def get_conninfo() -> str:
    """生成 PostgreSQL 连接串（psycopg 协议）。"""
    return (f"host={settings.db_host} port={settings.db_port} "
            f"dbname={settings.db_name} user={settings.db_user} "
            f"password={settings.db_password}")


_pool: ConnectionPool | None = None
_checkpointer: PostgresSaver | None = None


def get_checkpointer() -> PostgresSaver:
    """获取（惰性初始化）Checkpointer（同步版，Windows 兼容）。
    连接带超时：PG 不可用时不无限挂起，抛异常由调用方降级。"""
    global _pool, _checkpointer
    if _checkpointer is None:
        _pool = ConnectionPool(
            conninfo=get_conninfo(),
            min_size=1,
            max_size=5,
            kwargs={
                "autocommit": True,
                "prepare_threshold": 0,
                "row_factory": dict_row,
                "connect_timeout": 10,
            },
            open=False,
        )
        _pool.open()
        _pool.wait(timeout=15)  # 15 秒内建连失败则抛 TimeoutError
        _checkpointer = PostgresSaver(_pool)
        _checkpointer.setup()  # 自动建表（幂等）
    return _checkpointer
