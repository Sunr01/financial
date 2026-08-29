"""FinAgent Web 服务：FastAPI 接口（聊天/数据/策略/交易）。"""

import json
from pathlib import Path
from fastapi import FastAPI, Depends
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from finagent.agents.supervisor import build_graph
from finagent.agents.tools import (
    get_realtime_quote,
    get_kline_data,
    get_kline_df,
    get_financial_indicators,
    search_news,
)
from finagent.trading.account import Account
from finagent.auth.routes import router as auth_router
from finagent.auth.db import init_db
from finagent.auth.routes import get_current_user
from finagent import data_store

app = FastAPI(title="FinAgent")

# 初始化数据库 + 挂载认证路由
init_db()
app.include_router(auth_router)

# 用 PostgreSQL Checkpointer 编译图（同步版，节点内流式方案用 invoke）
from finagent.agents.checkpointer import get_checkpointer

try:
    graph = build_graph(checkpointer=get_checkpointer())  # 同步初始化，Windows 兼容
except Exception as e:
    print(f"Checkpointer 初始化失败，使用无持久化版本: {e}")
    graph = build_graph()

# ---------- 按用户隔离的状态 ----------
# 内存中的账户缓存（username -> Account），持久化到 PG
_accounts_cache: dict[str, Account] = {}
_running: dict[str, bool] = {}  # 用户名 -> 策略运行状态


def get_user_account(username: str) -> Account:
    """获取用户账户（从缓存或 PG 加载）。"""
    if username not in _accounts_cache:
        data = data_store.get_account_data(username)
        if data and "account" in data:
            acc = Account()
            acc.cash = data["account"].get("cash", 1_000_000.0)
            acc.positions = data["account"].get("positions", {})
            _accounts_cache[username] = acc
        else:
            _accounts_cache[username] = Account()
    return _accounts_cache[username]


def save_user_account(username: str) -> None:
    """持久化用户账户到 PG。"""
    acc = _accounts_cache.get(username)
    if acc:
        data_store.save_account_data(username, {
            "account": {"cash": acc.cash, "positions": acc.positions},
        })


def get_user_current_strategy(username: str) -> dict:
    """获取用户当前策略。"""
    return data_store.get_current_strategy(username)


def set_user_current_strategy(username: str, strategy: dict) -> None:
    """设置用户当前策略。"""
    data_store.set_current_strategy(username, strategy)


class OrderRequest(BaseModel):
    symbol: str
    side: str
    qty: int


class StrategyRequest(BaseModel):
    name: str
    symbol: str
    capital: str
    code: str


# ---------- 聊天 ----------
class ChatRequest(BaseModel):
    question: str
    thread_id: str = "default"  # 会话 ID（区分不同对话，持久化用）
    messages: list = []         # 最近 7 轮对话上下文（前端传）

FINANCE_INTENTS = {"market", "news", "k_chart", "report", "rag"}
CHITCHAT_LIMIT = 5  # 单次闲聊会话最多连续 5 轮
_chitchat_counts: dict = {}  # 用户+会话 -> 连续闲聊轮数


async def _need_tool(llm, question: str) -> bool:
    """用 LLM 判断问题是否需要工具（天气/地图等）。"""
    try:
        resp = await llm.ainvoke([
            {"role": "system", "content": "判断用户问题是否需要查询外部工具（如天气、地图、位置）。"
                                          "只需回答：是 或 否"},
            {"role": "user", "content": question},
        ])
        return "是" in (resp.content or "")
    except Exception:
        return False


def _quick_intent(question: str) -> str:
    """快速意图判断（关键词，毫秒级，不走 LLM）。返回 market/news/k_chart/report/rag/chitchat。"""
    q = question
    if "股价" in q or "行情" in q or "价格" in q:
        return "market"
    if "新闻" in q or "消息" in q:
        return "news"
    if "图" in q or "k线" in q.lower():
        return "k_chart"
    if "简报" in q or "报告" in q:
        return "report"
    if "营收" in q or "净利" in q or "财报" in q or "业绩" in q or "多少" in q:
        return "rag"
    return "chitchat"  # 默认闲聊


