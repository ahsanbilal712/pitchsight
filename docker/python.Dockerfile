# Backend image for docker-compose.yml (api, mcp, newsroom): Python 3.12, CPU torch, requirements.lock (T-064).
# Code only; ./data and ./.checkpoints are mounted at run time.
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONPATH=/app/packages PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1 WHYLINE_DEVICE=cpu
COPY requirements.lock ./
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu "torch==2.14.1" \
 && pip install --no-cache-dir -r requirements.lock
COPY packages ./packages
COPY scripts ./scripts
COPY config ./config
COPY schemas ./schemas
