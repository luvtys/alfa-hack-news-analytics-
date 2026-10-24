import os
import json
import uuid
import datetime
import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv

from scoring.scoring.score_relevance import Scorer
from rag import search as rag_search

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

    # 3. RAG (Аналитика Альфа-Банка)
    print("Поиск аналитики Альфа-Банка (RAG)...")
    rag_query = f"{event_data.get('title', '')} {best_score.scenario_name} {profile.get('MAINOKVED_NAME', '')}"
    try:
        analytics_chunks = rag_search(rag_query, top_k=2)
        print(f"Найдено {len(analytics_chunks)} чанков аналитики")
        alfa_context = "\n".join([f"[{c['source']}]: {c['text']}" for c in analytics_chunks])
        alfa_doc_name = analytics_chunks[0]['source'] if analytics_chunks else "Нет данных"
    except Exception as e:
        print(f"RAG недоступен: {e}. Работаем без аналитики.")
        alfa_context = "Аналитика недоступна."
        alfa_doc_name = "Нет данных"

    # 4. ПРОМПТ (формат key=value без примеров-шаблонов)
    print("Генерация инсайта (LLM)...")
    system_prompt = (
        "Ты — аналитик Альфа-Банка. Отвечай только фактами из данных. "
        "Формат: key=value, каждая пара с новой строки. Никаких шаблонов, скобок и примеров."
    )

    user_message = (
        "Заполни поля для бизнес-инсайта на основе данных ниже.\n"
        "Пиши конкретные цифры (выручка, ставка, проценты). Не пиши абстрактные фразы.\n\n"
        "ФОРМАТ ОТВЕТА (строго так):\n"
        "headline=Текст заголовка\n"
        "what_happened=Текст\n"
        "why_it_matters=Текст\n"
        "risk=Текст\n"
        "opportunity=Текст\n"
        "bank_view=Текст\n"
        "action=Текст\n\n"
        f"ДАННЫЕ КОМПАНИИ:\n{json.dumps(profile, ensure_ascii=False, default=str)}\n\n"
        f"СОБЫТИЕ:\n{json.dumps(event_data, ensure_ascii=False, default=str)}\n\n"
        f"АНАЛИТИКА БАНКА:\n{alfa_context}"
    )

    try:
        response = client.chat.completions.create(
            model=MODEL_TEXT,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            max_tokens=1500,          
            temperature=0.3,          
            presence_penalty=0.5,     
            frequency_penalty=0.5,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            timeout=120.0
        )
        
        message = response.choices[0].message
        result_text = message.content or getattr(message, 'reasoning_content', '')
        
        # Парсим key=value
        parsed = {}
        for line in result_text.split('\n'):
            line = line.strip()
            if '=' in line:
                key, val = line.split('=', 1)
                key = key.strip().lower()
                if key in ["headline", "what_happened", "why_it_matters", "risk", "opportunity", "bank_view", "action"]:
                    parsed[key] = val.strip()
        
        if len(parsed) < 4:
            return {"status": "error", "message": "Не удалось распарсить текст", "raw_tail": result_text[-800:]}

        # 5. СБОРКА КОНТРАКТА (insight.schema.json)
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
                "id": "e2", "kind": "alfa_view", "ref": f"corpus://{alfa_doc_name}",
                "label": "Аналитика Альфа-Банка", "as_of_date": "2026-09-01"
            }
        ]

        consequences = []
        if "risk" in parsed:
            consequences.append({
                "type": "risk", "horizon": "3-6M", "text": parsed["risk"],
                "confidence": "medium", "evidence_ids": ["e1", "e2"]
            })
        if "opportunity" in parsed:
            consequences.append({
                "type": "opportunity", "horizon": "6-12M", "text": parsed["opportunity"],
                "confidence": "medium", "evidence_ids": ["e1", "e2"]
            })

        # Проверка guard'ов (критерий приёмки 2)
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
                "headline": parsed.get("headline", "Без заголовка")[:160],
                "what_happened": parsed.get("what_happened", ""),
                "why_it_matters": parsed.get("why_it_matters", ""),
                "consequences": consequences,
                "bank_view": {
                    "text": parsed.get("bank_view", ""),
                    "doc": alfa_doc_name,
                    "as_of_date": "2026-09-01",
                    "page": 1
                },
                "model_inference": []
            },
            "actions": [
                {
                    "text": parsed.get("action", "Рекомендаций нет"),
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
            "tokens_used": response.usage.total_tokens if response.usage else 0
        }

    except Exception as e:
        return {"status": "error", "message": f"API Error: {type(e).__name__}: {str(e)}"}

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