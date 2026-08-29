# FinAgent 流式输出实现与排查记录

> 记录 AI 聊天"逐字流式 + 会话持久化共存"的实现过程与踩坑。

## 1. 需求
- 金融问题走 Agent 图，**LLM 文本逐字流式**输出
- 保留 **Checkpointer 会话持久化**（追问记忆、重启不忘）

## 2. 踩坑过程

### 坑 1：stream_mode="messages" 与同步 PostgresSaver 不兼容
- 现象：`NotImplementedError`（checkpoint/base aget_tuple）
- 原因：同步 `PostgresSaver` 不支持异步 `aget_tuple`
- 试过：换 AsyncPostgresSaver → 异步连接池 Windows 上 `PoolTimeout`（ProactorEventLoop 不支持 psycopg 异步）

### 坑 2：AsyncConnectionPool 在 Windows 超时
- 现象：`PoolTimeout: pool initialization incomplete after 30 sec`
- 原因：Windows 的 ProactorEventLoop 与 psycopg 异步池不兼容（需 SelectorEventLoop）
- 解决：**回同步版**（ConnectionPool + PostgresSaver）

### 坑 3：config 传对象被 LangGraph 过滤
- 现象：把流式 handler 塞 config 传节点，节点读不到
- 原因：LangGraph 对 config 序列化/过滤，对象丢失
- 解决：**模块级全局变量**传递 handler

### 坑 4：supervisor_node 的 LLM 意图提取阻塞
- 现象：图执行卡在 supervisor（LLM 调用），rag_node 没执行
- 解决：server 用**关键词快速判断**（`_quick_intent`）→ config 传给 supervisor → 不再调 LLM

## 3. 最终方案（节点内流式）
```
[后台线程] graph.invoke（同步 + 同步 PostgresSaver → 持久化 ✅）
  → rag_node 检测全局 handler → answer_stream
  → LLM.stream() 逐 token → 回调 → 队列
[SSE 生成器] 读队列 → 逐字 yield
```
- `agents/stream_handler.py`：TokenStreamHandler（on_llm_new_token 写队列）
- `rag/query.py`：answer_stream（流式版，保留原 answer）
- `supervisor.py`：rag_node 支持全局 handler；supervisor 用快速意图
- `server.py`：后台线程 invoke + 队列读流 + 超时保护

## 4. 加速优化
- `_quick_intent(question)`：关键词判断意图（毫秒级，不走 LLM）
- 意图判断从"LLM 2 次"减到"关键词 1 次"

## 5. 经验
- **LangGraph 流式模式 vs Checkpointer 有兼容限制**（messages 模式要 AsyncSaver）
- **Windows 上 psycopg 异步池不靠谱**，用同步版
- **config 只传可序列化数据**，对象用全局/其他方式传
- **SSE 生成器读队列要加超时**（防卡死）
