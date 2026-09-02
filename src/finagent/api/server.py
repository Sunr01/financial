"""FinAgent Web 服务：FastAPI 接口（聊天/数据/策略/交易）。"""

import json
import re
import sys
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
try:
    init_db()
except Exception as e:
    print(f"[启动失败] 无法连接 PostgreSQL：{type(e).__name__}: {e}", file=sys.stderr)
    print("请先启动 PostgreSQL 再运行，例如：", file=sys.stderr)
    print("    docker compose up -d postgres", file=sys.stderr)
    print("或检查 .env 中的 DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD 配置。", file=sys.stderr)
    raise SystemExit(1) from e
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
# 注意:策略运行状态已持久化到 PG(data_store.set_strategy_running),
#       不再使用内存 _running(容器重启后自动恢复)。
_accounts_cache: dict[str, Account] = {}


def get_user_account(username: str) -> Account:
    """获取用户账户（从缓存或 PG 加载）。"""
    if username not in _accounts_cache:
        data = data_store.get_account_data(username)
        if data and "account" in data:
            _accounts_cache[username] = Account.from_dict(data["account"])
        else:
            _accounts_cache[username] = Account()
    return _accounts_cache[username]


def save_user_account(username: str) -> None:
    """持久化用户账户到 PG（合并保存，避免覆盖 current_strategy/strategy_running）。"""
    acc = _accounts_cache.get(username)
    if acc:
        data = data_store.get_account_data(username) or {}
        data["account"] = acc.to_dict()
        data_store.save_account_data(username, data)


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

FINANCE_INTENTS = {"market", "news", "k_chart", "report", "rag", "strategy", "stock"}
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


def load_mcp_tools_sync(async_fn) -> list:
    """在无事件循环的线程里同步调用 async 的 load_mcp_tools。"""
    import asyncio
    try:
        return asyncio.run(async_fn())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(async_fn())
        finally:
            loop.close()


def _quick_intent(question: str) -> str:
    """快速意图判断（关键词，毫秒级，不走 LLM）。
    返回 market/news/k_chart/report/rag/strategy/stock/chitchat。"""
    q = question
    # 6 位股票代码（兼容 sh600519/sz000001/bj430047/600519.SH 写法）
    has_code = bool(re.search(r"(?<!\d)(?:sh|sz|bj)?\d{6}(?!\d)", q.lower()))
    # ① 提到"策略" → 策略讲解（功能+使用方法）
    if "策略" in q:
        return "strategy"
    # ② 带股票代码 → 优先具体意图，裸代码/查询类 → 股票内容总览
    if has_code:
        if "新闻" in q or "消息" in q:
            return "news"
        if "图" in q or "k线" in q.lower():
            return "k_chart"
        if "简报" in q or "报告" in q:
            return "report"
        if "股价" in q or "行情" in q or "价格" in q:
            return "market"
        if "营收" in q or "净利" in q or "财报" in q or "业绩" in q or "多少" in q:
            return "rag"
        return "stock"
    # ③ 无代码 → 原有关键词判断
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

    def _need_tool_sync(llm, question: str) -> bool:
        """同步判断是否需要外部工具（天气/地图）。"""
        try:
            resp = llm.invoke([
                {"role": "system", "content": "判断用户问题是否需要查询外部工具（如天气、地图、位置）。"
                                              "只需回答：是 或 否"},
                {"role": "user", "content": question},
            ])
            return "是" in (resp.content or "")
        except Exception:
            return False

    async def chat_event_gen():
        """闲聊：后台线程同步 LLM 流式（绕开 Python 3.14 异步 TaskGroup 兼容问题）。
        需要工具（天气/地图）时先走 MCP，否则直接流式回答。"""
        import threading
        import queue as _queue
        llm = ChatDeepSeek(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            extra_body={"thinking": {"type": "disabled"}},  # 关闭思考，保证流式正文
        )
        q: _queue.Queue = _queue.Queue()

        def run():
            messages = [{"role": "user", "content": req.question}]
            try:
                # 第一步：LLM 判断是否需要工具（同步）
                need_tool = _need_tool_sync(llm, req.question)
                if need_tool:
                    # 需要工具 → 走 MCP 调用（同步版本）
                    from finagent.agents.mcp_tools import load_mcp_tools
                    mcp_tools = load_mcp_tools_sync(load_mcp_tools)
                    llm_with_tools = llm.bind_tools(mcp_tools)
                    for _ in range(3):
                        ai_msg = llm_with_tools.invoke(messages)
                        if ai_msg.tool_calls:
                            messages.append({"role": "assistant", "content": ai_msg.content or "",
                                             "tool_calls": ai_msg.tool_calls})
                            for call in ai_msg.tool_calls:
                                tool = next((t for t in mcp_tools if t.name == call["name"]), None)
                                if tool:
                                    result = tool.invoke(call["args"])
                                    messages.append({"role": "tool", "tool_call_id": call["id"],
                                                     "content": str(result)})
                            continue
                        break
                # 第二步：直接同步流式回答（带工具结果上下文）
                for chunk in llm.stream(messages):
                    c = chunk.content
                    if c:
                        q.put(c)
            except Exception as e:
                q.put(f"\n[ERROR] {type(e).__name__}: {e}")
            finally:
                q.put(None)

        t = threading.Thread(target=run, daemon=True)
        t.start()

        # 读队列 → 逐字 yield
        try:
            while True:
                try:
                    item = q.get(timeout=60)
                except _queue.Empty:
                    yield "data: [DONE]\n\n"
                    return
                if item is None:
                    break
                yield f"data: {item}\n\n"
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


