# FinAgent JWT 认证 + PostgreSQL 实现总结

> 记录 JWT 注册登录 + PostgreSQL 数据库接入的实现过程、踩坑与成果。

## 1. 实现内容

### 1.1 JWT 注册登录（企业级）
| 文件 | 职责 |
|---|---|
| `src/finagent/api/auth/security.py` | 密码加密（bcrypt）+ JWT 签发/验证（pyjwt）|
| `src/finagent/api/auth/db.py` | PostgreSQL 连接 + 用户表操作（psycopg）|
| `src/finagent/api/auth/routes.py` | 注册/登录/me 接口（FastAPI 路由）|
| `src/finagent/api/server.py` | 挂载认证路由 + 初始化数据库 |

### 1.2 接口
- `POST /api/auth/register`：注册（用户名≥3位、密码≥6位，bcrypt 加密存储）
- `POST /api/auth/login`：登录 → 返回 JWT token（24 小时有效）
- `GET /api/auth/me`：受保护接口（OAuth2PasswordBearer + 依赖注入）

### 1.3 技术选型（企业标准）
| 组件 | 选型 | 理由 |
|---|---|---|
| 密码加密 | **bcrypt**（官方库）| 加盐哈希、防彩虹表；passlib 已不维护且有兼容问题 |
| Token | **JWT**（pyjwt）| 无状态认证、跨服务、业界标准 |
| 数据库 | **PostgreSQL 16**（Docker）| 企业标准关系型数据库 |
| 驱动 | **psycopg3**（含 binary/pool）| 官方现代驱动、支持连接池 |
| 认证方式 | **OAuth2PasswordBearer** | FastAPI 官方推荐 |

## 2. 环境搭建

### 2.1 PostgreSQL（Docker，企业容器化方式）
```bash
docker run -d --name finagent-pg \
  -e POSTGRES_USER=finagent \
  -e POSTGRES_PASSWORD=finagent123 \
  -e POSTGRES_DB=finagent \
  -p 5432:5432 \
  postgres:16
```
- 专用用户 finagent（应用不用 root，企业规范）
- 自动建库 finagent
- ⚠️ 拉镜像可能遇代理问题（127.0.0.1:7890 refused）→ 开代理或配国内镜像加速器

### 2.2 依赖（装入 .venv）
```bash
pip install psycopg[binary,pool] langgraph-checkpoint-postgres pyjwt bcrypt
```

## 3. 踩坑记录

### 坑 1：.venv 缺 pip → 包装错环境
- **现象**：`python -m pip` 报 `No module named pip`；之前"装好的包"全在系统 Python，.venv 没有。
- **原因**：.venv 创建时没带 pip（或损坏）。
- **解决**：`python -m ensurepip --upgrade` 补装 pip，再 `python -m pip install ...`。
- **教训**：装包前先确认解释器（`python -c "import sys; print(sys.executable)"`）和 pip 可用。

### 坑 2：passlib + bcrypt 5.0 兼容问题
- **现象**：`ValueError: password cannot be longer than 72 bytes`。
- **原因**：passlib 1.7.4 已不维护，与 bcrypt 5.0 行为不兼容。
- **解决**：**放弃 passlib，直接用 bcrypt 官方库**（`hashpw`/`checkpw`）。
- **教训**：密码哈希用官方 bcrypt 库，别用维护停滞的封装库。

### 坑 3：PostgreSQL 镜像拉取代理问题
- **现象**：`127.0.0.1:7890 refused`（Docker 走代理但代理不通）。
- **解决**：开代理软件，或 Docker Desktop 配置国内镜像加速器（docker.m.daocloud.io）。

## 4. 测试结果（全部通过）

```
语法OK
数据库初始化OK（PostgreSQL 建 users 表）
创建用户OK / 查询用户OK
密码验证: True（bcrypt 加密+验证）
token生成: eyJhbGciOiJIUzI1NiIs...（JWT 签发）
token解码: testuser（JWT 验证）
无效token: None（拒绝无效 token）
```

## 5. 后续待办
- LangGraph Checkpointer（Agent 会话持久化，AsyncPostgresSaver，参考之前项目写法）
- 前端注册/登录页面
- SECRET_KEY 改从 .env 读取（生产安全）
- 更新技术栈文档（09-tech-stack.md 的认证/数据库部分状态）
