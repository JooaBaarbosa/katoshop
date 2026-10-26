#!/bin/sh
# Cria um banco e um usuário por serviço. Roda só na primeira inicialização do volume.
set -eu

psql -v ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v identity_pw="$IDENTITY_DB_PASSWORD" \
  -v catalog_pw="$CATALOG_DB_PASSWORD" <<'SQL'
CREATE ROLE identity_svc LOGIN PASSWORD :'identity_pw';
CREATE ROLE catalog_svc LOGIN PASSWORD :'catalog_pw';

CREATE DATABASE identity OWNER identity_svc;
CREATE DATABASE catalog OWNER catalog_svc;

REVOKE CONNECT ON DATABASE identity FROM PUBLIC;
REVOKE CONNECT ON DATABASE catalog FROM PUBLIC;
GRANT CONNECT ON DATABASE identity TO identity_svc;
GRANT CONNECT ON DATABASE catalog TO catalog_svc;

\connect catalog
CREATE EXTENSION IF NOT EXISTS unaccent;
SQL
