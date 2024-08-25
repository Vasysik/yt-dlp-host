FROM python:3.9-slim

RUN apt-get -y update && apt-get -y upgrade && apt-get install -y ffmpeg

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["flask", "run"]
