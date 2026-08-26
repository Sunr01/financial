"""意图提取：用 LLM 从用户问题中提取股票代码和意图。"""

from pydantic import BaseModel, Field
from langchain_deepseek import ChatDeepSeek

from finagent.config import settings


class Intent(BaseModel):
    """LLM 提取的结果结构。"""
    symbol: str = Field(description="6位股票代码，如 600519；无则填空")
    intent: str = Field(description="意图分类：market/news/k_chart/report/rag")


def extract_intent(question: str) -> Intent:
    """从问题中提取股票代码和意图。"""
    llm = ChatDeepSeek(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        extra_body={"thinking": {"type": "disabled"}},
    ).with_structured_output(Intent)
    return llm.invoke(question)
