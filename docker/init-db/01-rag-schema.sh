#!/usr/bin/env bash
# Apply the pgvector RAG schema (the `documents` table).
#
# Postgres' standard entrypoint runs every executable file in
# /docker-entrypoint-initdb.d on first boot, in alphabetical order, against
# the database named by POSTGRES_DB.  This script is wired in as a bind-mount
# from docker-compose.yml.
#
# The repo's `agents/rag_agent/db/schema.sql` uses Python `.format()` style
# placeholders (`{embedding_dim}`, `{ivfflat_lists}`).  We substitute them
# here with `sed` so the schema is portable across drivers.
set -euo pipefail

EMBEDDING_DIM="${EMBEDDING_DIM:-768}"
IVFFLAT_LISTS="${IVFFLAT_LISTS:-100}"

echo "[init] applying RAG schema (embedding_dim=${EMBEDDING_DIM}, ivfflat_lists=${IVFFLAT_LISTS})"

# Substitute the Python format placeholders, then unescape `{{...}}` → `{...}`.
sed \
  -e "s/{embedding_dim}/${EMBEDDING_DIM}/g" \
  -e "s/{ivfflat_lists}/${IVFFLAT_LISTS}/g" \
  -e "s/{{/{/g" \
  -e "s/}}/}/g" \
  /sql/rag-schema.sql \
  | psql --username "${POSTGRES_USER}" --dbname "${POSTGRES_DB}" --no-psqlrc --set ON_ERROR_STOP=on
