-- Витрина данных для агента новостной аналитики
-- Генерируется build_datamart.py; загрузка — load.sh

drop table if exists company_features cascade;
create table company_features (
    "SYNTHETIC_U" text not null,
    "GROUP_ID" text,
    "CL_TYPE" text,
    "OKFS_NAME" text,
    "COMPANY_AGE_YEARS_GRADATION" text,
    "ECO_MARK_LABEL" text,
    "MAINOKVED_CODE" text,
    "MAINOKVED_NAME" text,
    "okved2" text,
    "sector" text,
    "sector_name" text,
    "CITY" text,
    "REGION" text,
    "AMOUNT_WORKERS_FNS_GRADATION" text,
    "revenue_rub" double precision,
    "revenue_bn_rub" double precision,
    "is_large_entity" bigint,
    "CL_PRODUCT_RKO_MARK" bigint,
    "CL_PRODUCT_GAR_MARK" bigint,
    "CL_PRODUCT_LOA_MARK" bigint,
    "CL_PRODUCT_LEA_MARK" bigint,
    "CL_PRODUCT_DEP_MARK" bigint,
    "CL_PRODUCT_ZPP_MARK" bigint,
    "FACTORING_MARK" bigint,
    "FTS_FLAG" bigint,
    "key_owner_flag" bigint,
    "exp_rate" bigint,
    "exp_fx" bigint,
    "exp_labour" bigint,
    "exp_commodity" bigint,
    "exp_consumer" bigint,
    "import_countries" text,
    "imports_china" bigint,
    "n_import_countries" bigint,
    "features_missing" text
);
alter table company_features add primary key ("SYNTHETIC_U");
create index on company_features ("GROUP_ID");
create index on company_features ("okved2");
create index on company_features ("REGION");
create index on company_features ("is_large_entity");
create index on company_features ("exp_rate");
create index on company_features ("exp_fx");

drop table if exists group_features cascade;
create table group_features (
    "GROUP_ID" text not null,
    "n_entities" bigint,
    "revenue_rub" double precision,
    "n_regions" bigint,
    "n_okved" bigint,
    "n_sectors" bigint,
    "n_clients" bigint,
    "has_loan" bigint,
    "has_leasing" bigint,
    "has_guarantee" bigint,
    "has_deposit" bigint,
    "has_payroll" bigint,
    "has_factoring" bigint,
    "n_importers" bigint,
    "revenue_bn_rub" double precision,
    "is_large_group" bigint,
    "group_structure_suspect" bigint,
    "exp_rate" bigint,
    "exp_fx" bigint,
    "head_entity" text,
    "head_okved_name" text,
    "head_region" text
);
alter table group_features add primary key ("GROUP_ID");
create index on group_features ("is_large_group");

drop table if exists payment_edges cascade;
create table payment_edges (
    "beneficiary" text,
    "payer" text,
    "amount_rub" double precision,
    "payments_cnt" bigint,
    "payer_group" text,
    "beneficiary_group" text,
    "payer_known" bigint,
    "beneficiary_known" bigint,
    "layer" text
);
create index on payment_edges ("payer");
create index on payment_edges ("beneficiary");
create index on payment_edges ("layer");

drop table if exists counterparty_stats cascade;
create table counterparty_stats (
    "SYNTHETIC_U" text not null,
    "in_cnt" double precision,
    "in_amount_rub" double precision,
    "in_payments_cnt" double precision,
    "in_known_cnt" double precision,
    "out_cnt" double precision,
    "out_amount_rub" double precision,
    "out_payments_cnt" double precision,
    "out_known_cnt" double precision,
    "top_payer" text,
    "top_payer_amount_rub" double precision,
    "top_beneficiary" text,
    "top_beneficiary_amount_rub" double precision,
    "top_payer_share" double precision,
    "top_beneficiary_share" double precision,
    "unknown_in_share" double precision,
    "revenue_rub" double precision,
    "observed_flow_to_revenue" double precision,
    "flow_coverage_tier" text,
    "concentration_raw" bigint,
    "concentration_flag" bigint,
    "concentration_weak" bigint
);
alter table counterparty_stats add primary key ("SYNTHETIC_U");
create index on counterparty_stats ("concentration_flag");

drop table if exists affiliates cascade;
create table affiliates (
    "company_a" text,
    "company_b" text,
    "person_id" text,
    "group_a" text,
    "group_b" text,
    "same_group" boolean,
    "both_profiled" boolean
);
create index on affiliates ("company_a");
create index on affiliates ("company_b");

drop table if exists feature_availability cascade;
create table feature_availability (
    "field" text,
    "filled_share_all" double precision,
    "filled_share_large" double precision,
    "n_unique" bigint,
    "usable" boolean
);
