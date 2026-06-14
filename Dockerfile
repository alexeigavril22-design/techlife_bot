FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ARG BOT_TOKEN
ARG ADMIN_IDS
ARG TIMEZONE
ENV BOT_TOKEN=$BOT_TOKEN
ENV ADMIN_IDS=$ADMIN_IDS
ENV TIMEZONE=$TIMEZONE
CMD ["python", "bot.py"]
