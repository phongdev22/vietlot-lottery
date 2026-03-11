FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Environment variables will be passed from docker-compose or .env
ENV PYTHONUNBUFFERED=1

# Script to run both Flask and Telegram Bot in parallel
CMD ["sh", "-c", "python crawler.py & python app.py & python bot.py"]