# ---------- 股市行情列表（分页）----------
_stock_snapshot = {"data": None, "ts": 0.0}
_STOCK_SNAPSHOT_TTL = 300  # 全市场快照缓存 5 分钟


def _get_stock_snapshot(refresh: bool = False):
    """全市场 A 股快照（带缓存，5 分钟）。东财源优先，失败自动降级新浪源。
    返回统一列：代码/名称/最新价/涨跌幅/换手率/成交额/总市值/市盈率-动态。"""
    import time
    now = time.time()
    if not refresh and _stock_snapshot["data"] is not None \
            and now - _stock_snapshot["ts"] < _STOCK_SNAPSHOT_TTL:
        return _stock_snapshot["data"]

    import akshare as ak
    import pandas as pd
    em_err = None
    try:
        # ① 东财全市场快照（含北交所，字段全；网络偶发断连，带重试）
        df = _retry_call(lambda: ak.stock_zh_a_spot_em())
        keep = [c for c in ["代码", "名称", "最新价", "涨跌幅", "换手率",
                            "成交额", "总市值", "市盈率-动态"] if c in df.columns]
        df = df[keep]
    except Exception as e:
        em_err = e
        try:
            # ② 新浪全市场快照兜底（无换手率/市值/市盈率，置空）
            sina = ak.stock_zh_a_spot()
            df = pd.DataFrame({
                "代码": sina["代码"].astype(str).str.replace(r"^(sh|sz|bj)", "", regex=True),
                "名称": sina["名称"],
                "最新价": sina["最新价"],
                "涨跌幅": sina["涨跌幅"],
                "换手率": [None] * len(sina),
                "成交额": sina["成交额"],
                "总市值": [None] * len(sina),
                "市盈率-动态": [None] * len(sina),
            })
        except Exception as sina_err:
            raise ConnectionError(
                f"东财源失败：{em_err}；新浪兜底也失败：{sina_err}") from sina_err

    _stock_snapshot["data"] = df
    _stock_snapshot["ts"] = now
    return df


# ---------- 行业分类 ----------
_industries_cache = {"data": None, "ts": 0.0}
_INDUSTRY_TTL = 600  # 行业列表缓存 10 分钟


def _pick_chinese_names(df) -> list:
    """从行业 DataFrame 中提取中文行业名。
    新浪行业接口有 label/板块 两列，label 可能是英文/代码名，
    只取含中文的列（保证前端分类显示为中文）。"""
    names = []
    for _, row in df.iterrows():
        picked = ""
        for col in ("label", "板块"):
            n = str(row.get(col, "")).strip()
            if n and any("\u4e00" <= c <= "\u9fff" for c in n):
                picked = n
                break
        if not picked:
            picked = str(row.get("label", "")).strip()
        if picked:
            names.append(picked)
    return names


def _get_industries(refresh: bool = False) -> list:
    """A 股行业板块名称列表（东财优先，新浪兜底）。返回中文行业名。"""
    import time
    now = time.time()
    if not refresh and _industries_cache["data"] is not None \
            and now - _industries_cache["ts"] < _INDUSTRY_TTL:
        return _industries_cache["data"]
    import akshare as ak
    try:
        df = ak.stock_board_industry_name_em()
        names = [str(n) for n in df["板块名称"].tolist()]
    except Exception as em_err:
        try:
            df = ak.stock_sector_spot(indicator="新浪行业")
            names = _pick_chinese_names(df)
        except Exception as sina_err:
            raise ConnectionError(
                f"东财行业失败：{em_err}；新浪兜底也失败：{sina_err}") from sina_err
    _industries_cache["data"] = names
    _industries_cache["ts"] = now
    return names


