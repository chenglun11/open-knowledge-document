# syntax=docker/dockerfile:1
ARG NODE_IMAGE=node:24-alpine
ARG PYTHON_IMAGE=python:3.12-slim

FROM ${NODE_IMAGE} AS web-build
WORKDIR /build/web
COPY web/package.json web/package-lock.json ./
RUN npm install --include=optional
COPY web/ ./
RUN npm run build

FROM ${PYTHON_IMAGE} AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OKD_WEB_DIST=/app/workbench
WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/
RUN python -m pip install --no-cache-dir ".[workbench,validation]"

COPY --from=web-build /build/web/dist/ /app/workbench/

RUN useradd --create-home --uid 10001 okd
USER okd
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)"

CMD ["uvicorn", "open_knowledge_document.server:app", "--host", "0.0.0.0", "--port", "8000"]
