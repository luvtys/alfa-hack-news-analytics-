from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import sqlite3
import os
from typing import List, Optional

from agent_core import agent_plan_and_execute
from rag import search as rag_search

app = FastAPI(title="Alfa Hack News Analytics API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = "../frontend"
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
    print(f"✅ Фронтенд найден: {os.path.abspath(FRONTEND_DIR)}")
else:
    print(f"⚠️ ВНИМАНИЕ: Папка {os.path.abspath(FRONTEND_DIR)} не найдена!")

def get_db():
    conn = sqlite3.connect("hackathon.db")
    conn.row_factory = sqlite3.Row
    return conn

class NewsEvent(BaseModel):
    id: str
    title: str
    facts: str
    date: str
    region: Optional[str] = None
    event_type: Optional[str] = None
    entities: Optional[List[str]] = None
    scope: Optional[str] = None

class InsightRequest(BaseModel):
    company_id: str
    event: NewsEvent
    role: Optional[str] = "CFO"

class FeedRequest(BaseModel):
    company_id: str
    role: Optional[str] = "CFO"

class ChatRequest(BaseModel):
    question: str
    company_id: str
    role: str
    context: Optional[str] = None

@app.get("/")
def serve_frontend():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "API is running, but frontend/index.html not found"}

@app.post("/api/insight")
def generate_insight(request: InsightRequest):
    try:
        event_dict = request.event.model_dump(exclude_none=True)
        result = agent_plan_and_execute(
            company_id=request.company_id,
            event_data=event_dict,
            role=request.role
        )
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/feed")
def get_feed(request: FeedRequest):
    news_list = [
        {
            "id": "event_001",
            "title": "ЦБ РФ сохранил ключевую ставку на уровне 14% годовых",
            "facts": "Совет директоров Банка России принял решение сохранить ключевую ставку на уровне 14% годовых.",
            "date": "2026-09-11",
            "region": "Свердловская область",
            "event_type": "monetary_policy",
            "entities": ["KEY_RATE", "CBR"],
            "scope": "national"
        },
        {
            "id": "event_002",
            "title": "Инфляция в России ускорилась до 8,5% в годовом выражении",
            "facts": "Росстат сообщил, что инфляция в августе достигла 8,5% в годовом выражении, что выше прогнозов ЦБ.",
            "date": "2026-09-05",
            "region": "Свердловская область",
            "event_type": "inflation",
            "entities": ["CPI"],
            "scope": "national"
        },
        {
            "id": "event_003",
            "title": "Курс юаня вырос до 13 рублей на фоне волатильности",
            "facts": "На Московской бирже курс юаня поднялся до 13 рублей, что увеличивает стоимость импорта из Китая.",
            "date": "2026-09-15",
            "region": "Свердловская область",
            "event_type": "fx",
            "entities": ["CNY", "FX_RATE"],
            "scope": "national"
        },
        {
            "id": "event_004",
            "title": "Рынок труда: безработица сохраняется на историческом минимуме",
            "facts": "Уровень безработицы в России остается на уровне 2,4%, что создает дефицит кадров.",
            "date": "2026-08-25",
            "region": "Свердловская область",
            "event_type": "labour",
            "entities": ["UNEMPLOYMENT", "WAGES"],
            "scope": "national"
        },
        {
            "id": "event_005",
            "title": "Цены на золото обновили исторический максимум",
            "facts": "Стоимость золота достигла $2500 за унцию на фоне геополитической напряженности.",
            "date": "2026-08-30",
            "region": "Свердловская область",
            "event_type": "commodity",
            "entities": ["GOLD"],
            "scope": "national"
        },
        {
            "id": "event_006",
            "title": "Потребление в России достигло пика за последние 5 лет",
            "facts": "Росстат зафиксировал рост розничного товарооборота на 12% в годовом выражении.",
            "date": "2026-09-01",
            "region": "Свердловская область",
            "event_type": "sector_demand",
            "entities": ["RETAIL_TURNOVER"],
            "scope": "national"
        },
        {
            "id": "event_007",
            "title": "Правительство ввело новые санкционные ограничения на импорт",
            "facts": "Введены ограничения на ввоз ряда товаров из стран ЕС, что может повлиять на цепочки поставок.",
            "date": "2026-09-10",
            "region": "Свердловская область",
            "event_type": "regulation",
            "entities": ["SANCTIONS"],
            "scope": "national"
        },
        {
            "id": "event_008",
            "title": "Ключевой контрагент компании снизил объем закупок на 20%",
            "facts": "Крупный контрагент объявил о сокращении закупок, что создает риск для выручки.",
            "date": "2026-09-12",
            "region": "Свердловская область",
            "event_type": "counterparty",
            "entities": ["COUNTERPARTY"],
            "scope": "national"
        },
        {
            "id": "event_009",
            "title": "Бюджет России на 2027 год предусматривает рост расходов на 15%",
            "facts": "Минфин представил проект бюджета с увеличением расходов, что может повлиять на инфляцию.",
            "date": "2026-09-20",
            "region": "Свердловская область",
            "event_type": "budget",
            "entities": ["MINFIN", "BUDGET"],
            "scope": "national"
        }
    ]
    
    results = []
    for news in news_list:
        try:
            res = agent_plan_and_execute(
                company_id=request.company_id,
                event_data=news,
                role=request.role
            )
            if res.get("status") == "success":
                results.append(res)
        except Exception as e:
            print(f"Ошибка при обработке {news['id']}: {e}")
            
    return {"items": results, "total": len(results)}

