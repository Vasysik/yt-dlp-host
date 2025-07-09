FROM python:3.9

WORKDIR /app

COPY requirements.txt .
RUN apt update && \
    apt install ffmpeg -y && \
    pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/downloads /app/jsons

ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD exec gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 0 --preload src.server:app
