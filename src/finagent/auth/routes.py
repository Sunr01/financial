"""认证路由：注册、登录、当前用户。"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel

from finagent.auth import db
from finagent.auth.security import hash_password, verify_password, create_token, decode_token

router = APIRouter(prefix="/api/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    """依赖：从 token 解析当前用户名（保护接口用）。"""
    username = decode_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="无效或过期的 token")
    return username


@router.post("/register")
def register(req: RegisterRequest) -> dict:
    """注册：用户名 + 密码 → 加密存储。"""
    if len(req.username) < 3 or len(req.password) < 6:
        raise HTTPException(status_code=400, detail="用户名至少3位，密码至少6位")
    if db.user_exists(req.username):
        raise HTTPException(status_code=400, detail="用户名已存在")
    db.create_user(req.username, hash_password(req.password))
    return {"message": "注册成功", "username": req.username}


@router.post("/login")
def login(req: LoginRequest) -> dict:
    """登录：验证密码 → 签发 JWT token。"""
    user = db.get_user(req.username)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_token(req.username)
    return {"access_token": token, "token_type": "bearer", "username": req.username}


@router.get("/me")
def me(username: str = Depends(get_current_user)) -> dict:
    """受保护接口：返回当前登录用户。"""
    return {"username": username}
