export type Metric = {
  id: string;
  name: string;
  domain: string;
  unit: string;
  description: string;
  dimensions: string[];
  aliases: string[];
  source: string[];
  owner: string;
  version: string;
  sensitivity: string;
  minimum_group_size: number;
  example: string;
};
export type Plan = {
  kind: 'metric' | 'people' | 'attendance' | 'clarify' | 'refuse';
  metric: string;
  dimension: string;
  period: string;
  relation: string;
  department?: string | null;
  employee_name?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  limit?: number;
  message?: string | null;
};
export type DataRow = Record<string, string | number | boolean | null>;
export type Answer = {
  status: 'success' | 'clarify' | 'refuse';
  summary: string;
  rows: DataRow[];
  columns: { key: string; label: string }[];
  plan: Plan;
  metric: Metric;
  period: { start: string; end: string };
  scope: { count: number; label: string; policy_version: string };
  as_of: string;
  catalog_version: string;
  sql: string;
  sql_parameter_count: number;
  duration_ms: number;
  warnings: string[];
  suppressed_groups: number;
  chart_type: string;
  trace?: { name: string; detail: string; duration_ms: number }[];
  conversation_id?: string;
  model?: string;
  model_ms?: number;
  debug_run_id?: string;
};
export type Principal = {
  id: string;
  employee_id: number;
  role: string;
  label: string;
  title: string;
  scope_mode: string;
  scope_root: number;
  policy_version: number;
  salary_aggregate: boolean;
  can_export: boolean;
  scope_count: number;
  direct_count: number;
  indirect_count: number;
  scope_label: string;
  csrf: string;
};
export type ModelStatus = {
  connected: boolean;
  model: string;
  display_name: string;
  provider: string;
  local: boolean;
  message: string;
};
export type Bootstrap = {
  principal: Principal;
  model: ModelStatus;
  dataset: { as_of: string; calendar_start: string; synthetic: boolean };
  catalog_version: string;
  personas: { id: string; label: string; title: string; role: string }[];
};
export type OverviewData = {
  kpis: Answer[];
  distribution: Answer;
  trend: Answer;
  attendance_trend: Answer;
};
export type Dashboard = {
  id: string;
  title: string;
  plan: Plan | null;
  created_at: string;
  result: Answer | null;
  error?: string;
};
export type Department = {
  id: number;
  name: string;
  parent_id: number | null;
  level: number;
  division_id: number | null;
  direct_employees: number;
  count: number;
};
export type OrganizationData = {
  departments: Department[];
  people: Answer;
  principal: Principal;
};
export type GovernanceData = {
  validation: {
    passed: boolean;
    checks: { name: string; passed: boolean; violations: number }[];
    counts: Record<string, number>;
    active_employees: number;
    total_employees: number;
    as_of: string;
    seed: number;
  };
  audit: {
    action: string;
    outcome: string;
    metric_id: string | null;
    scope_count: number | null;
    duration_ms: number;
    created_at: string;
  }[];
  storage: Record<string, string>;
  boundaries: string[];
};
export type View =
  | 'overview'
  | 'chat'
  | 'boards'
  | 'organization'
  | 'catalog'
  | 'governance'
  | 'dictionary'
  | 'debug';

export type DebugRunSummary = {
  id: string;
  question: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  duration_ms: number;
};
export type DebugNode = {
  id: string;
  key: string;
  name: string;
  status: string;
  started_at: string;
  duration_ms: number;
  input: unknown;
  output: unknown;
  error: unknown;
};
export type DebugRun = DebugRunSummary & {
  owner_id: string;
  model: string;
  catalog_version: string;
  nodes: DebugNode[];
  result: Answer | null;
  error: { message?: string } | null;
  capture_policy: string;
};
export type SchemaTable = {
  name: string;
  database: string;
  description: string;
  row_count: number | null;
  create_sql: string;
  fields: {
    name: string;
    type: string;
    not_null: boolean;
    default: string | null;
    primary_key_position: number;
    description: string;
  }[];
  foreign_keys: {
    from: string;
    table: string;
    to: string;
    on_delete: string;
    on_update: string;
  }[];
  indexes: {
    name: string;
    unique: number;
    partial: number;
    columns: string[];
    sql: string | null;
  }[];
};
export type DataDictionary = {
  tables: SchemaTable[];
  metrics: (Metric & {
    sql_expression: string | null;
    example_sql: string | null;
    example_plan: Plan;
    dimension_labels: Record<string, string>;
    example_error?: string;
  })[];
  storage: { name: string; location: string; purpose: string }[];
  conventions: { name: string; value: string }[];
  dataset: Record<string, string>;
  catalog_version: string;
  note: string;
  summary: {
    business_tables: number;
    application_tables: number;
    fields: number;
    metrics: number;
  };
};
