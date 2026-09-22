#!/bin/sh
set -eu
# 首次创建 Superset 元数据库；业务数据库和最小权限账号由 setup.py 管理。
# PostgreSQL 官方镜像只在空数据卷首次初始化时运行此脚本，普通重启不会重复执行。
# :'meta_pass' 是 psql 的 SQL 字面量引用，密码来自环境变量，不在源码中写死。
psql -v ON_ERROR_STOP=1 --username postgres --dbname postgres -v meta_pass="$META_PASSWORD" <<'SQL'
CREATE ROLE superset_meta LOGIN PASSWORD :'meta_pass';
CREATE DATABASE superset_meta OWNER superset_meta;
SQL
