#!/bin/sh
set -eu
# 首次创建 Superset 元数据库；业务数据库和最小权限账号由 setup.py 管理。
psql -v ON_ERROR_STOP=1 --username postgres --dbname postgres -v meta_pass="$META_PASSWORD" <<'SQL'
CREATE ROLE superset_meta LOGIN PASSWORD :'meta_pass';
CREATE DATABASE superset_meta OWNER superset_meta;
SQL
