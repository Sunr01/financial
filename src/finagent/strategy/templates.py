"""策略模板库：内置常见策略模板。"""

TEMPLATES = [
    {
        "name": "均线策略",
        "type": "single",
        "description": "价格上穿20日均线买入，下穿20日均线卖出",
        "params": {"window": 20, "symbol": "600519"},
        "default_code": "当价格上穿20日均线时买入，下穿20日均线时卖出",
    },
    {
        "name": "网格策略",
        "type": "single",
        "description": "价格较成本跌5%买入，涨5%卖出（区间震荡）",
        "params": {"buy_pct": 5, "sell_pct": 5, "symbol": "600519"},
        "default_code": "当价格较买入成本下跌5%时买入，上涨5%时卖出",
    },
    {
        "name": "动量策略",
        "type": "single",
        "description": "近20日涨幅超10%追入，跌幅超5%止损",
        "params": {"window": 20, "buy_pct": 10, "stop_pct": 5, "symbol": "600519"},
        "default_code": "当近20日涨幅超过10%时买入，亏损超过5%时卖出",
    },
    {
        "name": "成长因子策略",
        "type": "multi",
        "description": "按市值与营收增速排序，持仓10只每日换仓1只",
        "params": {"hold_num": 10, "change_num": 1},
        "default_code": "按市值与营收增速对股票池排序，持有前10只，每日换仓1只",
    },
]
