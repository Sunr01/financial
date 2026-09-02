"""问答：检索 Milvus + DeepSeek 生成带引用回答。"""

from langchain_milvus import Milvus
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_deepseek import ChatDeepSeek
from langchain_core.prompts import ChatPromptTemplate

from finagent.config import settings


def get_store() -> Milvus:
    """连接已入库的 Milvus 向量库（不重新入库，只连接）。"""
    embeddings = DashScopeEmbeddings(
        dashscope_api_key=settings.dashscope_api_key,
        model=settings.dashscope_embedding_model,
    )
    return Milvus(
        embedding_function=embeddings,
        connection_args={"uri": f"http://{settings.milvus_host}:{settings.milvus_port}"},
        collection_name="fin_docs",
    )


def answer(question: str) -> str:
    """检索相关文本块，生成带引用的回答。"""
    store = get_store()
    docs = store.similarity_search(question, k=3)

    context = "\n\n".join(f"[{i+1}] {d.page_content} (来源: {d.metadata.get('source')})"
                          for i, d in enumerate(docs))

    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是金融投研助手。请基于提供的资料回答问题，"
                   "并用 [1][2] 这样的编号标注引用来源。资料：\n{context}"),
        ("human", "{question}"),
    ])

    llm = ChatDeepSeek(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        extra_body={"thinking": {"type": "disabled"}},  # 关闭思考，保证流式正文
    )
    chain = prompt | llm
    return chain.invoke({"context": context, "question": question}).content


def answer_stream(question: str, handler) -> None:
    """流式版回答：LLM token 通过 handler 回调输出（供图内流式用）。"""
    store = get_store()
    docs = store.similarity_search(question, k=3)

    context = "\n\n".join(f"[{i+1}] {d.page_content} (来源: {d.metadata.get('source')})"
                          for i, d in enumerate(docs))

    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是金融投研助手。请基于提供的资料回答问题，"
                   "并用 [1][2] 这样的编号标注引用来源。资料：\n{context}"),
        ("human", "{question}"),
    ])

    llm = ChatDeepSeek(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        extra_body={"thinking": {"type": "disabled"}},  # 关闭思考，保证流式正文
        callbacks=[handler],  # 绑定流式回调
    )
    chain = prompt | llm
    # 用 stream 触发逐 token 回调
    for _ in chain.stream({"context": context, "question": question}):
        pass  # token 已通过 handler 回调进队列


if __name__ == "__main__":
    print(answer("贵州茅台2023年营收和净利润是多少？"))
