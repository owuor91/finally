# Build (if needed) and run the FinAlly container. Idempotent.
# Usage: .\scripts\start_windows.ps1 [-Build]
param([switch]$Build)
$ErrorActionPreference = "Stop"

$Image = "finally"
$Container = "finally"
$Port = "8000"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".env")) {
    Write-Host "No .env found. Copy .env.example to .env and add your keys:"
    Write-Host "  Copy-Item .env.example .env"
    exit 1
}

docker image inspect $Image *> $null
if ($Build -or ($LASTEXITCODE -ne 0)) {
    Write-Host "Building image '$Image'..."
    docker build -t $Image .
}

docker rm -f $Container *> $null

docker run -d --name $Container `
    -p "${Port}:8000" `
    --env-file .env `
    -v finally-data:/app/db `
    $Image

$Url = "http://localhost:$Port"
Write-Host "FinAlly is running at $Url"
Start-Process $Url
