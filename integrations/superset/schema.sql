-- V2 授权模型：原始事实、授权配置、受控出口分别归入三个 schema。
-- 本脚本只在独立数据库 hr_v2 执行，绝不使用课堂 hr_lab 中的表。
CREATE SCHEMA IF NOT EXISTS v2_data;
CREATE SCHEMA IF NOT EXISTS v2_auth;
CREATE SCHEMA IF NOT EXISTS v2_api;

-- 人员宽表由 setup.py 根据 fixtures.json 的 26 个字段创建，避免字段定义双写。
CREATE TABLE IF NOT EXISTS v2_auth.role_policy (
    role_key text PRIMARY KEY,
    reports boolean NOT NULL,
    hrbp boolean NOT NULL,
    inherit_hrbp boolean NOT NULL,
    field_groups jsonb NOT NULL,
    details boolean NOT NULL,
    export boolean NOT NULL,
    version integer NOT NULL
);
CREATE TABLE IF NOT EXISTS v2_auth.identity_map (
    superset_user_id integer PRIMARY KEY,
    username text UNIQUE NOT NULL,
    persona_id text UNIQUE NOT NULL,
    person_id text NOT NULL,
    role_key text NOT NULL
);
CREATE TABLE IF NOT EXISTS v2_auth.snapshot (
    singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
    as_of text NOT NULL,
    data_fingerprint text NOT NULL,
    data_version text NOT NULL,
    field_definitions jsonb NOT NULL
);

-- 自上而下生成管理链。path 记录完整途径，也防止环导致无限递归。
-- depth=0 是本人，1 是直属下属，2 及以上是间接下属。
CREATE OR REPLACE VIEW v2_auth.management_closure AS
WITH RECURSIVE chain(root_id,target_id,depth,path,is_cycle) AS (
    SELECT person_id,person_id,0,ARRAY[person_id],false FROM v2_data.people
    UNION ALL
    SELECT c.root_id,p.person_id,c.depth+1,c.path||p.person_id,p.person_id=ANY(c.path)
    FROM chain c JOIN v2_data.people p ON p.head_person_id=c.target_id
    WHERE NOT c.is_cycle
)
SELECT * FROM chain;

-- 与原 V2 保持一致：任何一处主管环、主管孤儿或 HRBP 孤儿使整张图拒绝授权。
-- HRBP 指向本人是有效的服务关系，不按管理环处理。
CREATE OR REPLACE VIEW v2_auth.graph_health AS
SELECT NOT (
    EXISTS(SELECT 1 FROM v2_auth.management_closure WHERE is_cycle)
    OR EXISTS(SELECT 1 FROM v2_data.people p LEFT JOIN v2_data.people m
              ON m.person_id=p.head_person_id WHERE p.head_person_id IS NOT NULL AND m.person_id IS NULL)
    OR EXISTS(SELECT 1 FROM v2_data.people p LEFT JOIN v2_data.people h
              ON h.person_id=p.dept_hrbp_id WHERE p.dept_hrbp_id IS NOT NULL AND h.person_id IS NULL)
) AS graph_valid;

-- 四种来源各自计算，再合并；不能把 HRBP 可见人群当成管理线继续递归。
CREATE OR REPLACE VIEW v2_auth.visible_people AS
WITH origins AS (
    SELECT i.superset_user_id,i.person_id AS target_id,'self'::text AS kind,
           ARRAY[i.person_id] AS path,'本人'::text AS reason,0 AS priority
    FROM v2_auth.identity_map i
    JOIN v2_data.people p ON p.person_id=i.person_id
    JOIN v2_auth.role_policy r USING(role_key)
    UNION ALL
    SELECT i.superset_user_id,c.target_id,'reports',c.path,'管理线下属',1
    FROM v2_auth.identity_map i JOIN v2_auth.role_policy r USING(role_key)
    JOIN v2_auth.management_closure c ON c.root_id=i.person_id
    WHERE r.reports AND c.depth>0 AND NOT c.is_cycle
    UNION ALL
    SELECT i.superset_user_id,p.person_id,'hrbp',ARRAY[i.person_id,p.person_id],'本人 HRBP 服务',2
    FROM v2_auth.identity_map i JOIN v2_auth.role_policy r USING(role_key)
    JOIN v2_data.people p ON p.dept_hrbp_id=i.person_id
    WHERE r.hrbp
    UNION ALL
    SELECT i.superset_user_id,p.person_id,'inherited_hrbp',c.path||p.person_id,'继承下属 HRBP 服务',3
    FROM v2_auth.identity_map i JOIN v2_auth.role_policy r USING(role_key)
    JOIN v2_auth.management_closure c ON c.root_id=i.person_id
    JOIN v2_data.people p ON p.dept_hrbp_id=c.target_id
    WHERE r.reports AND r.inherit_hrbp AND c.depth>0 AND NOT c.is_cycle
), merged AS (
    SELECT superset_user_id,target_id,
           bool_or(kind='reports') AS reports,
           bool_or(kind='hrbp') AS hrbp,
           bool_or(kind='inherited_hrbp') AS inherited,
           jsonb_agg(jsonb_build_object('kind',kind,'path',path,'text',reason) ORDER BY priority)::text AS origins
    FROM origins GROUP BY superset_user_id,target_id
)
SELECT m.*, c.depth
FROM merged m JOIN v2_auth.identity_map i USING(superset_user_id)
LEFT JOIN v2_auth.management_closure c ON c.root_id=i.person_id AND c.target_id=m.target_id AND NOT c.is_cycle
CROSS JOIN v2_auth.graph_health h
WHERE h.graph_valid;

-- 只给调用者自己的上下文；调用者选择由 Superset Base RLS 负责。
-- graph_valid 显式暴露图校验结果，Agent 必须在无效时报告错误，不能把拒绝误报成 0 人。
CREATE OR REPLACE VIEW v2_api.context WITH(security_barrier=true) AS
SELECT i.superset_user_id,i.persona_id,i.person_id,i.role_key,r.version AS policy_version,
       (to_jsonb(r)-'role_key'-'version')::text AS rules_json,
       s.as_of,s.data_fingerprint,h.graph_valid
FROM v2_auth.identity_map i JOIN v2_auth.role_policy r USING(role_key)
JOIN v2_data.people p ON p.person_id=i.person_id
CROSS JOIN v2_auth.snapshot s CROSS JOIN v2_auth.graph_health h;

-- 人员和事件视图由 setup.py 根据字段列表创建。注意：security_barrier 不是用户身份机制。
-- _viewer_id 仍需在 Superset 通过可信 current_user_id() 加上 Base RLS。
