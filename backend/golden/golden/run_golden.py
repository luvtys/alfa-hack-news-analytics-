#!/usr/bin/env python3
"""
Прогон golden set.

Без бэкенда проверяет отбор: сработал ли нужный сценарий, промолчал ли там,
где должен, отработали ли guard-ы. С бэкендом дополнительно прогоняет через
check_insight каждый выданный инсайт.

    python3 run_golden.py --datamart ../datamart/out --scoring ../scoring
    python3 run_golden.py ... --insights backend_out/   # когда API поднят
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).parent))
from check_insight import check  # noqa: E402


def load_scorer(scoring_dir: Path):
    sys.path.insert(0, str(scoring_dir))
    from score_relevance import Scorer  # noqa: E402
    return Scorer(scoring_dir / "scenarios.yaml")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", type=Path, default=Path(__file__).parent / "golden_set.yaml")
    ap.add_argument("--datamart", type=Path, default=Path("../datamart/out"))
    ap.add_argument("--scoring", type=Path, default=Path("../scoring"))
    ap.add_argument("--insights", type=Path, help="каталог с выдачей бэкенда")
    a = ap.parse_args()

    gs = yaml.safe_load(a.golden.read_text(encoding="utf-8"))
    scorer = load_scorer(a.scoring.resolve())
    prof = pd.read_parquet(a.datamart / "company_profile.parquet")
    prof = prof.where(pd.notna(prof), None)
    by_id = {r["SYNTHETIC_U"]: r for r in prof.to_dict("records")}

    tp = fp = tn = fn = 0
    wrong_scenario = blocked_ok = 0
    rows = []

    for pair in gs["pairs"]:
        comp = by_id.get(pair["company"])
        if comp is None:
            print(f"{pair['id']}: компания {pair['company']} отсутствует в витрине")
            return 1
        ev = dict(gs["events"][pair["event"]])
        ev.setdefault("geo_match_import_country", False)
        exp = pair["expect"]

        results = scorer.score(comp, ev, pair.get("role", "CFO"))
        passed = [r for r in results if r.passed]
        top = passed[0] if passed else None
        blocked = [r for r in results if r.blocked_by]

        if exp.get("appears"):
            if top is None:
                fn += 1
                status, note = "ПРОПУСК", "ничего не прошло порог"
            elif exp.get("scenario") and top.scenario_id != exp["scenario"]:
                wrong_scenario += 1
                fp += 1
                status, note = "НЕ ТОТ", f"{top.scenario_id} вместо {exp['scenario']}"
            elif exp.get("score_min") and top.score < exp["score_min"]:
                fn += 1
                status, note = "НИЗКИЙ", f"{top.score:.2f} < {exp['score_min']}"
            else:
                tp += 1
                status, note = "ok", f"{top.scenario_id} {top.score:.2f}"
        else:
            forb = exp.get("forbidden_scenario")
            hit = [r for r in passed if not forb or r.scenario_id == forb]
            if hit:
                fp += 1
                status, note = "ЛОЖНОЕ", f"{hit[0].scenario_id} {hit[0].score:.2f}"
            else:
                tn += 1
                reason = ""
                if exp.get("blocked_by"):
                    b = [r for r in blocked if r.blocked_by == exp["blocked_by"]]
                    if b:
                        blocked_ok += 1
                        reason = f"заблокирован guard-ом {exp['blocked_by']}"
                    else:
                        reason = f"ожидался блок {exp['blocked_by']}, его нет"
                        fp += 1
                        tn -= 1
                status, note = "ok", reason or "молчит"

        rows.append((pair["id"], pair["company"], pair["event"],
                     pair.get("role", "CFO"), status, note))

    print(f"{'пара':<5} {'компания':<10} {'событие':<11} {'роль':<17} {'итог':<8} примечание")
    for r in rows:
        print(f"{r[0]:<5} {r[1]:<10} {r[2]:<11} {r[3]:<17} {r[4]:<8} {r[5]}")

    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
    print(f"\nверно сработал {tp}, верно промолчал {tn}, "
          f"ложных срабатываний {fp}, пропусков {fn}")
    print(f"точность {precision:.2f}, полнота {recall:.2f}, F1 {f1:.2f}")
    print(f"guard-ов отработало по ожиданию: {blocked_ok}")

    code = 0 if (fp == 0 and fn == 0) else 1

    if a.insights:
        print("\n=== АВТОПРОВЕРКА ВЫДАННЫХ ИНСАЙТОВ ===")
        errs = 0
        files = sorted(a.insights.glob("*.json"))
        for fpath in files:
            doc = json.loads(fpath.read_text(encoding="utf-8"))
            for item in doc.get("items", [doc]):
                if "interpretation" not in item:
                    continue
                vs = [v for v in check(item) if v.severity == "error"]
                errs += len(vs)
                if vs:
                    print(f"{item.get('insight_id', fpath.name)}")
                    for v in vs:
                        print(f"  {v}")
        print(f"файлов: {len(files)}, ошибок: {errs}")
        code = code or (1 if errs else 0)

    return code


if __name__ == "__main__":
    raise SystemExit(main())
