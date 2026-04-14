FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .

ENV SERVICE_NAME=monitored-service-1
ENV MONITORING_URL=http://monitoring-backend:8000
ENV METRICS_INGEST_TOKEN=dev-internal-metrics-token
ENV CHAOS_MODE=false

EXPOSE 9000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9000"]