@app.post("/chat")
async def chat(req: ChatRequest, user: str = Depends(get_current_user)):
    """流式聊天：金融问题走 Agent 图（LLM 部分逐字流式），闲聊走 MCP 流式。
    规则：单次闲聊会话连续超过 5 轮则不再回答闲聊；闲聊中遇金融问题重置计数。"""
    from fastapi.responses import StreamingResponse
    from langchain_deepseek import ChatDeepSeek
    from finagent.config import settings

    # 快速意图判断（关键词，毫秒级，不走 LLM）
    quick = _quick_intent(req.question)
    is_finance = quick in FINANCE_INTENTS

    # 闲聊计数控制（按 用户+会话）
    key = f"{user}:{req.thread_id}"
    if is_finance:
        _chitchat_counts[key] = 0  # 金融问题重置闲聊计数
    else:
        _chitchat_counts[key] = _chitchat_counts.get(key, 0) + 1

    config = {"configurable": {"thread_id": req.thread_id}}

    async def empty_gen():
        """闲聊超限：返回固定话术（引导用金融功能）。"""
        yield "data: 我是金融助手，我可以帮你解决金融类问题。\n\n"
        yield "data: [DONE]\n\n"

    async def agent_event_gen():
        """金融问题：后台线程跑图（持久化）+ 节点流式 token 逐字输出。"""
        import threading
        from finagent.agents.stream_handler import TokenStreamHandler
        from finagent.agents import supervisor as sup

        handler = TokenStreamHandler()
        sup._current_stream_handler = handler  # 全局 handler（线程内传递）
        # 把快速意图传给图（supervisor 不再调 LLM）
        config_with_intent = {"configurable": {**config["configurable"],
                                               "quick_intent": quick}}

        def run_graph():
            try:
                graph.invoke({"question": req.question}, config=config_with_intent)
            except Exception as e:
                handler.q.put(f"\n[ERROR] {type(e).__name__}: {e}")
            finally:
                sup._current_stream_handler = None  # 清除
                handler.q.put(None)

        t = threading.Thread(target=run_graph, daemon=True)
        t.start()

        # 读队列 → 逐字 yield（带超时防卡死）
        import queue as _queue
        try:
            while True:
                try:
                    item = handler.q.get(timeout=60)
                except _queue.Empty:
                    yield "data: [DONE]\n\n"
                    return
                if item is None:
                    break
                yield f"data: {item}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: [ERROR] {type(e).__name__}: {e}\n\n"

    async def chat_event_gen():
        """闲聊：先判断是否需要工具（天气/地图），需要才走 MCP，否则直接流式。"""
        llm = ChatDeepSeek(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
        )
        messages = [{"role": "user", "content": req.question}]
        try:
            # 第一步：LLM 判断是否需要工具
            need_tool = await _need_tool(llm, req.question)
            if need_tool:
                # 需要工具 → 走 MCP 调用
                from finagent.agents.mcp_tools import load_mcp_tools
                mcp_tools = await load_mcp_tools()
                llm_with_tools = llm.bind_tools(mcp_tools)
                for _ in range(3):
                    ai_msg = await llm_with_tools.ainvoke(messages)
                    if ai_msg.tool_calls:
                        messages.append({"role": "assistant", "content": ai_msg.content or "",
                                         "tool_calls": ai_msg.tool_calls})
                        for call in ai_msg.tool_calls:
                            tool = next((t for t in mcp_tools if t.name == call["name"]), None)
                            if tool:
                                result = await tool.ainvoke(call["args"])
                                messages.append({"role": "tool", "tool_call_id": call["id"],
                                                 "content": str(result)})
                        continue
                    break
            # 第二步：直接流式回答（带工具结果上下文）
            async for chunk in llm.astream(messages):
                c = chunk.content
                if c:
                    yield f"data: {c}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: [ERROR] {type(e).__name__}: {e}\n\n"

    # 闲聊超限 → 空流（不回答）；金融 → Agent 图；闲聊 → MCP
    if not is_finance and _chitchat_counts.get(key, 0) > CHITCHAT_LIMIT:
        return StreamingResponse(empty_gen(), media_type="text/event-stream")
    return StreamingResponse(agent_event_gen() if is_finance else chat_event_gen(),
                             media_type="text/event-stream")


