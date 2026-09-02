"""Supervisor 编排：LangGraph 状态图，负责意图路由。

意图：rag=知识库问答 market=行情 news=新闻 k_chart=K线图 report=简报
      strategy=策略讲解 stock=股票内容总览
"""

import re
from typing import TypedDict
from langgraph.graph import StateGraph, END

from finagent.rag.query import answer
from finagent.agents.report import generate_report
from finagent.agents.intent import extract_intent
from finagent.agents.tools import (
    get_realtime_quote,
    search_news,
    get_kline_data,
    get_financial_indicators,
)
from finagent.agents.chart import generate_kline_chart
from finagent.strategy.templates import TEMPLATES

_graph_ref = None  # 编译后的图引用（供会话历史查询用）
_current_stream_handler = None  # 当前流式 handler（线程内传递，绕开 config 序列化）


class AgentState(TypedDict):
    """状态：节点间传递的托盘。"""
    question: str      # 用户问题
    answer: str        # 最终回答
    route: str
    symbol: str        # 股票代码（正则/LLM 提取）


def extract_symbol(text: str) -> str:
    """从文本中提取 6 位股票代码（兼容 sh600519 / sz000001 / bj430047 / 600519.SH 写法）。"""
    m = re.search(r"(?<!\d)(?:sh|sz|bj)?(\d{6})(?!\d)", (text or "").lower())
    return m.group(1) if m else ""


def supervisor_node(state: AgentState, config=None) -> dict:
    """总管节点：优先用 config 传入的意图（快速关键词判断），避免 LLM 阻塞。
    股票代码优先用正则从问题里提取（快、稳），没有才用 LLM 提取。"""
    global _current_stream_handler
    route = ""
    if config:
        route = config.get("configurable", {}).get("quick_intent", "")
    symbol = extract_symbol(state.get("question", "")) or state.get("symbol", "")
    if not route:
        # 没有快速意图才走 LLM（兜底）
        history, prev_intent = "", ""
        try:
            history, prev_intent = _get_history(config) if config else ("", "")
        except Exception:
            history, prev_intent = "", ""
        intent = extract_intent(state["question"], history, prev_intent)
        route, symbol = intent.intent, intent.symbol or symbol
    return {"route": route, "symbol": symbol}


def _get_history(config) -> tuple:
    """从 Checkpointer 提取会话历史（上一轮的问题、回答、意图）。"""
    try:
        from finagent.agents.supervisor import _graph_ref
        snapshot = _graph_ref.get_state(config)
    except Exception:
        return "", ""
    vals = snapshot.values
    prev_q = vals.get("question", "")
    prev_a = vals.get("answer", "")
    prev_route = vals.get("route", "")  # 上一轮意图
    history = f"上次问题：{prev_q} 上次回答：{prev_a}" if prev_q else ""
    return history, prev_route


def _stream_text(handler, text: str) -> None:
    """把整段文本按字符推入流式队列，前端呈现逐字流式效果。
    （用于组合类回答：股票总览、降级文本等；LLM 回答本身已逐 token 流式。）"""
    if handler is None:
        return
    for ch in text:
        handler.q.put(ch)
    handler.q.put(None)


def rag_node(state: AgentState, config=None) -> dict:
    """RAG 节点：知识库问答。若有流式 handler（全局）则逐 token 输出。"""
    global _current_stream_handler
    from finagent.rag.query import answer_stream
    handler = _current_stream_handler
    if handler is not None:
        try:
            answer_stream(state["question"], handler)
        except Exception as e:
            print(f"[rag_node] answer_stream 错误: {type(e).__name__}: {e}")
        finally:
            handler.q.put(None)
        return {"answer": "（流式输出中）"}
    return {"answer": answer(state["question"])}


def market_node(state: AgentState) -> dict:
    """行情节点：查询实时行情。"""
    return {"answer": get_realtime_quote(state["symbol"])}


def news_node(state: AgentState) -> dict:
    """新闻节点：搜索相关新闻。"""
    return {"answer": search_news(state["symbol"])}


