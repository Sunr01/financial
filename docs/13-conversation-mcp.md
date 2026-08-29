# FinAgent 会话管理与 MCP 工具笔记

> 记录会话管理（列表/保存/重命名/删除）与 MCP 外部工具接入。

## 1. 会话管理（PostgreSQL）

### 数据表（conversations）
```sql
CREATE TABLE conversations (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    thread_id VARCHAR(100) NOT NULL,
    title VARCHAR(200) DEFAULT '新对话',
    messages JSONB DEFAULT '[]',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(username, thread_id)
);
```

### 接口
| 接口 | 功能 |
|---|---|
| GET /api/conversations | 会话列表（按更新时间倒序）|
| POST /api/conversations | 新建会话 |
| GET /api/conversations/messages?thread_id= | 加载会话消息 |
| POST /api/conversations/messages | 追加消息 |
| POST /api/conversations/rename | 重命名 |
| DELETE /api/conversations/{thread_id} | 删除 |

### 前端功能
- 会话侧栏（可隐藏，☰ 按钮）
- 新建对话 / 点击加载 / ✎ 重命名 / 🗑 删除
- 默认加载最近一次会话
- 标题 = 第一条用户消息前 20 字（可重命名）
- 输入框在聊天卡片底部

## 2. MCP 工具（天气/地图）

### 什么是 MCP
Model Context Protocol：连接外部工具的**行业标准协议**（Anthropic 提出）。
企业级做法：不自己写 HTTP 请求，用 MCP 服务器统一接入。

### 配置（agents/mcp_tools.py）
```python
MCP_CONFIG = {
    "amap-maps": {"transport": "streamable_http",
                  "url": "https://mcp.api-inference.modelscope.net/cfb9f78209ce46/mcp"},
    "XingYuWeather": {"transport": "streamable_http",
                      "url": "https://mcp.api-inference.modelscope.net/6c52f04c9aee49/mcp"},
}
async def load_mcp_tools():
    client = MultiServerMCPClient(MCP_CONFIG)
    return await client.get_tools()
```

### 工具
- 天气：`predict`（传 city 获取近3天天气）
- 地图（高德）：8 个工具（关键词搜索/路径规划/距离测量等）

### 调用流程（意图识别后再走 MCP）
```
用户问"北京天气" → _quick_intent 判断（关键词）
  → 闲聊分支 → _need_tool（LLM 判断是否需工具）
  → 需要 → load_mcp_tools → bind_tools → 工具调用循环 → 结果给 LLM
  → 不需要 → 直接 llm.astream 流式回答
```

## 3. 闲聊限制规则
- 单次闲聊会话连续 >5 轮 → 返回固定话术"我是金融助手，我可以帮你解决金融类问题"
- 闲聊中遇金融问题 → 重置计数
- 实现：服务端 `_chitchat_counts[用户:会话]`

## 4. 经验
- MCP 是标准做法（面试可讲），但依赖网络（modelscope 服务器）
- 工具调用要"意图识别后才加载"（省资源、避免组合问题）
- 会话用 PostgreSQL 存储（企业级，用户隔离）
