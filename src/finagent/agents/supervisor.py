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


class AgentState(TypedDict):
    """状态：节点间传递的托盘。"""
    question: str      # 用户问题
    answer: str        # 最终回答
    route: str
    symbol: str        # 股票代码（LLM 提取）


def supervisor_node(state: AgentState) -> dict:
    """总管节点：用 LLM 提取意图和股票代码，决定路由。"""
    intent = extract_intent(state["question"])
    return {"route": intent.intent, "symbol": intent.symbol}


def rag_node(state: AgentState) -> dict:
    """RAG 节点：知识库问答（调用真实问答逻辑）。"""
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


def build_graph():
    """构建并返回编译后的图。"""
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
    return g.compile()


if __name__ == "__main__":
    graph = build_graph()
    for q in ["茅台今天股价多少", "茅台2023年营收多少", "茅台最近有什么新闻",
              "画一下茅台的k线图", "帮我写一份茅台的投研简报"]:
        print(q, "→", graph.invoke({"question": q})["answer"])
