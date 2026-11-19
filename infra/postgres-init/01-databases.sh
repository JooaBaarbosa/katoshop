#!/bin/sh
# Cria um banco e um usuário por serviço. O Postgres roda este script sozinho só na primeira
# inicialização do volume; ele é idempotente, então num volume que já existe (um serviço novo
# entrou depois) dá para rodar de novo sem apagar nada:
#   docker compose exec postgres sh /docker-entrypoint-initdb.d/01-databases.sh
set -eu

psql -v ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" --dbname "${POSTGRES_DB:-$POSTGRES_USER}" \
  -v identity_pw="$IDENTITY_DB_PASSWORD" \
  -v catalog_pw="$CATALOG_DB_PASSWORD" \
  -v promotions_pw="$PROMOTIONS_DB_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', r.name, r.pw)
FROM (VALUES ('identity_svc', :'identity_pw'), ('catalog_svc', :'catalog_pw'),
             ('promotions_svc', :'promotions_pw')) AS r(name, pw)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r.name)
\gexec

SELECT format('CREATE DATABASE %I OWNER %I', d.name, d.owner)
FROM (VALUES ('identity', 'identity_svc'), ('catalog', 'catalog_svc'),
             ('promotions', 'promotions_svc')) AS d(name, owner)
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = d.name)
\gexec

REVOKE CONNECT ON DATABASE identity FROM PUBLIC;
REVOKE CONNECT ON DATABASE catalog FROM PUBLIC;
REVOKE CONNECT ON DATABASE promotions FROM PUBLIC;
GRANT CONNECT ON DATABASE identity TO identity_svc;
GRANT CONNECT ON DATABASE catalog TO catalog_svc;
GRANT CONNECT ON DATABASE promotions TO promotions_svc;

\connect catalog
CREATE EXTENSION IF NOT EXISTS unaccent;
SQL
