#!/usr/bin/env python3
"""
Автопроверка инсайта. Главная функция — ловить числа без источника.

Работает на выходе бэкенда, без языковых моделей и без человека. Ставится
в CI и прогоняется на каждом инсайте golden set перед демонстрацией.

Принцип: инсайт по контракту обязан сам перечислить всё, на чём построен —
`client.features_used`, `event.confirmed_facts`, `interpretation.bank_view`
и `data_quality`. Значит, любое число в тексте, которого нет в этом
перечне, появилось из головы модели. Именно это и проверяется.

    python3 check_insight.py insight.json
    python3 check_insight.py insight.json --tools tool_outputs.json
    python3 check_insight.py fixtures/*.json --quiet
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Служебные строки, из которых числа не извлекаются: это не утверждения
# о бизнесе, а адреса и метки времени.
NOISE = [
    r"\d{4}-\d{2}-\d{2}T[\d:+.]+", r"\d{4}-\d{2}-\d{2}",
    r"\b\d+-\d+M\b", r"\bU_\d+\b", r"\bF_\d+\b",
    r"corpus://\S+", r"db://\S+", r"inference://\S+", r"https?://\S+",
    r"\bins_\d+_\S+", r"\btrc_\w+", r"\be\d+\b",
    r"\b\d+[ПКк]\d+\b", r"\b\d{1,2}[МM]\d{2}\b",
]
NOISE_RE = re.compile("|".join(NOISE))
NUM_RE = re.compile(r"(?<![\d\-])\d+(?:[.,]\d+)?")

FORBIDDEN_PHRASES = [
    ("доля выручки", "П4"), ("доли выручки", "П4"),
    ("долю выручки", "П4"), ("доле выручки", "П4"),
    ("процент выручки", "П4"),
]
RISK_WORDS = ("риск", "угроз", "тревож", "негатив")
STALE_MONTHS = 12


@dataclass
class Violation:
    rule: str
    where: str
    detail: str
    severity: str = "error"

    def __str__(self) -> str:
        return f"[{self.rule}] {self.where}: {self.detail}"


def nums_from(text: str) -> set[float]:
    # Сначала выбрасываем служебное, затем разрываем диапазоны вида
    # «12-18%»: иначе второе число прячется за дефисом и проверка его
    # не видит. Горизонты «0-3M» к этому моменту уже вырезаны.
    cleaned = re.sub(r"(?<=\d)-(?=\d)", " ", NOISE_RE.sub(" ", text))
    return {float(m.replace(",", ".")) for m in NUM_RE.findall(cleaned)}


def collect_sources(insight: dict, tools: dict | None) -> set[float]:
    """Все числа, которые инсайт объявил своими источниками."""
    src: set[float] = set()

    def add(v):
        if isinstance(v, bool):
            return
        if isinstance(v, (int, float)):
            src.add(float(v))
            if 0 <= v <= 1:
                src.add(float(round(v * 100)))   # доля, записанная процентами
        elif isinstance(v, str):
            src.update(nums_from(v))
        elif isinstance(v, dict):
            for x in v.values():
                add(x)
        elif isinstance(v, list):
            for x in v:
                add(x)

    for f in insight.get("client", {}).get("features_used", []):
        add(f.get("value"))
        add(f.get("label"))
    add(insight.get("data_quality", {}))
    for key in ("confirmed_facts", "unconfirmed", "headline"):
        add(insight.get("event", {}).get(key))
    bv = insight.get("interpretation", {}).get("bank_view") or {}
    add(bv.get("quote"))
    add(bv.get("text"))
    for e in insight.get("evidence", []):
        add(e.get("label"))
    if tools:
        add(tools)

    extra = set()
    for s in src:
        extra.add(round(s))
        if 0 <= s <= 1:
            extra.add(float(round(s * 100)))
    return src | extra


def narrative_numbers(insight: dict) -> list[tuple[str, float]]:
    """Числа в тексте, который читает пользователь."""
    found: list[tuple[str, float]] = []
    interp = insight.get("interpretation", {})
    for key in ("headline", "what_happened", "why_it_matters"):
        for n in nums_from(interp.get(key, "") or ""):
            found.append((f"interpretation.{key}", n))
    for i, c in enumerate(interp.get("consequences", [])):
        for n in nums_from(c.get("text", "")):
            found.append((f"interpretation.consequences[{i}].text", n))
    for i, m in enumerate(interp.get("model_inference", []) or []):
        for n in nums_from(m):
            found.append((f"interpretation.model_inference[{i}]", n))
    for i, a in enumerate(insight.get("actions", []) or []):
        for n in nums_from(a.get("text", "")):
            found.append((f"actions[{i}].text", n))
    return found


def check(insight: dict, tools: dict | None = None) -> list[Violation]:
    v: list[Violation] = []
    interp = insight.get("interpretation", {})

    # П1 — числа без источника. Ради этой проверки всё и затевалось.
    sources = collect_sources(insight, tools)
    for where, n in narrative_numbers(insight):
        if not any(abs(n - s) < 1e-6 for s in sources):
            v.append(Violation("П1", where,
                               f"число {n:g} не найдено ни в одном объявленном источнике"))

    # П2 — утверждение без ссылки, ссылка в никуда
    ids = {e["id"] for e in insight.get("evidence", [])}
    for i, c in enumerate(interp.get("consequences", [])):
        if not c.get("evidence_ids"):
            v.append(Violation("П2", f"consequences[{i}]", "вывод без evidence_ids"))
        for eid in c.get("evidence_ids", []):
            if eid not in ids:
                v.append(Violation("П2", f"consequences[{i}]",
                                   f"ссылка на несуществующий источник {eid}"))
    for e in insight.get("evidence", []):
        for dep in e.get("depends_on", []) or []:
            if dep not in ids:
                v.append(Violation("П2", f"evidence[{e['id']}]",
                                   f"зависимость от несуществующего {dep}"))

    # П6 — позиция банка без даты или из пересмотренного документа
    bv = interp.get("bank_view")
    if bv:
        if not bv.get("as_of_date"):
            v.append(Violation("П6", "interpretation.bank_view",
                               "позиция банка без даты не проверяема"))
        if bv.get("superseded_by"):
            v.append(Violation("П6", "interpretation.bank_view",
                               f"цитируется документ, пересмотренный в {bv['superseded_by']}"))
        if not bv.get("page"):
            v.append(Violation("П6", "interpretation.bank_view",
                               "нет номера страницы", "warning"))
    for e in insight.get("evidence", []):
        if e.get("kind") == "alfa_view" and not e.get("as_of_date"):
            v.append(Violation("П6", f"evidence[{e['id']}]",
                               "цитата аналитики без даты"))

    # П4 — запрещённая формулировка
    blob = json.dumps(insight, ensure_ascii=False).lower()
    for phrase, rule in FORBIDDEN_PHRASES:
        if phrase in blob:
            v.append(Violation(rule, "insight",
                               f"формулировка «{phrase}» применительно к платежам"))

    # П4 — вывод о контрагентах при недостаточном покрытии
    dq = insight.get("data_quality", {}) or {}
    tier = dq.get("flow_coverage_tier")
    if tier in {"low", "negligible"}:
        text = " ".join(filter(None, [
            interp.get("why_it_matters", ""),
            " ".join(c.get("text", "") for c in interp.get("consequences", []))]))
        if re.search(r"плательщик|покупател|контрагент|зависимост", text, re.I):
            v.append(Violation("П4", "interpretation",
                               f"вывод о контрагентах при покрытии {tier}"))
        if not dq.get("notes"):
            v.append(Violation("П4", "data_quality",
                               f"покрытие {tier} без примечания"))

    # П3 — ссылка на поле, которого нет
    missing = set(insight.get("client", {}).get("features_missing", []) or [])
    used = {f.get("code") for f in insight.get("client", {}).get("features_used", [])}
    for m in missing & used:
        v.append(Violation("П3", "client", f"использовано пустое поле {m}"))
    blob_raw = json.dumps(insight, ensure_ascii=False)
    for m in missing:
        if m in blob_raw.replace(f'"{m}"', "", 1):
            v.append(Violation("П3", "insight",
                               f"упоминание пустого поля {m} в тексте", "warning"))

    # П5 — признак ключевого собственника как риск
    for i, c in enumerate(interp.get("consequences", [])):
        t = c.get("text", "").lower()
        if "key_owner" in t or "ключевого собственника" in t:
            if c.get("type") == "risk" or any(w in t for w in RISK_WORDS):
                v.append(Violation("П5", f"consequences[{i}]",
                                   "признак ключевого собственника подан как риск"))

    # Ролевое правило для главбуха
    if insight.get("client", {}).get("role_view") == "CHIEF_ACCOUNTANT":
        if interp.get("model_inference"):
            v.append(Violation("РОЛЬ", "interpretation.model_inference",
                               "главбуху не показываются выводы модели"))
        for i, c in enumerate(interp.get("consequences", [])):
            if c.get("confidence") != "high":
                v.append(Violation("РОЛЬ", f"consequences[{i}]",
                                   f"главбуху показано последствие с confidence={c.get('confidence')}"))

    # П8 — выводы по неподтверждённой группе
    if insight.get("client", {}).get("group_structure_suspect"):
        text = json.dumps(interp, ensure_ascii=False).lower()
        if "групп" in text:
            v.append(Violation("П8", "interpretation",
                               "вывод уровня группы при неподтверждённой структуре"))

    return v


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--tools", type=Path, help="json с ответами инструментов")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    tools = json.loads(a.tools.read_text(encoding="utf-8")) if a.tools else None
    total_err = total_warn = checked = 0

    for fp in a.files:
        doc = json.loads(fp.read_text(encoding="utf-8"))
        items = doc.get("items", [doc]) if isinstance(doc, dict) else doc
        for item in items:
            if "interpretation" not in item:
                continue
            checked += 1
            vs = check(item, tools)
            errs = [x for x in vs if x.severity == "error"]
            warns = [x for x in vs if x.severity == "warning"]
            total_err += len(errs)
            total_warn += len(warns)
            iid = item.get("insight_id", fp.name)
            if errs or warns:
                print(f"{iid}")
                for x in errs + warns:
                    print(f"  {'ОШИБКА' if x.severity == 'error' else 'предупр.'} {x}")
            elif not a.quiet:
                print(f"{iid}: чисто")

    print(f"\nпроверено инсайтов: {checked}, ошибок: {total_err}, предупреждений: {total_warn}")
    return 1 if total_err else 0


if __name__ == "__main__":
    raise SystemExit(main())
