FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy package metadata first for better layer caching
COPY pyproject.toml .
COPY README.md .

# Install Python dependencies
RUN pip install --no-cache-dir -e ".[train,dashboard]"

# Copy source code
COPY src/ ./src/

# Create necessary operational directories
RUN mkdir -p /app/data/raw /app/data/dpo /app/.moro /app/runs /app/releases /app/eval

# Set environment variables
ENV PYTHONPATH=/app/src
ENV MORO_PROJECT_ROOT=/app

# Expose microservice ports: Gateway (8000), Webhook (8001), Dashboard (8501)
EXPOSE 8000 8001 8501

# Default command starts Mission Control Dashboard
CMD ["python", "-m", "uvicorn", "moro.dashboard.mission_control:mission_app", "--host", "0.0.0.0", "--port", "8501"]
