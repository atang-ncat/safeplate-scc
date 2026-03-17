FROM ubuntu:22.04

# SafePlate SCC — ARM64 Container for NVIDIA DGX Spark (GB10 Blackwell)
# Follows container-first deployment philosophy per SKILL.md
LABEL maintainer="SafePlate Team"
LABEL description="AI-Powered Food Safety Intelligence for Santa Clara County"
LABEL platform="linux/arm64"

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3 python3-pip python3-venv \
    curl wget \
    && rm -rf /var/lib/apt/lists/*

# Install PyTorch with CUDA 13.0 (required for sm_121 / GB10 Blackwell)
RUN pip3 install torch --index-url https://download.pytorch.org/whl/cu130

# Create app directory
WORKDIR /app

# Copy requirements and install Python deps
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py llm_service.py data_pipeline.py ./
COPY static/ ./static/
COPY openclaw_mcp/ ./openclaw_mcp/

# Copy pre-built database (37.3 MB)
COPY safeplate.db .

# Expose web app port
EXPOSE 8888

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8888/api/stats || exit 1

# Start the web app
# LLM server (llama.cpp) runs separately on the host
CMD ["python3", "app.py"]
