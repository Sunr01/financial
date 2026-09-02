# ============================================================
# FinAgent 应用镜像(多阶段构建 + 非 root 运行)
#   阶段1 builder:编译依赖、安装全部 Python 依赖
#   阶段2 runtime:只带运行产物,瘦身 + 安全
# ============================================================

# ---------- 阶段 1:builder ----------
FROM docker.m.daocloud.io/library/python:3.13-slim AS builder

WORKDIR /build

# 系统依赖(psycopg 编译等,仅 builder 需要)
RUN sed -i \
        's|http://deb.debian.org/debian-security|https://mirrors.tuna.tsinghua.edu.cn/debian-security|g; \
         s|http://deb.debian.org/debian|https://mirrors.tuna.tsinghua.edu.cn/debian|g' \
        /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && rm -rf /var/lib/apt/lists/*

# pip 镜像加速(国内网络),可用 --build-arg PIP_INDEX_URL=... 覆盖
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

# 安装 Python 依赖(与 pyproject.toml 对齐;pytest 等测试依赖不装入生产镜像)
# 注意:langchain-milvus 0.4.0 要求 pymilvus>=3,而 llama-index-vector-stores-milvus
# 元数据声明 pymilvus<3(1.1.0 运行时兼容 3.x,本地已验证),故分两步安装:
#   1) 主依赖(pymilvus 解析为 3.x)
#   2) --no-deps 补装 llama-index-vector-stores-milvus(依赖已在第 1 步装齐)
RUN pip install --no-cache-dir --index-url ${PIP_INDEX_URL} \
    langchain-core langchain-community \
    "langchain-milvus==0.4.0" langchain-text-splitters \
    "langchain-deepseek==1.1.0" langgraph \
    "langgraph-checkpoint-postgres==3.1.2" \
    akshare "dashscope==1.27.0" "pymilvus==3.0.1" \
    fastapi uvicorn pydantic-settings \
    "pyjwt==2.13.0" "bcrypt==5.0.0" \
    "psycopg[binary,pool]==3.3.4" \
    matplotlib mplfinance \
    "mcp==1.29.1" "langchain-mcp-adapters==0.3.2" \
    "llama-index==0.14.24" \
    requests pandas numpy \
 && pip install --no-cache-dir --index-url ${PIP_INDEX_URL} \
    --no-deps "llama-index-vector-stores-milvus==1.1.0"

# ---------- 阶段 2:runtime ----------
FROM docker.m.daocloud.io/library/python:3.13-slim AS runtime

WORKDIR /app

# 运行时系统库(仅 libpq5,编译工具不进镜像)
RUN sed -i \
        's|http://deb.debian.org/debian-security|https://mirrors.tuna.tsinghua.edu.cn/debian-security|g; \
         s|http://deb.debian.org/debian|https://mirrors.tuna.tsinghua.edu.cn/debian|g' \
        /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
    libpq5 && rm -rf /var/lib/apt/lists/*

# 从 builder 拷贝依赖(runtime 不需要编译工具)
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# 复制代码
COPY src/ /app/src/
COPY frontend/ /app/frontend/
COPY docker-entrypoint.sh /app/docker-entrypoint.sh

# 非 root 运行:创建应用用户,目录属主交给它
RUN useradd --create-home --shell /bin/sh appuser \
    && chown -R appuser:appuser /app \
    && chmod +x /app/docker-entrypoint.sh

# 环境变量
ENV PYTHONPATH=/app/src

EXPOSE 9997

# 健康检查(与 compose 中 finagent 服务的 healthcheck 一致)
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:9997/health')" || exit 1

# 入口脚本以 root 启动(修正卷权限后降权到 appuser,见脚本内逻辑)
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn", "finagent.api.server:app", "--host", "0.0.0.0", "--port", "9997"]
