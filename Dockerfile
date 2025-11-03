FROM python:3.11-slim

WORKDIR /app

# Copy and install dependencies
COPY . .
RUN pip3 install -r requirements.txt

EXPOSE 5000

# Health check
HEALTHCHECK CMD curl -f http://localhost:5000/ || exit 1

CMD ["python", "bot.py"]
