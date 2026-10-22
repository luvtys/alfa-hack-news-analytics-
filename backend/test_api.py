import os
from openai import OpenAI
from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv()

client = OpenAI(
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL"),
)

print("🔄 Пингуем API (это может занять до 60 секунд, пока сервер 'просывается')...")
print(f"URL: {os.getenv('LLM_BASE_URL')}")

try:
    response = client.chat.completions.create(
        model="qwen/qwen3.6-35b-a3b",  # Используем текстовую модель для быстрого теста
        messages=[
            {"role": "user", "content": "Напиши только слово 'УСПЕХ', если ты меня видишь."}
        ],
        max_tokens=10,
        timeout=60.0  # <-- ВАЖНО: Увеличиваем таймаут до 60 секунд
    )
    print("✅ Ответ от API:", response.choices[0].message.content.strip())
except Exception as e:
    print("❌ Ошибка подключения:", e)
    print("💡 Проверь:")
    print("1. Нет ли опечаток в LLM_BASE_URL и LLM_API_KEY в файле .env")
    print("2. Попробуй запустить скрипт еще раз (иногда серверу нужно 2 попытки)")