FROM python:3.9

WORKDIR /app

# system deps
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir --upgrade yt-dlp  

COPY . .

ENV FLASK_APP=src.server:app \
    FLASK_RUN_HOST=0.0.0.0 \
    FLASK_RUN_PORT=5000

CMD ["flask", "run", "--no-debugger", "--reload"]
