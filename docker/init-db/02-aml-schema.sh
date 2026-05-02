#!/usr/bin/env bash
# Apply the AML investigation schema (the `aml.*` tables) on top of the
# RAG schema.  Runs after 01-rag-schema.sh, in the same database.
set -euo pipefail

echo "[init] applying AML schema"

psql --username "${POSTGRES_USER}" --dbname "${POSTGRES_DB}" \
     --no-psqlrc --set ON_ERROR_STOP=on \
     --file /sql/aml-schema.sql

echo "[init] applying AML case scenarios + transactions schema"
psql --username "${POSTGRES_USER}" --dbname "${POSTGRES_DB}" \
     --no-psqlrc --set ON_ERROR_STOP=on \
     --file /sql/aml-case-scenarios-txns.sql
