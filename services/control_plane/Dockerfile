FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
RUN pip install --no-cache-dir uv==0.4.18

WORKDIR /app
# Copy workspace metadata first for layer caching
COPY pyproject.toml uv.lock /app/
COPY packages /app/packages
COPY services/control_plane /app/services/control_plane
COPY scripts /app/scripts

RUN uv sync --frozen --package control-plane --no-dev
ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /app/services/control_plane
COPY services/control_plane/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "control_plane.main:app", "--host", "0.0.0.0", "--port", "8000"]
