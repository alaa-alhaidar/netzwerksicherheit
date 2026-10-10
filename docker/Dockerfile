FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends nmap iputils-ping iproute2 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY scanner/ scanner/
ENV PYTHONUNBUFFERED=1 MONITOR_DB=/data/monitor.sqlite3
