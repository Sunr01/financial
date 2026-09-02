#!/usr/bin/env bash
# FinAgent 数据备份脚本
# 备份内容:
#   1) PostgreSQL 业务数据(用户/会话/策略/账户)→ SQL 文件
#   2) Milvus 向量库(volumes/milvus 目录)→ tar.gz
# 用法:
#   ./scripts/backup.sh                # 默认备份到 backups/
#   ./scripts/backup.sh /path/to/dir   # 指定备份目录
set -euo pipefail

BK_DIR="${1:-backups}"
STAMP="$(date +%Y%m%d_%H%M%S)"
DEST="$BK_DIR/$STAMP"
mkdir -p "$DEST"

echo "==> 备份 PostgreSQL"
docker compose exec -T postgres pg_dump -U finagent -d finagent > "$DEST/finagent.sql"
echo "    -> $DEST/finagent.sql ($(du -h "$DEST/finagent.sql" | cut -f1))"

echo "==> 备份 Milvus 数据卷(建议先 docker compose stop milvus 保证一致性)"
if docker compose ps milvus --format '{{.Status}}' | grep -q Up; then
  echo "    [警告] milvus 正在运行,备份可能不一致;建议先执行: docker compose stop milvus"
fi
tar -czf "$DEST/milvus_volumes.tar.gz" -C volumes milvus 2>/dev/null \
  || echo "    [跳过] volumes/milvus 不存在"
echo "    -> $DEST/milvus_volumes.tar.gz"

echo "==> 备份输出目录(output)"
tar -czf "$DEST/output.tar.gz" -C . output 2>/dev/null || true

echo
echo "✅ 备份完成: $DEST"
echo "恢复: ./scripts/restore.sh $DEST"
