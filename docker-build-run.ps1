# DiskStat — kettakasutus analuus
# Topeltklõpsa või käivita: powershell -ExecutionPolicy Bypass -File docker-build-run.ps1

$ErrorActionPreference = "Stop"

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  DiskStat — kettakasutus analuus" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

# Kontrolli Docker olemasolu
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "VIGA: Docker ei ole installitud või pole PATH-is." -ForegroundColor Red
    Write-Host "Paigalda Docker Desktop: https://www.docker.com/products/docker-desktop/" -ForegroundColor Yellow
    pause
    exit 1
}

# 1. Build
Write-Host "[1/3] Docker image ehitamine..." -ForegroundColor Green
docker build -t diskstat:latest .

# 2. Run — skaneeri C: ketas, väljund Downloads/diskstat-output
$outDir = "$env:USERPROFILE\Downloads\diskstat-output"
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir | Out-Null }

Write-Host "[2/3] Skaneerimine - C: ketas..." -ForegroundColor Green
docker run --rm -v "C:\:/mnt/c" -v "${outDir}:/out" diskstat:latest /mnt/c/ -o /out

# 3. Ava raport brauseris
$report = Get-ChildItem -Path $outDir -Recurse -Filter "report.html" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($report) {
    Write-Host "[3/3] Raport avatud: $($report.FullName)" -ForegroundColor Green
    Start-Process $report.FullName
} else {
    Write-Host "Raporti ei leitud. Kontrolli: $outDir" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Valmis!" -ForegroundColor Cyan
pause
