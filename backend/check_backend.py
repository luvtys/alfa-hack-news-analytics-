import requests
import json

url = "http://127.0.0.1:8000/api/insight"

payload = {
    "company_id": "U_80",
    "role": "CFO",
    "event": {
        "id": "event_001",
        "title": "ЦБ РФ сохранил ключевую ставку на уровне 14% годовых",
        "facts": "Совет директоров Банка России принял решение сохранить ключевую ставку на уровне 14% годовых.",
        "date": "2026-09-11",
        "region": "Свердловская область",
        "event_type": "monetary_policy",
        "entities": ["KEY_RATE", "CBR"],
        "scope": "national"
    }
}

print("Отправляем запрос на сервер (это займет 5-10 секунд)...")

try:
    response = requests.post(url, json=payload)
    
    print(f"\nСтатус ответа: {response.status_code}")
    print("Ответ сервера:")
    print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    
except Exception as e:
    print(f"Ошибка при запросе: {e}")