export type Cell = string | number | null;
export type Row = Record<string, Cell>;
export type Filter = {
  field: string;
  op: 'eq' | 'in' | 'contains' | 'gte' | 'lte' | 'not_null';
  values: string[];
};
export type Plan = {
  kind: 'aggregate' | 'people';
  scope: string;
  population: string;
  departments: string[];
  filters: Filter[];
  date_field: string | null;
  start_date: string | null;
  end_date: string | null;
  group_by: string[];
  metrics: string[];
  columns: string[];
  order_by: { field: string; direction: 'asc' | 'desc' }[];
  page: number;
  page_size: number;
  message?: string | null;
  inspect_ids?: string[];
};
export type Column = { key: string; label: string };
export type Trace = {
  name: string;
  input: unknown;
  output: unknown;
  duration_ms: number;
};
export type Result = {
  status: string;
  plan: Plan;
  rows: Row[];
  columns: Column[];
  total_rows: number;
  totals: Row;
  summary: string;
  message?: string;
  id?: string;
  parent_id?: string;
  question?: string;
  trace?: Trace[];
  page: number;
  page_size: number;
  sql: string;
  parameters: Record<string, Cell>;
  as_of: string;
  duration_ms: number;
  fingerprint: string;
  policy_version: number;
  notes: string[];
};
export type FieldDoc = {
  id: string;
  key: string;
  label: string;
  group: string;
  description: string;
  not_meaning: string;
  aliases: string[];
  type: string;
};
export type MetricDoc = {
  id: string;
  key: string;
  label: string;
  definition: string;
  unit: string;
  fields: string[];
  null_rule: string;
};
export type Rules = {
  reports: boolean;
  hrbp: boolean;
  inherit_hrbp: boolean;
  field_groups: string[];
  details: boolean;
  export: boolean;
};
export type Policy = {
  version: number;
  assumption: boolean;
  roles: Record<string, Rules>;
};
export type Principal = {
  id: string;
  label: string;
  name: string;
  role: string;
  count: number;
  candidate_count: number;
  csrf: string;
  policy_version: number;
  can_configure: boolean;
  rules: Rules;
};
export type Bootstrap = {
  query_backend?: 'sqlite' | 'superset';
  fingerprint: string;
  principal: Principal;
  personas: { id: string; label: string }[];
  model: { connected: boolean; display_name: string };
  catalog: {
    fields: FieldDoc[];
    metrics: MetricDoc[];
    dimensions: Record<string, string>;
    departments: string[];
    as_of: string;
    version: string;
    storage: string;
  };
};
export type Verification = {
  passed: boolean;
  compared_rows: number;
  difference_count: number;
  differences: unknown[];
  query_hash: string;
  reference_hash: string;
  method: string;
  limitation: string;
  fingerprint: string;
};
export type Case = {
  id: string;
  question: string;
  actor: string;
  required_source_fields: string[];
  acceptance_checks: string[];
  previous_case_id?: string;
};
export const defaultPlan: Plan = {
  kind: 'people',
  scope: 'all',
  population: 'active',
  departments: [],
  filters: [],
  date_field: null,
  start_date: null,
  end_date: null,
  group_by: [],
  metrics: ['count'],
  columns: ['employee_no', 'name', 'dept_cn_name'],
  order_by: [],
  page: 1,
  page_size: 50,
};
export async function request<T>(
  path: string,
  csrf: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch('/api/v2' + path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
  const data = (await response.json()) as T & { detail?: unknown };
  if (!response.ok)
    throw new Error(
      typeof data.detail === 'string'
        ? data.detail
        : '请求字段无效，请检查条件。',
    );
  return data;
}
