# FinAgent 应用镜像
FROM python:3.13-slim

WORKDIR /app

# 安装系统依赖（psycopg 编译需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && rm -rf /var/lib/apt/lists/*

# 复制依赖清单并安装
COPY pyproject.toml ./
RUN pip install --no-cache-dir pyproject-hooks 2>/dev/null || true
RUN pip install --no-cache-dir \
    langchain-core langchain-community langchain-milvus langchain-text-splitters \
    langchain-deepseek langgraph langgraph-checkpoint-postgres \
    akshare dashscope pymilvus fastapi uvicorn pydantic-settings \
    pyjwt bcrypt "psycopg[binary,pool]" mcp langchain-mcp-adapters \
    matplotlib mplfinance llama-index

# 复制代码
COPY src/ /app/src/
COPY frontend/ /app/frontend/

# 环境变量
ENV PYTHONPATH=/app/src

EXPOSE 9996

CMD ["uvicorn", "finagent.api.server:app", "--host", "0.0.0.0", "--port", "9996"]
