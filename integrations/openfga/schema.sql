-- 本库只用于 OpenFGA 课堂；与 hr_v2、Superset 元数据库隔离。
CREATE SCHEMA hr_source;
CREATE SCHEMA hr_control;
CREATE SCHEMA hr_data;
CREATE SCHEMA hr_api;

-- 源表相当于现有业务库的只读接入副本，主键不随岗位变化。
CREATE TABLE hr_source.people (person_id text PRIMARY KEY, record jsonb NOT NULL);
CREATE TABLE hr_source.identities (persona text PRIMARY KEY, person_id text NOT NULL, role_key text NOT NULL);
CREATE TABLE hr_source.policy (singleton boolean PRIMARY KEY CHECK(singleton), config jsonb NOT NULL);
CREATE TABLE hr_control.revision (singleton boolean PRIMARY KEY CHECK(singleton), version bigint NOT NULL);
INSERT INTO hr_control.revision VALUES(true, 0);

-- 演示用数据库触发器：任何源表写入都会改变版本。运行时发现待同步就拒绝查询。
-- 接入不能装触发器的外部数据库时，要改为 CDC/轮询及明确的新鲜度协议。
CREATE FUNCTION hr_control.changed() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    UPDATE hr_control.revision SET version=version+1;
    RETURN NULL;
END $$;
CREATE TRIGGER people_changed AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE ON hr_source.people
    FOR EACH STATEMENT EXECUTE FUNCTION hr_control.changed();
CREATE TRIGGER identities_changed AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE ON hr_source.identities
    FOR EACH STATEMENT EXECUTE FUNCTION hr_control.changed();
CREATE TRIGGER policy_changed AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE ON hr_source.policy
    FOR EACH STATEMENT EXECUTE FUNCTION hr_control.changed();

-- 一份发布绑定业务快照、身份映射、OpenFGA store 与不可变 model ID。
CREATE TABLE hr_control.publications (
    id text PRIMARY KEY, source_revision bigint NOT NULL, store_id text NOT NULL,
    model_id text NOT NULL, metadata jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE hr_control.active (singleton boolean PRIMARY KEY CHECK(singleton),
    publication text NOT NULL REFERENCES hr_control.publications(id));
CREATE TABLE hr_data.people (
    generation text NOT NULL REFERENCES hr_control.publications(id),
    person_id text NOT NULL, record jsonb NOT NULL, PRIMARY KEY(generation, person_id)
);
CREATE ROLE hr_fga_view_owner NOLOGIN;
CREATE ROLE hr_fga_reader NOLOGIN;
REVOKE ALL ON DATABASE hr_openfga FROM PUBLIC;
GRANT CONNECT ON DATABASE hr_openfga TO hr_fga_reader;
GRANT USAGE ON SCHEMA hr_api,hr_control TO hr_fga_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA hr_control TO hr_fga_reader;
GRANT USAGE ON SCHEMA hr_data,hr_api TO hr_fga_view_owner;
GRANT SELECT ON hr_data.people TO hr_fga_view_owner;
ALTER TABLE hr_data.people ENABLE ROW LEVEL SECURITY;
ALTER TABLE hr_data.people FORCE ROW LEVEL SECURITY;
-- USING 的表达式对每一行检查：版本必须匹配，且人员 ID 在 OpenFGA 授权集合中。
CREATE POLICY fga_selection ON hr_data.people FOR SELECT TO hr_fga_view_owner
USING (generation = current_setting('hr.generation', true)
    AND COALESCE(NULLIF(current_setting('hr.allowed_ids',true),''),'[]')::jsonb ? person_id);
ALTER ROLE hr_fga_reader SET default_transaction_read_only=on;
ALTER ROLE hr_fga_reader SET statement_timeout='10s';
