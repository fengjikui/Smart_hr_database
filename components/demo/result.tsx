'use client';
import { useMemo, useState } from 'react';
import { CheckCircle2, Download, ShieldCheck, Table2 } from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { QueryGrid } from './grid';
import { RunDebugLink } from './debug-link';
import {
  request,
  type Bootstrap,
  type Result,
  type Row,
  type Verification,
} from './types';

export function ResultView({
  seed,
  boot,
  onExplore,
  onError,
}: {
  seed: Result;
  boot: Bootstrap;
  onExplore: (r: Result) => void;
  onError: (m: string) => void;
}) {
  const [result, setResult] = useState(seed);
  const [verification, setVerification] = useState<Verification | null>(null);
  const [busy, setBusy] = useState(false);
  const [metric, setMetric] = useState(seed.plan.metrics[0]);
  const labels = useMemo(
    () =>
      Object.fromEntries(
        [...boot.catalog.fields, ...boot.catalog.metrics].map((f) => [
          f.key,
          f.label,
        ]),
      ),
    [boot.catalog],
  );
  const conditions = [
    `范围：${{ all: '全部授权', reports: '直属与间接下属', direct: '直属下属', indirect: '间接下属', hrbp: '本人HRBP服务', inherited_hrbp: '下属HRBP服务', self: '本人' }[result.plan.scope] || result.plan.scope}`,
    `状态：${{ active: '当前在职', all: '全部状态', confirmed: '实际已转正' }[result.plan.population]}`,
    ...(result.plan.departments.length
      ? [`部门：${result.plan.departments.join('、')}`]
      : []),
    ...(result.plan.date_field
      ? [
          `${labels[result.plan.date_field] || '入离职期间'}：${result.plan.start_date} 至 ${result.plan.end_date}`,
        ]
      : []),
    ...result.plan.filters.map(
      (f) =>
        `${labels[f.field]} ${{ eq: '等于', in: '属于', gte: '≥', lte: '≤', contains: '包含', not_null: '不为空' }[f.op]} ${f.values.join(' 或 ')}`,
    ),
  ];
  async function verify() {
    setBusy(true);
    try {
      setVerification(
        await request<Verification>(
          '/verify',
          boot.principal.csrf,
          result.plan,
        ),
      );
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function download() {
    try {
      const response = await fetch('/api/v2/export', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': boot.principal.csrf,
        },
        body: JSON.stringify(result.plan),
      });
      if (!response.ok) {
        const data = (await response.json()) as { detail: string };
        throw new Error(data.detail);
      }
      const url = URL.createObjectURL(await response.blob());
      const a = document.createElement('a');
      a.href = url;
      a.download = 'HR查询.csv';
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      onError((e as Error).message);
    }
  }
  async function drill(row: Row, m: string) {
    try {
      const r = await request<Result>('/drill', boot.principal.csrf, {
        plan: result.plan,
        group: Object.fromEntries(result.plan.group_by.map((k) => [k, row[k]])),
        metric: m,
      });
      onExplore(r);
    } catch (e) {
      onError((e as Error).message);
    }
  }
  const chartRows = result.rows.map((r) => ({
    ...r,
    label: result.plan.group_by.map((k) => String(r[k])).join(' / '),
  }));
  return (
    <section className="d-result">
      <p className="d-answer">{result.summary}</p>
      <div className="d-effective" aria-label="实际生效条件">
        <ShieldCheck size={16} />
        <div>
          {conditions.map((c, i) => (
            <span key={i}>{c}</span>
          ))}
        </div>
      </div>
      <div className="d-result-toolbar">
        <strong>
          完整结果 {result.total_rows}{' '}
          {result.plan.kind === 'people' ? '人' : '组'}
        </strong>
        <span className="d-muted">列头筛选、排序在服务端生效</span>
        <div className="d-actions">
          <button onClick={() => onExplore(result)}>
            <Table2 size={15} />
            编辑条件
          </button>
          <button disabled={busy} onClick={verify}>
            <CheckCircle2 size={15} />
            {busy ? '对账中…' : '独立对账'}
          </button>
          {boot.principal.rules.export && (
            <button onClick={download}>
              <Download size={15} />
              导出全部匹配记录
            </button>
          )}
        </div>
      </div>
      {verification && (
        <output className={verification.passed ? 'd-verified' : 'd-error'}>
          <strong>
            {verification.passed ? '逐行与合计一致' : '发现差异'} · 核对{' '}
            {verification.compared_rows} 行 · 差异{' '}
            {verification.difference_count}
          </strong>
          <p>{verification.method}</p>
          <p className="d-muted">{verification.limitation}</p>
          <details>
            <summary>查看校验哈希与差异</summary>
            <pre>{JSON.stringify(verification, null, 2)}</pre>
          </details>
        </output>
      )}
      <QueryGrid
        plan={seed.plan}
        columns={seed.columns}
        csrf={boot.principal.csrf}
        onResult={(r) => {
          setResult(r);
          setVerification(null);
        }}
        onError={onError}
        onDrill={seed.plan.kind === 'aggregate' ? drill : undefined}
      />
      {result.plan.kind === 'aggregate' && result.plan.group_by.length > 0 && (
        <>
          <div className="d-chart-head">
            <h3>分组对比</h3>
            <label>
              图表指标
              <select
                value={metric}
                onChange={(e) => setMetric(e.target.value)}
              >
                {result.plan.metrics.map((m) => (
                  <option key={m} value={m}>
                    {labels[m]}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {result.total_rows > 50 ? (
            <p className="d-muted">
              超过 50 个分组，请缩小条件后查看图表，避免将当前页当作全部分组。
            </p>
          ) : (
            <div className="d-chart">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={chartRows}
                  onClick={(state) => {
                    const i = Number(state.activeTooltipIndex);
                    if (Number.isInteger(i) && result.rows[i])
                      void drill(result.rows[i], metric);
                  }}
                  margin={{ top: 10, right: 20, left: 0, bottom: 48 }}
                >
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis
                    dataKey="label"
                    tick={{ fontSize: 11 }}
                    angle={-18}
                    textAnchor="end"
                    interval={0}
                  />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Bar
                    dataKey={metric}
                    name={labels[metric]}
                    fill="#a32b36"
                    maxBarSize={48}
                    radius={[3, 3, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
          <p className="d-muted">
            双击统计单元格或点击图表查看对应人员；比例下钻显示分子。净增需分别查看入职、离职。
          </p>
        </>
      )}
      <details className="d-debug">
        <summary>查看查询计划、SQL 与参数</summary>
        <pre>
          {JSON.stringify(
            {
              plan: result.plan,
              sql: result.sql,
              parameters: result.parameters,
              totals: result.totals,
            },
            null,
            2,
          )}
        </pre>
      </details>
      {seed.id && <RunDebugLink runId={seed.id} />}
      <p className="d-footnote">{result.notes.join(' ')}</p>
    </section>
  );
}
