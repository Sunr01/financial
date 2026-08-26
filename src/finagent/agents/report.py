"""投研简报：用 LLM 生成结构化简报。"""

from langchain_deepseek import ChatDeepSeek
from langchain_core.prompts import ChatPromptTemplate

from finagent.config import settings


def generate_report(topic: str) -> str:
    """根据主题生成投研简报（Markdown）。"""
    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是资深金融分析师。请为指定股票生成一份投研简报，"
                   "包含：公司概况、财务表现、行业分析、风险提示、投资结论。"
                   "用 Markdown 格式输出。"),
        ("human", "请生成 {topic} 的投研简报"),
    ])
    llm = ChatDeepSeek(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
    )
    chain = prompt | llm
    return chain.invoke({"topic": topic}).content


if __name__ == "__main__":
    print(generate_report("贵州茅台"))
