# Drishti3D read-only showcase: the API, the built UI and the exported missions
# in one container.
#
# The build context is the folder scripts/build_space.py assembles, not the
# repository: the repository's data/ is ~74 GB, and the folder is also what gets
# uploaded to a Hugging Face Space. It serves on port 7860 as uid 1000, which is
# what a Docker Space expects; any other Docker host runs it the same way.

FROM node:22-alpine AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
RUN useradd -m -u 1000 user
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY reconstruction/ reconstruction/
RUN pip install --no-cache-dir --no-deps ./reconstruction
COPY backend/ backend/
COPY --from=ui /ui/dist frontend/dist
# Owned by the server's user: at startup it restores the artifact times an
# upload resets (backend/app/showcase.py), which needs ownership.
COPY --chown=user showcase-data/ data/

USER user
ENV DRISHTI_READ_ONLY=1 \
    DRISHTI_DATA_DIR=/app/data \
    DRISHTI_FRONTEND_DIST=/app/frontend/dist \
    DRISHTI_SANDBOX_DIR=/tmp/drishti3d-sandboxes \
    PYTHONUNBUFFERED=1
EXPOSE 7860
# One worker: each visitor's sandbox is tracked inside the process
# (backend/app/sandbox.py), so a second worker would not find it.
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "7860"]
