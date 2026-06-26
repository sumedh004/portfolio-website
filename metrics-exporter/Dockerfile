FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy exporter script
COPY exporter.py .

# Run as non-root user
RUN useradd -r -u 1001 exporter
USER exporter

EXPOSE 8000

CMD ["python", "-u", "exporter.py"]
