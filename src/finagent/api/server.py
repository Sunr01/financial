"""FinAgent Web 服务：FastAPI 接口（聊天/数据/策略/交易）。"""

import json
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from finagent.agents.supervisor import build_graph
from finagent.agents.tools import (
    get_realtime_quote,
    get_kline_data,
    get_kline_df,
    get_financial_indicators,
    search_news,
)
from finagent.trading.account import Account

app = FastAPI(title="FinAgent")
graph = build_graph()
account = Account()

STRATEGY_FILE = Path(__file__).resolve().parent.parent.parent.parent / "strategies.json"


class ChatRequest(BaseModel):
    question: str


class OrderRequest(BaseModel):
    symbol: str
    side: str
    qty: int


class StrategyRequest(BaseModel):
    name: str
    symbol: str
    capital: str
    code: str


# ---------- 聊天 ----------
@app.post("/chat")
def chat(req: ChatRequest) -> dict:
    result = graph.invoke({"question": req.question})
    return {"question": req.question, "answer": result["answer"]}


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# ---------- 数据平台 ----------
@app.get("/api/quote")
def api_quote(symbol: str) -> dict:
    """实时行情（结构化返回给前端）。"""
    text = get_realtime_quote(symbol)
    # 从文本解析出结构化字段（名称/价格/涨跌幅）
    parts = text.split()
    return {"name": parts[0], "symbol": symbol, "price": parts[2],
            "change_pct": parts[4].replace("，", "").replace("%", "")}


@app.get("/api/kline")
def api_kline(symbol: str, days: int = 120) -> dict:
    """K线数据（JSON），前端用 ECharts 动态绘制。"""
    df = get_kline_df(symbol, days)
    return {
        "symbol": symbol,
        "dates": df["date"].astype(str).tolist(),
        "kline": [
            [o, c, l, h]  # ECharts 顺序：开、收、低、高
            for o, c, l, h in zip(df["open"], df["close"], df["low"], df["high"])
        ],
        "volumes": df["volume"].tolist(),
    }


@app.get("/api/news")
def api_news(symbol: str) -> dict:
    """新闻列表。"""
    return {"news": search_news(symbol).split("\n")}


# ---------- 策略 ----------
@app.post("/api/strategy")
def save_strategy(req: StrategyRequest) -> dict:
    """保存策略：用 LLM 把中文策略描述转成结构化规则。"""
    from finagent.agents.strategy_parser import parse_strategy
    try:
        rule = parse_strategy(req.code).model_dump()
    except Exception as e:
        return {"error": f"策略解析失败：{e}"}
    strategies = []
    if STRATEGY_FILE.exists():
        strategies = json.loads(STRATEGY_FILE.read_text("utf-8"))
    strategies.append({**req.model_dump(), "rule": rule})
    STRATEGY_FILE.write_text(json.dumps(strategies, ensure_ascii=False, indent=2), "utf-8")
    return {"status": "saved", "rule": rule}


@app.get("/api/strategy")
def list_strategies() -> list:
    if not STRATEGY_FILE.exists():
        return []
    return json.loads(STRATEGY_FILE.read_text("utf-8"))


# ---------- 我的交易 ----------
@app.get("/api/account")
def get_account() -> dict:
    return {"cash": account.cash, "position_value": account.position_value,
            "total": account.total, "pnl": account.pnl}


@app.get("/api/positions")
def get_positions() -> list:
    return [
        {"symbol": p.symbol, "name": p.name, "qty": p.qty,
         "cost": round(p.cost, 2), "price": p.price,
         "pnl": round((p.price - p.cost) * p.qty, 2)}
        for p in account.positions.values()
    ]


@app.post("/api/order")
def place_order(req: OrderRequest) -> dict:
    """下单：买入/卖出。价格用实时行情（简化：从文本取价格）。"""
    text = get_realtime_quote(req.symbol)
    parts = text.split()
    name, price = parts[0], float(parts[2])
    if req.side == "buy":
        msg = account.buy(req.symbol, name, req.qty, price)
    else:
        msg = account.sell(req.symbol, req.qty, price)
    return {"message": msg, "price": price}


# ---------- 静态文件 ----------
# 注意：先挂载 /output（K线图片），再挂载 /（前端页面），避免 "/" 吞掉其他路由
OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)  # 确保目录存在
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")

STATIC_DIR = Path(__file__).resolve().parent.parent.parent.parent / "frontend"
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("finagent.api.server:app", host="127.0.0.1", port=9996, reload=True)
