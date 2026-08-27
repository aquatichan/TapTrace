FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY work/backend/requirements.txt /tmp/taptrace-requirements.txt
RUN pip install --no-cache-dir -r /tmp/taptrace-requirements.txt
COPY . /app
RUN useradd --create-home --uid 10001 taptrace && mkdir -p /data /backups && chown -R taptrace:taptrace /data /backups
USER taptrace
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)"
CMD ["python", "work/backend/api.py", "--host", "0.0.0.0", "--port", "8080"]
