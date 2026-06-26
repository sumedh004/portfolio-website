#!/usr/bin/env python3
"""
Portfolio nginx log metrics exporter.
Tails /var/log/nginx/access.log, parses each line,
and exposes Prometheus metrics on port 8000.
"""
import re
import time
import os
from prometheus_client import (
    start_http_server,
    Counter,
    Histogram,
    Gauge,
    REGISTRY,
    PROCESS_COLLECTOR,
    PLATFORM_COLLECTOR,
)

# Remove default Python process metrics — keep /metrics clean
REGISTRY.unregister(PROCESS_COLLECTOR)
REGISTRY.unregister(PLATFORM_COLLECTOR)

# ── Metric definitions ─────────────────────────────────────────
REQUEST_COUNT = Counter(
    "portfolio_requests_total",
    "Total HTTP requests handled by nginx",
    ["status", "path"],
)

REQUEST_DURATION = Histogram(
    "portfolio_request_duration_seconds",
    "HTTP request duration in seconds",
    ["path"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
)

BYTES_SENT = Counter(
    "portfolio_bytes_sent_total",
    "Total bytes sent by nginx",
    ["path"],
)

PARSE_ERRORS = Counter(
    "portfolio_log_parse_errors_total",
    "Number of nginx log lines that could not be parsed",
)

# ── Log format regex ───────────────────────────────────────────
# Matches: prometheus_format from nginx.conf
# '$remote_addr - $remote_user [$time_local] "$request" $status
#  $body_bytes_sent "$http_referer" "$http_user_agent" rt=$request_time'
LOG_PATTERN = re.compile(
    r'(?P<remote_addr>\S+) - \S+ \[.*?\] '
    r'"(?P<method>\S+) (?P<path>\S+) \S+" '
    r'(?P<status>\d{3}) '
    r'(?P<bytes_sent>\d+) '
    r'".*?" ".*?" '
    r'rt=(?P<request_time>[\d.]+)'
)

# Normalise paths — collapse IDs and hashes to avoid high cardinality
def normalise_path(path: str) -> str:
    # Strip query strings
    path = path.split("?")[0]
    # Collapse asset paths to their extension group
    if re.search(r'\.(css|js|png|jpg|jpeg|svg|ico|woff2)$', path):
        return "/static"
    # Keep known paths, collapse everything else
    known = {"/", "/index.html", "/healthz", "/nginx_status", "/metrics"}
    return path if path in known else "/other"

def tail_log(log_path: str):
    """
    Open log file and yield new lines as they are written.
    Handles log rotation by re-opening if file shrinks.
    """
    while not os.path.exists(log_path):
        print(f"Waiting for log file: {log_path}")
        time.sleep(2)

    with open(log_path, "r") as f:
        # Start at end of file — don't re-process existing lines on restart
        f.seek(0, 2)
        last_size = f.tell()
        while True:
            line = f.readline()
            if line:
                yield line.strip()
            else:
                time.sleep(0.1)
                # Detect log rotation
                current_size = os.path.getsize(log_path)
                if current_size < last_size:
                    f.seek(0)
                last_size = current_size

def process_line(line: str):
    match = LOG_PATTERN.match(line)
    if not match:
        PARSE_ERRORS.inc()
        return

    path        = normalise_path(match.group("path"))
    status      = match.group("status")
    bytes_sent  = int(match.group("bytes_sent"))
    request_time = float(match.group("request_time"))

    # Skip internal nginx endpoints from metrics to avoid noise
    if path in ("/nginx_status", "/healthz"):
        return

    REQUEST_COUNT.labels(status=status, path=path).inc()
    REQUEST_DURATION.labels(path=path).observe(request_time)
    BYTES_SENT.labels(path=path).inc(bytes_sent)

if __name__ == "__main__":
    log_path = os.environ.get("NGINX_LOG_PATH", "/var/log/nginx/access.log")
    port     = int(os.environ.get("METRICS_PORT", "8000"))

    print(f"Starting metrics exporter on :{port}")
    print(f"Tailing log file: {log_path}")
    start_http_server(port)

    for line in tail_log(log_path):
        process_line(line)