# ---------- 会话管理 ----------
class ConversationRequest(BaseModel):
    thread_id: str


class MessageRequest(BaseModel):
    thread_id: str
    role: str
    content: str


@app.get("/api/conversations")
def list_conversations(user: str = Depends(get_current_user)) -> list:
    """用户会话列表。"""
    return data_store.list_conversations(user)


@app.post("/api/conversations")
def create_conversation(req: ConversationRequest, user: str = Depends(get_current_user)) -> dict:
    """新建会话。"""
    data_store.create_conversation(user, req.thread_id)
    return {"thread_id": req.thread_id}


@app.get("/api/conversations/messages")
def get_conversation_messages(thread_id: str, user: str = Depends(get_current_user)) -> dict:
    """获取会话消息。"""
    conv = data_store.get_conversation(user, thread_id)
    if not conv:
        return {"messages": []}
    return {"messages": conv["messages"] or [], "title": conv["title"]}


@app.post("/api/conversations/messages")
def append_conversation_message(req: MessageRequest, user: str = Depends(get_current_user)) -> dict:
    """追加消息到会话。"""
    data_store.append_message(user, req.thread_id, req.role, req.content)
    return {"status": "ok"}


class RenameRequest(BaseModel):
    thread_id: str
    title: str


@app.post("/api/conversations/rename")
def rename_conversation(req: RenameRequest, user: str = Depends(get_current_user)) -> dict:
    """重命名会话。"""
    data_store.rename_conversation(user, req.thread_id, req.title)
    return {"status": "ok"}


@app.delete("/api/conversations/{thread_id}")
def delete_conversation(thread_id: str, user: str = Depends(get_current_user)) -> dict:
    """删除会话。"""
    data_store.delete_conversation(user, thread_id)
    return {"status": "ok"}


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# ---------- 数据平台 ----------
@app.get("/api/quote")
def api_quote(symbol: str, user: str = Depends(get_current_user)) -> dict:
    """实时行情（结构化返回给前端）。"""
    text = get_realtime_quote(symbol)
    # 从文本解析出结构化字段（名称/价格/涨跌幅）
    parts = text.split()
    return {"name": parts[0], "symbol": symbol, "price": parts[2],
            "change_pct": parts[4].replace("，", "").replace("%", "")}


@app.get("/api/kline")
def api_kline(symbol: str, days: int = 120, user: str = Depends(get_current_user)) -> dict:
    """K线数据（JSON），前端用 ECharts 动态绘制。"""
    df = get_kline_df(symbol, days)
    return {
        "symbol": symbol,
        "dates": df["date"].astype(str).tolist(),
        "kline": [
            [o, c, l, h]  # ECharts 顺序：开、收、低、高
            for o, c, l, h in zip(df["open"], df["close"], df["low"], df["high"])
        ],
        "volumes": df["volume"].tolist(),
    }


@app.get("/api/news")
def api_news(symbol: str, user: str = Depends(get_current_user)) -> dict:
    """新闻列表。"""
    return {"news": search_news(symbol).split("\n")}


