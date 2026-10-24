#!/usr/bin/env python3
"""
score_relevance() — детерминированный отбор событий под компанию.

Ни одного обращения к языковой модели. Ноль токенов, воспроизводимый
результат, объяснимая выдача: на вопрос «почему эта новость наверху»
возвращается разложение по пяти компонентам, а не ссылка на модель.

Это вторая ступень каскада. Первая — словарный фильтр по сущностям,
третья — языковая модель на тех событиях, что прошли порог.

    from score_relevance import Scorer
    scorer = Scorer("scenarios.yaml")
    results = scorer.score(profile, event, role="CFO")

Возвращается список ScenarioScore, отсортированный по убыванию score.
Поле `to_contract()` отдаёт объект `relevance` из insight.schema.json.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    raise SystemExit("нужен pyyaml: pip install pyyaml")

COMPONENTS = ("factor_exposure", "sector_match", "counterparty_proximity",
              "geography", "materiality")


# ------------------------------------------------------------- условия
def _get(ctx: dict, spec: dict) -> Any:
    """Достаёт значение: field — из профиля компании, event — из события."""
    if "field" in spec:
        return ctx["profile"].get(spec["field"])
    if "event" in spec:
        return ctx["event"].get(spec["event"])
    return None


def evaluate(cond: dict | None, ctx: dict) -> bool:
    """Мини-язык условий. Сознательно крошечный: всё, что он не умеет,
    должно считаться в витрине, а не в конфиге."""
    if not cond:
        return True
    if "all" in cond:
        return all(evaluate(c, ctx) for c in cond["all"])
    if "any" in cond:
        return any(evaluate(c, ctx) for c in cond["any"])
    if "not" in cond:
        return not evaluate(cond["not"], ctx)

    value = _get(ctx, cond)

    if "eq_field" in cond:
        # Сравнение значения события с полем профиля: регион новости против
        # региона компании. Пустое значение с любой стороны — не совпадение.
        other = ctx["profile"].get(cond["eq_field"])
        return value is not None and other is not None and _norm(value) == _norm(other)
    if "eq" in cond:
        return _norm(value) == _norm(cond["eq"])
    if "ne" in cond:
        return _norm(value) != _norm(cond["ne"])
    if "in" in cond:
        return _norm(value) in {_norm(v) for v in cond["in"]}
    if "gte" in cond:
        return _num(value) is not None and _num(value) >= cond["gte"]
    if "lte" in cond:
        return _num(value) is not None and _num(value) <= cond["lte"]
    if "gt" in cond:
        return _num(value) is not None and _num(value) > cond["gt"]
    if "lt" in cond:
        return _num(value) is not None and _num(value) < cond["lt"]
    if "startswith" in cond:
        s = "" if value is None else str(value)
        return any(s.startswith(p) for p in cond["startswith"])
    if "contains_any" in cond:
        items = value or []
        if isinstance(items, str):
            items = [items]
        have = {_norm(i) for i in items}
        return bool(have & {_norm(v) for v in cond["contains_any"]})
    if "contains" in cond:
        items = value or []
        if isinstance(items, str):
            items = [items]
        return _norm(cond["contains"]) in {_norm(i) for i in items}
    raise ValueError(f"непонятное условие: {cond}")


def _norm(v: Any) -> Any:
    if isinstance(v, bool):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, str):
        return v.strip().lower()
    return v


def _num(v: Any) -> float | None:
    try:
        if v is None:
            return None
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def component_value(spec: dict | None, ctx: dict) -> float:
    """Первое сработавшее правило выигрывает. Порядок правил в конфиге —
    это приоритет, и он виден человеку без чтения кода."""
    if spec is None:
        return 0.0
    for rule in spec.get("rules", []):
        if evaluate(rule.get("when"), ctx):
            return float(rule["value"])
    return float(spec.get("default", 0.0))


# ------------------------------------------------------------- результат
@dataclass
class ScenarioScore:
    scenario_id: str
    scenario_name: str
    role: str
    score: float
    threshold: float
    passed: bool
    raw: dict = field(default_factory=dict)
    weighted: dict = field(default_factory=dict)
    role_multiplier: float = 1.0
    penalties: list = field(default_factory=list)
    blocked_by: str | None = None
    block_message: str | None = None
    evidence_required: dict = field(default_factory=dict)
    product_hints: list = field(default_factory=list)
    copy: str = ""

    def explanation(self) -> str:
        if self.blocked_by:
            return self.block_message or "сценарий заблокирован проверкой качества данных"
        top = sorted(self.weighted.items(), key=lambda kv: kv[1], reverse=True)[:2]
        names = {
            "factor_exposure": "экспозиция на фактор события",
            "sector_match": "отраслевое совпадение",
            "counterparty_proximity": "связь через контрагентов",
            "geography": "география",
            "materiality": "масштаб компании",
        }
        parts = [f"{names[k]} {v:.2f}" for k, v in top if v > 0]
        return "Наибольший вклад: " + ", ".join(parts) if parts else "вклад компонент близок к нулю"

    def to_contract(self) -> dict:
        """Объект `relevance` из insight.schema.json."""
        return {
            "scenario_id": self.scenario_id,
            "score": round(self.score, 2),
            "threshold": self.threshold,
            "components": {k: round(v, 2) for k, v in self.weighted.items()},
            "explanation": self.explanation(),
        }

    def to_refusal(self) -> dict | None:
        """Запись для `data_quality.refused`, если guard остановил вывод.

        Решение команды от 21.10.2026 (критерий приёмки 2): при недостаточном
        качестве данных система не выдаёт осторожный вывод с предупреждением,
        а отказывается от вывода и называет причину. Предупреждение рядом с
        неверным выводом оставляет неверный вывод на экране.
        """
        if not self.blocked_by:
            return None
        return {
            "scenario_id": self.scenario_id,
            "guard": self.blocked_by,
            "message": self.block_message or "вывод остановлен проверкой качества данных",
        }


# ------------------------------------------------------------- скорер
class Scorer:
    def __init__(self, config_path: str | Path) -> None:
        cfg = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
        self.version = cfg["version"]
        self.defaults = cfg["defaults"]
        self.scenarios = [s for s in cfg["scenarios"] if s.get("enabled", True)]
        self._validate()

    def _validate(self) -> None:
        for s in self.scenarios:
            w = s.get("weights", self.defaults["weights"])
            total = round(sum(w.values()), 6)
            if total != 1.0:
                raise ValueError(f"{s['id']}: сумма весов {total}, должна быть 1.0")
            for c in s.get("components", {}):
                if c not in COMPONENTS:
                    raise ValueError(f"{s['id']}: неизвестная компонента {c}")

    @staticmethod
    def prepare_profile(profile: dict) -> dict:
        """Производные поля, которые нужны конфигу, но которых нет в витрине."""
        p = dict(profile)
        suspect = bool(p.get("grp_group_structure_suspect"))
        grp_rev = _num(p.get("grp_revenue_bn_rub"))
        own_rev = _num(p.get("revenue_bn_rub")) or 0.0
        p["effective_revenue_bn"] = own_rev if (suspect or grp_rev is None) else max(grp_rev, own_rev)
        ic = p.get("import_countries")
        if isinstance(ic, str):
            p["import_countries"] = [x for x in re.split(r"[|,]", ic) if x.strip()]
        return p

    def score(self, profile: dict, event: dict, role: str = "CFO") -> list[ScenarioScore]:
        ctx = {"profile": self.prepare_profile(profile), "event": event}
        out: list[ScenarioScore] = []

        for s in self.scenarios:
            if not evaluate(s.get("triggers"), ctx):
                continue
            if not evaluate(s.get("audience"), ctx):
                continue

            weights = s.get("weights", self.defaults["weights"])
            threshold = s.get("threshold", self.defaults["threshold"])
            mult = float(s.get("role_multiplier", {}).get(role, 1.0))

            blocked_by = block_msg = None
            penalties: list[dict] = []
            for g in s.get("guards", []):
                if evaluate(g["require"], ctx):
                    continue
                if g.get("on_fail") == "block":
                    blocked_by, block_msg = g["id"], g.get("message")
                    break
                penalties.append({"id": g["id"], "penalty": float(g.get("penalty", 0.0)),
                                  "message": g.get("message", "")})

            raw: dict[str, float] = {}
            for c in COMPONENTS:
                spec = s.get("components", {}).get(c)
                if spec is None and c == "materiality":
                    spec = self.defaults["materiality"]
                raw[c] = component_value(spec, ctx)

            weighted = {c: raw[c] * weights[c] for c in COMPONENTS}
            total = sum(weighted.values()) * mult
            total = max(0.0, total - sum(p["penalty"] for p in penalties))
            if blocked_by:
                total = 0.0

            out.append(ScenarioScore(
                scenario_id=s["id"],
                scenario_name=s["name"],
                role=role,
                score=round(total, 4),
                threshold=threshold,
                passed=(total >= threshold and not blocked_by),
                raw=raw,
                weighted=weighted,
                role_multiplier=mult,
                penalties=penalties,
                blocked_by=blocked_by,
                block_message=block_msg,
                evidence_required=s.get("evidence_required", {}),
                product_hints=s.get("product_hints", []),
                copy=s.get("copy", {}).get(role, ""),
            ))

        return sorted(out, key=lambda r: r.score, reverse=True)

    def best(self, profile: dict, event: dict, role: str = "CFO") -> ScenarioScore | None:
        passed = [r for r in self.score(profile, event, role) if r.passed]
        return passed[0] if passed else None


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Разовый прогон скоринга")
    ap.add_argument("--config", default="scenarios.yaml")
    ap.add_argument("--profile", required=True, help="json-файл профиля компании")
    ap.add_argument("--event", required=True, help="json-файл события")
    ap.add_argument("--role", default="CFO")
    a = ap.parse_args()

    sc = Scorer(a.config)
    prof = json.loads(Path(a.profile).read_text(encoding="utf-8"))
    ev = json.loads(Path(a.event).read_text(encoding="utf-8"))
    for r in sc.score(prof, ev, a.role):
        mark = "прошёл" if r.passed else ("заблокирован" if r.blocked_by else "ниже порога")
        print(f"{r.scenario_id:<26} {r.score:.2f}  {mark}")
        print(f"   {r.explanation()}")
