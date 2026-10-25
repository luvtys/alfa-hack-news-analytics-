FROM python:3.11-slim

WORKDIR /app

# Системные зависимости для chromadb и sentence-transformers
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Копируем requirements и ставим зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь бэкенд
COPY . .

# Открываем порт
EXPOSE 8000

# Запускаем сервер
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]