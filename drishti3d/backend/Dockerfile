# Drishti3D backend (CPU). Offline-capable once built.
FROM python:3.11-slim

# System libs for OpenCV / Open3D headless rendering.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install reconstruction package first (better layer caching).
COPY reconstruction/ /app/reconstruction/
RUN pip install --no-cache-dir -e /app/reconstruction \
    && pip install --no-cache-dir open3d laspy

# Backend requirements.
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend/ /app/backend/
COPY sample_data/ /app/sample_data/

ENV DRISHTI_HOST=0.0.0.0 DRISHTI_DATA_DIR=/app/data
EXPOSE 8000
WORKDIR /app/backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
