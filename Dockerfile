# Multi-stage build for AppleBooks Map API
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:3.11-slim

WORKDIR /app

# Copy Python dependencies from builder
COPY --from=builder /root/.local /root/.local

# Copy application code
COPY map/ ./map/
COPY abx/ ./abx/
COPY abxgeo/ ./abxgeo/
COPY setup.py .

# Install the package
RUN pip install --no-cache-dir -e .

# Database will be mounted as a volume or copied at runtime
# Default to looking for DB at /app/data/full_book.sqlite
ENV DB_PATH=/app/data/full_book.sqlite

# Expose port
EXPOSE 8000

# Run the FastAPI server
CMD ["uvicorn", "map.server:app", "--host", "0.0.0.0", "--port", "8000"]