# ---------- 回测 ----------
@app.get("/api/backtest")
def api_backtest(symbol: str, days: int = 250, benchmark: str = "sh000300",
                 rule_desc: str = "", window: int = 20,
                 user: str = Depends(get_current_user)) -> dict:
    """跑回测，返回策略收益曲线 + 基准收益曲线 + 完整指标 + 交易记录。"""
    rule = {"description": rule_desc or "价格上穿20日均线时买入，下穿20日均线时卖出",
            "window": window}
    from finagent.backtest.engine import run_backtest, calc_returns, get_benchmark
    from finagent.backtest.metrics import (
        calc_relative_return, calc_max_drawdown, calc_annualized_return,
        calc_volatility, calc_sharpe, calc_trade_stats,
    )
    result = run_backtest(symbol, rule, days)
    dates = [n["date"] for n in result["nav"]]
    navs = [n["nav"] for n in result["nav"]]
    returns = calc_returns(navs)
    bench = get_benchmark(dates, benchmark)
    # 日收益率（用于波动率/夏普）
    daily_rets = []
    for i in range(1, len(navs)):
        daily_rets.append((navs[i] - navs[i - 1]) / navs[i - 1])
    total_return = returns[-1] if returns else 0
    return {
        "symbol": symbol,
        "dates": dates,
        "strategy_returns": returns,
        "benchmark_returns": bench,
        "relative_return": calc_relative_return(returns, bench),
        "max_drawdown": calc_max_drawdown(result["nav"]),
        "annualized_return": calc_annualized_return(total_return, len(dates)),
        "volatility": calc_volatility(daily_rets),
        "sharpe": calc_sharpe(daily_rets),
        "trade_stats": calc_trade_stats(result["trades"]),
        "trades": result["trades"],
        "final_value": result["final_value"],
    }


@app.get("/api/backtest/multi")
def api_backtest_multi(stocks: str = "600519,300750,600036,000858,600887",
                       hold_num: int = 3, days: int = 120,
                       benchmark: str = "sh000300",
                       factor: str = "momentum",
                       user: str = Depends(get_current_user)) -> dict:
    """多股票回测。stocks 为逗号分隔代码，factor 为因子（momentum/growth/volatility）。"""
    from finagent.backtest.engine_multi import run_multi_backtest
    from finagent.backtest.engine import calc_returns, get_benchmark
    from finagent.backtest.metrics import (
        calc_relative_return, calc_max_drawdown, calc_annualized_return,
        calc_volatility, calc_sharpe, calc_trade_stats,
    )
    stock_list = [s.strip() for s in stocks.split(",") if s.strip()]
    result = run_multi_backtest(stock_list, hold_num=hold_num, days=days, factor=factor)
    dates = [str(n["date"]) for n in result["nav"]]
    navs = [n["nav"] for n in result["nav"]]
    returns = calc_returns(navs)
    bench = get_benchmark(dates, benchmark)
    daily_rets = []
    for i in range(1, len(navs)):
        daily_rets.append((navs[i] - navs[i - 1]) / navs[i - 1])
    return {
        "symbol": stocks,
        "dates": dates,
        "strategy_returns": returns,
        "benchmark_returns": bench,
        "relative_return": calc_relative_return(returns, bench),
        "max_drawdown": calc_max_drawdown(result["nav"]),
        "annualized_return": calc_annualized_return(returns[-1] if returns else 0, len(dates)),
        "volatility": calc_volatility(daily_rets),
        "sharpe": calc_sharpe(daily_rets),
        "trade_stats": calc_trade_stats(result["trades"]),
        "trades": result["trades"],
        "final_value": result["final_value"],
    }


# ---------- 策略 ----------
@app.get("/api/strategy/current")
def get_current_strategy(user: str = Depends(get_current_user)) -> dict:
    """获取当前策略（按用户）。"""
    return get_user_current_strategy(user)


@app.post("/api/strategy/current")
def set_current_strategy(req: StrategyRequest, user: str = Depends(get_current_user)) -> dict:
    """设置当前策略（按用户）。"""
    strategy = {"name": req.name, "symbol": req.symbol, "description": req.code}
    set_user_current_strategy(user, strategy)
    return strategy


@app.get("/api/strategy/templates")
def list_templates(user: str = Depends(get_current_user)) -> list:
    """策略模板列表（前端下拉选择用）。"""
    from finagent.strategy.templates import TEMPLATES
    return TEMPLATES


