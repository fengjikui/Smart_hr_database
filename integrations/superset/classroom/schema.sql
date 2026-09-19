-- 课堂专用对象，使用 learn_ 前缀；不修改既有 hr / authz / analytics 实验。
-- 三层分开：原始事实 learn_data；授权关系 learn_auth；只读出口 learn_api。
CREATE SCHEMA IF NOT EXISTS learn_data;
CREATE SCHEMA IF NOT EXISTS learn_auth;
CREATE SCHEMA IF NOT EXISTS learn_api;

CREATE TABLE IF NOT EXISTS learn_data.people (
    person_id text PRIMARY KEY,
    employee_no text UNIQUE NOT NULL,
    name text NOT NULL,
    department text NOT NULL,
    manager_id text REFERENCES learn_data.people(person_id) DEFERRABLE INITIALLY DEFERRED,
    hrbp_id text REFERENCES learn_data.people(person_id) DEFERRABLE INITIALLY DEFERRED,
    education text NOT NULL
);
CREATE TABLE IF NOT EXISTS learn_data.payroll (
    person_id text PRIMARY KEY REFERENCES learn_data.people(person_id),
    salary integer NOT NULL CHECK (salary >= 0)
);
CREATE TABLE IF NOT EXISTS learn_data.orders (
    order_id text PRIMARY KEY,
    owner_id text NOT NULL REFERENCES learn_data.people(person_id),
    region text NOT NULL CHECK (region IN ('EAST', 'WEST', 'NORTH')),
    order_date date NOT NULL,
    amount integer NOT NULL CHECK (amount > 0),
    classification text NOT NULL CHECK (classification IN ('PUBLIC', 'RESTRICTED')),
    customer_name text NOT NULL,
    customer_phone text NOT NULL
);

-- 数据库中的角色策略是我们定义的业务规则，不是 Superset 内置角色。
CREATE TABLE IF NOT EXISTS learn_auth.role_policy (
    role_key text PRIMARY KEY,
    reports boolean NOT NULL,
    hrbp boolean NOT NULL,
    inherit_hrbp boolean NOT NULL
);
CREATE TABLE IF NOT EXISTS learn_auth.identity_map (
    superset_user_id integer PRIMARY KEY,
    username text UNIQUE NOT NULL,
    person_id text NOT NULL REFERENCES learn_data.people(person_id),
    role_key text NOT NULL REFERENCES learn_auth.role_policy(role_key)
);
CREATE TABLE IF NOT EXISTS learn_auth.user_regions (
    superset_user_id integer NOT NULL REFERENCES learn_auth.identity_map(superset_user_id),
    region text NOT NULL,
    PRIMARY KEY(superset_user_id, region)
);
CREATE INDEX IF NOT EXISTS learn_people_manager_idx ON learn_data.people(manager_id);

-- 教学用递归：root_id 是查看人对应的员工；target_id 是逐层找到的下属。
-- path 防止管理环无限展开；正式组织数据也必须先校验无环。
CREATE OR REPLACE VIEW learn_auth.management_closure AS
WITH RECURSIVE chain(root_id, target_id, depth, path, is_cycle) AS (
    SELECT person_id, person_id, 0, ARRAY[person_id], false FROM learn_data.people
    UNION ALL
    SELECT c.root_id, p.person_id, c.depth + 1, c.path || p.person_id,
           p.person_id = ANY(c.path)
    FROM chain c JOIN learn_data.people p ON p.manager_id = c.target_id
    WHERE NOT c.is_cycle
)
SELECT * FROM chain;

-- 授权来源分开写，便于理解：不是把所有关系放进同一递归里。
CREATE OR REPLACE VIEW learn_auth.visible_people AS
WITH grants AS (
    SELECT i.superset_user_id, i.person_id AS target_id
    FROM learn_auth.identity_map i
    UNION
    SELECT i.superset_user_id, c.target_id
    FROM learn_auth.identity_map i
    JOIN learn_auth.role_policy r USING(role_key)
    JOIN learn_auth.management_closure c ON c.root_id = i.person_id
    WHERE r.reports AND c.depth > 0 AND NOT c.is_cycle
    UNION
    SELECT i.superset_user_id, p.person_id
    FROM learn_auth.identity_map i
    JOIN learn_auth.role_policy r USING(role_key)
    JOIN learn_data.people p ON p.hrbp_id = i.person_id
    WHERE r.hrbp
    UNION
    SELECT i.superset_user_id, p.person_id
    FROM learn_auth.identity_map i
    JOIN learn_auth.role_policy r USING(role_key)
    JOIN learn_auth.management_closure c ON c.root_id = i.person_id
    JOIN learn_data.people p ON p.hrbp_id = c.target_id
    WHERE r.reports AND r.inherit_hrbp AND c.depth > 0 AND NOT c.is_cycle
)
SELECT DISTINCT superset_user_id, target_id FROM grants
WHERE NOT EXISTS (SELECT 1 FROM learn_auth.management_closure WHERE is_cycle);

-- 公开出口从物理结构上不包含完整电话与薪资。
-- 注意：security_barrier 不会自动添加任何行权限；RLS 仍需在课堂手填。
CREATE OR REPLACE VIEW learn_api.orders WITH (security_barrier=true) AS
SELECT order_id, owner_id, region, order_date, amount, classification, customer_name,
       left(customer_phone, 3) || '****' || right(customer_phone, 4) AS phone_masked
FROM learn_data.orders;
CREATE OR REPLACE VIEW learn_api.people WITH (security_barrier=true) AS
SELECT person_id, employee_no, name, department, manager_id, hrbp_id, education
FROM learn_data.people;
CREATE OR REPLACE VIEW learn_api.payroll WITH (security_barrier=true) AS
SELECT p.person_id, p.name, p.department, s.salary
FROM learn_data.people p JOIN learn_data.payroll s USING(person_id);
CREATE OR REPLACE VIEW learn_api.orders_private WITH (security_barrier=true) AS
SELECT * FROM learn_data.orders;

COMMENT ON VIEW learn_api.orders IS '课堂订单：12笔，总金额78000；手机号已在数据库视图脱敏。尚未配置行过滤。';
COMMENT ON COLUMN learn_api.orders.owner_id IS '订单负责人person_id；不是登录账号ID。';
COMMENT ON COLUMN learn_api.orders.region IS '业务区域：EAST华东、WEST华西、NORTH华北。';
COMMENT ON COLUMN learn_api.orders.amount IS '模拟订单金额，整数元；12笔总额78000。';
COMMENT ON COLUMN learn_api.orders.classification IS 'PUBLIC普通订单；RESTRICTED受限订单，用于条件交并集练习。';
COMMENT ON COLUMN learn_api.orders.phone_masked IS '数据库视图生成的脱敏电话；完整值未进入这个数据集。';

-- 角色先由 setup.py 创建；这里只授予必要出口，不授予原始表访问权。
GRANT USAGE ON SCHEMA learn_api, learn_auth TO learn_public_reader, learn_private_reader;
GRANT SELECT ON learn_api.orders, learn_api.people TO learn_public_reader;
GRANT SELECT ON learn_api.payroll, learn_api.orders_private TO learn_private_reader;
GRANT SELECT ON learn_auth.identity_map, learn_auth.user_regions, learn_auth.visible_people
    TO learn_public_reader, learn_private_reader;
ALTER ROLE learn_public_reader SET default_transaction_read_only=on;
ALTER ROLE learn_private_reader SET default_transaction_read_only=on;
ALTER ROLE learn_public_reader SET statement_timeout='10s';
ALTER ROLE learn_private_reader SET statement_timeout='10s';
