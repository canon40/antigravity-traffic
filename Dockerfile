FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements-cloud.txt /app/requirements-cloud.txt
RUN pip install --no-cache-dir -r /app/requirements-cloud.txt

COPY . /app

ENV PORT=8766
EXPOSE 8766

CMD ["sh", "-c", "uvicorn api.jarvis_mobile_server:app --host 0.0.0.0 --port ${PORT}"]
