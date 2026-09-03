FROM python:3.11-slim

WORKDIR /app
COPY meteo_telegram_bot.py .

ENV PYTHONUNBUFFERED=1

CMD ["python", "meteo_telegram_bot.py"]
