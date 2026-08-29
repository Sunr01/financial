"""数据库操作：用户表（PostgreSQL，psycopg 驱动）。"""

import psycopg
from psycopg.rows import dict_row

from finagent.config import settings


def get_conninfo() -> str:
    """生成 PostgreSQL 连接串。"""
    return (f"host={settings.db_host} port={settings.db_port} "
            f"dbname={settings.db_name} user={settings.db_user} "
            f"password={settings.db_password}")


def get_conn() -> psycopg.Connection:
    """获取数据库连接（dict 行工厂）。"""
    return psycopg.connect(get_conninfo(), row_factory=dict_row)


def init_db() -> None:
    """建表：用户表、策略表、账户表（如不存在）。"""
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_strategies (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) NOT NULL,
                name VARCHAR(100) NOT NULL,
                symbol VARCHAR(20) NOT NULL,
                capital VARCHAR(20),
                code TEXT,
                rule JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_accounts (
                username VARCHAR(50) PRIMARY KEY,
                data JSONB NOT NULL,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) NOT NULL,
                thread_id VARCHAR(100) NOT NULL,
                title VARCHAR(200) DEFAULT '新对话',
                messages JSONB DEFAULT '[]',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(username, thread_id)
            )
        """)


def create_user(username: str, password_hash: str) -> None:
    """插入新用户。"""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
            (username, password_hash),
        )


def get_user(username: str) -> dict | None:
    """按用户名查用户。"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = %s", (username,)
        ).fetchone()
        return row


def user_exists(username: str) -> bool:
    """用户名是否已存在。"""
    return get_user(username) is not None
