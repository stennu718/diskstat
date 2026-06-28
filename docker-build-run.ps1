# DiskStat — kettakasutus analüüs
# Topeltklõpsa või käivita: powershell -ExecutionPolicy Bypass -File docker-build-run.ps1

$ErrorActionPreference = "Stop"

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  DiskStat — kettakasutus analüüs" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

# Kontrolli Docker olemasolu
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "VIGA: Docker ei ole installitud või pole PATH-is." -ForegroundColor Red
    Write-Host "Paigalda Docker Desktop: https://www.docker.com/products/docker-desktop/" -ForegroundColor Yellow
    pause
    exit 1
}

# Vali image — GHCR (soovitatud) või lokaalne build
$image = "ghcr.io/y84312/diskstat:latest"
$useLocal = $false

# Tõmmata GHCR image (kui pole lokaalselt)
Write-Host "[1/3] Docker image kontroll... (vajadusel tõmbamine)" -ForegroundColor Green
$localExists = docker images $image --format '{{.Repository}}' 2>$null
if (-not $localExists) {
    try {
        docker pull $image
    } catch {
        Write-Host "GHCR tõmbamine ebaõnnestus, kasutatakse lokaalset buildi..." -ForegroundColor Yellow
        docker build -t diskstat:latest .
        $image = "diskstat:latest"
    }
}

# Väljundkaust
$outDir = "$env:USERPROFILE\Downloads\diskstat-output"
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir | Out-Null }

# Skaneeri
Write-Host "[2/3] Skaneerimine — C: ketas..." -ForegroundColor Green
docker run --rm -v "C:\:/mnt/c" -v "${outDir}:/out" $image /mnt/c -o /out

# Ava raport
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
