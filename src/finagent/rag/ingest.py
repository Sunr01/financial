"""入库：把切分好的文本块向量化并写入 Milvus。"""

from pathlib import Path
from langchain_milvus import Milvus
from langchain_community.embeddings import DashScopeEmbeddings

from finagent.config import settings
from finagent.rag.splitter import split_documents


def build_vector_store(docs_dir: Path) -> Milvus:
    """读取文档→切分→向量化→写入 Milvus，返回向量库连接对象。"""
    embeddings = DashScopeEmbeddings(
        dashscope_api_key=settings.dashscope_api_key,
        model=settings.dashscope_embedding_model,
    )
    chunks = split_documents(docs_dir)
    store = Milvus.from_documents(
        documents=chunks,
        embedding=embeddings,
        connection_args={"host": settings.milvus_host, "port": settings.milvus_port},
        collection_name="fin_docs",
    )
    print(f"已入库 {len(chunks)} 个文本块到 Milvus collection 'fin_docs'")
    return store


if __name__ == "__main__":
    # 用 __file__ 推导项目根目录，与 build_knowledge.py 保持一致
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    build_vector_store(project_root / "docs" / "knowledge")
