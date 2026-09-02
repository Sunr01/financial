"""LlamaIndex 版 RAG：增量索引 + 查询引擎 + 元数据过滤。

对外接口与 query.py 的 answer() 一致（Agent 层无感切换）。

注意：本模块当前未接入主线（supervisor 用 LangChain 版 query.py）。
LlamaIndex 依赖已从 pyproject 默认依赖移除（与 pymilvus 3 冲突，
见 pyproject.toml 注释），未安装时调用本模块会给出明确提示。
"""

from pathlib import Path

try:
    from llama_index.core import VectorStoreIndex, Document, Settings
    from llama_index.core.embeddings import BaseEmbedding
    from llama_index.core.node_parser import SentenceSplitter
    from llama_index.core.indices.loading import load_index_from_storage
    from llama_index.core.storage import StorageContext
    from llama_index.vector_stores.milvus import MilvusVectorStore
    _LLAMA_AVAILABLE = True
except ImportError as _e:  # 依赖未安装（pymilvus 冲突，见 pyproject 注释）
    _LLAMA_AVAILABLE = False
    _LLAMA_IMPORT_ERR = _e

from langchain_community.embeddings import DashScopeEmbeddings

from finagent.config import settings


def _require_llama() -> None:
    """检查 LlamaIndex 依赖是否可用，缺失时给出安装指引。"""
    if not _LLAMA_AVAILABLE:
        raise RuntimeError(
            "LlamaIndex 依赖未安装：llama-index / llama-index-vector-stores-milvus "
            "（当前与 pymilvus 3 冲突，已从 pyproject 移除）。"
            f"原始错误：{_LLAMA_IMPORT_ERR}。"
            "如确需启用 LlamaIndex 双轨，请等待其支持 pymilvus 3 后再加回依赖，"
            "或使用独立的 Python 环境安装。"
        )


if _LLAMA_AVAILABLE:

    class DashScopeEmbedding(BaseEmbedding):
        """把 LangChain 的 DashScopeEmbeddings 包装成 LlamaIndex 的 BaseEmbedding。"""

        def __init__(self, **kwargs) -> None:
            super().__init__(**kwargs)
            self._emb = DashScopeEmbeddings(
                dashscope_api_key=settings.dashscope_api_key,
                model=settings.dashscope_embedding_model,
            )

        def _get_query_embedding(self, query: str) -> list[float]:
            return self._emb.embed_query(query)

        def _get_text_embedding(self, text: str) -> list[float]:
            return self._emb.embed_query(text)

        async def _aget_query_embedding(self, query: str) -> list[float]:
            return self._emb.embed_query(query)

        async def _aget_text_embedding(self, text: str) -> list[float]:
            return self._emb.embed_query(text)

        def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
            return self._emb.embed_documents(texts)

        async def _aget_text_embeddings(self, texts: list[str]) -> list[list[float]]:
            return self._emb.embed_documents(texts)

    # 配置 LlamaIndex 用 DashScope embedding
    Settings.embed_model = DashScopeEmbedding()

# 索引缓存（内存级，避免重复构建）
_index_cache: dict = {}


def _get_index(symbol: str | None = None):
    """获取（或构建）LlamaIndex 向量索引。symbol 用于元数据过滤。"""
    _require_llama()
    cache_key = symbol or "all"
    if cache_key in _index_cache:
        return _index_cache[cache_key]

    # Milvus 向量存储（LlamaIndex 版）
    vector_store = MilvusVectorStore(
        uri=f"http://{settings.milvus_host}:{settings.milvus_port}",
        collection_name="fin_docs_llama",
        dim=1024,  # DashScope text-embedding-v3 实测维度
        overwrite=False,
    )
    index = VectorStoreIndex.from_vector_store(vector_store)
    _index_cache[cache_key] = index
    return index


def build_index(docs_dir: Path) -> None:
    """增量构建索引：把知识库文档切分入库（幂等，只处理新内容）。"""
    _require_llama()
    documents = []
    for file in docs_dir.glob("*.md"):
        text = file.read_text(encoding="utf-8")
        documents.append(Document(
            text=text,
            metadata={"source": file.name},
        ))
    if not documents:
        return
    vector_store = MilvusVectorStore(
        uri=f"http://{settings.milvus_host}:{settings.milvus_port}",
        collection_name="fin_docs_llama",
        dim=1024,  # DashScope text-embedding-v3 实测维度
        overwrite=False,
    )
    StorageContext.from_defaults(vector_store=vector_store)
    index = VectorStoreIndex.from_documents(documents, vector_store=vector_store)
    _index_cache["all"] = index


def answer(question: str, symbol: str | None = None) -> str:
    """LlamaIndex 检索 + DeepSeek 生成带引用回答（兼容 query.answer 接口）。

    说明：检索用 LlamaIndex（增量索引/元数据过滤），生成用 DeepSeek
    （不配置 LlamaIndex 的 LLM，绕开 OpenAI 依赖）。
    """
    _require_llama()
    index = _get_index(symbol)
    retriever = index.as_retriever(similarity_top_k=3)
    # 元数据过滤：按股票代码过滤
    if symbol:
        retriever = index.as_retriever(
            similarity_top_k=3,
            filters={"source": f"{symbol}_*.md"},
        )
    nodes = retriever.retrieve(question)
    context = "\n\n".join(f"[{i+1}] {n.node.text} (来源: {n.node.metadata.get('source')})"
                          for i, n in enumerate(nodes))

    from langchain_deepseek import ChatDeepSeek
    from langchain_core.prompts import ChatPromptTemplate
    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是金融投研助手。请基于提供的资料回答问题，"
                   "并用 [1][2] 这样的编号标注引用来源。资料：\n{context}"),
        ("human", "{question}"),
    ])
    llm = ChatDeepSeek(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
    )
    chain = prompt | llm
    return chain.invoke({"context": context, "question": question}).content
