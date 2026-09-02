# FinAgent 数据备份脚本 (PowerShell / Windows)
# 备份: PostgreSQL 业务数据 + Milvus 向量库卷 + output 输出目录
# 用法: .\scripts\backup.ps1              # 默认备份到 backups/
#       .\scripts\backup.ps1 -Dest D:\bk   # 指定目录
param([string]$Dest = "backups")

$ErrorActionPreference = "Stop"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Dst = Join-Path $Dest $Stamp
New-Item -ItemType Directory -Force -Path $Dst | Out-Null

Write-Host "==> 备份 PostgreSQL"
docker compose exec -T postgres pg_dump -U finagent -d finagent | Out-File -Encoding utf8 (Join-Path $Dst "finagent.sql")
Write-Host "    -> $(Join-Path $Dst 'finagent.sql')"

Write-Host "==> 备份 Milvus 数据卷"
$status = docker compose ps milvus --format '{{.Status}}'
if ($status -match "Up") { Write-Host "    [警告] milvus 正在运行,备份可能不一致;建议: docker compose stop milvus" }
if (Test-Path "volumes\milvus") {
    # Windows tar 可能无法读容器(WSL)写入的文件,失败不阻塞整体备份
    try {
        tar -czf (Join-Path $Dst "milvus_volumes.tar.gz") -C volumes milvus
        Write-Host "    -> $(Join-Path $Dst 'milvus_volumes.tar.gz')"
    } catch {
        Write-Host "    [跳过] Milvus 卷打包失败(Windows 读 WSL 文件受限)。替代方案见 docs\26-docker-backup.md"
    }
} else { Write-Host "    [跳过] volumes\milvus 不存在" }

if (Test-Path "output") {
    tar -czf (Join-Path $Dst "output.tar.gz") -C . output
    Write-Host "    -> $(Join-Path $Dst 'output.tar.gz')"
}

Write-Host ""
Write-Host "备份完成: $Dst"
Write-Host "恢复: .\scripts\restore.ps1 $Dst"