def k_chart_node(state: AgentState) -> dict:
    """K线图表节点：生成K线图。"""
    path = generate_kline_chart(state["symbol"])
    return {"answer": f"已生成K线图：{path}"}


def report_node(state: AgentState) -> dict:
    """投研简报节点：汇总生成简报。"""
    return {"answer": generate_report(state["question"])}


# ---------- 策略讲解（LLM 总结：方式 + 效果，纯文本无符号）----------
_STRATEGY_KEYWORDS = [
    ("均线", "均线策略"),
    ("网格", "网格策略"),
    ("动量", "动量策略"),
    ("成长", "成长因子策略"),
]

_STRATEGY_EXPLAIN_SYSTEM = (
    "你是量化交易策略讲解助手。用户想了解某个交易策略，请用自然、流畅的中文介绍，要求：\n"
    "1. 不要使用任何 Markdown 符号（不要 #、*、-、**、数字序号等标记），用普通段落文字；\n"
    "2. 不要写'使用步骤/操作方法/进入某某页面'之类的平台操作引导；\n"
    "3. 内容只包含两部分：① 这个策略怎么交易（买入/卖出规则，以及关键参数的含义）；"
    "② 它适合什么行情、预期效果和主要风险；\n"
    "4. 篇幅控制在 150~250 字。"
)


def _plain_strategy_text(tpl: dict) -> str:
    """降级用纯文本模板（去掉 markdown 符号，不引导操作）。"""
    return (f"{tpl['name']}：{tpl['description']}。"
            f"交易规则：{tpl['default_code']}。"
            f"关键参数：{tpl['params']}。")


def _llm_strategy_explain(tpl: dict) -> str:
    """用 LLM 总结策略的「交易方式 + 适用效果」（纯文本）。
    关闭 thinking：v4-flash 默认思考模式会延迟输出正文，导致非流式观感。"""
    from langchain_deepseek import ChatDeepSeek
    from langchain_core.prompts import ChatPromptTemplate
    from finagent.config import settings
    prompt = ChatPromptTemplate.from_messages([
        ("system", _STRATEGY_EXPLAIN_SYSTEM),
        ("human", "策略名称：{name}\n策略描述：{description}\n"
                  "关键参数：{params}\n交易规则：{rule}"),
    ])
    llm = ChatDeepSeek(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        extra_body={"thinking": {"type": "disabled"}},
    )
    chain = prompt | llm
    return chain.invoke({
        "name": tpl["name"], "description": tpl["description"],
        "params": tpl["params"], "rule": tpl["default_code"],
    }).content


def _stream_strategy_explain(handler, tpl: dict) -> None:
    """流式版 LLM 总结：token 经 handler 回调逐字进队列。
    关闭 thinking 保证 content 逐 token 输出（否则正文一次性到达）。"""
    from langchain_deepseek import ChatDeepSeek
    from langchain_core.prompts import ChatPromptTemplate
    from finagent.config import settings
    prompt = ChatPromptTemplate.from_messages([
        ("system", _STRATEGY_EXPLAIN_SYSTEM),
        ("human", "策略名称：{name}\n策略描述：{description}\n"
                  "关键参数：{params}\n交易规则：{rule}"),
    ])
    llm = ChatDeepSeek(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        extra_body={"thinking": {"type": "disabled"}},
        callbacks=[handler],
    )
    chain = prompt | llm
    for _ in chain.stream({
        "name": tpl["name"], "description": tpl["description"],
        "params": tpl["params"], "rule": tpl["default_code"],
    }):
        pass  # token 已通过 handler 回调进队列


