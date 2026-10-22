from fastapi import FastAPI
import sqlite3

app = FastAPI(title="Alfa Hack News Analytics API")

def get_db():
    conn = sqlite3.connect("hackathon.db")
    conn.row_factory = sqlite3.Row
    return conn

@app.get("/")
def root():
    return {"message": "Alfa Hack API is running!"}

@app.get("/api/companies/{company_id}")
def get_company(company_id: str):
    ...  

@app.get("/api/persons/{company_id}")
def get_persons(company_id: str):
    ...  

@app.get("/api/companies/{company_id}/context")
def get_company_context(company_id: str):
    """Полный бизнес-контекст компании: профиль + физлица + контрагенты"""
    conn = get_db()
    cursor = conn.cursor()

    # 1. Профиль компании
    cursor.execute("SELECT * FROM companies WHERE SYNTHETIC_U = ?", (company_id,))
    row = cursor.fetchone()
    if row is None:
        conn.close()
        return {"error": "Company not found"}
    profile = dict(row)

    # 2. Связанные физлица (владельцы/директора)
    cursor.execute(
        "SELECT SYNTHETIC_F, CITY_NAME, RC_NAME FROM persons WHERE SYNTHETIC_U = ?",
        (company_id,)
    )
    persons = [dict(r) for r in cursor.fetchall()]

    # 3. Топ-10 кто платил нам (источники выручки)
    cursor.execute("""
        SELECT PAYER AS counterparty, SUM(PAY_AMT) AS total_amount, SUM(PAY_CNT) AS total_ops
        FROM payments WHERE BENEFICIARY = ?
        GROUP BY PAYER ORDER BY total_amount DESC LIMIT 10
    """, (company_id,))
    income = [dict(r) for r in cursor.fetchall()]

    # 4. Топ-10 кому платили мы (наши поставщики)
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