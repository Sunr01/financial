# FinAgent 重要问答（二）：企业级与工程

> 近期关于企业级实践、工程、面试的重要问答。

## 1. 为什么要用户数据隔离？怎么实现？

- 每个用户应有独立的策略/账户/持仓（不能共享）。
- **实现**：所有业务接口用 `Depends(get_current_user)` 拿 username → 按用户存取：
  - 策略：PostgreSQL `user_strategies` 表（username 过滤）
  - 账户：`_accounts_cache[username]` + PG 持久化
  - 当前策略：账户 JSON 里
- 面试话术："JWT 认证 + 用户数据按账户隔离（PostgreSQL）"。

## 2. 为什么用 PostgreSQL 而不用 SQLite？

- 企业级标准：关系型数据库，支持并发、事务、生产部署。
- 本项目：认证用户表 + 策略表 + 账户表 + 会话表都在 PG（Docker 跑）。
- SQLite 只适合单机演示；PG 是可上生产的。

## 3. 密钥为什么要放 .env？

- 硬编码密钥 = 上传 GitHub 泄露（任何人能伪造 JWT）。
- `.env` 被 .gitignore 保护 → 不上传。
- 企业标准："密钥不进代码，进环境变量"。SECRET_KEY 已从 .env 读。

## 4. 回测为什么要计入手续费和滑点？

- 不计成本 = 回测虚高、不真实。
- 企业标准：买入加滑点、卖出减滑点、扣手续费。
- 面试话术："回测计入交易成本，结果更真实"。

## 5. 因子为什么要模块化？

- 因子计算独立（factor.py），新增因子只加函数 + 注册表。
- 支持动量/成长/波动率多因子切换（回测引擎传 factor 参数）。
- 面试话术："因子模块化，支持扩展多因子"。

## 6. 为什么要单元测试？

- 指标/因子是纯函数，测公式正确性（10 个测试通过）。
- pytest 配置 `pythonpath=["src"]`（src 布局）。
- 企业级："有测试保障，改动不怕回归"。

## 7. 为什么 Docker 容器化？

- Milvus + PG + FinAgent 一键启动（compose）。
- 环境一致、部署简单、简历加分。
- 应用容器通过容器名互连（MILVUS_HOST=milvus）。

## 8. SECRET_KEY 环境变量改法

- config.py 加 `secret_key` 字段（.env 可覆盖）
- security.py `SECRET_KEY = settings.secret_key`
- .env.example 加说明（生产用强随机值）
