# Python environment
FROM python:3.9-slim

# Working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project files including main.py, questions.json, etc.
COPY . .

# Set environment variable (Koyeb sets TELEGRAM_BOT_TOKEN & PORT automatically)
ENV PORT=8080

# Expose the port for Flask
EXPOSE 8080

# Run the bot
CMD ["python", "main.py"]
