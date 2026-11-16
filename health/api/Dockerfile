# Health API for Cloud Run (or any container host). uvicorn binds $PORT.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY migrations ./migrations
ENV PORT=8080 HEALTH_DATA_DIR=/data
VOLUME ["/data"]
EXPOSE 8080
CMD exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}" --workers 1
