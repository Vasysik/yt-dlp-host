FROM python:3.9

WORKDIR /app

# system deps
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV FLASK_APP=src.server:app \
    FLASK_RUN_HOST=0.0.0.0

# Use Gunicorn for production on Cloud Run
# It listens on the port specified by the PORT environment variable ($PORT)
# Use /bin/sh -c to ensure $PORT variable expansion
CMD ["/bin/sh", "-c", "gunicorn --bind 0.0.0.0:$PORT --workers 4 --log-level info --timeout 300 src.server:app"]