def _retry_call(fn, retries: int = 2):
    """带重试的调用：网络源不稳定（如东财偶发断连）时提高成功率。"""
    import time
    for i in range(retries + 1):
        try:
            return fn()
        except Exception:
            if i == retries:
                raise
            time.sleep(1)


def _get_industry_stocks(name: str):
    """某行业成分股（东财优先重试，新浪兜底），统一列：
    代码/名称/最新价/涨跌幅/换手率/成交额/总市值/市盈率-动态。"""
    import akshare as ak
    import pandas as pd
    try:
        df = _retry_call(lambda: ak.stock_board_industry_cons_em(symbol=name))
        keep = [c for c in ["代码", "名称", "最新价", "涨跌幅", "换手率",
                            "成交额", "市盈率-动态"] if c in df.columns]
        df = df[keep]
        df["总市值"] = None
    except Exception as em_err:
        try:
            # 新浪成分股：接口要求新浪内部 label（非中文名），先反查映射
            spot = ak.stock_sector_spot(indicator="新浪行业")
            label = ""
            for _, row in spot.iterrows():
                if str(row.get("板块", "")).strip() == name \
                        or str(row.get("label", "")).strip() == name:
                    label = str(row.get("label", "")).strip()
                    break
            if not label:
                raise ValueError(f"未找到行业 [{name}] 的新浪标识")
            detail = ak.stock_sector_detail(sector=label)
            df = pd.DataFrame({
                "代码": detail["symbol"].astype(str).str.replace(r"^(sh|sz|bj)", "", regex=True),
                "名称": detail["name"],
                "最新价": detail["trade"],
                "涨跌幅": detail["changepercent"],
                "换手率": detail["turnoverratio"] if "turnoverratio" in detail.columns else [None] * len(detail),
                "成交额": detail["amount"],
                "总市值": detail["mktcap"] if "mktcap" in detail.columns else [None] * len(detail),
                "市盈率-动态": detail["per"] if "per" in detail.columns else [None] * len(detail),
            })
        except Exception as sina_err:
            raise ConnectionError(
                f"东财成分失败：{em_err}；新浪兜底也失败：{sina_err}") from sina_err
    return df


@app.get("/api/stocks/industries")
def api_stock_industries(refresh: bool = False,
                         user: str = Depends(get_current_user)) -> dict:
    """行业板块列表（前端分类点击用）。"""
    try:
        return {"industries": _get_industries(refresh=refresh)}
    except Exception as e:
        return {"error": f"获取行业列表失败：{type(e).__name__}: {e}"}


@app.get("/api/stocks/industry")
def api_stock_industry(name: str, page: int = 1, page_size: int = 20,
                       sort_by: str = "", sort_order: str = "desc",
                       user: str = Depends(get_current_user)) -> dict:
    """某行业成分股（分页 + 按列排序）。"""
    try:
        df = _get_industry_stocks(name)
    except Exception as e:
        return {"error": f"获取行业成分失败：{type(e).__name__}: {e}"}
    if sort_by and sort_by in df.columns:
        df = df.sort_values(sort_by, ascending=(sort_order != "desc"), na_position="last")
    total = int(len(df))
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    pages = (total + page_size - 1) // page_size or 1
    start = (page - 1) * page_size
    items = json.loads(df.iloc[start:start + page_size]
                       .to_json(orient="records", force_ascii=False))
    return {"total": total, "page": page, "page_size": page_size,
            "pages": pages, "items": items}


@app.get("/api/stocks")
def api_stocks(page: int = 1, page_size: int = 20, keyword: str = "",
               refresh: bool = False, sort_by: str = "", sort_order: str = "desc",
               user: str = Depends(get_current_user)) -> dict:
    """股市部分股票数据（分页 + 代码/名称筛选 + 按列排序）。"""
    try:
        df = _get_stock_snapshot(refresh=refresh)
    except Exception as e:
        return {"error": f"获取行情失败：{type(e).__name__}: {e}"}
    if keyword:
        kw = keyword.strip()
        df = df[df["代码"].astype(str).str.contains(kw)
                | df["名称"].astype(str).str.contains(kw)]
    if sort_by and sort_by in df.columns:
        df = df.sort_values(sort_by, ascending=(sort_order != "desc"), na_position="last")
    total = int(len(df))
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    pages = (total + page_size - 1) // page_size or 1
    start = (page - 1) * page_size
    items = json.loads(df.iloc[start:start + page_size]
                       .to_json(orient="records", force_ascii=False))  # NaN→null，中文正常
    return {"total": total, "page": page, "page_size": page_size,
            "pages": pages, "items": items}


