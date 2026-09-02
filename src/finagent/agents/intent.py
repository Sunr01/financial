"""意图提取：用 LLM 从用户问题（结合历史）中提取股票代码和意图。"""

from pydantic import BaseModel, Field
from langchain_deepseek import ChatDeepSeek

from finagent.config import settings

# 意图分类：market=行情 news=新闻 k_chart=K线图表 report=投研简报 rag=知识库问答
#           strategy=策略讲解 stock=股票内容总览
VALID_INTENTS = {"market", "news", "k_chart", "report", "rag", "strategy", "stock"}


class Intent(BaseModel):
    """LLM 提取的结果结构。"""
    symbol: str = Field(description="6位股票代码，如 600519；追问时从上文推断，无则填空")
    intent: str = Field(
        description="意图分类，只能取：market/news/k_chart/report/rag 之一。"
                    "追问（如'那2024年呢'）时应保持与上一轮一致的意图。"
    )


def extract_intent(question: str, history: str = "", prev_intent: str = "") -> Intent:
    """从问题中提取股票代码和意图。history 为上文对话，prev_intent 为上一轮意图。"""
    prompt = question
    if history:
        prompt = f"上文对话：{history}\n当前问题：{question}"
    if prev_intent:
        prompt += f"\n注意：这是追问，意图应与上一轮一致（上一轮意图：{prev_intent}）"
    llm = ChatDeepSeek(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        extra_body={"thinking": {"type": "disabled"}},
    ).with_structured_output(Intent)
    intent = llm.invoke(prompt)
    # 校验：意图必须是合法值，否则回退到 rag
    if intent.intent not in VALID_INTENTS:
        intent.intent = "rag"
    return intent


async def aextract_intent(question: str, history: str = "", prev_intent: str = "") -> Intent:
    """异步版意图提取（async 环境用，避免阻塞事件循环）。"""
    prompt = question
    if history:
        prompt = f"上文对话：{history}\n当前问题：{question}"
    if prev_intent:
        prompt += f"\n注意：这是追问，意图应与上一轮一致（上一轮意图：{prev_intent}）"
    llm = ChatDeepSeek(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        extra_body={"thinking": {"type": "disabled"}},
    ).with_structured_output(Intent)
    intent = await llm.ainvoke(prompt)
    if intent.intent not in VALID_INTENTS:
        intent.intent = "rag"
    return intent
