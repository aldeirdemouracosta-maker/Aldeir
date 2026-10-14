FROM python:3.12-slim-bookworm

# ngspice (simulação em modo batch) – nenhuma biblioteca gráfica é necessária
RUN apt-get update && apt-get install -y --no-install-recommends ngspice \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN useradd -m forge && chown -R forge /app
USER forge

# O LLM roda em um contêiner separado (ver docker-compose.yml) ou no host: defina OLLAMA_HOST.
ENV OLLAMA_HOST=http://ollama:11434 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
EXPOSE 8501
HEALTHCHECK CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8501/_stcore/health')" || exit 1
CMD ["streamlit", "run", "app/main.py", "--server.port=8501", "--server.address=0.0.0.0"]
