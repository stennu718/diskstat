# DiskStat

Kettakasutuse analüüs, mis skaneerib kataloogi ja loob interaktiivse treemap raporti + CSV väljundi.

## Kasutamine

### Kiirstart (Windows)

Topeltklõpsa faili `docker-build-run.ps1` või käivita PowerShellis:

```powershell
powershell -ExecutionPolicy Bypass -File docker-build-run.ps1
```

See teha:
1. Ehitab Docker image
2. Skaneerib C: ketta
3. Avab raporti brauseris

Väljund läheb: `~/Downloads/diskstat-output/`

### Käsurealt (ilma Dockerita, WSL)

```bash
python diskstat.py /path/to/scan -o /path/to/output
```

### Docker käsitsi

```powershell
docker build -t diskstat:latest .
docker run --rm -v C:\:/mnt/c -v %USERPROFILE%\Downloads\diskstat-output:/out diskstat:latest /mnt/c/ -o /out
```

## Nõuded

- **Docker Desktop** (Windowsis topeltklõpsu jaoks)
- Või **Python 3.11+** otsesel käivitamiseks

## Väljund

- `report.html` — interaktiivne treemap (D3.js), saab klõpsata kaustade peal
- `files.csv` — detailne failinimekiri
