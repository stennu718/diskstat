FROM python:3.12-slim

LABEL org.opencontainers.image.title="DiskStat"
LABEL org.opencontainers.image.description="Disk usage analyzer with interactive treemap"
LABEL org.opencontainers.image.source="https://github.com/y84312/diskstat"
LABEL org.opencontainers.image.version="1.0.0"

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY . /app/

ENTRYPOINT ["python", "diskstat.py"]
CMD ["/"]
