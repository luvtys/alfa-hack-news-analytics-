#!/usr/bin/env python3
"""Проверяет все фикстуры против схем. Ставится в CI: любое расхождение
фронта и бэка падает здесь, а не на демо.

    pip install jsonschema
    python3 validate_contract.py
"""
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).parent
INSIGHT = json.loads((ROOT / "insight.schema.json").read_text(encoding="utf-8"))
TRACE = json.loads((ROOT / "trace.schema.json").read_text(encoding="utf-8"))

CONTRACT_VERSION = "1.1.0"

ENVELOPE_REQUIRED = {"contract_version", "synthetic_u", "role_view", "generated_at", "total", "items"}
EMPTY_REASON_REQUIRED = {"code", "message", "threshold", "trace_id"}
EMPTY_REASON_CODES = {"below_threshold", "no_events", "no_profile", "company_unknown",
                      "blocked_by_guard"}
BLOCKED_REQUIRED = {"scenario_id", "guard", "message"}

# Критерий приёмки 2, решение команды от 21.10.2026: при недостаточном
# покрытии система отказывается от вывода о контрагентах, а не показывает
# предупреждение рядом с цифрой. Здесь это проверяется машиной.
THIN_TIERS = {"low", "negligible"}
COVERAGE_DEPENDENT = {"counterparty_dependence"}

insight_v = Draft202012Validator(INSIGHT)
trace_v = Draft202012Validator(TRACE)

failures = 0


def fail(where: str, msg: str) -> None:
    global failures
    failures += 1
    print(f"  [ОШИБКА] {where}: {msg}")


for fp in sorted((ROOT / "fixtures").glob("*.json")):
    print(f"{fp.name}")
    doc = json.loads(fp.read_text(encoding="utf-8"))

    if fp.name.startswith("trace_"):
        errs = sorted(trace_v.iter_errors(doc), key=lambda e: e.path)
        for e in errs:
            fail(fp.name, f"{'/'.join(map(str, e.path))}: {e.message}")
        if not errs:
            print(f"  [ok] трасса валидна, шагов {len(doc['steps'])}, "
                  f"retry-циклов {sum(1 for s in doc['steps'] if s['action'] == 'retry')}")
        continue

    missing = ENVELOPE_REQUIRED - set(doc)
    if missing:
        fail(fp.name, f"в конверте нет полей {sorted(missing)}")
        continue
    if doc["contract_version"] != CONTRACT_VERSION:
        fail(fp.name, f"contract_version должен быть {CONTRACT_VERSION}")
    if doc["total"] != len(doc["items"]):
        fail(fp.name, f"total={doc['total']}, а items={len(doc['items'])}")

    if not doc["items"]:
        reason = doc.get("empty_reason")
        if not reason:
            fail(fp.name, "пустая лента без empty_reason")
        else:
            miss = EMPTY_REASON_REQUIRED - set(reason)
            if miss:
                fail(fp.name, f"в empty_reason нет полей {sorted(miss)}")
            elif reason["code"] not in EMPTY_REASON_CODES:
                fail(fp.name, f"неизвестный empty_reason.code {reason['code']!r}")
            elif reason["code"] == "blocked_by_guard":
                blocked = reason.get("blocked")
                if not blocked:
                    fail(fp.name, "code=blocked_by_guard без непустого списка blocked")
                else:
                    for i, b in enumerate(blocked):
                        gaps = BLOCKED_REQUIRED - set(b)
                        if gaps:
                            fail(fp.name, f"blocked[{i}] без полей {sorted(gaps)}")
                    if not failures:
                        print(f"  [ok] отказ описан: {len(blocked)} заблокированных "
                              f"сценариев, guard {blocked[0]['guard']}")
            else:
                print("  [ok] пустая лента описана корректно")
        continue

    for item in doc["items"]:
        errs = sorted(insight_v.iter_errors(item), key=lambda e: e.path)
        for e in errs:
            fail(item.get("insight_id", "?"), f"{'/'.join(map(str, e.path))}: {e.message}")
        if errs:
            continue

        # Проверки, которых нет в JSON Schema, но которые ломают демо
        ids = {ev["id"] for ev in item["evidence"]}
        for cons in item["interpretation"]["consequences"]:
            unknown = set(cons["evidence_ids"]) - ids
            if unknown:
                fail(item["insight_id"], f"вывод ссылается на несуществующие evidence {sorted(unknown)}")
        for ev in item["evidence"]:
            unknown = set(ev.get("depends_on", [])) - ids
            if unknown:
                fail(item["insight_id"], f"evidence {ev['id']} зависит от несуществующих {sorted(unknown)}")
            if ev["kind"] == "alfa_view" and not ev.get("as_of_date"):
                fail(item["insight_id"], f"evidence {ev['id']} типа alfa_view без as_of_date")

        comp = item["relevance"]["components"]
        total = round(sum(comp.values()), 3)
        if abs(total - item["relevance"]["score"]) > 0.02:
            fail(item["insight_id"], f"сумма компонент {total} не сходится со score {item['relevance']['score']}")
        if item["relevance"]["score"] < item["relevance"]["threshold"]:
            fail(item["insight_id"], "инсайт ниже порога, но попал в ленту")

        missing_feats = set(item["client"].get("features_missing", []))
        used = {f["code"] for f in item["client"]["features_used"]}
        overlap = missing_feats & used
        if overlap:
            fail(item["insight_id"], f"агент сослался на пустые поля {sorted(overlap)}")

        text = json.dumps(item, ensure_ascii=False)
        if "доля выручки" in text or "доли выручки" in text:
            fail(item["insight_id"], "запрещённая формулировка «доля выручки» применительно к платежам")

        dq = item.get("data_quality", {})
        tier = dq.get("flow_coverage_tier")
        if tier in THIN_TIERS and not dq.get("notes"):
            fail(item["insight_id"], f"покрытие {tier} без примечания в data_quality.notes")

        # Критерий приёмки 2: отказ, а не предупреждение.
        scen = item["relevance"]["scenario_id"]
        if tier in THIN_TIERS and scen in COVERAGE_DEPENDENT:
            fail(item["insight_id"],
                 f"сценарий {scen} выдан при покрытии {tier}: такой вывод должен быть "
                 f"не предупреждением, а отказом (empty_reason.code=blocked_by_guard)")

        for i, ref in enumerate(dq.get("refused", [])):
            gaps = {"scenario_id", "guard", "message"} - set(ref)
            if gaps:
                fail(item["insight_id"], f"data_quality.refused[{i}] без полей {sorted(gaps)}")
            elif ref["scenario_id"] == scen:
                fail(item["insight_id"],
                     f"сценарий {scen} одновременно выдан и объявлен отказанным")

        print(f"  [ok] {item['insight_id']}: {len(item['evidence'])} источников, "
              f"{len(item['interpretation']['consequences'])} последствий, score {item['relevance']['score']}")

print()
if failures:
    print(f"ПРОВАЛЕНО: {failures} ошибок")
    sys.exit(1)
print(f"Все фикстуры соответствуют контракту {CONTRACT_VERSION}")
