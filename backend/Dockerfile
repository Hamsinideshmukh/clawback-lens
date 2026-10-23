# Build context: repository root (the image needs both backend/ and native/).

# ---- Build the C++ image kernel into a wheel -------------------------------
# The full image ships a C++ toolchain; scikit-build-core fetches CMake from PyPI.
FROM python:3.12 AS native
COPY native /src/native
RUN pip wheel --no-cache-dir /src/native -w /wheels

# ---- Runtime ----------------------------------------------------------------
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install -r requirements.txt
COPY --from=native /wheels /wheels
RUN pip install /wheels/*.whl && rm -rf /wheels

COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
COPY backend/models ./models
COPY backend/app ./app

RUN useradd --create-home --uid 10001 clawback
USER clawback
# Fail the build early if the bundled OCR models cannot be loaded.
RUN python -c "from app.vision.ocr import warm_up; warm_up()"

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://localhost:{os.getenv(\"PORT\", \"8000\")}/health', timeout=4)"
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
