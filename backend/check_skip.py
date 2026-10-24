import requests
import json

url = "http://127.0.0.1:8000/api/insight"

# Новость, которая НЕ должна пройти скоринг (нет триггеров для сценариев)
payload = {
    "company_id": "U_80",
    "role": "CFO",
    "event": {
        "id": "event_sport_001",
        "title": "Сборная России выиграла товарищеский матч по футболу",
        "facts": "В Москве завершился товарищеский матч, сборная России одержала победу со счетом 3:1.",
        "date": "2026-10-24",
        "event_type": "other",  # <-- тип 'other' не подходит ни под один сценарий
        "entities": []
    }
}

print("Отправляем НЕРЕЛЕВАНТНУЮ новость...")
response = requests.post(url, json=payload)

print(f"Статус ответа: {response.status_code}")
print("Ответ сервера:")
print(json.dumps(response.json(), indent=2, ensure_ascii=False))