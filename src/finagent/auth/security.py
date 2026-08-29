"""JWT 认证工具：密码加密、token 签发与验证。"""

import time
import bcrypt
import jwt

from finagent.config import settings

SECRET_KEY = settings.secret_key  # 从 .env 读取（生产必须配置强随机值）
ALGORITHM = "HS256"
TOKEN_EXPIRE_SECONDS = 3600 * 24  # token 有效期 24 小时


def hash_password(password: str) -> str:
    """密码加密（bcrypt 加盐哈希）。"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """验证密码。"""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_token(username: str) -> str:
    """签发 JWT token（含用户名和过期时间）。"""
    payload = {"sub": username, "exp": int(time.time()) + TOKEN_EXPIRE_SECONDS}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> str | None:
    """验证 token，返回用户名；无效返回 None。"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except jwt.InvalidTokenError:
        return None