def strategy_node(state: AgentState, config=None) -> dict:
    """策略讲解节点：LLM 总结策略的「交易方式 + 适用效果」（纯文本，无符号无引导）。"""
    global _current_stream_handler
    handler = _current_stream_handler
    q = state.get("question", "")
    name = next((n for kw, n in _STRATEGY_KEYWORDS if kw in q), "")
    if not name:
        text = ("平台内置策略：均线策略、网格策略、动量策略、成长因子策略。"
                "直接告诉我策略名字，我来介绍它的交易方式和适用效果。")
        if handler is not None:
            _stream_text(handler, text)
            return {"answer": "（流式输出中）"}
        return {"answer": text}
    tpl = next(t for t in TEMPLATES if t["name"] == name)
    try:
        if handler is not None:
            _stream_strategy_explain(handler, tpl)
            handler.q.put(None)
            return {"answer": "（流式输出中）"}
        return {"answer": _llm_strategy_explain(tpl)}
    except Exception as e:
        # LLM 不可用（网络/模型异常）时降级为纯文本，并附上原因便于排查
        print(f"[strategy_node] LLM 总结失败，降级纯文本: {type(e).__name__}: {e}")
        fallback = (_plain_strategy_text(tpl) + f"\n\n（策略在线讲解暂不可用："
                    f"{type(e).__name__}：{str(e)[:120]}）")
        if handler is not None:
            _stream_text(handler, fallback)
            return {"answer": "（流式输出中）"}
        return {"answer": fallback}


# ---------- 股票内容总览（输入代码 → 行情/走势/财务/新闻）----------
def stock_node(state: AgentState, config=None) -> dict:
    """股票内容节点：输入 6 位股票代码 → 汇总行情、近期走势、财务、新闻。"""
    global _current_stream_handler
    handler = _current_stream_handler
    symbol = state.get("symbol", "")
    if not symbol:
        text = "请告诉我股票代码（6 位数字），例如 600519，我来帮你获取该股票的行情、走势、财务和新闻。"
    else:
        parts = []
        for title, fn in (
            ("📊 实时行情", lambda: get_realtime_quote(symbol)),
            ("📈 近期走势", lambda: get_kline_data(symbol)),
            ("💰 财务摘要", lambda: get_financial_indicators(symbol)),
            ("📰 最新新闻", lambda: search_news(symbol)),
        ):
            try:
                parts.append(f"**{title}**\n{fn()}")
            except Exception as e:
                parts.append(f"**{title}**\n（获取失败：{type(e).__name__}，请稍后重试）")
        text = f"### 🏢 {symbol} 股票内容总览\n\n" + "\n\n".join(parts)
    if handler is not None:
        _stream_text(handler, text)
        return {"answer": "（流式输出中）"}
    return {"answer": text}


def route_by_intent(state: AgentState) -> str:
    """条件边：根据 route 决定走哪个节点。"""
    return state.get("route", "rag")


def build_graph(checkpointer=None):
    """构建并返回编译后的图。checkpointer 为可选的会话持久化器。"""
    global _graph_ref
    g = StateGraph(AgentState)
    g.add_node("supervisor", supervisor_node)
    g.add_node("rag", rag_node)
    g.add_node("market", market_node)
    g.add_node("news", news_node)
    g.add_node("k_chart", k_chart_node)
    g.add_node("report", report_node)
    g.add_node("strategy", strategy_node)
    g.add_node("stock", stock_node)
    g.set_entry_point("supervisor")
    g.add_conditional_edges("supervisor", route_by_intent,
                            {"rag": "rag", "market": "market", "news": "news",
                             "k_chart": "k_chart", "report": "report",
                             "strategy": "strategy", "stock": "stock"})
    g.add_edge("rag", END)
    g.add_edge("market", END)
    g.add_edge("news", END)
    g.add_edge("k_chart", END)
    g.add_edge("report", END)
    g.add_edge("strategy", END)
    g.add_edge("stock", END)
    _graph_ref = g.compile(checkpointer=checkpointer)
    return _graph_ref


if __name__ == "__main__":
    graph = build_graph()
    for q in ["茅台今天股价多少", "茅台2023年营收多少", "茅台最近有什么新闻",
              "画一下茅台的k线图", "帮我写一份茅台的投研简报",
              "请介绍一下均线策略的功能和使用方法", "600519"]:
        print(q, "→", graph.invoke({"question": q})["answer"][:120])
