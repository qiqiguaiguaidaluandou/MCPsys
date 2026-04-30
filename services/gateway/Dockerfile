FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
RUN pip install --no-cache-dir uv==0.4.18

WORKDIR /app
COPY pyproject.toml uv.lock /app/
COPY packages /app/packages
COPY services/gateway /app/services/gateway

RUN uv sync --frozen --package gateway --no-dev
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8080
CMD ["uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8080"]
