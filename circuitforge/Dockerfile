FROM python:3.12-slim-bookworm

# Dependências de sistema para ngspice + renderização
RUN apt-get update && apt-get install -y --no-install-recommends \
    ngspice \
    libngspice0-dev \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instalar Ollama (runtime)
RUN curl -fsSL https://ollama.com/install.sh | sh

COPY . .

EXPOSE 8501

# Modelo leve recomendado (<1 GB quantizado)
# No primeiro start: ollama pull phi3:mini  ou  qwen2:0.5b  ou  gemma2:2b

CMD ["streamlit", "run", "app/main.py", "--server.port=8501", "--server.address=0.0.0.0"]
