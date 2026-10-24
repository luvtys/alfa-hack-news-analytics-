#!/usr/bin/env python3
"""Генерирует DDL под PostgreSQL и прогоняет проверки витрины."""
import sys
from pathlib import Path
import pandas as pd

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "out")
# Демо-компании питча. U_9250 из первой версии списка убран сознательно:
# у него доля топ-1 плательщика 65%, но банк наблюдает 0,06% выручки —
# ровно тот случай, который guard flow_coverage обязан блокировать.
DEMO = ["U_106783", "U_26030", "U_1941", "U_102920", "U_4601"]

PG = {"int64": "bigint", "Int64": "bigint", "float64": "double precision",
      "bool": "boolean", "object": "text"}

TABLES = ["company_features", "group_features", "payment_edges",
          "counterparty_stats", "affiliates", "feature_availability"]
PK = {"company_features": "SYNTHETIC_U", "group_features": "GROUP_ID",
      "counterparty_stats": "SYNTHETIC_U"}
INDEX = {
    "company_features": ["GROUP_ID", "okved2", "REGION", "is_large_entity", "exp_rate", "exp_fx"],
    "payment_edges": ["payer", "beneficiary", "layer"],
    "counterparty_stats": ["concentration_flag"],
    "affiliates": ["company_a", "company_b"],
    "group_features": ["is_large_group"],
}

ddl = ["-- Витрина данных для агента новостной аналитики",
       "-- Генерируется build_datamart.py; загрузка — load.sh", ""]
for t in TABLES:
    df = pd.read_parquet(OUT / f"{t}.parquet")
    cols = []
    for c, dt in df.dtypes.items():
        typ = PG.get(str(dt), "text")
        null = " not null" if c == PK.get(t) else ""
        cols.append(f'    "{c}" {typ}{null}')
    ddl.append(f"drop table if exists {t} cascade;")
    ddl.append(f"create table {t} (\n" + ",\n".join(cols) + "\n);")
    if t in PK:
        ddl.append(f'alter table {t} add primary key ("{PK[t]}");')
    for col in INDEX.get(t, []):
        ddl.append(f'create index on {t} ("{col}");')
    ddl.append("")
(OUT / "schema.sql").write_text("\n".join(ddl), encoding="utf-8")

load = ["#!/usr/bin/env bash", "# Загрузка витрины в PostgreSQL.",
        "# Использование: DB_URL=postgres://user:pass@host/db ./load.sh [каталог]",
        "set -euo pipefail", 'DIR="${1:-.}"', 'psql "$DB_URL" -f "$DIR/schema.sql"', ""]
for t in TABLES:
    load.append(f'psql "$DB_URL" -c "\\\\copy {t} from \'$DIR/{t}.csv\' with (format csv, header true, delimiter \';\')"')
load.append("")
load.append('psql "$DB_URL" -c "analyze;"')
(OUT / "load.sh").write_text("\n".join(load), encoding="utf-8")
(OUT / "load.sh").chmod(0o755)
print(f"schema.sql и load.sh записаны ({len(ddl)} строк DDL)")

# ------------------------- проверки -------------------------
print("\n=== ПРОВЕРКИ ===")
comp = pd.read_parquet(OUT / "company_features.parquet")
prof = pd.read_parquet(OUT / "company_profile.parquet")
edges = pd.read_parquet(OUT / "payment_edges.parquet")
cps = pd.read_parquet(OUT / "counterparty_stats.parquet")
grp = pd.read_parquet(OUT / "group_features.parquet")

checks = []
checks.append(("уникальность SYNTHETIC_U", comp.SYNTHETIC_U.is_unique))
checks.append(("мусорный ID исключён", "U_428697" not in set(comp.SYNTHETIC_U)))
checks.append(("сумма выручки групп = сумме по компаниям",
               abs(grp.revenue_rub.sum() - comp.revenue_rub.sum()) < 1))
checks.append(("крупных юрлиц 115", int(comp.is_large_entity.sum()) == 115))
checks.append(("крупных групп 341", int(grp.is_large_group.sum()) == 341))
checks.append(("слои графа покрывают все рёбра",
               set(edges.layer) == {"self", "intragroup", "external"}))
checks.append(("self-loops не попали во внешний слой",
               not (edges[edges.layer == "external"].payer == edges[edges.layer == "external"].beneficiary).any()))
checks.append(("доли top-1 в диапазоне 0..1",
               bool(cps.top_payer_share.dropna().between(0, 1).all())))
checks.append(("профиль не потерял компаний", len(prof) == len(comp)))
for name, ok in checks:
    print(f"  [{'ok' if ok else 'ОШИБКА'}] {name}")

print("\n=== ДЕМО-КОМПАНИИ ===")
cols = ["SYNTHETIC_U", "MAINOKVED_NAME", "REGION", "revenue_bn_rub",
        "grp_n_entities", "grp_revenue_bn_rub", "exp_rate", "exp_fx", "exp_consumer",
        "in_cnt", "out_cnt", "top_payer_share", "unknown_in_share",
        "concentration_flag", "observed_flow_to_revenue"]
d = prof[prof.SYNTHETIC_U.isin(DEMO)][cols].copy()
d["MAINOKVED_NAME"] = d.MAINOKVED_NAME.str[:34]
for c in ["top_payer_share", "unknown_in_share", "observed_flow_to_revenue"]:
    d[c] = d[c].round(2)
pd.set_option("display.width", 220)
print(d.to_string(index=False))

print("\n=== ЭКСПОЗИЦИИ: сколько компаний поймает каждый сценарий ===")
seg = pd.DataFrame({
    "сценарий": ["стоимость долга", "импорт и валюта", "зависимость от контрагента", "спрос и ФОТ"],
    "фильтр": ["exp_rate=1", "exp_fx=1", "concentration_flag=1", "exp_consumer=1 и exp_labour=1"],
    "всего": [int(comp.exp_rate.sum()), int(comp.exp_fx.sum()),
              int(cps.concentration_flag.sum()),
              int(((comp.exp_consumer == 1) & (comp.exp_labour == 1)).sum())],
    "из них крупных": [
        int(comp[comp.is_large_entity == 1].exp_rate.sum()),
        int(comp[comp.is_large_entity == 1].exp_fx.sum()),
        int(cps[cps.SYNTHETIC_U.isin(set(comp[comp.is_large_entity == 1].SYNTHETIC_U))].concentration_flag.sum()),
        int(((comp.is_large_entity == 1) & (comp.exp_consumer == 1) & (comp.exp_labour == 1)).sum()),
    ],
})
print(seg.to_string(index=False))

print("\n=== ПОКРЫТИЕ ГРУППАМИ ===")
lg = grp[grp.is_large_group == 1]
print(f"  юрлиц в крупных группах: {int(lg.n_entities.sum()):,} "
      f"| это {lg.n_entities.sum()/len(comp)*100:.1f}% базы")
print(f"  медианный размер крупной группы: {int(lg.n_entities.median())} юрлиц, "
      f"максимум {int(lg.n_entities.max())}")
print(f"  крупных групп, где НЕТ ни одного крупного юрлица: "
      f"{int((~lg.head_entity.isin(set(comp[comp.is_large_entity==1].SYNTHETIC_U))).sum())}")
