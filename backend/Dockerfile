# syntax=docker/dockerfile:1

# ---- builder ----
FROM python:3.12-slim AS builder

# gcc defensivo: se algum pacote nao tiver wheel cp312 para linux/amd64,
# o pip precisa compilar. Custo zero na imagem final.
RUN apt-get update && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Instala o pacote em modo nao-editable e gera wheels das dependencias.
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip wheel --no-cache-dir --wheel-dir /wheels .

# ---- runtime ----
FROM python:3.12-slim AS runtime

WORKDIR /app

# Instala os wheels gerados no builder, sem acessar PyPI.
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels caixaclaro-backend \
    && rm -rf /wheels

# Migrations NAO entram no wheel (packages.find so cobre src/).
# Copiadas explicitamente e referenciadas via MIGRATIONS_DIR.
COPY migrations/ /app/migrations/
ENV MIGRATIONS_DIR=/app/migrations

EXPOSE 8000

CMD ["uvicorn", "caixaclaro.main:app", "--host", "0.0.0.0", "--port", "8000"]
