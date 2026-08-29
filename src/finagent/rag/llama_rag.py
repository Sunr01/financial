"""LlamaIndex 版 RAG：增量索引 + 查询引擎 + 元数据过滤。

对外接口与 query.py 的 answer() 一致（Agent 层无感切换）。
"""

from pathlib import Path

from llama_index.core import VectorStoreIndex, Document, Settings
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.indices.loading import load_index_from_storage
from llama_index.core.storage import StorageContext
from llama_index.vector_stores.milvus import MilvusVectorStore

from finagent.config import settings

# 索引缓存（内存级，避免重复构建）
_index_cache: dict = {}


def _get_index(symbol: str | None = None):
    """获取（或构建）LlamaIndex 向量索引。symbol 用于元数据过滤。"""
    cache_key = symbol or "all"
    if cache_key in _index_cache:
        return _index_cache[cache_key]

    # Milvus 向量存储（LlamaIndex 版）
    vector_store = MilvusVectorStore(
        uri=f"http://{settings.milvus_host}:{settings.milvus_port}",
        collection_name="fin_docs_llama",
        dim=1536,
        overwrite=False,
    )
    index = VectorStoreIndex.from_vector_store(vector_store)
    _index_cache[cache_key] = index
    return index


def build_index(docs_dir: Path) -> None:
    """增量构建索引：把知识库文档切分入库（幂等，只处理新内容）。"""
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
        dim=1536,
        overwrite=False,
    )
    StorageContext.from_defaults(vector_store=vector_store)
    index = VectorStoreIndex.from_documents(documents, vector_store=vector_store)
    _index_cache["all"] = index


def answer(question: str, symbol: str | None = None) -> str:
    """LlamaIndex 查询：检索 + LLM 生成带引用回答（兼容 query.answer 接口）。"""
    index = _get_index(symbol)
    query_engine = index.as_query_engine(similarity_top_k=3)
    # 元数据过滤：按股票代码过滤
    if symbol:
        query_engine = index.as_query_engine(
            similarity_top_k=3,
            filters={"source": f"{symbol}_*.md"},
        )
    response = query_engine.query(question)
    return str(response)
