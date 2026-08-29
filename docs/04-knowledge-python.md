# FinAgent 知识点问答（一）：Python 与 LangChain 基础

> 开发过程中遇到的"为什么"与"是什么"，整理成问答方便复习与面试。

## 1. 相对路径为什么会导致文件写错位置？

- **问**：`Path("docs/knowledge")` 生成的文档跑到 `src/...` 里去了？
- **答**：相对路径是相对"运行时的工作目录"（PyCharm 里通常是你运行脚本的位置），不是项目根目录。
- **正解**：用 `__file__` 推导绝对路径：
  ```python
  PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
  ```
- **教训**：写文件路径永远用基于 `__file__` 的绝对路径。

## 2. `df.iterrows()` 和 `_` 是什么？

- `df.iterrows()`：pandas 表格的"逐行遍历"，每次返回 `(行号, 行数据)`。
- `_`：占位符变量名，表示"这个值我不要"。如 `for _, row in df.iterrows():` 意思是"行号不要，行数据命名为 row"。

## 3. `class`、继承、对象是什么？

- **类（class）**：模板/模具。`class Settings(BaseSettings)` = 定义 Settings 类，继承 BaseSettings 的能力。
- **对象**：`settings = Settings()` = 照着模板造出实物。
- **继承**：站在巨人肩膀上，自动获得父类功能。

## 4. `from A import B` 是什么？

- 从 A 模块拿 B 进来用。如 `from pathlib import Path` = 拿路径工具。
- `import x as y` = 拿来并起小名，如 `akshare as ak`。

## 5. 函数、for 循环、f-string 是什么？

- **函数**：`def f(x):` = 定义小机器，`return` 交结果。
- **for**：`for x in 东西:` = 遍历每一项。
- **f-string**：`f"你好{name}"` = 把变量塞进句子。
- **列表推导式**：`[Document(page_content=c) for c in chunks]` = 批量转换。

## 6. `if __name__ == "__main__":` 是什么？

- 每个 Python 文件运行时有个内置变量 `__name__`。
- **直接运行**时 = `"__main__"` → 执行；**被 import** 时 = 文件名 → 不执行。
- 作用：同一文件既能"当按钮运行"，又能"被借用不乱跑"。

## 7. pydantic-settings 和 load_dotenv 的区别？

- `load_dotenv()`：读 .env 进环境变量，手动 `os.getenv` 取值，类型自己转。
- `pydantic-settings`：`env_file=".env"` 声明即可，自动类型转换、默认值、校验。
- **底层**：pydantic-settings 内部就是调 dotenv 的 `dotenv_values`，只是封装更强。
- **结论**：企业标准用 pydantic-settings（声明式、省心、能讲规范）。

## 8. LangGraph 的 State/节点/边是什么？

- **State（状态）**：节点间传递的"托盘"（TypedDict 定义）。
- **Node（节点）**：干一件事的函数，读状态返回更新。
- **Edge（边）**：节点间连接。
- **条件边**：路由函数决定走哪个分支。
- **关键坑**：State 里没声明的字段会被静默丢弃！返回字段必须先在 TypedDict 声明。

## 9. `prompt | llm`（LCEL 管道）是什么？

- 流水线：`prompt`（模具）出料 → 传送带（`|`）→ `llm`（DeepSeek）出成品。
- `chain.invoke({"context": ..., "question": ...})` = 放原料进流水线拿结果。
- 可自由组合（`prompt | llm | 其他环节`），LangChain 新一代标准写法。

## 10. 为什么用 Document 对象而不是字符串？

- `Milvus.from_documents()` 要求 Document（有 `page_content` 和 `metadata`）。
- 字符串报错：`'str' object has no attribute 'page_content'`。
- **metadata 作用**：记录来源（文件名），支撑引用溯源。

## 11. 为什么切分参数要匹配文档长度？

- `chunk_size=800` 但文档才 300 字符 → 切不出任何块 → 0 块入库。
- 要先看文档规模，再定 chunk_size（我们的短文档用 100/20）。
