#!/usr/bin/env python3
"""
Витрина данных для агента новостной аналитики (хакатон Альфа-Банка).

Собирает из трёх исходных CSV шесть таблиц, пригодных для прямой загрузки
в PostgreSQL и для вызова из инструментов агента.

    company_features     одна строка на юрлицо: профиль + производные признаки
    group_features       одна строка на группу компаний
    payment_edges        граф платежей, размеченный на три слоя
    counterparty_stats   агрегаты по контрагентам на очищенном внешнем слое
    affiliates           пары компаний, связанные через общих физлиц
    feature_availability карта заполненности полей

Решения, которые здесь зашиты (обоснование — в документе БА):
  * SYNTHETIC_U дедуплицируется, мусорный идентификатор исключается;
  * граф режется на три слоя: self / intragroup / external;
  * концентрация считается ТОЛЬКО на внешнем слое;
  * платежи — наблюдаемый банком поток, а не оборот компании;
  * NEGATIVEMARK трактуется как признак ключевого собственника, не как негатив.

Запуск:
    python3 build_datamart.py --data DIR --out DIR
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

JUNK_IDS = {"U_428697"}  # 12 строк с разными ОКВЭД, регионами и выручкой
LARGE_REVENUE_RUB = 15_000_000_000  # определение крупного бизнеса из ТЗ

SECTIONS = {
    "A": range(1, 4), "B": range(5, 10), "C": range(10, 34), "D": [35],
    "E": range(36, 40), "F": range(41, 44), "G": range(45, 48),
    "H": range(49, 54), "I": [55, 56], "J": range(58, 64), "K": range(64, 67),
    "L": [68], "M": range(69, 76), "N": range(77, 83), "O": [84], "P": [85],
    "Q": range(86, 89), "R": range(90, 94), "S": range(94, 97),
}
SECTION_NAMES = {
    "A": "Сельское хозяйство", "B": "Добыча", "C": "Обрабатывающая промышленность",
    "D": "Энергетика", "E": "Водоснабжение и отходы", "F": "Строительство",
    "G": "Торговля", "H": "Транспорт и логистика", "I": "Гостиницы и общепит",
    "J": "ИТ и медиа", "K": "Финансы", "L": "Недвижимость",
    "M": "Профессиональные услуги", "N": "Административные услуги",
    "O": "Госуправление", "P": "Образование", "Q": "Здравоохранение",
    "R": "Культура и спорт", "S": "Прочие услуги",
}

# ОКВЭД, чувствительные к сырьевым факторам — для признака exp_commodity
COMMODITY_OKVED2 = {"05", "06", "07", "08", "09", "19", "24", "46"}
COMMODITY_OKVED_PREFIX = ("46.71", "46.72", "46.21", "19.", "24.")

PRODUCT_COLS = [
    "CL_PRODUCT_RKO_MARK", "CL_PRODUCT_GAR_MARK", "CL_PRODUCT_LOA_MARK",
    "CL_PRODUCT_LEA_MARK", "CL_PRODUCT_DEP_MARK", "CL_PRODUCT_ZPP_MARK",
    "FACTORING_MARK",
]


def section_of(okved2: str) -> str:
    try:
        n = int(okved2)
    except (TypeError, ValueError):
        return "NA"
    for code, rng in SECTIONS.items():
        if n in rng:
            return code
    return "NA"


def log(msg: str) -> None:
    print(msg, flush=True)


# --------------------------------------------------------------------------
# 1. Справочник компаний
# --------------------------------------------------------------------------
def build_company_features(path: Path) -> pd.DataFrame:
    u = pd.read_csv(path, sep=";", low_memory=False)
    rows_raw = len(u)

    u = u[~u.SYNTHETIC_U.isin(JUNK_IDS)]
    dropped_junk = rows_raw - len(u)
    u = u.drop_duplicates("SYNTHETIC_U", keep="first").reset_index(drop=True)
    log(f"  компании: {rows_raw} строк -> {len(u)} уникальных "
        f"(мусорных {dropped_junk}, дублей {rows_raw - dropped_junk - len(u)})")

    u["okved2"] = u.MAINOKVED_CODE.astype(str).str.split(".").str[0].str.zfill(2)
    u["sector"] = u.okved2.map(section_of)
    u["sector_name"] = u.sector.map(SECTION_NAMES)

    u["revenue_rub"] = u.REVENUE_COMPANY.astype(float)
    u["revenue_bn_rub"] = (u.revenue_rub / 1e9).round(3)
    u["is_large_entity"] = (u.revenue_rub >= LARGE_REVENUE_RUB).astype(int)

    for col in PRODUCT_COLS + ["FTS_FLAG", "NEGATIVEMARK"]:
        u[col] = u[col].fillna(0).astype(int)

    # Экспозиции на макрофакторы — вход для score_relevance()
    u["exp_rate"] = ((u.CL_PRODUCT_LOA_MARK == 1) | (u.CL_PRODUCT_LEA_MARK == 1)).astype(int)
    u["exp_fx"] = (u.FTS_FLAG == 1).astype(int)
    u["exp_labour"] = (u.CL_PRODUCT_ZPP_MARK == 1).astype(int)
    u["exp_commodity"] = (
        u.okved2.isin(COMMODITY_OKVED2)
        & u.MAINOKVED_CODE.astype(str).str.startswith(COMMODITY_OKVED_PREFIX)
    ).astype(int)
    u["exp_consumer"] = u.okved2.isin({"46", "47", "55", "56"}).astype(int)

    countries = u.FTS_COUNTRY_NAME.fillna("")
    u["import_countries"] = countries.apply(
        lambda s: [c.strip() for c in s.split(",") if c.strip()] if s else []
    )
    u["imports_china"] = countries.str.contains("КИТАЙ", na=False).astype(int)
    u["n_import_countries"] = u.import_countries.str.len()

    # Признак ключевого собственника. ВАЖНО: не негатив, несмотря на имя поля.
    u = u.rename(columns={"NEGATIVEMARK": "key_owner_flag"})

    u["has_workers_spark"] = u.AMOUNT_WORKERS_SPARK_GRADATION.notna().astype(int)
    u["has_fts_country"] = u.FTS_COUNTRY_NAME.notna().astype(int)
    u["has_eco_mark"] = u.ECO_MARK_LABEL.notna().astype(int)
    u["features_missing"] = u.apply(
        lambda r: [
            name for name, present in (
                ("AMOUNT_WORKERS_SPARK_GRADATION", r.has_workers_spark),
                ("FTS_COUNTRY_NAME", r.has_fts_country),
                ("ECO_MARK_LABEL", r.has_eco_mark),
            ) if not present
        ],
        axis=1,
    )

    keep = [
        "SYNTHETIC_U", "GROUP_ID", "CL_TYPE", "OKFS_NAME",
        "COMPANY_AGE_YEARS_GRADATION", "ECO_MARK_LABEL",
        "MAINOKVED_CODE", "MAINOKVED_NAME", "okved2", "sector", "sector_name",
        "CITY", "REGION", "AMOUNT_WORKERS_FNS_GRADATION",
        "revenue_rub", "revenue_bn_rub", "is_large_entity",
        *PRODUCT_COLS, "FTS_FLAG", "key_owner_flag",
        "exp_rate", "exp_fx", "exp_labour", "exp_commodity", "exp_consumer",
        "import_countries", "imports_china", "n_import_countries",
        "features_missing",
    ]
    return u[keep].copy()


# --------------------------------------------------------------------------
# 2. Группы компаний
# --------------------------------------------------------------------------
def build_group_features(comp: pd.DataFrame) -> pd.DataFrame:
    g = comp.groupby("GROUP_ID").agg(
        n_entities=("SYNTHETIC_U", "size"),
        revenue_rub=("revenue_rub", "sum"),
        n_regions=("REGION", "nunique"),
        n_okved=("MAINOKVED_CODE", "nunique"),
        n_sectors=("sector", "nunique"),
        n_clients=("CL_TYPE", lambda s: int((s == "CLIENT").sum())),
        has_loan=("CL_PRODUCT_LOA_MARK", "max"),
        has_leasing=("CL_PRODUCT_LEA_MARK", "max"),
        has_guarantee=("CL_PRODUCT_GAR_MARK", "max"),
        has_deposit=("CL_PRODUCT_DEP_MARK", "max"),
        has_payroll=("CL_PRODUCT_ZPP_MARK", "max"),
        has_factoring=("FACTORING_MARK", "max"),
        n_importers=("FTS_FLAG", "sum"),
    ).reset_index()

    g["revenue_bn_rub"] = (g.revenue_rub / 1e9).round(3)
    g["is_large_group"] = (g.revenue_rub >= LARGE_REVENUE_RUB).astype(int)

    # Блок идентификаторов group_1340xx–group_1347xx устроен иначе остальных:
    # медиана 65 юрлиц против 1, медиана 10 отраслевых разделов против 1,
    # медиана 6 регионов против 1. Это не структура владения, а какая-то другая
    # разметка. Пока заказчик не подтвердит её смысл, такие группы помечаются
    # и не используются в выводах клиенту.
    g["group_num"] = g.GROUP_ID.str.extract(r"group_(\d+)_sb").astype(float)
    g["group_structure_suspect"] = g.group_num.between(134000, 135000).astype(int)
    g = g.drop(columns=["group_num"])
    g["exp_rate"] = ((g.has_loan == 1) | (g.has_leasing == 1)).astype(int)
    g["exp_fx"] = (g.n_importers > 0).astype(int)

    # Головная компания = максимальная выручка в группе
    head = comp.sort_values("revenue_rub", ascending=False).drop_duplicates("GROUP_ID")
    g = g.merge(
        head[["GROUP_ID", "SYNTHETIC_U", "MAINOKVED_NAME", "REGION"]].rename(
            columns={
                "SYNTHETIC_U": "head_entity",
                "MAINOKVED_NAME": "head_okved_name",
                "REGION": "head_region",
            }
        ),
        on="GROUP_ID", how="left",
    )
    clean = g[(g.is_large_group == 1) & (g.group_structure_suspect == 0)]
    log(f"  группы: {len(g)} | крупных по сумме выручки: {int(g.is_large_group.sum())}")
    log(f"    из них с подтверждённой структурой: {len(clean)} "
        f"(многоюрлицовых {int((clean.n_entities > 1).sum())}), "
        f"сомнительных: {int(((g.is_large_group == 1) & (g.group_structure_suspect == 1)).sum())}")
    return g


# --------------------------------------------------------------------------
# 3. Граф платежей
# --------------------------------------------------------------------------
def build_payment_edges(path: Path, comp: pd.DataFrame) -> pd.DataFrame:
    p = pd.read_csv(path, sep=";", low_memory=False)
    p = p.rename(columns={
        "PAYER": "payer", "BENEFICIARY": "beneficiary",
        "PAY_AMT": "amount_rub", "PAY_CNT": "payments_cnt",
    })
    p = p[~p.payer.isin(JUNK_IDS) & ~p.beneficiary.isin(JUNK_IDS)]

    group_of = comp.set_index("SYNTHETIC_U").GROUP_ID
    known = set(comp.SYNTHETIC_U)

    p["payer_group"] = p.payer.map(group_of)
    p["beneficiary_group"] = p.beneficiary.map(group_of)
    p["payer_known"] = p.payer.isin(known).astype(int)
    p["beneficiary_known"] = p.beneficiary.isin(known).astype(int)

    layer = np.where(
        p.payer == p.beneficiary, "self",
        np.where(
            p.payer_group.notna() & p.beneficiary_group.notna()
            & (p.payer_group == p.beneficiary_group),
            "intragroup", "external",
        ),
    )
    p["layer"] = layer

    total_amt = p.amount_rub.sum()
    for name, part in p.groupby("layer"):
        log(f"  слой {name:<10} рёбер {len(part):>9,} ({len(part)/len(p)*100:5.1f}%) "
            f"| объём {part.amount_rub.sum()/total_amt*100:5.1f}%")
    return p


# --------------------------------------------------------------------------
# 4. Контрагентские агрегаты (только внешний слой)
# --------------------------------------------------------------------------
def build_counterparty_stats(edges: pd.DataFrame, comp: pd.DataFrame) -> pd.DataFrame:
    ext = edges[edges.layer == "external"]

    inc = ext.groupby("beneficiary").agg(
        in_cnt=("payer", "nunique"),
        in_amount_rub=("amount_rub", "sum"),
        in_payments_cnt=("payments_cnt", "sum"),
        in_known_cnt=("payer_known", "sum"),
    )
    out = ext.groupby("payer").agg(
        out_cnt=("beneficiary", "nunique"),
        out_amount_rub=("amount_rub", "sum"),
        out_payments_cnt=("payments_cnt", "sum"),
        out_known_cnt=("beneficiary_known", "sum"),
    )

    top_in = (ext.sort_values("amount_rub", ascending=False)
              .drop_duplicates("beneficiary")[["beneficiary", "payer", "amount_rub"]]
              .rename(columns={"payer": "top_payer", "amount_rub": "top_payer_amount_rub"})
              .set_index("beneficiary"))
    top_out = (ext.sort_values("amount_rub", ascending=False)
               .drop_duplicates("payer")[["payer", "beneficiary", "amount_rub"]]
               .rename(columns={"beneficiary": "top_beneficiary",
                                "amount_rub": "top_beneficiary_amount_rub"})
               .set_index("payer"))

    s = inc.join(out, how="outer").join(top_in, how="left").join(top_out, how="left")
    s.index.name = "SYNTHETIC_U"
    s = s.reset_index()

    for col in ["in_cnt", "out_cnt", "in_amount_rub", "out_amount_rub",
                "in_payments_cnt", "out_payments_cnt", "in_known_cnt", "out_known_cnt"]:
        s[col] = s[col].fillna(0)

    # Доля в НАБЛЮДАЕМОМ потоке, не в выручке. Формулировка зафиксирована в промпте.
    s["top_payer_share"] = (s.top_payer_amount_rub / s.in_amount_rub).where(s.in_amount_rub > 0)
    s["top_beneficiary_share"] = (s.top_beneficiary_amount_rub / s.out_amount_rub).where(s.out_amount_rub > 0)
    s["unknown_in_share"] = (1 - s.in_known_cnt / s.in_cnt).where(s.in_cnt > 0)

    rev = comp.set_index("SYNTHETIC_U").revenue_rub
    s["revenue_rub"] = s.SYNTHETIC_U.map(rev)
    s["observed_flow_to_revenue"] = (s.in_amount_rub / s.revenue_rub).where(s.revenue_rub > 0)

    # Достоверность концентрации. Доля top-1 на тонком наблюдаемом потоке
    # формально верна, но вводит в заблуждение: у 35% компаний с высокой
    # долей поток составляет менее 5% выручки. Агенту нужен явный уровень
    # доверия, иначе он скажет «ключевой плательщик даёт 65% потока» там,
    # где банк видит одну сотую оборота.
    cov = s.observed_flow_to_revenue
    s["flow_coverage_tier"] = pd.cut(
        cov, bins=[-0.001, 0.05, 0.20, 0.50, np.inf],
        labels=["negligible", "low", "medium", "high"],
    ).astype(str)
    s.loc[cov.isna(), "flow_coverage_tier"] = "unknown"

    s["concentration_raw"] = ((s.in_cnt >= 3) & (s.top_payer_share > 0.5)).astype(int)
    s["concentration_flag"] = (
        (s.concentration_raw == 1) & (cov >= 0.20)
    ).astype(int)  # пригодно для вывода клиенту
    s["concentration_weak"] = (
        (s.concentration_raw == 1) & (s.concentration_flag == 0)
    ).astype(int)  # есть сигнал, но поток слишком тонкий — только как гипотеза

    s = s[s.SYNTHETIC_U.isin(set(comp.SYNTHETIC_U))].copy()
    log(f"  контрагентские агрегаты: {len(s)} компаний с профилем")
    log(f"    концентрация top-1 >50%: сырых {int(s.concentration_raw.sum()):,} | "
        f"достоверных {int(s.concentration_flag.sum()):,} | "
        f"слабых {int(s.concentration_weak.sum()):,}")
    log("    покрытие потоком: " + " | ".join(
        f"{k} {v:,}" for k, v in s.flow_coverage_tier.value_counts().items()))
    return s


# --------------------------------------------------------------------------
# 5. Связи через физлиц
# --------------------------------------------------------------------------
def build_affiliates(path: Path, comp: pd.DataFrame) -> pd.DataFrame:
    f = pd.read_csv(path, sep=";", low_memory=False)
    f = f.rename(columns={
        "SYNTHETIC_F": "person_id", "SYNTHETIC_U": "SYNTHETIC_U",
        "CITY_NAME": "person_city", "RC_NAME": "person_region",
    })
    f = f[~f.SYNTHETIC_U.isin(JUNK_IDS)]

    multi = f.groupby("person_id").SYNTHETIC_U.nunique()
    linking = multi[multi > 1].index
    pairs = []
    for pid, part in f[f.person_id.isin(linking)].groupby("person_id"):
        ids = sorted(part.SYNTHETIC_U.unique())
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                pairs.append((a, b, pid))

    out = pd.DataFrame(pairs, columns=["company_a", "company_b", "person_id"])
    group_of = comp.set_index("SYNTHETIC_U").GROUP_ID
    out["group_a"] = out.company_a.map(group_of)
    out["group_b"] = out.company_b.map(group_of)
    out["same_group"] = (out.group_a == out.group_b) & out.group_a.notna()
    out["both_profiled"] = out.company_a.isin(set(comp.SYNTHETIC_U)) & out.company_b.isin(set(comp.SYNTHETIC_U))
    log(f"  физлица: {f.person_id.nunique()} уникальных | связывающих 2+ компании: {len(linking)} "
        f"| пар компаний: {len(out)} | вне общей группы: {int((~out.same_group).sum())}")
    return out


# --------------------------------------------------------------------------
# 6. Карта заполненности
# --------------------------------------------------------------------------
def build_feature_availability(path: Path, comp: pd.DataFrame) -> pd.DataFrame:
    raw = pd.read_csv(path, sep=";", low_memory=False)
    raw = raw[~raw.SYNTHETIC_U.isin(JUNK_IDS)].drop_duplicates("SYNTHETIC_U", keep="first")
    large = raw[raw.REVENUE_COMPANY >= LARGE_REVENUE_RUB]

    rows = []
    for col in raw.columns:
        rows.append({
            "field": col,
            "filled_share_all": round(raw[col].notna().mean(), 4),
            "filled_share_large": round(large[col].notna().mean(), 4) if len(large) else None,
            "n_unique": int(raw[col].nunique(dropna=True)),
            "usable": raw[col].notna().mean() >= 0.5,
        })
    av = pd.DataFrame(rows).sort_values("filled_share_all")
    unusable = av[~av.usable].field.tolist()
    log(f"  карта заполненности: непригодных полей {len(unusable)} -> {unusable}")
    return av


# --------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, type=Path, help="каталог с исходными CSV")
    ap.add_argument("--out", required=True, type=Path, help="каталог для витрины")
    ap.add_argument("--companies", default="df_Uid_data_hack.csv")
    ap.add_argument("--payments", default="df_Uid_payment_hack.csv")
    ap.add_argument("--links", default="df_Fid_Uid_link_hack.csv")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    comp_path = args.data / args.companies
    pay_path = args.data / args.payments
    link_path = args.data / args.links
    for p in (comp_path, pay_path, link_path):
        if not p.exists():
            print(f"нет файла: {p}", file=sys.stderr)
            return 1

    log("1/6 company_features")
    comp = build_company_features(comp_path)
    log("2/6 group_features")
    grp = build_group_features(comp)
    log("3/6 payment_edges")
    edges = build_payment_edges(pay_path, comp)
    log("4/6 counterparty_stats")
    cps = build_counterparty_stats(edges, comp)
    log("5/6 affiliates")
    aff = build_affiliates(link_path, comp)
    log("6/6 feature_availability")
    av = build_feature_availability(comp_path, comp)

    # Денормализованный профиль: то, что get_company_profile() отдаёт одним запросом
    profile = (comp
               .merge(grp.add_prefix("grp_").rename(columns={"grp_GROUP_ID": "GROUP_ID"}),
                      on="GROUP_ID", how="left")
               .merge(cps.drop(columns=["revenue_rub"]), on="SYNTHETIC_U", how="left"))

    tables = {
        "company_features": comp,
        "group_features": grp,
        "payment_edges": edges,
        "counterparty_stats": cps,
        "affiliates": aff,
        "feature_availability": av,
        "company_profile": profile,
    }
    log("\nзапись:")
    manifest = {}
    for name, df in tables.items():
        # list-колонки parquet переварит, а CSV — нет: сериализуем в строку
        out_df = df.copy()
        for col in out_df.columns:
            if out_df[col].map(type).eq(list).any():
                out_df[col] = out_df[col].map(lambda v: "|".join(v) if isinstance(v, list) else v)
        fp = args.out / f"{name}.parquet"
        out_df.to_parquet(fp, index=False)
        if len(out_df) <= 200_000:
            out_df.to_csv(args.out / f"{name}.csv", sep=";", index=False)
        manifest[name] = {"rows": int(len(out_df)), "columns": list(out_df.columns),
                          "bytes_parquet": fp.stat().st_size}
        log(f"  {name:<22} {len(out_df):>9,} строк  {fp.stat().st_size/1e6:6.1f} МБ")

    (args.out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"\nготово: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
