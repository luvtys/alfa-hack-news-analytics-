import requests
import os
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("LLM_BASE_URL")
api_key = os.getenv("LLM_API_KEY")

# Библиотека openai автоматически добавляет /chat/completions к base_url.
# Проверяем именно этот путь.
endpoint = f"{url}/chat/completions"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

# Используем одну из разрешенных текстовых моделей из правил кейса
payload = {
    "model": "qwen/qwen3.6-35b-a3b",
    "messages": [{"role": "user", "content": "Напиши только слово ДА"}],
    "max_tokens": 5
}

print(f"📡 Стучусь в: {endpoint}")
print("⏳ Жду ответа (это может занять до 40 секунд, если сервер 'просыпается')...\n")

try:
    # Увеличиваем таймаут до 40 секунд
    response = requests.post(endpoint, json=payload, headers=headers, timeout=40)
    
    print(f"📥 Статус ответа: {response.status_code}")
    if response.status_code == 200:
        print("✅ УСПЕХ! Сервер жив и отвечает:")
        print(response.json()['choices'][0]['message']['content'])
    else:
        print("⚠️ Сервер ответил, но вернул ошибку:")
        print(response.text)
        
except requests.exceptions.Timeout:
    print("⏱️ ТАЙМАУТ (40 секунд).")
    print("💡 ДИАГНОЗ: Сервер жив, но он ПЕРЕГРУЖЕН запросами других команд или находится в режиме 'сна' (cold start).")
    print("🛠 ЧТО ДЕЛАТЬ: Подожди 5-10 минут и попробуй запустить этот скрипт снова. Это нормально для хакатонного API.")
    
except requests.exceptions.ConnectionError:
    print("🚫 ОШИБКА СОЕДИНЕНИЯ.")
    print("💡 ДИАГНОЗ: Твой провайдер или VPN блокирует доступ к railway.app.")
    print("🛠 ЧТО ДЕЛАТЬ: Отключи VPN (или наоборот, включи его), либо попробуй раздать интернет с телефона.")
    
except Exception as e:
    print(f"❌ НЕИЗВЕСТНАЯ ОШИБКА: {e}")