@app.post("/api/strategy")
def save_strategy(req: StrategyRequest, user: str = Depends(get_current_user)) -> dict:
    """保存策略：用 LLM 把中文策略描述转成结构化规则（按用户）。"""
    from finagent.agents.strategy_parser import parse_strategy
    try:
        rule = parse_strategy(req.code).model_dump()
    except Exception as e:
        return {"error": f"策略解析失败：{e}"}
    data_store.save_strategy(user, {**req.model_dump(), "rule": rule})
    return {"status": "saved", "rule": rule}


@app.get("/api/strategy")
def list_strategies(user: str = Depends(get_current_user)) -> list:
    """获取用户策略列表。"""
    return data_store.list_strategies(user)


# ---------- 我的交易 ----------
@app.get("/api/account")
def get_account(user: str = Depends(get_current_user)) -> dict:
    acc = get_user_account(user)
    return {"cash": acc.cash, "position_value": acc.position_value,
            "total": acc.total, "pnl": acc.pnl}


@app.get("/api/positions")
def get_positions(user: str = Depends(get_current_user)) -> list:
    acc = get_user_account(user)
    return [
        {"symbol": p.symbol, "name": p.name, "qty": p.qty,
         "cost": round(p.cost, 2), "price": p.price,
         "pnl": round((p.price - p.cost) * p.qty, 2)}
        for p in acc.positions.values()
    ]


@app.post("/api/order")
def place_order(req: OrderRequest, user: str = Depends(get_current_user)) -> dict:
    """下单：买入/卖出。价格用实时行情（简化：从文本取价格）。"""
    acc = get_user_account(user)
    text = get_realtime_quote(req.symbol)
    parts = text.split()
    name, price = parts[0], float(parts[2])
    if req.side == "buy":
        msg = acc.buy(req.symbol, name, req.qty, price)
    else:
        msg = acc.sell(req.symbol, req.qty, price)
    save_user_account(user)
    return {"message": msg, "price": price}


# ---------- 策略自动执行 ----------

@app.get("/api/strategy/status")
def strategy_status(user: str = Depends(get_current_user)) -> dict:
    """策略运行状态（按用户）。"""
    cur = get_user_current_strategy(user)
    return {"running": _running.get(user, False),
            "strategy": cur.get("name", ""),
            "symbol": cur.get("symbol", "")}


@app.post("/api/strategy/start")
def strategy_start(user: str = Depends(get_current_user)) -> dict:
    """启动策略自动执行（前端轮询）。"""
    cur = get_user_current_strategy(user)
    if not cur.get("name"):
        return {"error": "尚未设置策略"}
    _running[user] = True
    return {"running": True}


@app.post("/api/strategy/stop")
def strategy_stop(user: str = Depends(get_current_user)) -> dict:
    """停止策略自动执行。"""
    _running[user] = False
    return {"running": False}


@app.get("/api/strategy/execute")
def strategy_execute(user: str = Depends(get_current_user)) -> dict:
    """执行一次策略检查（前端轮询调用，按用户）。"""
    from finagent.trading.strategy_runner import run_strategy
    if not _running.get(user, False):
        return {"message": "策略未运行", "ran": False}
    cur = get_user_current_strategy(user)
    symbol = cur.get("symbol", "600519")
    rule = {"description": cur.get("description", ""), "window": 20}
    acc = get_user_account(user)
    msg = run_strategy(acc, symbol, rule)
    save_user_account(user)
    return {"message": msg, "ran": True, "account": {
        "cash": acc.cash, "total": acc.total, "pnl": acc.pnl}}


# ---------- 静态文件 ----------
# 注意：先挂载 /output（K线图片），再挂载 /（前端页面），避免 "/" 吞掉其他路由
OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)  # 确保目录存在
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")

STATIC_DIR = Path(__file__).resolve().parent.parent.parent.parent / "frontend"
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("finagent.api.server:app", host="127.0.0.1", port=9996, reload=True)