@app.post("/api/chat")
def chat_with_ai(request: ChatRequest):
    question_lower = request.question.lower()
    context = request.context or ""
    
    if "риск" in question_lower or "угроз" in question_lower:
        if "Риски:" in context:
            parts = context.split("Риски:")
            if len(parts) > 1:
                return {"answer": f"Основной риск: {parts[1].strip()[:300]}"}
        return {"answer": "Риск: Рост процентных расходов по кредитам и лизингу из-за сохранения высокой ключевой ставки."}
    
    if "возможност" in question_lower:
        return {"answer": "Возможность: Рефинансирование лизинга под текущую ставку или использование факторинга для управления ликвидностью."}
    
    if "действ" in question_lower or "что делать" in question_lower:
        return {"answer": "Рекомендация: Провести аудит лизинговых платежей и рассмотреть рефинансирование долга."}
    
    if "ставк" in question_lower:
        return {"answer": "Ставка ЦБ сохранена на уровне 14%. Это означает, что кредиты и лизинг не подешевеют в ближайшее время."}

        # 6. Если спрашивают про долг
    if "долг" in question_lower or "кредит" in question_lower or "лизинг" in question_lower:
        return {"answer": "Рекомендация: Провести аудит лизинговых платежей и кредитного портфеля, оценить возможность рефинансирования под текущую ставку и диверсифицировать источники финансирования."}
    
    return {"answer": "Я могу ответить на вопросы про риски, возможности, действия или ключевую ставку. Уточните вопрос."}

# --- СУЩЕСТВУЮЩИЕ ЭНДПОИНТЫ ---
@app.get("/api/companies/{company_id}")
def get_company(company_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM companies WHERE SYNTHETIC_U = ?", (company_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Company not found")
    return dict(row)

@app.get("/api/persons/{company_id}")
def get_persons(company_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT SYNTHETIC_F, CITY_NAME, RC_NAME FROM persons WHERE SYNTHETIC_U = ?", (company_id,))
    persons = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return persons

@app.get("/api/companies/{company_id}/context")
def get_company_context(company_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM companies WHERE SYNTHETIC_U = ?", (company_id,))
    row = cursor.fetchone()
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Company not found")
    profile = dict(row)
    cursor.execute("SELECT SYNTHETIC_F, CITY_NAME, RC_NAME FROM persons WHERE SYNTHETIC_U = ?", (company_id,))
    persons = [dict(r) for r in cursor.fetchall()]
    cursor.execute("""
        SELECT PAYER AS counterparty, SUM(PAY_AMT) AS total_amount, SUM(PAY_CNT) AS total_ops
        FROM payments WHERE BENEFICIARY = ?
        GROUP BY PAYER ORDER BY total_amount DESC LIMIT 10
    """, (company_id,))
    income = [dict(r) for r in cursor.fetchall()]
    cursor.execute("""
        SELECT BENEFICIARY AS counterparty, SUM(PAY_AMT) AS total_amount, SUM(PAY_CNT) AS total_ops
        FROM payments WHERE PAYER = ?
        GROUP BY BENEFICIARY ORDER BY total_amount DESC LIMIT 10
    """, (company_id,))
    outcome = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {
        "profile": profile,
        "persons": persons,
        "counterparties_income": income,
        "counterparties_outcome": outcome,
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)