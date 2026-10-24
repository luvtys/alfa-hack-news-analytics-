#!/usr/bin/env python3
"""Прогон конфига сценариев на реальной витрине.

Проверяет три вещи:
  1. движок работает на настоящих профилях, а не на выдуманных;
  2. охват каждого сценария по базе совпадает с ожиданием из документа БА;
  3. демо-компании ведут себя так, как заявлено в питче, включая
     контрольный пример, на котором агент НЕ должен срабатывать.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from score_relevance import Scorer  # noqa: E402

DATAMART = Path(sys.argv[1] if len(sys.argv) > 1 else "../datamart/out")
CONFIG = Path(__file__).parent / "scenarios.yaml"

EVENTS = {
    "key_rate": {
        "headline": "Банк России сохранил ключевую ставку на уровне 14,0%",
        "event_type": "monetary_policy", "entities": ["CBR", "KEY_RATE"],
        "scope": "national", "geo_match_import_country": False,
    },
    "cny": {
        "headline": "Прогноз курса рубля к юаню на конец 2026 года — 13,0",
        "event_type": "fx", "entities": ["FX_RATE", "CNY"],
        "scope": "national", "geo_match_import_country": True,
    },
    "investment": {
        "headline": "Росстат: инвестиции в основной капитал снизились",
        "event_type": "sector_demand", "entities": ["ROSSTAT"],
        "scope": "national", "geo_match_import_country": False,
    },
    "retail": {
        "headline": "Росстат: оборот розничной торговли замедлился",
        "event_type": "sector_demand", "entities": ["ROSSTAT", "RETAIL_TURNOVER", "WAGES"],
        "scope": "national", "geo_match_import_country": False,
    },
    # Негативные события: не должны поднимать ничего. Без них тест
    # проверяет только срабатывания и не ловит ленту, реагирующую на всё.
    "gold": {
        "headline": "Обзор рынка золота: ФРС охладила ралли",
        "event_type": "other", "entities": ["FED", "GOLD"],
        "scope": "global", "geo_match_import_country": False,
    },
    "sport": {
        "headline": "Итоги тура чемпионата по футболу",
        "event_type": "other", "entities": [],
        "scope": "national", "geo_match_import_country": False,
    },
}

DEMO = {
    "U_106783": "производство распределительной аппаратуры",
    "U_26030": "опт моторным топливом",
    "U_1941": "опт бытовыми товарами",
    "U_102920": "опт рыбой и продуктами",
    "U_4601": "опт мясом (контрольный)",
}

failures = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global failures
    if not ok:
        failures += 1
    print(f"  [{'ok' if ok else 'ОШИБКА'}] {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    scorer = Scorer(CONFIG)
    print(f"конфиг версии {scorer.version}, сценариев {len(scorer.scenarios)}\n")

    prof = pd.read_parquet(DATAMART / "company_profile.parquet")
    prof = prof.where(pd.notna(prof), None)
    records = prof.to_dict("records")
    print(f"профилей в витрине: {len(records):,}\n")

    print("=== ОХВАТ ПО БАЗЕ: сколько компаний проходит порог ===")
    coverage = {}
    for ev_name, ev in EVENTS.items():
        passed = {}
        for r in records:
            for res in scorer.score(r, ev, role="CFO"):
                if res.passed:
                    passed.setdefault(res.scenario_id, 0)
                    passed[res.scenario_id] += 1
        coverage[ev_name] = passed
        pretty = ", ".join(f"{k}: {v:,}" for k, v in sorted(passed.items())) or "никто"
        print(f"  {ev_name:<12} -> {pretty}")

    print("\n=== ПРОВЕРКИ ОХВАТА ===")
    base = len(records)
    for ev_name, scen in (("key_rate", "cost_of_debt"), ("cny", "fx_import"),
                          ("investment", "counterparty_dependence"),
                          ("retail", "demand_and_payroll")):
        n = coverage[ev_name].get(scen, 0)
        check(f"{scen}: лента — небольшая доля базы",
              0 < n < base * 0.12, f"{n:,} из {base:,} ({n / base * 100:.1f}%)")
    check("новость про ставку не поднимает сценарий зависимости",
          "counterparty_dependence" not in coverage["key_rate"])
    check("новость про инвестиции не поднимает валютный сценарий",
          "fx_import" not in coverage["investment"])
    check("нерелевантное событие про золото не поднимает ничего",
          not coverage["gold"], str(coverage["gold"]))
    check("спортивная новость не поднимает ничего",
          not coverage["sport"], str(coverage["sport"]))

    print("\n=== РАСПРЕДЕЛЕНИЕ БАЛЛОВ: лента должна ранжировать, а не пропускать всё ===")
    for ev_name in ("key_rate", "investment"):
        vals = sorted(res.score
                      for r in records
                      for res in scorer.score(r, EVENTS[ev_name], role="CFO"))
        if not vals:
            continue
        q = lambda p: vals[min(len(vals) - 1, int(len(vals) * p / 100))]  # noqa: E731
        share = sum(1 for v in vals if v >= 0.55) / len(vals) * 100
        spread = q(90) - q(50)
        print(f"  {ev_name:<11} прошли аудиторию {len(vals):>6,} | "
              f"медиана {q(50):.2f} | p90 {q(90):.2f} | максимум {vals[-1]:.2f} | "
              f"выше порога {share:.0f}%")
        # Смысл проверки не в том, сколько отсеяно, а в том, что баллы
        # различаются: иначе ранжирование ленты вырождается в случайный порядок.
        check(f"{ev_name}: баллы различимы, лента ранжируется",
              spread >= 0.07, f"p90 − медиана = {spread:.2f}")

    print("\n=== ДЕМО-КОМПАНИИ ===")
    by_id = {r["SYNTHETIC_U"]: r for r in records}
    for uid, label in DEMO.items():
        r = by_id[uid]
        print(f"\n  {uid} — {label}")
        for ev_name, ev in EVENTS.items():
            for res in scorer.score(r, ev, role="CFO"):
                mark = "ПРОШЁЛ" if res.passed else ("блок" if res.blocked_by else "ниже порога")
                extra = f" [{res.blocked_by}]" if res.blocked_by else ""
                print(f"    {ev_name:<11} {res.scenario_id:<26} {res.score:.2f}  {mark}{extra}")

    print("\n=== КЛЮЧЕВЫЕ УТВЕРЖДЕНИЯ ПИТЧА ===")
    hero = scorer.score(by_id["U_106783"], EVENTS["investment"], "CFO")
    hero_dep = next((x for x in hero if x.scenario_id == "counterparty_dependence"), None)
    check("U_106783 срабатывает по зависимости от контрагента",
          hero_dep is not None and hero_dep.passed,
          f"score {hero_dep.score:.2f}" if hero_dep else "сценарий не применился")

    ctrl = scorer.score(by_id["U_4601"], EVENTS["investment"], "CFO")
    ctrl_dep = next((x for x in ctrl if x.scenario_id == "counterparty_dependence"), None)
    check("U_4601 НЕ срабатывает по зависимости (контрольный)",
          ctrl_dep is None or not ctrl_dep.passed,
          "сценарий не применился" if ctrl_dep is None else f"score {ctrl_dep.score:.2f}")

    debt = scorer.score(by_id["U_26030"], EVENTS["key_rate"], "CFO")
    debt_s = next((x for x in debt if x.scenario_id == "cost_of_debt"), None)
    check("U_26030 срабатывает по стоимости долга",
          debt_s is not None and debt_s.passed,
          f"score {debt_s.score:.2f}" if debt_s else "нет")

    fx = scorer.score(by_id["U_1941"], EVENTS["cny"], "CFO")
    fx_s = next((x for x in fx if x.scenario_id == "fx_import"), None)
    check("U_1941 срабатывает по импорту",
          fx_s is not None and fx_s.passed,
          f"score {fx_s.score:.2f}" if fx_s else "нет")

    print("\n=== GUARD ПО КАЧЕСТВУ ДАННЫХ ===")
    cps = pd.read_parquet(DATAMART / "counterparty_stats.parquet")
    # Слабый сигнал сознательно впускается в сценарий и блокируется guard-ом,
    # а не отсекается фильтром аудитории: иначе в трассе остаётся пустота
    # вместо объяснения, почему вывод не сделан.
    weak = cps[cps.concentration_weak == 1].head(400).to_dict("records")
    blocked = passed_weak = 0
    for r in weak:
        full = dict(by_id.get(r["SYNTHETIC_U"], {}))
        full.update(r)
        for res in scorer.score(full, EVENTS["investment"], "CFO"):
            if res.scenario_id != "counterparty_dependence":
                continue
            if res.blocked_by == "flow_coverage":
                blocked += 1
            elif res.passed:
                passed_weak += 1
    check("ни один слабый сигнал не попал в ленту", passed_weak == 0, f"{passed_weak}")
    check("слабые сигналы блокируются guard-ом с объяснением",
          blocked == len(weak), f"{blocked} из {len(weak)}")

    print("\n=== РОЛИ ===")
    for role in ("OWNER", "CFO", "CHIEF_ACCOUNTANT"):
        res = scorer.score(by_id["U_106783"], EVENTS["investment"], role)
        dep = next((x for x in res if x.scenario_id == "counterparty_dependence"), None)
        if dep:
            print(f"  {role:<18} score {dep.score:.2f} "
                  f"(множитель {dep.role_multiplier}) — "
                  f"{'в ленте' if dep.passed else 'отсеян'}")
    check("главбуху сценарий зависимости не попадает в ленту",
          not next(x for x in scorer.score(by_id["U_106783"], EVENTS["investment"],
                                           "CHIEF_ACCOUNTANT")
                   if x.scenario_id == "counterparty_dependence").passed)

    print("\n=== СЦЕНАРИИ ОТБИРАЮТ РАЗНЫЕ КОМПАНИИ ===")
    sets = {}
    for ev_name, scen in (("key_rate", "cost_of_debt"), ("cny", "fx_import"),
                          ("investment", "counterparty_dependence"),
                          ("retail", "demand_and_payroll")):
        sets[scen] = {r["SYNTHETIC_U"] for r in records
                      for res in scorer.score(r, EVENTS[ev_name], "CFO")
                      if res.passed and res.scenario_id == scen}
    names = list(sets)
    worst = 0.0
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            inter = len(sets[a] & sets[b])
            union = len(sets[a] | sets[b])
            j = inter / union if union else 0
            worst = max(worst, j)
            print(f"  {a:<26} ∩ {b:<26} пересечение {j * 100:4.1f}%")
    check("сценарии не дублируют друг друга", worst < 0.6, f"максимум {worst * 100:.0f}%")

    print("\n=== ОБЪЕКТ relevance ДЛЯ КОНТРАКТА ===")
    print(" ", hero_dep.to_contract() if hero_dep else "нет")

    print()
    if failures:
        print(f"ПРОВАЛЕНО: {failures}")
        return 1
    print("Все проверки пройдены")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
