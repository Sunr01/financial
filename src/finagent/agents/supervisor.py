"""Supervisor 编排：LangGraph 状态图，负责意图路由。"""

from typing import TypedDict
from langgraph.graph import StateGraph, END

from finagent.rag.query import answer
from finagent.agents.report import generate_report
from finagent.agents.intent import extract_intent
from finagent.agents.tools import (
    get_realtime_quote,
    search_news,
    get_kline_data,
)
from finagent.agents.chart import generate_kline_chart

_graph_ref = None  # 编译后的图引用（供会话历史查询用）
_current_stream_handler = None  # 当前流式 handler（线程内传递，绕开 config 序列化）


class AgentState(TypedDict):
    """状态：节点间传递的托盘。"""
    question: str      # 用户问题
    answer: str        # 最终回答
    route: str
    symbol: str        # 股票代码（LLM 提取）


def supervisor_node(state: AgentState, config=None) -> dict:
    """总管节点：优先用 config 传入的意图（快速关键词判断），避免 LLM 阻塞。"""
    global _current_stream_handler
    # 优先用 server 传入的快速意图（config 里）
    route = ""
    if config:
        route = config.get("configurable", {}).get("quick_intent", "")
    symbol = state.get("symbol", "")
    if not route:
        # 没有快速意图才走 LLM（兜底）
        history, prev_intent = "", ""
        try:
            history, prev_intent = _get_history(config) if config else ("", "")
        except Exception:
            history, prev_intent = "", ""
        intent = extract_intent(state["question"], history, prev_intent)
        route, symbol = intent.intent, intent.symbol
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


def rag_node(state: AgentState, config=None) -> dict:
    """RAG 节点：知识库问答。若有流式 handler（全局）则逐 token 输出。"""
    global _current_stream_handler
    from finagent.rag.query import answer_stream
    handler = _current_stream_handler
    print(f"[rag_node] handler={'有' if handler else '无'}")  # 临时调试
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
    g.set_entry_point("supervisor")
    g.add_conditional_edges("supervisor", route_by_intent,
                            {"rag": "rag", "market": "market", "news": "news",
                             "k_chart": "k_chart", "report": "report"})
    g.add_edge("rag", END)
    g.add_edge("market", END)
    g.add_edge("news", END)
    g.add_edge("k_chart", END)
    g.add_edge("report", END)
    _graph_ref = g.compile(checkpointer=checkpointer)
    return _graph_ref


if __name__ == "__main__":
    graph = build_graph()
    for q in ["茅台今天股价多少", "茅台2023年营收多少", "茅台最近有什么新闻",
              "画一下茅台的k线图", "帮我写一份茅台的投研简报"]:
        print(q, "→", graph.invoke({"question": q})["answer"])
