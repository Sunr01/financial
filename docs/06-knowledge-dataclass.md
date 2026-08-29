# FinAgent 知识点问答（三）：数据类与属性魔法

> 回顾代码时对 `df`、`@dataclass`、`@property` 的疑问总结。

## 1. df 是什么？

- **df = DataFrame（pandas 数据表）**，像 Excel 表格，行=记录、列=字段。
- 项目里 df 主要来自 AkShare 接口（行情表、K线表、财务表）。
- 常用操作：`df["列"]` 取列、`df[条件]` 筛选行、`.iloc[0]` 取行、`.max()/.min()` 统计、`.tail(n)` 取尾部、`.tolist()` 转列表、`.iterrows()` 遍历。

## 2. `from dataclasses import dataclass, field` 是什么？

- **dataclasses 是 Python 自带模块**（不用装），提供 `@dataclass` 装饰器。
- 作用：快速定义"存数据的类"，自动生成 `__init__` 等样板代码。
- 对比：手写类要写很多 `self.xxx = xxx`，dataclass 只需声明字段+类型+默认值。

## 3. `@dataclass` 怎么用？

```python
@dataclass
class Position:
    symbol: str
    name: str
    qty: int = 0
    cost: float = 0.0
    price: float = 0.0
```

- 声明字段即可，初始化方法自动生成。

## 4. `field(default_factory=dict)` 是什么？

- **field**：dataclass 的高级字段配置工具。
- `positions: dict = field(default_factory=dict)` = 每次创建实例时新建一个空字典。
- **为什么**：直接写 `= {}` 有"可变默认值陷阱"（所有实例共享同一个字典，互相污染）。
- **default_factory**：每次实例化时调用工厂函数生成新的默认值。

## 5. `@property` 是什么？

- **把方法伪装成属性**：调用时不加括号。
- 作用：
  1. 调用方便：`account.total`（无括号）像读变量
  2. 只读保护：不能随意赋值
  3. 动态计算：每次读取实时算（现金+持仓市值）
- 对比：`@property` 的 total 用 `account.total`；普通方法 buy 用 `account.buy(...)`。

## 6. 整合理解（account.py）

```python
@dataclass
class Account:
    cash: float = 1_000_000.0
    positions: dict = field(default_factory=dict)

    @property
    def total(self) -> float:
        return self.cash + self.position_value
```

- dataclass 简化数据类定义
- field 保证每个账户持仓独立
- property 让 total 实时计算、调用方便

## 7. 面试话术

> "我用 dataclass 简化数据类定义，用 field(default_factory) 避免可变默认值陷阱，用 property 实现实时计算的总资产属性。"
