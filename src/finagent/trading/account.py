"""模拟交易账户：虚拟资金、持仓、买卖（含风控：手续费/滑点/仓位上限/止损）。"""

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
    """模拟账户：现金 + 持仓列表 + 风控参数。"""
    cash: float = 1_000_000.0
    positions: dict = field(default_factory=dict)
    trade_log: list = field(default_factory=list)  # 本次会话产生的交易流水（待持久化）
    # ---- 风控参数（可在初始化时覆盖） ----
    commission_rate: float = 0.00025   # 手续费率 万2.5
    min_commission: float = 5.0        # 最低手续费 5 元
    slippage: float = 0.001            # 滑点 0.1%（买卖各吃 0.1%）
    max_position_pct: float = 0.5      # 单只股票仓位上限 50%
    stop_loss_pct: float = 0.1         # 止损线：亏损 10% 强平

    def _record_trade(self, symbol: str, name: str, side: str,
                      qty: int, price: float, fee: float) -> None:
        """记录一笔交易到流水（供持久化到 trades 表）。"""
        self.trade_log.append({
            "symbol": symbol, "name": name, "side": side,
            "qty": qty, "price": round(price, 4), "fee": round(fee, 4),
        })

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

    def _commission(self, amount: float) -> float:
        """计算手续费：费率计费，但低于最低手续费按最低收。"""
        return max(amount * self.commission_rate, self.min_commission)

    def buy(self, symbol: str, name: str, qty: int, price: float) -> str:
        """买入：扣现金（含手续费+滑点），增加持仓。带仓位上限风控。"""
        exec_price = price * (1 + self.slippage)  # 买入吃滑点
        cost = qty * exec_price
        fee = self._commission(cost)
        total_cost = cost + fee
        if total_cost > self.cash:
            return f"资金不足（需 {total_cost:.2f}，现金 {self.cash:.2f}）"
        # 仓位上限：买入后该股市值 ≤ 总资产 × 上限
        new_position_value = self.position_value + cost
        if new_position_value > self.total * self.max_position_pct:
            max_qty = int(self.total * self.max_position_pct / exec_price / 100) * 100
            return (f"超过仓位上限（最多 {max_qty} 股，约 {self.total * self.max_position_pct:.0f} 元）")
        self.cash -= total_cost
        p = self.positions.get(symbol)
        if p:
            total_cost_basis = p.cost * p.qty + cost + fee
            p.qty += qty
            p.cost = total_cost_basis / p.qty
            p.price = exec_price
        else:
            self.positions[symbol] = Position(symbol, name, qty, (cost + fee) / qty, exec_price)
        self._record_trade(symbol, name, "buy", qty, exec_price, fee)
        return f"已买入 {qty} 股 {name}@{exec_price:.2f}（手续费 {fee:.2f}）"

    def sell(self, symbol: str, qty: int, price: float) -> str:
        """卖出：加现金（扣手续费+滑点），减少持仓。"""
        p = self.positions.get(symbol)
        if not p or p.qty < qty:
            return "持仓不足"
        exec_price = price * (1 - self.slippage)  # 卖出吃滑点
        proceeds = qty * exec_price
        fee = self._commission(proceeds)
        self.cash += proceeds - fee
        p.qty -= qty
        p.price = exec_price
        if p.qty == 0:
            del self.positions[symbol]
        self._record_trade(symbol, p.name, "sell", qty, exec_price, fee)
        return f"已卖出 {qty} 股 {symbol}@{exec_price:.2f}（手续费 {fee:.2f}）"

    def check_stop_loss(self) -> list:
        """止损检查：返回需要强平的持仓列表（亏损超过止损线）。"""
        forced = []
        for symbol, p in list(self.positions.items()):
            if p.qty > 0 and p.cost > 0:
                loss_pct = (p.price - p.cost) / p.cost
                if loss_pct <= -self.stop_loss_pct:
                    forced.append(symbol)
        return forced

    def update_prices(self, prices: dict):
        """更新持仓现价（用于计算盈亏）。"""
        for symbol, price in prices.items():
            if symbol in self.positions:
                self.positions[symbol].price = price

    # ---------- 序列化（PG 存 JSON 用） ----------
    def to_dict(self) -> dict:
        """转为可 JSON 序列化的 dict。"""
        return {
            "cash": self.cash,
            "positions": {
                s: {"symbol": p.symbol, "name": p.name,
                    "qty": p.qty, "cost": p.cost, "price": p.price}
                for s, p in self.positions.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Account":
        """从 dict 恢复账户（positions 还原为 Position 对象）。"""
        acc = cls()
        acc.cash = data.get("cash", 1_000_000.0)
        for s, p in (data.get("positions") or {}).items():
            acc.positions[s] = Position(
                symbol=p.get("symbol", s),
                name=p.get("name", s),
                qty=p.get("qty", 0),
                cost=p.get("cost", 0.0),
                price=p.get("price", 0.0),
            )
        return acc
