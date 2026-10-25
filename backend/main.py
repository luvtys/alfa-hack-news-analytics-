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

@app.post("/api/chat")
def chat_with_ai(request: ChatRequest):
    # Отвечаем на основе данных, без вызова LLM
    question_lower = request.question.lower()
    context = request.context or ""
    
    # 1. Риски
    if "риск" in question_lower or "угроз" in question_lower:
        if "Риски:" in context:
            parts = context.split("Риски:")
            if len(parts) > 1:
                return {"answer": f"Основной риск: {parts[1].strip()[:300]}"}
        return {"answer": "Риск: Рост процентных расходов по кредитам и лизингу из-за сохранения высокой ключевой ставки."}
    
    # 2. Возможности
    if "возможност" in question_lower:
        return {"answer": "Возможность: Рефинансирование лизинга под текущую ставку или использование факторинга для управления ликвидностью."}
    
    # 3. Действия
    if "действ" in question_lower or "что делать" in question_lower:
        return {"answer": "Рекомендация: Провести аудит лизинговых платежей и рассмотреть рефинансирование долга."}
    
    # 4. Ставка
    if "ставк" in question_lower:
        return {"answer": "Ставка ЦБ сохранена на уровне 14%. Это означает, что кредиты и лизинг не подешевеют в ближайшее время."}
    
    # 5. Если вопрос не распознан
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