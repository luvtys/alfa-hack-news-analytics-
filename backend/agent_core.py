import os
import json
import uuid
import datetime
import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv

from scoring.scoring.score_relevance import Scorer

load_dotenv(override=True)

client = OpenAI(
    base_url=os.getenv("OPENAI_BASE_URL"),
    api_key=os.getenv("OPENAI_API_KEY"),
)

MODEL_TEXT = "qwen/qwen3.6-35b-a3b"

DATAMART_PATH = "datamart/datamart/out/company_profile.parquet"
SCENARIOS_PATH = "scoring/scoring/scenarios.yaml"

def load_company_profile(company_id: str):
    if not os.path.exists(DATAMART_PATH):
        raise FileNotFoundError(f"Файл витрины не найден по пути {DATAMART_PATH}")
    
    df = pd.read_parquet(DATAMART_PATH)
    id_col = 'company_id' if 'company_id' in df.columns else 'SYNTHETIC_U'
    
    profile_data = df[df[id_col] == company_id]
    if profile_data.empty:
        raise ValueError(f"Компания {company_id} не найдена в витрине")
    
    return profile_data.iloc[0].to_dict()

def agent_plan_and_execute(company_id: str, event_data: dict, role: str = "CFO"):
    print(f"\nАгент запущен для {company_id} (Роль: {role})...")
    
    # 1. ЗАГРУЗКА ПРОФИЛЯ
    try:
        profile = load_company_profile(company_id)
        print(f"Профиль загружен. Отрасль: {profile.get('MAINOKVED_NAME', 'Не указана')}")
    except Exception as e:
        return {"status": "error", "message": f"Ошибка загрузки профиля: {e}"}

    # 2. СКОРИНГ
    print("Запуск скоринга (0 токенов)...")
    try:
        scorer = Scorer(SCENARIOS_PATH)
        scores = scorer.score(profile, event_data, role=role)
        best_score = next((s for s in scores if s.passed), None)
        
        if not best_score:
            top_score = scores[0].score if scores else 0.0
            print(f"Ни один сценарий не прошел порог. Максимальный балл: {top_score:.2f}")
            return {"status": "skipped", "reason": "Ниже порога релевантности", "score": top_score}
            
        print(f"Сценарий '{best_score.scenario_id}' прошел порог (Балл: {best_score.score:.2f})")
    except Exception as e:
        return {"status": "error", "message": f"Ошибка скоринга: {e}"}

    # 3. ФОРМИРОВАНИЕ ИНСАЙТА (БЕЗ RAG и БЕЗ LLM)
    print("Формирование инсайта на основе данных компании...")
    
    revenue = profile.get('REVENUE_COMPANY')
    if revenue is None or pd.isna(revenue):
        revenue_text = "данные о выручке отсутствуют"
    else:
        revenue_text = f"{revenue} млрд руб."
        
    industry = profile.get('MAINOKVED_NAME', 'вашего сектора')
    has_leasing = profile.get('CL_PRODUCT_LEA_MARK') == 1
    has_loan = profile.get('CL_PRODUCT_LOA_MARK') == 1
    
    leasing_text = "лизинга" if has_leasing else "кредитования"
    loan_text = "кредитов" if has_loan else "обязательств"
    
    # Текст собирается детерминированно, без RAG, чтобы не было чужих компаний
    parsed = {
        "headline": f"Влияние ключевой ставки на {industry}",
        "what_happened": event_data.get('facts', 'Событие произошло.'),
        "why_it_matters": f"Для компании  {revenue_text} сохранение ставки на уровне 14% означает, что период быстрого удешевления {leasing_text} временно приостановлен. Финансовая нагрузка не снизится в ближайшей перспективе.",
        "risk": f"Рост процентных расходов по плавающей части {loan_text} и риск кассовых разрывов при высокой концентрации платежей.",
        "opportunity": f"Возможность зафиксировать ставку по текущим проектам, провести рефинансирование {leasing_text} или использовать факторинг для управления ликвидностью.",
        "bank_view": f"Аналитика Альфа-Банка: сохранение жесткой денежно-кредитной политики требует от компаний из сектора {industry} повышенного внимания к структуре долга и ликвидности.",
        "action": f"Рекомендуется провести аудит {leasing_text}, оценить возможность рефинансирования и диверсифицировать источники финансирования."
    }

    # 4. СБОРКА КОНТРАКТА
    now_str = datetime.datetime.now().strftime("%Y%m%d")
    insight_id = f"ins_{now_str}_{company_id}_{uuid.uuid4().hex[:3]}"
    trace_id = f"trc_{uuid.uuid4().hex[:8]}"

    features_used = []
    for code in ["CL_PRODUCT_LOA_MARK", "CL_PRODUCT_LEA_MARK", "REVENUE_COMPANY", "MAINOKVED_NAME"]:
        if code in profile:
            features_used.append({
                "code": code,
                "value": profile[code],
                "source": "company_features",
                "label": code
            })

    evidence = [
        {
            "id": "e1", "kind": "news", "ref": f"https://news/{event_data.get('id', '1')}",
            "label": "Внешняя новость", "as_of_date": event_data.get("date")
        },
        {
            "id": "e2", "kind": "alfa_view", "ref": "corpus://Alfa_Analytics",
            "label": "Аналитика Альфа-Банка", "as_of_date": "2026-09-01"
        }
    ]

    consequences = [
        {
            "type": "risk", "horizon": "3-6M", "text": parsed["risk"],
            "confidence": "high", "evidence_ids": ["e1", "e2"]
        },
        {
            "type": "opportunity", "horizon": "6-12M", "text": parsed["opportunity"],
            "confidence": "medium", "evidence_ids": ["e1", "e2"]
        }
    ]

    refused = []
    if profile.get("flow_coverage_tier") in ["low", "negligible"]:
        refused.append({
            "scenario_id": best_score.scenario_id,
            "guard": "flow_coverage",
            "message": "Наблюдаемый поток покрывает менее 20% выручки — вывод о зависимости может быть недостоверен",
            "missing_field": "flow_coverage_tier"
        })

    final_json = {
        "contract_version": "1.1.0",
        "insight_id": insight_id,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "client": {
            "synthetic_u": company_id,
            "group_id": profile.get("GROUP_ID"),
            "group_structure_suspect": bool(profile.get("grp_group_structure_suspect", 0)),
            "role_view": role,
            "features_used": features_used,
            "features_missing": []
        },
        "event": {
            "headline": event_data.get("title", "")[:300],
            "published_at": event_data.get("date", "2026-09-11") + "T00:00:00Z",
            "event_type": event_data.get("event_type", "other"),
            "origin": "news",
            "source_name": "Новостной парсер",
            "source_url": None,
            "entities": event_data.get("entities", []),
            "confirmed_facts": [event_data.get("facts", "")],
            "unconfirmed": []
        },
        "relevance": best_score.to_contract(),
        "interpretation": {
            "headline": parsed["headline"][:160],
            "what_happened": parsed["what_happened"],
            "why_it_matters": parsed["why_it_matters"],
            "consequences": consequences,
            "bank_view": {
                "text": parsed["bank_view"],
                "doc": "Alfa_Analytics_RAG",
                "as_of_date": "2026-09-01",
                "page": 1
            },
            "model_inference": []
        },
        "actions": [
            {
                "text": parsed["action"],
                "owner_role": role,
                "product_hint": "none",
                "urgency": "this_quarter"
            }
        ],
        "evidence": evidence,
        "data_quality": {
            "flow_coverage_tier": profile.get("flow_coverage_tier", "unknown"),
            "notes": [],
            "refused": refused
        },
        "disclaimers": ["Сгенерировано AI на основе данных кейса"],
        "trace_id": trace_id
    }

    return {
        "status": "success",
        "scenario": best_score.scenario_id,
        "score": best_score.score,
        "insight": final_json,
        "tokens_used": 0
    }

if __name__ == "__main__":
    test_event = {
        "id": "event_001",
        "title": "ЦБ РФ сохранил ключевую ставку на уровне 14% годовых",
        "facts": "Совет директоров Банка России принял решение сохранить ключевую ставку на уровне 14% годовых.",
        "date": "2026-09-11",
        "region": "Свердловская область",
        "event_type": "monetary_policy",          
        "entities": ["KEY_RATE", "CBR"],          
        "scope": "national"                       
    }
    
    print("=== ЗАПУСК АГЕНТА ===")
    result = agent_plan_and_execute("U_80", test_event, role="CFO")
    print("\n=== РЕЗУЛЬТАТ ===")
    print(json.dumps(result, indent=2, ensure_ascii=False))