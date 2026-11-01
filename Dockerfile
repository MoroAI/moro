FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/moro
RUN apt-get update && apt-get install -y --no-install-recommends curl git \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home moro
COPY pyproject.toml README.md LICENSE ./
COPY requirements/eval.lock ./requirements/eval.lock
COPY src/ ./src/
# Web services do not need the GPU training stack. Training uses its own environment.
# Install the frozen eval lock first, then the package itself with --no-deps so the
# image cannot drift from the lock (see requirements/README.md).
RUN pip install --no-cache-dir -r requirements/eval.lock \
    && pip install --no-cache-dir --no-deps . \
    && mkdir /workspace && chown moro:moro /workspace
USER moro
WORKDIR /workspace
EXPOSE 8000 8001 8501
CMD ["python", "-m", "uvicorn", "moro.dashboard.mission_control:mission_app", "--host", "0.0.0.0", "--port", "8501"]
