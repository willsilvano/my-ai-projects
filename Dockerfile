FROM python:3.12-slim

WORKDIR /app

# Instala dependências do sistema
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Instala UV - gerenciador de pacotes Python ultra rápido
RUN curl -sSf https://install.ultraviolet.rs | sh
ENV PATH="/root/.cargo/bin:${PATH}"

# Copia os arquivos do projeto
COPY pyproject.toml ./
COPY uv.lock ./
COPY table_mapping.json ./
COPY src/ ./src/

# Instala dependências usando UV
RUN uv pip install -e .

# Volume para persistência de dados
VOLUME /app/data

# Porta para o Streamlit
EXPOSE 8501

# Comando para iniciar a aplicação
CMD ["streamlit", "run", "src/app.py", "--server.port=8501", "--server.address=0.0.0.0"]