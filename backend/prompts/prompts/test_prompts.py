#!/usr/bin/env python3
"""Проверка промптов.

Главная идея: few-shot примеры обязаны подчиняться тем самым правилам,
которым они учат. Пример, нарушающий П1 или П4, учит модель нарушать П1
и П4 — и никакой инструкцией это потом не лечится.

    python3 test_prompts.py [путь к витрине]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_prompts import MODES, ROOT, build, estimate_tokens, json_blocks  # noqa: E402

DATAMART = Path(__file__).parent.parent.parent / "datamart" / "datamart" / "out"
TOKEN_BUDGET = 3500           # на один системный промпт
FORBIDDEN = ["доля выручки", "доли выручки", "долю выручки", "доле выручки"]

failures = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global failures
    if not ok:
        failures += 1
    print(f"  [{'ok' if ok else 'ОШИБКА'}] {name}" + (f" — {detail}" if detail else ""))


# Даты, горизонты и идентификаторы не являются утверждениями о бизнесе.
# Без их отсечения «3-6M» разбирается как числа 3 и −6, а ISO-дата —
# как 2026, −10 и −20, и проверка П1 начинает ругаться на пустом месте.
NOISE = [
    r"\d{4}-\d{2}-\d{2}T[\d:+.]+",      # отметка времени
    r"\d{4}-\d{2}-\d{2}",               # дата
    r"\b\d+-\d+M\b",                    # горизонт 0-3M
    r"\b[a-z]+\d+\b",                   # e1, p3
    r"\bU_\d+\b",                       # идентификатор компании
    r"corpus://\S+", r"db://\S+", r"inference://\S+",
    r"\b1П\d+\b", r"\b\d+К\d+\b",       # 1П26, 3К26
]
NOISE_RE = re.compile("|".join(NOISE))
NUM_RE = re.compile(r"(?<![\d\-])\d+(?:[.,]\d+)?")


def numbers(obj) -> set[float]:
    """Числа, которые что-то утверждают о бизнесе."""
    found: set[float] = set()

    def walk(o, key: str = ""):
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, k)
        elif isinstance(o, list):
            for v in o:
                walk(v, key)
        elif isinstance(o, bool):
            pass
        elif isinstance(o, (int, float)):
            # Номер шага плана — служебный. Номер страницы остаётся:
            # он встречается и во входе, и в подписи к источнику, и
            # проверка «страница взята из ответа инструмента» осмысленна.
            if key not in {"no", "step_no", "top_k"}:
                found.add(float(o))
        elif isinstance(o, str):
            for m in NUM_RE.findall(NOISE_RE.sub(" ", o)):
                found.add(float(m.replace(",", ".")))

    walk(obj)
    return found


def derivable(value: float, sources: set[float]) -> bool:
    """П1: число либо есть в источнике, либо получено из доли процентами
    с округлением до целого. Других преобразований не разрешено."""
    for s in sources:
        if abs(value - s) < 1e-9:
            return True
        if 0 <= s <= 1 and abs(value - round(s * 100)) < 1e-9:
            return True
        if abs(value - round(s)) < 1e-9:
            return True
    return False


def main() -> int:
    print("=== СБОРКА И БЮДЖЕТ ===")
    texts = {}
    for mode in MODES:
        t = build(mode)
        texts[mode] = t
        tok = estimate_tokens(t)
        check(f"{mode}: укладывается в {TOKEN_BUDGET} токенов",
              tok <= TOKEN_BUDGET, f"~{tok}")
        check(f"{mode}: общий блок подставлен",
              "П1. Числа не вычисляются" in t)

    print("\n=== JSON В ПРИМЕРАХ РАЗБИРАЕТСЯ ===")
    blocks = {}
    for mode in MODES:
        try:
            blocks[mode] = json_blocks((ROOT / MODES[mode][0]).read_text(encoding="utf-8"))
            check(f"{mode}: {len(blocks[mode])} блоков JSON валидны", True)
        except json.JSONDecodeError as e:
            blocks[mode] = []
            check(f"{mode}: JSON валиден", False, str(e))

    print("\n=== П1: ЧИСЛА В ПРИМЕРЕ АНАЛИТИКА ВЫВОДИМЫ ИЗ ВХОДА ===")
    an = blocks["analyst"]
    src, out_obj = an[0], an[1]
    src_nums = numbers(src)
    bad = []
    for v in numbers(out_obj):
        if not derivable(v, src_nums):
            bad.append(v)
    check("каждое число выхода есть во входе или получено округлением доли",
          not bad, f"не выводятся: {sorted(bad)}" if bad else "")

    print("\n=== П2: ССЫЛКИ НА ИСТОЧНИКИ СУЩЕСТВУЮТ ===")
    ids = {e["id"] for e in out_obj["evidence"]}
    missing = set()
    for c in out_obj["interpretation"]["consequences"]:
        missing |= set(c["evidence_ids"]) - ids
    for e in out_obj["evidence"]:
        missing |= set(e.get("depends_on", [])) - ids
    check("все evidence_ids определены", not missing, str(sorted(missing)))
    check("у каждого alfa_view проставлена дата",
          all(e.get("as_of_date") for e in out_obj["evidence"] if e["kind"] == "alfa_view"))
    check("вывод модели вынесен в model_inference",
          len(out_obj["interpretation"]["model_inference"]) > 0)

    print("\n=== П4: ЗАПРЕЩЁННАЯ ФОРМУЛИРОВКА В ПРИМЕРАХ ===")
    # Искать во всём промпте нельзя: сам текст правила П4 содержит эту
    # формулировку как запрещённую. Проверяем только примеры ответов.
    for mode in ("planner", "analyst", "writer"):
        sample = json.dumps(blocks[mode], ensure_ascii=False)
        hits = [f for f in FORBIDDEN if f in sample]
        check(f"{mode}: в примерах ответов нет «доли выручки»", not hits, str(hits))
    crit = texts["critic"]
    check("critic: формулировка присутствует только как разбираемый дефект",
          any(f in crit for f in FORBIDDEN) and "П4" in crit)

    print("\n=== П5: ПРИЗНАК СОБСТВЕННИКА НЕ ТРАКТУЕТСЯ КАК РИСК ===")
    an_text = (ROOT / "02_analyst.md").read_text(encoding="utf-8")
    bad_ctx = re.findall(r"[^.]*key_owner_flag[^.]*риск[^.]*\.", an_text)
    check("в примере аналитика нет связки «ключевой собственник — риск»", not bad_ctx)
    check("в примере критика такая связка разобрана как дефект",
          "П5" in crit and "key_owner_flag" in crit)

    print("\n=== КРИТИК ДЕЙСТВИТЕЛЬНО ЛОВИТ ОШИБКИ ===")
    verdicts = [b for b in blocks["critic"] if isinstance(b, dict) and "verdict" in b]
    check("пример критика заканчивается вердиктом fail",
          any(v["verdict"] == "fail" for v in verdicts))
    defects = [d for v in verdicts for d in v.get("defects", [])]
    check("в примере разобрано не меньше пяти дефектов", len(defects) >= 5, f"{len(defects)}")
    rules = {d["rule"] for d in defects}
    check("дефекты ссылаются на номера правил",
          rules.issubset({"П1", "П2", "П3", "П4", "П5", "П6", "П7", "П8", "П9"}), str(sorted(rules)))
    check("у каждого дефекта есть цитата и предписание",
          all(d.get("quote") and d.get("fix") for d in defects))

    print("\n=== РЕДАКТОР: ЧИСЛА ОДИНАКОВЫ ВО ВСЕХ РОЛЯХ ===")
    roles = blocks["writer"]
    check("три роли описаны", len(roles) == 3, f"{len(roles)}")
    owner_n, cfo_n, acc_n = (numbers(r) for r in roles)
    check("у главбуха нет чисел, которых нет у финдиректора",
          acc_n <= cfo_n | owner_n, str(sorted(acc_n - (cfo_n | owner_n))))
    check("у главбуха выводов меньше, чем у финдиректора",
          len(roles[2]["actions"]) <= len(roles[1]["actions"]))
    check("заголовки не длиннее 90 символов",
          all(len(r["headline"]) <= 90 for r in roles),
          str([len(r["headline"]) for r in roles]))

    print("\n=== ПРОФИЛИ В ПРИМЕРАХ СОВПАДАЮТ С ВИТРИНОЙ ===")
    try:
        import pandas as pd
        prof = pd.read_parquet(DATAMART / "company_profile.parquet")
        prof = prof.where(pd.notna(prof), None)
        real = {r["SYNTHETIC_U"]: r for r in prof.to_dict("records")}
        p = src["profile"]
        r = real[p["SYNTHETIC_U"]]
        mism = [k for k, v in p.items()
                if k in r and isinstance(v, (int, float)) and not isinstance(v, bool)
                and r[k] is not None and abs(float(v) - float(r[k])) > 0.001]
        check(f"профиль {p['SYNTHETIC_U']} в примере соответствует витрине",
              not mism, str(mism))
        cp = src["counterparties"]
        check("показатели по контрагентам совпадают с витриной",
              abs(cp["top_payer_share"] - float(r["top_payer_share"])) < 0.001
              and cp["in_cnt"] == int(r["in_cnt"])
              and cp["flow_coverage_tier"] == r["flow_coverage_tier"])
        ctrl = real["U_4601"]
        check("контрольная компания в примере критика действительно без концентрации",
              float(ctrl["top_payer_share"]) < 0.1 and int(ctrl["concentration_flag"]) == 0,
              f"top1 {float(ctrl['top_payer_share']):.3f}")
    except ImportError:
        print("  (pandas недоступен, сверка с витриной пропущена)")

    print()
    if failures:
        print(f"ПРОВАЛЕНО: {failures}")
        return 1
    print("Все проверки пройдены")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
