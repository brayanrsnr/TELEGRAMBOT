# Dockerfile : force Python 3.10 (imghdr inclus)
FROM python:3.10-slim

# Dossier de travail
WORKDIR /app

# Options Python propres
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Paquets système utiles (et timezone)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata ca-certificates && rm -rf /var/lib/apt/lists/*

# Dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code
COPY . .

# Lancement du bot
CMD ["python", "main.py"]
