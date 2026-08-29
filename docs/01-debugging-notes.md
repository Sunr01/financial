# FinAgent 开发排错笔记（阶段 1）

> 本文档记录阶段 1（RAG 入库）实际遇到并解决的 4 个问题，供复盘与面试讲述。

## 坑 1：相对路径导致文件写错位置

- **现象**：生成的知识库文档出现在 `src/finagent/data/docs/knowledge/`，而非 `docs/knowledge/`；入库读不到，报"0 个文本块"。
- **原因**：`Path("docs/knowledge")` 是相对路径，相对于"运行时工作目录"；PyCharm 运行时工作目录是脚本所在文件夹。
- **解决**：用 `__file__` 推导项目根目录，拼绝对路径：
  ```python
  PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
  KNOWLEDGE_DIR = PROJECT_ROOT / "docs" / "knowledge"
  ```
- **教训**：写路径永远用基于 `__file__` 的绝对路径。

## 坑 2：数据取错年份（顺序方向反了）

- **现象**：知识库文档是 2002/2001/2000 年的老数据，而非最近 5 年。
- **原因**：AkShare 返回列名顺序是最新在前（20251231 → 19981231），`[-5:]` 取到最后 5 个 = 最旧 5 年。
- **解决**：改 `[:5]` 取前 5 个。
- **教训**：不确定数据顺序时先打印 `df.columns.tolist()` 看真实顺序。

## 坑 3：切分参数不适配短文档

- **现象**：文档约 300 字符，`chunk_size=800` 切不出任何块 → 0 块。
- **原因**：块大小大于文档总长，切分器放弃。
- **解决**：调整参数匹配数据规模：`chunk_size=100, chunk_overlap=20`。
- **教训**：切分参数要匹配文档长度。

## 坑 4：字符串未转 Document 对象

- **现象**：入库报错 `AttributeError: 'str' object has no attribute 'page_content'`。
- **原因**：`Milvus.from_documents()` 需要 Document 对象，传入了纯字符串。
- **解决**：列表推导式转换：
  ```python
  documents = [Document(page_content=c) for c in chunks]
  ```
- **教训**：用 LangChain API 前先确认它要求的类型。

## 通用心法

1. 先打印真实数据，再写代码
2. 路径用绝对路径（`__file__`）
3. 参数要匹配数据规模
4. 看 API 要求什么类型

> 核心：不假设，先验证。
