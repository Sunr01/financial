# FinAgent 阶段 2 开发笔记（多智能体）

> 记录阶段 2（LangGraph 多智能体编排）遇到的关键问题与讨论结论。

## 1. 已解决的错误

### 错误 1：LangGraph 路由不生效（route 字段缺失）

- **现象**：问"茅台今天股价多少"（应走 market）却走了 rag 分支，两行输出都是 `[RAG]`。
- **原因**：`AgentState`（TypedDict）里没有声明 `route` 字段。LangGraph 默认只接受状态里声明过的字段，`supervisor_node` 返回的 `{"route": route}` 被丢弃，路由函数 `state.get("route", "rag")` 永远读到默认值 `"rag"`。
- **解决**：在 `AgentState` 里加 `route: str` 字段。
- **教训**：**LangGraph 的状态字段必须先在 TypedDict 里声明**，节点返回未声明字段会被静默丢弃。

### 错误 2：DeepSeek 思考模式不支持 tool_choice（with_structured_output 报错）

- **现象**：用 `with_structured_output(Intent)` 提取意图时报 400：`Thinking mode does not support this tool_choice`。
- **原因**：`deepseek-v4-flash` 开启思考模式时，不支持 `with_structured_output` 依赖的 function calling（tool_choice）。
- **解决**：给 `ChatDeepSeek` 加 `extra_body={"thinking": {"type": "disabled"}}` 关闭思考模式。
- **教训**：**模型思考模式与结构化输出/工具调用有兼容限制**；遇到此类错误先考虑关闭 thinking 或改用提示词+JSON解析。

### 错误 3：东财行情接口持续不稳定（时通时断）

- **现象**：`stock_zh_a_spot_em` / 直接 requests 请求 `82.push2.eastmoney.com` 报 `RemoteDisconnected`（连接被断开）；首次请求成功，后续全部失败，持续一天未恢复。
- **排查过程**：百度/东财主站通（200）→ 基础网络正常；代理已关、防火墙没开、hosts 干净、DNS 正常（ping 通）；带 headers 被断、不带也断。
- **结论**：网络环境对东财行情 API 不稳定（疑似风控/限流）。
- **解决**：**换数据源**（验证后全部改用稳定源）：
  - 实时行情 → 新浪 `stock_zh_a_spot`（代码带前缀 sh/sz/bj）
  - K线 → 腾讯 `stock_zh_a_hist_tx`（代码带前缀，英文列名 close/high/low）
  - 财务 → 东财 `stock_financial_abstract`（可用，不带前缀）
  - 新闻 → 东财 `stock_news_em`（可用，不带前缀）
- **教训**：**外部数据源不可靠时要有备选方案**；工具层封装（`tools.py`）让换源只改内部，上层无感（低耦合价值体现）。

### 错误 4：新浪/腾讯行情需代码前缀（StopIteration 找不到股票）

- **现象**：改新浪源后报 `StopIteration`——请求成功但匹配不到 `600519`。
- **原因**：新浪/腾讯的代码格式是带前缀的 `sh600519`/`sz000001`，而东财是不带前缀的 `600519`。
- **解决**：加 `_with_prefix()` 辅助函数（6开头→sh，其他→sz），匹配时转前缀。
- **教训**：**不同数据源的代码格式不同**，切换数据源时要注意字段名和代码格式差异。

## 2. 数据源方案（最终确定）

| 工具 | 数据源 | 代码格式 |
|---|---|---|
| 实时行情 | 新浪 `stock_zh_a_spot` | 带前缀（sh600519）|
| K线 | 腾讯 `stock_zh_a_hist_tx` | 带前缀（sh600519）|
| 财务 | 东财 `stock_financial_abstract` | 不带前缀（600519）|
| 新闻 | 东财 `stock_news_em` | 不带前缀（600519）|

- 所有工具带 `_retry` 重试容错（失败等 1 秒重试，最多 2 次）。

## 3. 用户提出的设计问题（讨论结论）

### 问题 1：Agent 改名
- **结论**：Chart Agent → **K_Chart Agent**（为以后其他图表 Agent 留区分）。

### 问题 2：金融数据源有哪些替代
- **结论**：AkShare（免费/在用）、Tushare、baostock、Wind/同花顺（商业）、交易所接口、本地数据。详见 `02-data-sources.md`。

### 问题 3：改 API 方式，已写的代码会大改吗？
- **结论**：**不会**。数据获取封装在 `agents/tools.py`，Agent/Supervisor/RAG 只调用函数、不碰 API。换源只改内部实现，函数签名不变，上层无感。

### 问题 4：后续想加的"模拟交易台"需求
- **内容**：虚拟资金 + 手动/策略并行交易 + 动态流式图表（SSE + ECharts）。
- **结论**：记录待办，排在阶段 2 之后（依赖 K 线 + SSE 基础）。

### 问题 5：`[RAG]`/`[行情]` 标签是什么
- **结论**：代码里临时加的"调试标签"，用于验证路由；接入真实功能后自动消失。

### 问题 6：路由用关键词还是 LLM 提取？
- **结论**：用 **LLM 提取**（`intent.py` + `with_structured_output`），Supervisor 真正理解意图而非匹配关键词。

### 问题 7：LlamaIndex 局部引入
- **结论**：主线 LangChain；阶段 2 后在 `rag/` 内部引入 LlamaIndex（增量索引/查询引擎/元数据过滤），接口不变。详见架构文档 6.4 节。

## 4. 阶段 2 进度（完成）

| 步骤 | 状态 |
|---|---|
| 工具层 `tools.py`（多源 + 重试）| ✅ |
| Supervisor（LLM 意图提取 + 路由）| ✅ |
| RAG Agent（Milvus 检索 + 引用溯源）| ✅ |
| Market Agent（新浪实时行情）| ✅ |
| News Agent（东财新闻）| ✅ |
| K_Chart Agent（mplfinance 图表，模拟数据）| ✅（真实K线待接）|
| Report Agent（LLM 投研简报）| ✅ |
| 端到端演示（5 类问题）| ✅ 全部真实响应 |

**待办**：K_Chart 接真实 K 线（`tools.get_kline_data` 已可用）；模拟交易台（阶段 2 之后）。

## 5. 知识点：K线数据格式转换（pandas → ECharts）

**场景**：后端把 K 线数据返回给前端 ECharts 动态绘制，需要把 pandas 表格转成 ECharts 格式。

**代码**：
```python
"kline": [
    [o, c, l, h]  # ECharts 顺序：开、收、低、高
    for o, c, l, h in zip(df["open"], df["close"], df["low"], df["high"])
],
"volumes": df["volume"].tolist()
```

**讲解**：
- `zip(A, B, C, D)` = 把 4 列按行对齐（拉链），每次取出同一行的 4 个值。
- `[o, c, l, h] for ... in zip(...)` = 列表推导式，把每行的 4 个值装进数组。
- **顺序必须是 `[开, 收, 低, 高]`**（ECharts K线固定要求），不是开收高低。
- `.tolist()` = 把 pandas 列（Series）转成 Python 普通列表。

**格式对比**：
| 数据 | 格式 |
|---|---|
| pandas 表格 | 每行一天：date/open/close/high/low/volume 各一列 |
| ECharts 需要 | `kline`: [[开,收,低,高], ...]；`volumes`: [成交量, ...] |
