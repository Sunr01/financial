"""模拟交易账户：虚拟资金、持仓、买卖。"""

from dataclasses import dataclass, field


@dataclass
class Position:
    """持仓：一只股票的持有信息。"""
    symbol: str
    name: str
    qty: int = 0
    cost: float = 0.0
    price: float = 0.0


@dataclass
class Account:
    """模拟账户：现金 + 持仓列表。"""
    cash: float = 1_000_000.0
    positions: dict = field(default_factory=dict)

    @property
    def position_value(self) -> float:
        """持仓总市值。"""
        return sum(p.qty * p.price for p in self.positions.values())

    @property
    def total(self) -> float:
        """总资产 = 现金 + 持仓市值。"""
        return self.cash + self.position_value

    @property
    def pnl(self) -> float:
        """总盈亏 = 总资产 - 初始资金。"""
        return self.total - 1_000_000.0

    def buy(self, symbol: str, name: str, qty: int, price: float) -> str:
        """买入：扣现金，增加持仓。"""
        cost = qty * price
        if cost > self.cash:
            return "资金不足"
        self.cash -= cost
        p = self.positions.get(symbol)
        if p:
            total_cost = p.cost * p.qty + cost
            p.qty += qty
            p.cost = total_cost / p.qty
            p.price = price
        else:
            self.positions[symbol] = Position(symbol, name, qty, price, price)
        return f"已买入 {qty} 股 {name}@{price}"

    def sell(self, symbol: str, qty: int, price: float) -> str:
        """卖出：加现金，减少持仓。"""
        p = self.positions.get(symbol)
        if not p or p.qty < qty:
            return "持仓不足"
        self.cash += qty * price
        p.qty -= qty
        p.price = price
        if p.qty == 0:
            del self.positions[symbol]
        return f"已卖出 {qty} 股 {symbol}@{price}"

    def update_prices(self, prices: dict):
        """更新持仓现价（用于计算盈亏）。"""
        for symbol, price in prices.items():
            if symbol in self.positions:
                self.positions[symbol].price = price
