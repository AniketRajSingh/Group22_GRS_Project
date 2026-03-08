FROM python:3.10-slim-bookworm

WORKDIR /app

RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    httpx

COPY group22_middleware.py .
COPY group22_telemetry.py .
COPY group22_config.py .

EXPOSE 8080

CMD ["python", "group22_middleware.py"]
