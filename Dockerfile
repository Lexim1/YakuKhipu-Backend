FROM node:24-alpine AS frontend
RUN apk add --no-cache git
ARG FRONTEND_COMMIT=8cf2b6f2fc7479e6c5a04ced76bf7442edcee462
WORKDIR /frontend
RUN git init && git remote add origin https://github.com/Lexim1/YakuKhipu.git \
    && git fetch --depth 1 origin "$FRONTEND_COMMIT" && git checkout --detach FETCH_HEAD
RUN npm ci --no-audit --no-fund
ENV VITE_API_URL= VITE_USAR_EJEMPLOS=false
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils tesseract-ocr tesseract-ocr-spa \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY --from=frontend /frontend/dist ./frontend_dist
RUN useradd --create-home yakukhipu
USER yakukhipu
CMD ["/bin/sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --no-access-log"]
