"""把拉取的财务数据生成知识库文档。"""

from pathlib import Path
from finagent.data.fetch_financial import STOCKS, fetch_financial_abstract, to_chinese_text

# 用 __file__ 推导项目根目录，保证在任何运行目录下都写到 docs/knowledge
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
KNOWLEDGE_DIR = PROJECT_ROOT / "docs" / "knowledge"


def build_all() -> None:
    """为每只股票生成一份知识库文档。"""
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    for stock in STOCKS:
        df = fetch_financial_abstract(stock["symbol"])
        text = to_chinese_text(df, stock["name"])
        file_path = KNOWLEDGE_DIR / f"{stock['symbol']}_{stock['name']}.md"
        file_path.write_text(text, encoding="utf-8")
        print(f"已生成：{file_path}")


if __name__ == "__main__":
    build_all()
