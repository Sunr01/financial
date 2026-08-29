# FinAgent 开发进度笔记（认证 + 策略联动 + 回测）

> 记录近期的功能实现与待办，重点是"企业级升级"路线（PostgreSQL + JWT + LangGraph Checkpointer）。

## 1. 已完成功能

### 1.1 策略自动执行
- 文件：`src/finagent/trading/strategy_runner.py`
- 功能：按当前策略规则自动买卖，驱动模拟账户（复用回测引擎的 `_should_buy/_should_sell` 判断，回测与实盘一致）。
- 接口：`/api/strategy/start|stop|execute|status`（前端每5秒轮询执行）。
- 前端：我的交易页"启动/停止策略 + 执行一次"按钮 + 运行日志。

### 1.2 策略联动（三页共享当前策略）
- 后端：`CURRENT_STRATEGY` 全局状态 + `/api/strategy/current`（GET/POST）。
- 前端：编写策略保存后设为当前策略 → 自动回测显示（收益曲线+指标+交易记录+投入按钮）；我的交易显示当前策略；数据平台自由查任意股票。
- 回测接口 `/api/backtest` 支持 `rule_desc`/`window` 参数（不再写死均线）。

### 1.3 回测与图表
- 单股票回测引擎 `src/finagent/backtest/engine.py`（均线/网格/动量规则判断）。
- 收益曲线：策略收益% vs 基准收益%（`calc_returns` + `get_benchmark`，基准可选沪深300/上证/中证500/深成指/创业板）。
- 前端 ECharts：K线图（悬停显示数值）+ 收益曲线（多折线+渐变填充+缩放）。
- 策略模板库 `src/finagent/strategy/templates.py`（均线/网格/动量/成长因子4种）。

### 1.4 前端
- 4 页面（首页/编写策略/数据平台/我的交易），白色基调。
- 数据平台三合一（查行情/看K线/回测 一个输入区+三个按钮，点击切换，激活变绿）。

## 2. 进行中：JWT 认证（企业级）

### 已建文件（src/finagent/api/auth/）
| 文件 | 职责 |
|---|---|
| `__init__.py` | 模块标识 |
| `security.py` | JWT 签发/验证（pyjwt）+ 密码加密（passlib bcrypt）|
| `db.py` | 数据库操作（当前是 SQLite 版，待改 PostgreSQL）|
| `routes.py` | 注册/登录/me 接口（FastAPI 路由）|

### 接口设计
- `/api/auth/register`：注册（用户名≥3位，密码≥6位）
- `/api/auth/login`：登录 → 返回 JWT token（24小时有效）
- `/api/auth/me`：受保护接口（OAuth2PasswordBearer + 依赖注入）

### 依赖
- `pyjwt`、`passlib[bcrypt]`（已装到系统 python，需装到 .venv）
- `psycopg[binary,pool]`、`langgraph-checkpoint-postgres`（PostgreSQL 版要用）

## 3. 待办：PostgreSQL（明天继续）

### 为什么用 PostgreSQL
- 用户要求企业级实现。
- 之前项目（保险顾问）用过：Docker 跑 PostgreSQL + LangGraph `AsyncPostgresSaver` 做会话持久化。

### 待办步骤
1. **启动 PostgreSQL 容器**（Docker）：
   ```
   docker run -d --name finagent-pg -e POSTGRES_USER=finagent -e POSTGRES_PASSWORD=finagent123 -e POSTGRES_DB=finagent -p 5432:5432 postgres:16
   ```
   - ⚠️ 当前卡在镜像拉取：`127.0.0.1:7890` 代理 refused（代理没开/端口不通）。
   - 解决：开代理重试，或配国内镜像加速器（docker.m.daocloud.io）。
2. **装依赖**：`psycopg[binary,pool]`、`langgraph-checkpoint-postgres`、`pyjwt`、`passlib[bcrypt]` 到 .venv。
3. **认证 db.py 改 PostgreSQL 版**（psycopg 连接，连接信息放 .env）。
4. **LangGraph Checkpointer**（Agent 会话记忆持久化）：
   - `AsyncPostgresSaver` + `AsyncConnectionPool`，`await checkpointer.setup()` 自动建表。
   - 参考之前项目写法（app.core.config 的 build_url 生成两种连接地址：SQLAlchemy 用 asyncpg，Checkpointer 用 psycopg）。
5. **配置 .env**：DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD。

## 4. 未实现/远期待办
- 多股票回测（成长因子策略 engine_multi.py）
- 绩效指标卡片（年化/夏普/回撤/胜率/阿尔法/贝塔）
- README（GitHub 页面）
- LlamaIndex 局部引入（增量索引/查询引擎/元数据过滤）
- 模拟交易台动态流式图表（SSE）
