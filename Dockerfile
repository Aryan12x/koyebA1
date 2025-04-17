# Base image
FROM python:3.9-slim

# Install required OS packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    libssl-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Working directory
WORKDIR /app

# Copy dependencies
COPY requirements.txt .

# Install Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project files (main.py, jsons etc.)
COPY . .

# Default port
ENV PORT=8080
EXPOSE 8080

# Start the bot
CMD ["python", "main.py"]
