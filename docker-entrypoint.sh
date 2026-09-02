#!/bin/sh
# FinAgent 容器入口：
#   1) 修正挂载卷权限（output 需可写）
#   2) 首次启动检测知识库是否已入库（Milvus），未入库则自动入库（失败不阻塞启动）
#   3) 以非 root(appuser)启动 Web 服务
set -e

echo "[entrypoint] FinAgent starting..."

# ---------- 挂载卷权限修正(仅 root 时执行) ----------
if [ "$(id -u)" = "0" ]; then
  # output 是宿主机挂载的 bind 卷,属主可能是 root,需要让 appuser 可写
  mkdir -p /app/output
  chown -R appuser:appuser /app/output 2>/dev/null || echo "[entrypoint] 警告:output 卷 chown 失败"
  # 知识库文档只读挂载,无需修改权限
fi

# ---------- 知识库自动入库(幂等) ----------
if [ -d /app/docs/knowledge ] && ls /app/docs/knowledge/*.md >/dev/null 2>&1; then
  echo "[entrypoint] 检测到知识库文档，检查是否已入库..."
  python - <<'PY' || echo "[entrypoint] 知识库入库失败（不阻塞启动）。可稍后手动执行: docker compose exec finagent python -m finagent.rag.ingest"
from pymilvus import utility, connections
from finagent.config import settings

try:
    connections.connect(host=settings.milvus_host, port=settings.milvus_port, timeout=10)
    if utility.has_collection("fin_docs"):
        print("[entrypoint] 知识库已入库（fin_docs 集合存在），跳过")
    else:
        print("[entrypoint] 知识库未入库，开始入库...")
        from pathlib import Path
        from finagent.rag.ingest import build_vector_store
        build_vector_store(Path("/app/docs/knowledge"))
        print("[entrypoint] 知识库入库完成")
except Exception as e:
    print(f"[entrypoint] 入库检查失败: {e}")
PY
else
  echo "[entrypoint] 未找到知识库文档（/app/docs/knowledge），跳过入库。挂载 ./docs/knowledge 后重启即可。"
fi

echo "[entrypoint] 启动 Web 服务..."
# matplotlib 需要可写缓存目录(appuser 无 HOME 写权限)
export MPLCONFIGDIR=/tmp/matplotlib
mkdir -p "$MPLCONFIGDIR"
chown -R appuser:appuser "$MPLCONFIGDIR" 2>/dev/null || true
if [ "$(id -u)" = "0" ]; then
  # 降权到 appuser 后启动(用 python 实现,避免依赖 su/gosu 等工具)
  exec python -c '
import os, pwd, sys
pw = pwd.getpwnam("appuser")
os.setgid(pw.pw_gid)
os.setuid(pw.pw_uid)
os.execvp(sys.argv[1], sys.argv[1:])
' "$@"
else
  exec "$@"
fi
