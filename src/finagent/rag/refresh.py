"""知识库自动刷新：对比文档指纹，变化则重建 Milvus 向量库。

设计：
- 指纹 = 所有 .md 文档的 (文件名, 大小, mtime) 哈希，存在 PG knowledge_sync 表
- 指纹一致 → 跳过；不一致 → drop 旧集合重建入库，并更新指纹
- 供 server 启动时 / 定时任务 / 手动接口调用
"""

import hashlib
from pathlib import Path

from finagent.data_store import get_knowledge_signature, save_knowledge_signature
from finagent.config import settings


def _compute_signature(docs_dir: Path) -> str:
    """计算知识库文档指纹。"""
    h = hashlib.sha256()
    for file in sorted(docs_dir.glob("*.md")):
        stat = file.stat()
        h.update(file.name.encode("utf-8"))
        h.update(str(stat.st_size).encode())
        h.update(str(int(stat.st_mtime)).encode())
    return h.hexdigest()


def refresh_knowledge(docs_dir: Path) -> dict:
    """刷新知识库：文档变化才重建入库。返回 {refreshed, reason, count}。"""
    if not docs_dir.is_dir() or not list(docs_dir.glob("*.md")):
        return {"refreshed": False, "reason": "无知识库文档", "count": 0}

    sig = _compute_signature(docs_dir)
    last = get_knowledge_signature()
    if last == sig:
        return {"refreshed": False, "reason": "文档无变化", "count": 0}

    # 重建：drop 旧集合 → 重新入库
    from pymilvus import utility, connections
    connections.connect(host=settings.milvus_host,
                        port=settings.milvus_port, timeout=10)
    if utility.has_collection("fin_docs"):
        utility.drop_collection("fin_docs")

    from finagent.rag.ingest import build_vector_store
    from finagent.rag.splitter import split_documents
    chunks = split_documents(docs_dir)
    build_vector_store(docs_dir)
    save_knowledge_signature(sig)
    return {"refreshed": True, "reason": "文档已更新，重建入库", "count": len(chunks)}
