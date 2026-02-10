# Usa Python 3.10 slim (leggero)
FROM python:3.10-slim

# Imposta la cartella di lavoro nel container
WORKDIR /app

# Installa dipendenze di sistema (necessarie per alcune lib scientifiche)
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copia il file dei requisiti e installa le librerie
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Espone le porte per Jupyter (8888), API (8000), Streamlit (8501), Flask (5000)
EXPOSE 8000 8501 5000

# Comando di default (verrà sovrascritto dal docker-compose)
CMD ["bash"]
