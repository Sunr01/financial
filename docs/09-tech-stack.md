# FinAgent 技术栈全景与实现状态

> 项目用到的全部技术点 + 实现状态（✅ 已实现 / ⏳ 进行中 / 📋 计划）。

## 一、核心框架与语言

| 技术 | 用途 | 状态 |
|---|---|---|
| Python 3.13 | 主语言 | ✅ |
| FastAPI | Web 后端框架（接口/静态服务）| ✅ |
| Uvicorn | ASGI 服务器 | ✅ |
| Pydantic v2 | 数据校验/配置 | ✅ |

## 二、AI / LLM / Agent

| 技术 | 用途 | 状态 |
|---|---|---|
| LangGraph | 多智能体编排（Supervisor + 5 Agent，StateGraph/条件边/路由）| ✅ |
| LangChain Core | RAG/文档处理/LCEL 管道（`prompt \| llm`）| ✅ |
| ChatDeepSeek | 对话模型（意图提取/简报/问答）| ✅ |
| LLM 结构化输出 | `with_structured_output` 提取意图/解析策略 | ✅ |
| RAG 问答 | Milvus 检索 + 引用溯源 | ✅ |
| DashScope Embedding | text-embedding-v3 向量化 | ✅ |
| LangGraph Checkpointer | Agent 会话持久化（PostgreSQL AsyncPostgresSaver）| ⏳ 待做（PG 启动后）|
| **LlamaIndex** | RAG 增强：增量索引/查询引擎/元数据过滤（局部引入，主线仍 LangChain）| 📋 计划（架构文档 6.4 节）|

## 三、数据库与存储

| 技术 | 用途 | 状态 |
|---|---|---|
| Milvus | 向量数据库（RAG 知识库，Docker 部署）| ✅ |
| PostgreSQL | 用户认证 + Checkpointer（Docker）| ⏳ 待做（镜像拉取中）|
| SQLite（过渡）| 认证用户表（当前临时）| ✅（待切 PG）|
| JSON 文件 | 策略保存 strategies.json | ✅ |

## 四、金融数据

| 技术 | 用途 | 状态 |
|---|---|---|
| AkShare | 免费金融数据源 | ✅ |
| 多数据源容错 | 新浪（行情）/腾讯（K线）/东财（财务/新闻）+ 重试 | ✅ |
| 指数基准 | 沪深300/上证/中证500/深成指/创业板 | ✅ 收益曲线对比 |

## 五、认证与安全

| 技术 | 用途 | 状态 |
|---|---|---|
| JWT（pyjwt）| 登录 token | ✅ 代码已写（待 PG）|
| bcrypt（passlib）| 密码加密 | ✅ 代码已写 |
| OAuth2PasswordBearer | FastAPI 标准认证 | ✅ 代码已写 |
| .env（pydantic-settings）| 配置/密钥管理 | ✅ |

## 六、前端

| 技术 | 用途 | 状态 |
|---|---|---|
| HTML/CSS/JS | 4 页面前端（白色基调）| ✅ |
| ECharts | 动态K线 + 收益曲线（CDN）| ✅ |
| SPA 路由 | 单页应用导航切换 | ✅ |
| fetch API | 前后端通信 | ✅ |

## 七、量化功能

| 技术 | 用途 | 状态 |
|---|---|---|
| 回测引擎 | 单股票回测（均线/网格/动量）| ✅ |
| 收益曲线 | 策略收益% vs 基准（可缩放）| ✅ |
| 策略模板 | 4 种（均线/网格/动量/成长因子）| ✅ |
| 策略自动执行 | 按规则自动买卖模拟账户 | ✅ |
| 模拟交易 | 虚拟资金 + 手动/策略并行 | ✅（策略并行已做，动态图待做）|
| **多股票回测** | 成长因子（持仓10只/换仓1只）| 📋 计划（engine_multi.py）|
| **绩效指标** | 年化/夏普/回撤/胜率/阿尔法/贝塔 | 📋 计划（metrics.py）|

## 八、工程化

| 技术 | 用途 | 状态 |
|---|---|---|
| Docker Compose | Milvus 部署（etcd+minio+milvus）| ✅ |
| Docker | PostgreSQL（待启动）| ⏳ |
| Git/GitHub | 版本管理 + 私有仓库 | ✅ |
| 虚拟环境 .venv | 依赖隔离 | ✅ |
| pyproject.toml | 依赖管理 | ✅ |
| **SSE 流式** | 动态流式输出/图表 | 📋 计划 |

## 九、实现进度总结

```
✅ 已完成：AI Agent + RAG + 数据多源 + 前端 + 模拟交易 + 回测 + 策略联动 + GitHub
⏳ 进行中：JWT 认证、PostgreSQL、LangGraph Checkpointer
📋 计划中：LlamaIndex、多股票回测、绩效指标、README、SSE 动态图表
```

## 十、简历亮点（面试话术）

> FinAgent 量化投研平台：基于 **LangGraph 多智能体编排**（Supervisor 路由 5 个子 Agent：RAG 问答带引用溯源、行情、新闻、K线、简报），**Milvus 向量库 + DashScope embedding** 企业级 RAG，**AkShare 多数据源**容错，**回测引擎 + 基准对比**，**JWT + bcrypt** 认证，**模拟交易**（手动+策略自动），FastAPI + ECharts 前后端分离，计划引入 **LlamaIndex 增强 RAG** 与 **PostgreSQL 持久化**。
