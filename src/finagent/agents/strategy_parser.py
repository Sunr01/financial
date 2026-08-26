"""策略解析：用 LLM 把中文策略描述转成结构化规则。"""

from pydantic import BaseModel, Field
from langchain_deepseek import ChatDeepSeek

from finagent.config import settings


class StrategyRule(BaseModel):
    """解析出的策略规则结构。"""
    symbol: str = Field(description="股票代码，如 600519")
    buy_trigger: str = Field(description="买入触发条件，如：价格跌5% / 上穿20日均线")
    sell_trigger: str = Field(description="卖出触发条件，如：价格涨10% / 下穿20日均线")
    buy_qty: int = Field(description="每次买入数量（股）")
    description: str = Field(description="策略的一句话描述")


def parse_strategy(text: str) -> StrategyRule:
    """把中文策略描述解析成结构化规则。"""
    llm = ChatDeepSeek(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        extra_body={"thinking": {"type": "disabled"}},
    ).with_structured_output(StrategyRule)
    return llm.invoke(f"请解析以下中文交易策略为规则：{text}")
