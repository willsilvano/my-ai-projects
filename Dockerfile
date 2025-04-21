# -------------------------
# Stage 1: Build com UV
# -------------------------
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

# Define variáveis de ambiente para otimização
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Copia arquivos necessários
COPY pyproject.toml uv.lock ./

# Instala dependências sem as de desenvolvimento
RUN uv sync --frozen --no-dev

# -------------------------------
# Stage 2: Imagem final leve
# -------------------------------
FROM python:3.12-slim-bookworm AS final

WORKDIR /app

# Copia ambiente virtual da build
COPY --from=builder /app /app

# Copia o restante do código da aplicação
COPY table_mapping.json ./
COPY src/ ./src/
COPY .streamlit /app/.streamlit

# Define ambiente virtual como padrão
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8501

ENTRYPOINT ["streamlit", "run", "src/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
