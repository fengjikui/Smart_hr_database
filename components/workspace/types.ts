/**
 * 前后端协议和轻量请求入口；对应 backend/hr/schema.py 与各 API 返回值。
 * TypeScript 类型只辅助开发，真正的字段白名单、身份和权限仍由后端校验。
 * 字段、计划和结果协议由后端 schema.py 与路由共同约束。
 */
export type Cell = string | number | null;
export type Row = Record<string, Cell>;
export type Filter = {
  field: string;
  op: 'eq' | 'in' | 'contains' | 'gte' | 'lte' | 'not_null';
  values: string[];
};
export type Plan = {
  // 浏览器只提交结构化业务条件；不能在这里指定数据库连接、SQL 或授权人员全集。
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
  // rows 是当前页；total_rows 和 totals 是服务端对全部匹配记录的结果，不能混算。
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
  // 用于展示能力和启用控件，不是浏览器可自行授予的权限凭证。
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
  // 初始化响应同时带回当前身份、权限裁剪后的目录与数据指纹，用于整页状态失效。
  query_backend?: 'sqlite' | 'superset' | 'openfga' | 'superset_mcp_catalog_rest_query';
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
  // passed 表示约定口径下的计算对账；limitation 明确其不能证明的业务假设。
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
  // 首次自助核验采用最少人员字段；scope=all 指全部授权范围，而非全公司无条件可见。
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
  // 同源请求自动携带当前会话 Cookie；写请求附 CSRF，取消信号由调用组件控制。
  // 错误必须向上传递，不能把 403/503 伪装成“查询成功但没有数据”。
  const response = await fetch('/api' + path, {
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
