# Build stage for dependencies
FROM python:3.10-slim-bookworm as builder

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    pkg-config \
    ninja-build \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir scikit-build-core ninja && \
    CMAKE_ARGS="-DGGML_OPENBLAS=off -DGGML_NATIVE=OFF" FORCE_CMAKE=1 \
    pip install --no-cache-dir \
    fastapi \
    uvicorn \
    pydantic \
    psutil \
    llama-cpp-python

# Final stage
FROM python:3.10-slim-bookworm

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy dependencies from builder
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY group22_app.py .

# Environment variables
ENV MODEL_PATH=/models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf
ENV N_THREADS=4
ENV NODE_ID=node-1

# Create models directory
RUN mkdir -p /models

EXPOSE 8000

CMD ["python", "-u", "group22_app.py"]
