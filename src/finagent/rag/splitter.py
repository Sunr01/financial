"""文档切分器：用 LangChain 递归切分器把文档切成小块。"""

from pathlib import Path
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


def split_documents(docs_dir: Path) -> list[Document]:
    """读取目录下所有 .md 文档，递归切分成带来源的 Document 列表。"""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=100,
        chunk_overlap=20,
        separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
    )
    docs = []
    for file in sorted(docs_dir.glob("*.md")):
        text = file.read_text(encoding="utf-8")
        for chunk in splitter.split_text(text):
            docs.append(Document(page_content=chunk, metadata={"source": file.name}))
    return docs
