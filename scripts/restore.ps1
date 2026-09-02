# FinAgent 数据恢复脚本 (PowerShell / Windows)
# 用法: .\scripts\restore.ps1 backups\20260830_102500
param([Parameter(Mandatory=$true)][string]$Src)

$ErrorActionPreference = "Stop"
if (-not (Test-Path $Src)) { Write-Error "备份目录不存在: $Src"; exit 1 }

Write-Host "==> 恢复 PostgreSQL (DROP + 导入)"
docker compose exec -T postgres psql -U finagent -d finagent -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" | Out-Null
Get-Content (Join-Path $Src "finagent.sql") -Raw | docker compose exec -T postgres psql -U finagent -d finagent | Out-Null
Write-Host "    PostgreSQL 已恢复"

if (Test-Path (Join-Path $Src "milvus_volumes.tar.gz")) {
    Write-Host "==> 恢复 Milvus 数据卷"
    docker compose stop milvus | Out-Null
    Remove-Item -Recurse -Force volumes\milvus -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path volumes | Out-Null
    tar -xzf (Join-Path $Src "milvus_volumes.tar.gz") -C volumes
    docker compose up -d milvus | Out-Null
    Write-Host "    Milvus 卷已恢复"
}

if (Test-Path (Join-Path $Src "output.tar.gz")) {
    Write-Host "==> 恢复输出目录"
    tar -xzf (Join-Path $Src "output.tar.gz") -C .
}

Write-Host "==> 重启应用"
docker compose up -d | Out-Null
Write-Host "恢复完成,验证: curl http://localhost:9996/health"
