#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 --username postgres --dbname postgres \
  -v meta_pass="$META_PASSWORD" -v public_pass="$PUBLIC_DB_PASSWORD" -v private_pass="$PRIVATE_DB_PASSWORD" <<'SQL'
CREATE ROLE superset_meta LOGIN PASSWORD :'meta_pass';
CREATE ROLE hr_public_reader LOGIN PASSWORD :'public_pass';
CREATE ROLE hr_private_reader LOGIN PASSWORD :'private_pass';
CREATE DATABASE superset_meta OWNER superset_meta;
CREATE DATABASE hr_lab OWNER postgres;
REVOKE CONNECT ON DATABASE hr_lab FROM PUBLIC;
GRANT CONNECT ON DATABASE hr_lab TO hr_public_reader, hr_private_reader;
SQL
