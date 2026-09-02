#!/usr/bin/env bash
# FinAgent 数据恢复脚本
# 用法: ./scripts/restore.sh backups/20260101_120000
# 前置: 容器需已启动(docker compose up -d),恢复 PG 前应用会短暂不可用
set -euo pipefail

SRC="${1:?用法: ./scripts/restore.sh <备份目录>}"
[ -d "$SRC" ] || { echo "错误: 备份目录不存在: $SRC"; exit 1; }

echo "==> 恢复 PostgreSQL (DROP + 导入)"
docker compose exec -T postgres psql -U finagent -d finagent -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" >/dev/null
docker compose exec -T postgres psql -U finagent -d finagent < "$SRC/finagent.sql"
echo "    ✅ PostgreSQL 已恢复"

if [ -f "$SRC/milvus_volumes.tar.gz" ]; then
  echo "==> 恢复 Milvus 数据卷"
  docker compose stop milvus >/dev/null 2>&1 || true
  rm -rf volumes/milvus
  mkdir -p volumes
  tar -xzf "$SRC/milvus_volumes.tar.gz" -C volumes
  echo "    ✅ Milvus 卷已恢复,重新启动 milvus"
  docker compose up -d milvus
else
  echo "[跳过] 备份中无 Milvus 卷"
fi

if [ -f "$SRC/output.tar.gz" ]; then
  echo "==> 恢复输出目录"
  tar -xzf "$SRC/output.tar.gz" -C .
  echo "    ✅ output 已恢复"
fi

echo
echo "==> 重启应用以加载恢复的数据"
docker compose up -d
echo "✅ 恢复完成,请验证: curl http://localhost:9996/health"
