FROM python:3.9-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl build-essential && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY ./requirements.txt /app/requirements.txt

ARG YT_DLP_VERSION=latest 
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir "yt-dlp${YT_DLP_VERSION:+==${YT_DLP_VERSION}}" && \
    pip install --no-cache-dir -r /app/requirements.txt

COPY ./app /app/app

RUN mkdir -p /app/downloads

EXPOSE 5000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5000"]
