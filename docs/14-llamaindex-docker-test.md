# FinAgent LlamaIndex / Docker / 测试笔记

> 记录 LlamaIndex 引入、Docker 容器化、pytest 单元测试。

## 1. LlamaIndex 引入（架构文档 6.4 节）

### 3 个引入点
| 引入点 | 实现 | 说明 |
|---|---|---|
| ① 增量索引 | `VectorStoreIndex.from_documents` | 新文档追加不重灌 |
| ② 查询引擎 | `index.as_query_engine(similarity_top_k=3)` | 多文档合成回答 |
| ③ 元数据过滤 | `filters={"source": f"{symbol}_*.md"}` | 按股票过滤检索 |

### 文件：rag/llama_rag.py
- `build_index(docs_dir)`：增量构建
- `answer(question, symbol)`：查询（接口与 query.py 兼容，Agent 无感切换）
- `_index_cache`：内存缓存索引
- 用 `MilvusVectorStore`（LlamaIndex 连 Milvus）

### ⚠️ 待验证
- `dim=1536`（DashScope v3 实际维度可能不同）
- `filters` 语法（LlamaIndex 版本差异）

## 2. Docker 容器化

### Dockerfile（应用镜像）
- python:3.13-slim 基础
- 装依赖（含 psycopg 编译的 gcc/libpq-dev）
- COPY src/ frontend/ → PYTHONPATH=/app/src
- CMD uvicorn 启动

### docker-compose.yml 扩展
```yaml
postgres:  # PG 容器（finagent/finagent123）
finagent:  # 应用容器
  build: .
  environment:
    MILVUS_HOST: milvus   # 容器名互通
    DB_HOST: postgres
  depends_on: [milvus, postgres]
```
- 一键启动：`docker compose up -d --build`

## 3. pytest 单元测试

### 配置（pyproject.toml）
```toml
[tool.pytest.ini_options]
pythonpath = ["src"]   # src 布局：让测试能找到 finagent
testpaths = ["tests"]
```

### 测试文件
- `tests/test_metrics.py`：6 个（相对收益/回撤/年化/波动率/夏普/交易统计）
- `tests/test_factor.py`：4 个（动量/成长/波动率/注册表）

### 运行
```bash
python -m pytest tests/ -v
```
**结果：10 passed in 0.36s** ✅

### 测试原则
- 纯函数测试（指标/因子），不依赖网络
- 造数据验证（不拉真实行情）
- 企业级：测试快、可重复、不依赖外部

## 4. 其他优化
- SECRET_KEY 从 .env 读取（不再硬编码）
- 成长因子：factor.py 新增 growth（价格近似，注释说明可升级真实财务数据）
- 多股回测支持 factor 参数（momentum/growth/volatility）
