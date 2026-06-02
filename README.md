# DiskStat

Kettakasutuse analüüs — skaneerib kataloogi ja loob interaktsiivse treemap raporti + CSV väljundi.

![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)
![Tests](https://github.com/y84312/diskstat/actions/workflows/docker.yml/badge.svg)
![Docker](https://img.shields.io/badge/docker-available-blue.svg)

## Kiired näited

```bash
# Skaneeri C: ketas (WSL)
python diskstat.py

# JSON väljund
python diskstat.py /mnt/c/ --format json

# Live progress
python diskstat.py /mnt/c/ --progress

# Kohandatud väljund
python diskstat.py /home/user/Downloads -o /tmp/my-report
```

### Väljund

```json
{
  "ok": true,
  "target": "/mnt/c/",
  "stats": {
    "files": 152340,
    "dirs": 28471,
    "elapsed_s": 12.3
  },
  "total_human": "485.2 GB",
  "nodes_included": 5000,
  "output": {
    "html": "diskstat/20260602_143022/report.html",
    "csv": "diskstat/20260602_143022/files.csv"
  }
}
```

## Kasutamine

### Docker (soovitatud)

```powershell
# Windows PowerShell
docker run --rm -v C:\:/mnt/c -v ${HOME}\diskstat-output:/out `
  ghcr.io/y84312/diskstat:latest /mnt/c/ -o /out
```

Või topeltklõpsa `docker-build-run.ps1`.

### Käsurealt

```bash
python diskstat.py [PATH] [OPTIONS]

Options:
  -o, --out DIR          Väljundkaust (vaikimisi: diskstat/YYYYMMDD_HHMMSS)
  --open                 Ava HTML raport peale loomist
  -m, --max-nodes N      Maksimaalse arv visualiseerimiseks (1-500000, vaikimisi 5000)
  --format {text,json}   Väljundi formaat
  --progress             Kuva skaneerimise edenemist
  --no-color             Väljasta ilma värvideta
  --min-size BYTES      Jäta väiksemad failid välja
  --category CAT         Filtreeri kategooriale (mitmekordne)
  --exclude DIR          Jäta kataloog välja (mitmekordne: .git, node_modules)
```

## Docker image

```powershell
docker pull ghcr.io/y84312/diskstat:latest
```

## Arendamine

```bash
uv tool run pytest tests/ -v
```

## Arhitektuur

- **Python 3.11+**, ainult stdlib (ei välis sõltuvusi)
- **D3.js** treemap visuaalisatsioon HTML-s
- **Zero-config**: `python diskstat.py` töötab kohe
- **Turvaline**: XSS guard, subprocess.shell=False, max_nodes clamp, CSP meta tag

## Litsents

MIT
