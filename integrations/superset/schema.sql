CREATE SCHEMA IF NOT EXISTS hr;
CREATE SCHEMA IF NOT EXISTS authz;
CREATE SCHEMA IF NOT EXISTS analytics;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE TABLE IF NOT EXISTS hr.people (
  person_id text PRIMARY KEY, employee_no text NOT NULL UNIQUE,
  name text NOT NULL, department text NOT NULL,
  head_person_id text REFERENCES hr.people(person_id) DEFERRABLE INITIALLY DEFERRED,
  dept_hrbp_id text REFERENCES hr.people(person_id) DEFERRABLE INITIALLY DEFERRED,
  education text NOT NULL, school text NOT NULL, salary numeric(12,2) NOT NULL
);
CREATE TABLE IF NOT EXISTS authz.role_policy (
  role_key text PRIMARY KEY, reports boolean NOT NULL, hrbp boolean NOT NULL,
  inherit_hrbp boolean NOT NULL, private_fields boolean NOT NULL
);
CREATE TABLE IF NOT EXISTS authz.identity_map (
  superset_user_id integer PRIMARY KEY, username text NOT NULL UNIQUE,
  person_id text NOT NULL REFERENCES hr.people(person_id),
  role_key text NOT NULL REFERENCES authz.role_policy(role_key)
);
CREATE INDEX IF NOT EXISTS people_head_idx ON hr.people(head_person_id);
CREATE INDEX IF NOT EXISTS people_hrbp_idx ON hr.people(dept_hrbp_id);

CREATE OR REPLACE VIEW authz.management_closure AS
WITH RECURSIVE tree(root_id,target_id,depth,path,is_cycle) AS (
  SELECT person_id, person_id, 0, ARRAY[person_id], false FROM hr.people
  UNION ALL
  SELECT t.root_id, p.person_id, t.depth+1, t.path || p.person_id, p.person_id=ANY(t.path)
  FROM tree t JOIN hr.people p ON p.head_person_id=t.target_id WHERE NOT t.is_cycle
)
SELECT * FROM tree;

CREATE OR REPLACE VIEW authz.person_access AS
WITH grants AS (
  SELECT i.superset_user_id, i.person_id AS target_id, 'self'::text AS origin
  FROM authz.identity_map i
  UNION ALL
  SELECT i.superset_user_id, m.target_id, 'reports'
  FROM authz.identity_map i JOIN authz.role_policy r USING(role_key)
  JOIN authz.management_closure m ON m.root_id=i.person_id
  WHERE r.reports AND m.depth>0 AND NOT m.is_cycle
  UNION ALL
  SELECT i.superset_user_id, p.person_id, 'hrbp'
  FROM authz.identity_map i JOIN authz.role_policy r USING(role_key)
  JOIN hr.people p ON p.dept_hrbp_id=i.person_id WHERE r.hrbp
  UNION ALL
  SELECT i.superset_user_id, p.person_id, 'inherited_hrbp'
  FROM authz.identity_map i JOIN authz.role_policy r USING(role_key)
  JOIN authz.management_closure m ON m.root_id=i.person_id AND m.depth>0 AND NOT m.is_cycle
  JOIN hr.people p ON p.dept_hrbp_id=m.target_id WHERE r.reports AND r.inherit_hrbp
)
SELECT DISTINCT * FROM grants
WHERE NOT EXISTS (SELECT 1 FROM authz.management_closure WHERE is_cycle);

CREATE OR REPLACE VIEW authz.visible_people AS
SELECT DISTINCT superset_user_id, target_id FROM authz.person_access;
CREATE OR REPLACE VIEW analytics.people_public WITH (security_barrier=true) AS
SELECT person_id,employee_no,name,department,education,school FROM hr.people;
CREATE OR REPLACE VIEW analytics.people_private WITH (security_barrier=true) AS
SELECT person_id,employee_no,name,department,education,school,salary FROM hr.people;
-- Intentionally unregistered Superset dataset: used only to prove the SQL Lab boundary.
CREATE OR REPLACE VIEW analytics.unregistered_probe AS
SELECT person_id,employee_no,name,department,education,school FROM hr.people;
GRANT USAGE ON SCHEMA analytics,authz TO hr_public_reader,hr_private_reader;
GRANT SELECT ON analytics.people_public,analytics.unregistered_probe,authz.visible_people TO hr_public_reader;
GRANT SELECT ON analytics.people_private,authz.visible_people TO hr_private_reader;
ALTER ROLE hr_public_reader SET default_transaction_read_only=on;
ALTER ROLE hr_private_reader SET default_transaction_read_only=on;
ALTER ROLE hr_public_reader SET statement_timeout='15s';
ALTER ROLE hr_private_reader SET statement_timeout='15s';
