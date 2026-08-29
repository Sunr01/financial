# FinAgent 企业级改造与新增功能笔记

> 记录近期完成的企业级改造（交易成本/参数化/缓存/因子模块）与新增功能（认证/用户隔离/多股回测/绩效指标）。

## 1. 企业级改造（回测系统）

### 1.1 手续费 + 滑点
- **文件**：`backtest/engine.py`、`backtest/engine_multi.py`
- **说明**：买卖计入手续费（默认万3）+ 滑点（默认 0.1%）
  - 买入价 = 收盘价 × (1 + 滑点)，卖出价 = 收盘价 × (1 - 滑点)
  - 手续费 = 成交额 × 费率
  - 交易记录带 `fee` 字段
- **价值**：回测结果更真实（企业标准：必须考虑交易成本）

### 1.2 参数配置化
- **文件**：`backtest/engine.py`
- **参数**：`initial_capital`、`commission_rate`、`slippage` 全部可配置
- **价值**：策略参数不写死，支持后续参数优化

### 1.3 数据缓存
- **文件**：`agents/tools.py`（`get_kline_df` 加 `_kline_cache`）
- **说明**：内存缓存 K 线数据，同一股票拉过一次不再请求外部接口
- **价值**：多股回测/多次回测性能提升；企业级可升级 Redis/文件缓存

### 1.4 因子模块化
- **文件**：`backtest/factor.py`（新建）
- **因子**：
  - `momentum_factor`（动量：近N日涨幅）
  - `volatility_factor`（波动率：负标准差，低波动高分）
  - `FACTORS` 注册表（可扩展新增因子）
- **价值**：因子计算与回测引擎解耦，新增因子只需加函数 + 注册

## 2. 新增功能

### 2.1 多股票回测
- **文件**：`backtest/engine_multi.py`（新建）+ `/api/backtest/multi` 接口
- **逻辑**：动量因子排序 → 持仓 N 只（等权）→ 每日换仓 → 净值 + 交易记录
- **前端**：数据平台"多股回测"按钮（股票池 + 持仓数可配）
- **测试**：5 股池/持 3 只/60 天：33 笔交易（含成本后 40 天 18 笔）

### 2.2 完整绩效指标
- **文件**：`backtest/metrics.py`（扩展）
- **指标**：累计收益、相对收益率、年化收益、夏普比率、最大回撤+区间、胜率、盈亏比、波动率
- **公式**：
  - 年化 = (1+总收益)^(252/天数) - 1
  - 夏普 = (年化收益 - 无风险利率) / 年化波动率
  - 波动率 = 日收益标准差 × √252
  - 胜率/盈亏比 = 按买卖配对统计

### 2.3 收益曲线增强（前端）
- 3 条线：策略收益（红）/基准收益（黄）/相对收益率（蓝）
- 最大回撤区间用 markArea 阴影标注

## 3. 认证与用户隔离（之前完成，补充记录）

### 3.1 JWT 认证（PostgreSQL）
- `src/finagent/auth/`（独立目录）：security/db/routes
- JWT + bcrypt，注册/登录/me，13 个业务接口全部保护

### 3.2 用户数据隔离
- `src/finagent/data_store.py`：策略/账户/当前策略按用户名隔离（PostgreSQL）
- 表：`user_strategies`、`user_accounts`（JSONB）

### 3.3 前端
- 登录/注册页 + token 存储（localStorage）+ 风险弹窗（理财有风险，梭哈需谨慎）+ 启动校验 token

## 4. 踩坑记录（新增）

### 坑：bcrypt 密码长度限制
- passlib 1.7.4 + bcrypt 5.0 报 `password cannot be longer than 72 bytes`
- 解决：弃用 passlib，直接用官方 bcrypt 库（hashpw/checkpw）

### 坑：.venv 缺 pip
- `python -m pip` 报 `No module named pip`，包装错环境（系统 python 有，.venv 没有）
- 解决：`python -m ensurepip --upgrade` 补 pip

### 坑：AsyncConnectionPool 超时
- Windows 下异步连接池 `PoolTimeout`（30秒）
- 解决：改用同步 `PostgresSaver` + `ConnectionPool`

## 5. 面试话术（企业级）

> "回测引擎计入手续费与滑点，参数可配置；数据层加缓存；因子计算模块化（动量/波动率，可扩展）；用户认证 JWT + bcrypt + PostgreSQL，用户数据按账户隔离；绩效指标完整（年化/夏普/回撤/胜率）。"
