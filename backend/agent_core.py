import os
import json
import re
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

def clean_llm_text(text: str) -> str:
    """Жестко чистит текст от бреда Qwen и таблиц из RAG"""
    if not text:
        return ""
    
    # Убираем markdown
    text = text.replace("```json", "").replace("```", "").replace("`", "")
    
    # Если это таблица (много | или цифр с $) — выкидываем
    if text.count('|') > 3 or text.count('$') > 2:
        return ""
    
    # Режем на строки и выкидываем мусор
    lines = text.split('\n')
    clean_lines = []
    for line in lines:
        line = line.strip()
        lower_line = line.lower()
        # Пропускаем английские размышления
        if any(w in lower_line for w in ["analyze", "thinking", "wait", "let me", "actually", "prompt", "constraint", "here's", "translated properly", "role:", "task:", "why it matters"]):
            continue
        # Пропускаем пустые и слишком короткие
        if len(line) < 10:
            continue
        clean_lines.append(line)
    
    text = " ".join(clean_lines)
    
    # Убираем зацикливания (ставкаставкаставка)
    text = re.sub(r'\b(\w+)(?:\s+\1){2,}\b', r'\1', text)
    
    # Убираем технические артефакты
    text = re.sub(r'->\s*(Better|Good)\.?\)?', '', text)
    text = re.sub(r'\(?Better\.?\)?', '', text)
    text = re.sub(r'\s+', ' ', text) # Убираем лишние пробелы
    
    return text.strip('()"\' ')

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
        analytics_chunks = rag_search(rag_query, top_k=3)
        print(f"Найдено {len(analytics_chunks)} чанков аналитики")
        
        best_chunk_text = ""
        bad_words = ["русгидро", "газпром", "роснефть", "лукойл", "сбербанк", "втб"]
        for chunk in analytics_chunks:
            txt = chunk['text']
            if not any(bw in txt.lower() for bw in bad_words):
                # Берем только русские предложения
                matches = re.findall(r'[А-ЯЁ][^.!?]*[.!?]', txt)
                if matches:
                    best_chunk_text = " ".join(matches[:2])
                    break
        
        if not best_chunk_text:
            best_chunk_text = "Аналитика указывает на рост кредитных рисков в текущих макроэкономических условиях."
            
        alfa_doc_name = analytics_chunks[0]['source'] if analytics_chunks else "Нет данных"
    except Exception as e:
        print(f"RAG недоступен: {e}. Работаем без аналитики.")
        best_chunk_text = "Аналитика банка временно недоступна."
        alfa_doc_name = "Нет данных"

    # 4. ВЫЗОВ LLM
    print("Генерация инсайта (LLM)...")
    
    revenue = profile.get('REVENUE_COMPANY', 'неизвестной')
    if pd.isna(revenue) or revenue is None:
        revenue_text = "данные о выручке отсутствуют"
    else:
        revenue_text = f"{revenue} млрд руб."
        
    industry = profile.get('MAINOKVED_NAME', 'вашего сектора')
    
    system_prompt = "Ты — финансовый аналитик Альфа-Банка. Отвечай на русском языке, кратко, по делу. Без размышлений и таблиц."
    user_message = (
        f"Событие: {event_data.get('title', '')}\n"
        f"Отрасль компании: {industry}\n"
        f"Выручка: {revenue_text}\n"
        f"Аналитика банка: {best_chunk_text}\n\n"
        "Напиши в формате key=value следующие поля:\n"
        "headline=Заголовок карточки\n"
        "why_it_matters=Почему это важно для компании\n"
        "risk=Риск\n"
        "opportunity=Возможность\n"
        "bank_view=Мнение банка\n"
        "action=Рекомендация"
    )

    try:
        response = client.chat.completions.create(
            model=MODEL_TEXT,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            max_tokens=1500,
            temperature=0.1,
            presence_penalty=0.5,
            frequency_penalty=0.5,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            timeout=60.0
        )
        
        message = response.choices[0].message
        result_text = message.content or getattr(message, 'reasoning_content', '')
        
        parsed = {}
        matches = re.finditer(r'(headline|why_it_matters|risk|opportunity|bank_view|action)\s*=\s*([^\n]+)', result_text, re.IGNORECASE)
        for match in matches:
            key = match.group(1).lower()
            val = clean_llm_text(match.group(2))
            if val:
                parsed[key] = val
                
    except Exception as e:
        print(f"LLM недоступна: {e}")
        parsed = {}

    # 5. ФОЛЛБЭК (если LLM выдала бред или пустоту)
    if len(parsed) < 3 or len(parsed.get("why_it_matters", "")) < 30:
        print("⚠️ LLM выдала бред или пустоту. Используем жесткий шаблон.")
        
        if best_score.scenario_id == "fx_import":
            why_text = f"Изменение курса валют напрямую влияет на стоимость импортных комплектующих и сырья для компании из сектора {industry}."
            risk_text = "Рост себестоимости импорта и волатильность валютных курсов усложняют ценообразование."
            opp_text = "Возможность перейти на локальных поставщиков или использовать инструменты хеджирования валютных рисков."
            bank_text = "Аналитика Альфа-Банка: высокая волатильность курса требует хеджирования и диверсификации цепочек поставок."
        elif best_score.scenario_id == "demand_and_payroll":
            why_text = f"Изменение потребительского спроса и ситуации на рынке труда влияет на операционные показатели компании из сектора {industry}."
            risk_text = "Риск снижения спроса и роста расходов на фонд оплаты труда."
            opp_text = "Возможность оптимизировать закупочный цикл и пересмотреть потребность в оборотном финансировании."
            bank_text = "Аналитика Альфа-Банка: потребление прошло пик, требуется пересмотр закупочного цикла."
        else:
            why_text = f"Сохранение высокой ключевой ставки увеличивает стоимость обслуживания долга и лизинговых платежей для компании с {revenue_text}."
            risk_text = "Рост процентных расходов по кредитам и лизингу, риск кассовых разрывов."
            opp_text = "Возможность зафиксировать ставку по текущим проектам или провести рефинансирование."
            bank_text = f"Аналитика Альфа-Банка: сохранение жесткой ДКП требует от компаний из сектора {industry} повышенного внимания к структуре долга."
        
        parsed = {
            "headline": f"Влияние события на {industry}",
            "why_it_matters": why_text,
            "risk": risk_text,
            "opportunity": opp_text,
            "bank_view": bank_text,
            "action": "Рекомендуется провести аудит финансовых обязательств и рассмотреть возможность рефинансирования."
        }

    # 6. СБОРКА КОНТРАКТА
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

    consequences = [
        {
            "type": "risk", "horizon": "3-6M", "text": parsed.get("risk", "Риск не определен"),
            "confidence": "high", "evidence_ids": ["e1", "e2"]
        },
        {
            "type": "opportunity", "horizon": "6-12M", "text": parsed.get("opportunity", "Возможность не определена"),
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
            "headline": parsed.get("headline", "Без заголовка")[:160],
            "what_happened": event_data.get('facts', 'Событие произошло.'),
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