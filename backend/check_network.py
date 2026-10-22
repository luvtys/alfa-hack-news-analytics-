import requests
import os
from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv()

url = os.getenv("LLM_BASE_URL")
api_key = os.getenv("LLM_API_KEY")

print(f"🔍 Проверяем URL: '{url}'")
print(f"🔑 Ключ начинается с: '{api_key[:5] if api_key else 'ПУСТО'}...'")

# Проверяем, нет ли скрытых пробелов или кавычек
if url and (url.startswith('"') or url.endswith(' ') or url.endswith('"')):
    print("⚠️ ВНИМАНИЕ: В URL найдены лишние кавычки или пробелы! Проверь файл .env")

try:
    # Пытаемся сделать простой запрос к списку моделей (стандартный эндпоинт OpenAI)
    headers = {"Authorization": f"Bearer {api_key}"}
    response = requests.get(f"{url}/models", headers=headers, timeout=10)
    
    print(f"✅ Сервер ответил! Статус: {response.status_code}")
    if response.status_code == 200:
        print("🎉 Соединение работает отлично! Проблема была в библиотеке openai или таймауте.")
    else:
        print(f"Ответ сервера: {response.text}")
        
except requests.exceptions.ConnectionError:
    print("❌ Ошибка соединения (Connection Error).")
    print("Компьютер не видит этот адрес. Возможные причины:")
    print("1. В файле .env есть ЛИШНИЙ ПРОБЕЛ в конце строки URL (например: '.../v1 ')")
    print("2. В файле .env URL взят в кавычки (например: URL=\"https://...\") — убери их.")
    print("3. Твой антивирус, VPN или прокси блокирует доступ к railway.app")
    print("4. Сервер организаторов действительно сейчас упал (попробуй через 5-10 минут).")
except Exception as e:
    print(f"❌ Произошла другая ошибка: {e}")