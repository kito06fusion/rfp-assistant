FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        poppler-utils \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libfontconfig1 \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        shared-mime-info \
        libgobject-2.0-0 && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --upgrade pip && \
    pip install -r requirements.txt

COPY backend backend
COPY frontend frontend
COPY image.png image.png
COPY docs ./docs

EXPOSE 8001

CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8001"]


