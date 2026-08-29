# FinAgent 重要问答（一）：聊天与流式

> 近期关于聊天、流式、Agent 的重要问答，面试可讲。

## 1. 为什么"会话持久化"和"逐字流式"会冲突？

- **问**：LangGraph 里持久化和流式不能共存吗？
- **答**：`stream_mode="messages"`（token 级流式）要求 **AsyncPostgresSaver**；而 Windows 上 psycopg 异步池不稳定（ProactorEventLoop 不支持）。**同步 PostgresSaver 只支持节点级流式**。
- **解决**：**节点内流式**——图用同步 invoke（持久化 OK），节点内 LLM 用 `stream()` + 回调把 token 推队列，SSE 逐字读。持久化和流式都保留。

## 2. LangGraph 的 stream_mode 有哪几种？

| 模式 | 粒度 | 兼容性 |
|---|---|---|
| `updates` | 节点级（每节点完成给一次）| 所有 checkpointer |
| `messages` | token 级（逐字）| 需 AsyncPostgresSaver |

## 3. 为什么 config 传对象（handler）会丢失？

- LangGraph 对 config 会**序列化/过滤**，非可序列化对象（如队列）会丢。
- **解决**：用**模块级全局变量**传对象（线程内设置、节点读取）。

## 4. 意图判断为什么要"关键词"而不是 LLM？

- LLM 判断意图要**一次 API 调用**（几秒），且可能阻塞。
- **关键词判断毫秒级**：`_quick_intent` 用"股价/行情/新闻/营收..."等词，够用且快。
- 金融问题进图后 supervisor 直接用快速意图（**避免重复 LLM 调用**）。

## 5. SSE 流式前端怎么读？

- `fetch("/chat")` + `resp.body.getReader()` 逐块读
- 解析 `data: 内容` 行 → 累积显示（逐字效果）
- `[DONE]` 结束；`[ERROR] 类型: 消息` 错误

## 6. 工具调用为什么要"意图识别后才加载 MCP"？

- 每次聊天都加载 MCP（13 个工具）+ bind_tools 浪费且可能组合出错。
- 先 LLM 判断"是否需要工具"（`_need_tool`）→ 需要才加载调用，不需要直接流式。
- 面试话术："按需加载工具，避免资源浪费和组合问题"。

## 7. 闲聊超 5 轮限制怎么实现？

- 服务端 `_chitchat_counts[用户:会话]` 计数
- 金融问题重置、闲聊 +1；>5 返回固定话术
- "闲聊中遇金融问题重新计数"（用户规则）