@app.get("/api/kline")
def api_kline(symbol: str, days: int = 120, user: str = Depends(get_current_user)) -> dict:
    """K线数据（JSON），前端用 ECharts 动态绘制。"""
    df = get_kline_df(symbol, days)
    return {
        "symbol": symbol,
        "dates": df["date"].astype(str).tolist(),        "kline": [
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
    try:
        rule = {"description": rule_desc or "价格上穿20日均线时买入，下穿20日均线时卖出",
                "window": window}
        from finagent.backtest.engine import run_backtest, calc_returns, get_benchmark
        from finagent.backtest.metrics import (
            calc_relative_return, calc_max_drawdown, calc_annualized_return,
            calc_volatility, calc_sharpe, calc_trade_stats,
        )
        result = run_backtest(symbol, rule, days)
        dates = [str(n["date"]) for n in result["nav"]]
        navs = [n["nav"] for n in result["nav"]]
        returns = calc_returns(navs)
        try:
            bench = get_benchmark(dates, benchmark)
        except Exception as be:
            bench = []
            print(f"[backtest] 基准获取失败({benchmark}): {type(be).__name__}: {be}")
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
    except Exception as e:
        return {"error": f"回测失败：{type(e).__name__}: {e}"}


@app.get("/api/backtest/multi")
def api_backtest_multi(stocks: str = "600519,300750,600036,000858,600887",
                       hold_num: int = 3, days: int = 120,
                       benchmark: str = "sh000300",
                       factor: str = "momentum",
                       user: str = Depends(get_current_user)) -> dict:
    """多股票回测。stocks 为逗号分隔代码，factor 为因子（momentum/growth/volatility）。"""
    try:
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
        try:
            bench = get_benchmark(dates, benchmark)
        except Exception as be:
            bench = []
            print(f"[backtest/multi] 基准获取失败({benchmark}): {type(be).__name__}: {be}")
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
    except Exception as e:
        return {"error": f"多股回测失败：{type(e).__name__}: {e}"}


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
    flush_trades(user, acc)  # 交易流水持久化
    save_user_account(user)
    return {"message": msg, "price": price}


# ---------- 策略自动执行 ----------
# 运行状态持久化到 PG，后台调度器(server 启动时挂载)按固定间隔执行；
# /execute 保留为"立即执行一次"的调试/手动触发接口。

@app.get("/api/strategy/status")
def strategy_status(user: str = Depends(get_current_user)) -> dict:
    """策略运行状态（按用户，读 PG 持久化状态）。"""
    cur = get_user_current_strategy(user)
    return {"running": data_store.get_strategy_running(user),
            "strategy": cur.get("name", ""),
            "symbol": cur.get("symbol", "")}


@app.post("/api/strategy/start")
def strategy_start(user: str = Depends(get_current_user)) -> dict:
    """启动策略自动执行（持久化状态 + 挂载后台调度器）。"""
    cur = get_user_current_strategy(user)
    if not cur.get("name"):
        return {"error": "尚未设置策略"}
    data_store.set_strategy_running(user, True)
    # 确保调度器在运行（幂等）
    from finagent.trading.strategy_scheduler import start
    start()
    return {"running": True}


@app.post("/api/strategy/stop")
def strategy_stop(user: str = Depends(get_current_user)) -> dict:
    """停止策略自动执行（持久化状态）。"""
    data_store.set_strategy_running(user, False)
    return {"running": False}


@app.get("/api/strategy/execute")
def strategy_execute(user: str = Depends(get_current_user)) -> dict:
    """立即执行一次策略检查（手动触发，不受调度器影响）。"""
    from finagent.trading.strategy_runner import run_strategy
    if not data_store.get_strategy_running(user):
        return {"message": "策略未运行", "ran": False}
    cur = get_user_current_strategy(user)
    symbol = cur.get("symbol", "600519")
    rule = {"description": cur.get("description", ""), "window": 20}
    acc = get_user_account(user)
    msg = run_strategy(acc, symbol, rule)
    flush_trades(user, acc)  # 交易流水持久化
    save_user_account(user)
    return {"message": msg, "ran": True, "account": {
        "cash": acc.cash, "total": acc.total, "pnl": acc.pnl}}


# ---------- 止损强平 ----------
@app.post("/api/strategy/stop-loss")
def strategy_stop_loss(user: str = Depends(get_current_user)) -> dict:
    """检查并执行止损：持仓亏损超阈值则强平。"""
    acc = get_user_account(user)
    forced = acc.check_stop_loss()
    results = []
    for symbol in forced:
        p = acc.positions[symbol]
        msg = acc.sell(symbol, p.qty, p.price)
        results.append(f"{symbol}: {msg}")
    if results:
        flush_trades(user, acc)  # 交易流水持久化
        save_user_account(user)
    return {"forced": results, "count": len(results)}


# 启动时挂载后台策略调度器（容器重启后自动恢复运行中的策略）
from finagent.trading.strategy_scheduler import start as _start_scheduler
_start_scheduler()


# 启动时检查知识库是否需刷新（文档变化自动重建入库，幂等）
def _refresh_knowledge_on_startup() -> None:
    """后台线程执行，避免阻塞启动。"""
    import threading as _th

    def _do():
        try:
            from finagent.rag.refresh import refresh_knowledge
            docs_dir = (Path(__file__).resolve().parent.parent.parent.parent
                        / "docs" / "knowledge")
            result = refresh_knowledge(docs_dir)
            print(f"[knowledge] 启动检查: {result['reason']}")
        except Exception as e:
            print(f"[knowledge] 启动刷新失败: {type(e).__name__}: {e}")

    _th.Thread(target=_do, daemon=True).start()


_refresh_knowledge_on_startup()


# ---------- 交易流水 ----------
@app.get("/api/trades")
def api_trades(limit: int = 50, user: str = Depends(get_current_user)) -> list:
    """用户交易流水（按时间倒序）。"""
    return data_store.list_trades(user, limit=limit)


def flush_trades(username: str, acc: Account) -> None:
    """把账户内存中的 trade_log 持久化到 trades 表并清空。"""
    if acc.trade_log:
        data_store.record_trades(username, acc.trade_log)
        acc.trade_log.clear()


# ---------- 知识库刷新 ----------
@app.post("/api/knowledge/refresh")
def api_knowledge_refresh(user: str = Depends(get_current_user)) -> dict:
    """手动刷新知识库：文档变化则重建入库（幂等，无变化直接返回）。"""
    from finagent.rag.refresh import refresh_knowledge
    from pathlib import Path as _P
    docs_dir = _P(__file__).resolve().parent.parent.parent.parent / "docs" / "knowledge"
    return refresh_knowledge(docs_dir)


# ---------- 用户数据导出/删除（合规） ----------
@app.get("/api/auth/export")
def export_my_data(user: str = Depends(get_current_user)) -> dict:
    """导出当前用户全部数据（账户/策略/会话/交易流水）。"""
    return data_store.export_user_data(user)


@app.delete("/api/auth/account")
def delete_my_account(user: str = Depends(get_current_user)) -> dict:
    """注销账户：删除用户全部数据（级联）。"""
    data_store.delete_user_data(user)
    _accounts_cache.pop(user, None)  # 清内存缓存
    return {"message": "账户已删除"}


# ---------- 静态文件 ----------
# 注意：先挂载 /output（K线图片），再挂载 /（前端页面），避免 "/" 吞掉其他路由
OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)  # 确保目录存在
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")

STATIC_DIR = Path(__file__).resolve().parent.parent.parent.parent / "frontend"


class NoCacheStaticFiles(StaticFiles):
    """静态文件禁用浏览器缓存：前端每次改动，刷新即可生效（不缓存旧 JS/CSS）。"""

    def file_response(self, *args, **kwargs):
        resp = super().file_response(*args, **kwargs)
        resp.headers["Cache-Control"] = "no-cache, must-revalidate"
        return resp


app.mount("/", NoCacheStaticFiles(directory=str(STATIC_DIR), html=True), name="static")


if __name__ == "__main__":
    import os
    import uvicorn
    # 默认单进程（PyCharm 调试/部署稳定，停止不留残留子进程占端口）。
    # 开发要热重载时：FINAGENT_RELOAD=1，或用命令行 uvicorn finagent.api.server:app --reload。
    # 端口可用 FINAGENT_PORT 覆盖（项目统一端口为 9997）。
    port = int(os.environ.get("FINAGENT_PORT", "9997"))
    reload = os.environ.get("FINAGENT_RELOAD", "") == "1"
    uvicorn.run("finagent.api.server:app", host="127.0.0.1", port=port, reload=reload)
