# MoroAI Production Deployment Playbook

This playbook guides you through deploying MoroAI from your laptop to production.

## Prerequisites

- Python 3.10+
- Docker & Docker Compose
- NVIDIA GPU with 8GB+ VRAM (for training, or Apple Silicon / CPU for development)
- 32GB+ RAM (recommended)
- 100GB+ disk space

## Phase 1: Local Development

### 1.1 Install MoroAI

```bash
# Clone the repository
git clone https://github.com/moroai/moro.git
cd moro

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install in development mode
pip install -e ".[dev,train,dashboard]"
```

### 1.2 Initialize Your Project

```bash
moro init my-project
cd my-project
```

### 1.3 Verify Installation

```bash
moro --version
moro doctor
moro services status
```

## Phase 2: Data Preparation

### 2.1 Add Your Data

```bash
# Copy your data to the raw directory
cp /path/to/your/data.jsonl data/raw/
```

### 2.2 Build the Dataset

```bash
moro data build
moro data report
```

## Phase 3: Training

### 3.1 Generate Recipe

```bash
moro recipe suggest
```

### 3.2 Run Training

```bash
moro train
```

### 3.3 Monitor Training

```bash
# In another terminal
moro dashboard serve
# Open http://localhost:8501 or http://localhost:8765
```

## Phase 4: Evaluation

### 4.1 Run Evaluation

```bash
moro eval compare --run-id <run_id>
```

### 4.2 Review Results

```bash
moro analytics list
moro analytics trend
moro analytics recommend
```

## Phase 5: Release

### 5.1 Export Model

```bash
moro release export --run-id <run_id> --version v1.0.0 --merge
```

### 5.2 Deploy to Ollama

```bash
moro release deploy --target ollama --version v1.0.0
```

### 5.3 Verify Deployment

```bash
# Test the deployed model
curl http://localhost:11434/api/generate -d '{
  "model": "my-model:v1.0.0",
  "prompt": "Hello, how are you?",
  "stream": false
}'
```

## Phase 6: Production Deployment

### 6.1 Build Docker Image

```bash
docker build -t moroai:latest .
```

### 6.2 Deploy with Docker Compose

```bash
docker compose up -d
```

### 6.3 Verify Services

```bash
moro services status
```

### 6.4 Start the Flywheel

```bash
# Start the webhook receiver
moro webhook serve --port 8001 &

# Start the dashboard
moro dashboard serve --port 8501 &

# Start the supervisor (monitors all services)
moro services supervise &
```

## Phase 7: Monitoring

### 7.1 Access Mission Control

Open http://localhost:8501 or http://localhost:8765 in your browser.

### 7.2 View Logs

```bash
moro services logs ollama
moro services logs webhook
moro services logs dashboard
```

### 7.3 Check Health

```bash
curl http://localhost:8501/api/health
```

## Phase 8: Continuous Learning

### 8.1 Collect Feedback

Point your chat UI to the webhook receiver:

```bash
# Your chat UI should POST to:
# http://localhost:8001/webhook/ingest
```

### 8.2 Run the Flywheel

```bash
# Manual trigger
moro flywheel run

# Or schedule with cron
echo "0 2 * * * cd /path/to/my-project && moro flywheel run" | crontab -
```

### 8.3 Monitor Flywheel

```bash
moro flywheel status
```

## Rollback Procedure

If a deployment goes wrong:

```bash
# 1. Stop the flywheel
moro services stop flywheel

# 2. Identify the last good release
moro analytics list

# 3. Roll back to previous version
moro release deploy --target ollama --version v0.9.0

# 4. Verify
curl http://localhost:11434/api/generate -d '{
  "model": "my-model:v0.9.0",
  "prompt": "Hello",
  "stream": false
}'

# 5. Restart services
moro services start all
```

## Troubleshooting

### OOM Errors

```bash
# Reduce batch size
moro recipe suggest --max-batch-size 1

# Or reduce sequence length
moro recipe suggest --max-seq-length 512
```

### Service Won't Start

```bash
# Check logs
moro services logs <service-name>

# Restart the service
moro services restart <service-name>
```

### Database Locked

```bash
# Stop all services
moro services stop all

# Remove lock file
rm .moro/*.db-wal

# Restart
moro services start all
```
