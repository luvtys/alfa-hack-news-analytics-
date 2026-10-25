from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import sqlite3
import os
from typing import List, Optional

from agent_core import agent_plan_and_execute

app = FastAPI(title="Alfa Hack News Analytics API")

# Настройка CORS (чтобы фронт мог обращаться к API)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Раздача статики фронтенда
FRONTEND_DIR = "../frontend"  # путь от папки backend к frontend
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

@app.get("/")
def serve_frontend():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Frontend not found, but API is running!"}

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

    cursor.execute("SELECT PAYER AS counterparty, SUM(PAY_AMT) AS total_amount, SUM(PAY_CNT) AS total_ops FROM payments WHERE BENEFICIARY = ? GROUP BY PAYER ORDER BY total_amount DESC LIMIT 10", (company_id,))
    income = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT BENEFICIARY AS counterparty, SUM(PAY_AMT) AS total_amount, SUM(PAY_CNT) AS total_ops FROM payments WHERE PAYER = ? GROUP BY BENEFICIARY ORDER BY total_amount DESC LIMIT 10", (company_id,))
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