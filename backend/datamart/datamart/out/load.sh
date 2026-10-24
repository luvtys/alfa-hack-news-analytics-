#!/usr/bin/env bash
# Загрузка витрины в PostgreSQL.
# Использование: DB_URL=postgres://user:pass@host/db ./load.sh [каталог]
set -euo pipefail
DIR="${1:-.}"
psql "$DB_URL" -f "$DIR/schema.sql"

psql "$DB_URL" -c "\\copy company_features from '$DIR/company_features.csv' with (format csv, header true, delimiter ';')"
psql "$DB_URL" -c "\\copy group_features from '$DIR/group_features.csv' with (format csv, header true, delimiter ';')"
psql "$DB_URL" -c "\\copy payment_edges from '$DIR/payment_edges.csv' with (format csv, header true, delimiter ';')"
psql "$DB_URL" -c "\\copy counterparty_stats from '$DIR/counterparty_stats.csv' with (format csv, header true, delimiter ';')"
psql "$DB_URL" -c "\\copy affiliates from '$DIR/affiliates.csv' with (format csv, header true, delimiter ';')"
psql "$DB_URL" -c "\\copy feature_availability from '$DIR/feature_availability.csv' with (format csv, header true, delimiter ';')"

psql "$DB_URL" -c "analyze;"