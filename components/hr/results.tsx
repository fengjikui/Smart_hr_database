'use client';
/**
 * V1 的答案、图表与普通表格展示。接收 Answer 后不重新计算业务指标。
 * V2 的服务端分页/独立核验位于 components/demo/result.tsx 和 grid.tsx。
 */
import { lazy, Suspense, useState } from 'react';
import {
  BookOpen,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Code2,
  Download,
  Plus,
  ShieldCheck,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { number } from './client';
import type { Answer, DataRow } from './types';
// 较重的折线图按需加载，普通文本/表格答案不必等待对应图表组件。
const TrendChart = lazy(() =>
  import('./charts').then((m) => ({ default: m.TrendChart })),
);

export function LoadingBlock() {
  return (
    <div className="loading-block" aria-label="正在加载数据">
      <Skeleton className="h-6 w-48" />
      <Skeleton className="h-36 w-full" />
      <Skeleton className="h-5 w-2/3" />
    </div>
  );
}
export function Failure({
  message,
  retry,
}: {
  message: string;
  retry?: () => void;
}) {
  return (
    <div className="error-state" role="alert">
      <p>{message}</p>
      {retry ? (
        <Button variant="outline" onClick={retry}>
          重试
        </Button>
      ) : null}
    </div>
  );
}
export function BarChart({ answer }: { answer: Answer }) {
  const max = Math.max(
    1,
    ...answer.rows.map((r) => (typeof r.value === 'number' ? r.value : 0)),
  );
  return (
    <figure className="bar-chart" aria-label={`${answer.metric.name}分布`}>
      {answer.rows.slice(0, 12).map((row, i) => (
        <div className="bar-row" key={String(row.label)}>
          <div className="bar-caption">
            <span>
              <i style={{ background: `var(--chart-${(i % 5) + 1})` }} />
              {row.label}
            </span>
            <strong>
              {number(row.value)} <small>{answer.metric.unit}</small>
              {typeof row.denominator === 'number' ? (
                <small>
                  {' '}
                  · {row.numerator} / {row.denominator} 人
                </small>
              ) : null}
            </strong>
          </div>
          <div className="bar-track">
            <div
              style={{
                width: `${typeof row.value === 'number' ? (row.value / max) * 100 : 0}%`,
                background: `var(--chart-${(i % 5) + 1})`,
              }}
            />
          </div>
        </div>
      ))}
      {answer.rows.length > 12 ? (
        <p className="muted text-sm">图表展示前 12 组，完整结果见数据表。</p>
      ) : null}
    </figure>
  );
}
export function Chart({ answer }: { answer: Answer }) {
  // 图表类型由服务端按查询结果决定；前端只选择可视化组件，保留原始数据口径。
  return answer.chart_type === 'comparison' ? (
    <WorkforceChart answer={answer} />
  ) : answer.chart_type === 'line' ? (
    <Suspense fallback={<LoadingBlock />}>
      <TrendChart answer={answer} />
    </Suspense>
  ) : (
    <BarChart answer={answer} />
  );
}
function WorkforceChart({ answer }: { answer: Answer }) {
  const max = Math.max(
    1,
    ...answer.rows.flatMap((r) => [Number(r.hires), Number(r.departures)]),
  );
  return (
    <figure
      className="bar-chart workforce-chart"
      aria-label="入职与离职人数对比"
    >
      <figcaption className="muted text-sm">
        每组分别展示入职、离职人数；净增为两者之差。
      </figcaption>
      {answer.rows.slice(0, 12).map((row) => (
        <div className="workforce-group" key={String(row.label)}>
          <div className="bar-caption">
            <strong>{row.label}</strong>
            <span>
              净增 {Number(row.value) > 0 ? '+' : ''}
              {row.value} 人
            </span>
          </div>
          {(['hires', 'departures'] as const).map((key) => (
            <div className="workforce-series" key={key}>
              <span>{key === 'hires' ? '入职' : '离职'}</span>
              <div className="bar-track">
                <div
                  style={{
                    width: `${(Number(row[key]) / max) * 100}%`,
                    background:
                      key === 'hires' ? 'var(--chart-1)' : 'var(--chart-3)',
                  }}
                />
              </div>
              <strong>{row[key]} 人</strong>
            </div>
          ))}
        </div>
      ))}
      {answer.rows.length > 12 ? (
        <p className="muted text-sm">
          图表展示前 12 组，完整 {answer.rows.length} 组见数据表。
        </p>
      ) : null}
    </figure>
  );
}
export function DataTable({
  answer,
}: {
  answer: Pick<Answer, 'rows' | 'columns'>;
}) {
  // V1 表格对已返回 rows 做本地每页 10 行展示，不等同于 V2 的服务端查询分页。
  const [page, setPage] = useState(0);
  const count = 10;
  const pages = Math.ceil(answer.rows.length / count);
  const safePage = Math.min(page, Math.max(0, pages - 1));
  return (
    <div className="data-table">
      <Table>
        <TableHeader>
          <TableRow>
            {answer.columns.map((c) => (
              <TableHead key={c.key}>{c.label}</TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {answer.rows
            .slice(safePage * count, (safePage + 1) * count)
            .map((row: DataRow, i) => (
              <TableRow key={i}>
                {answer.columns.map((c) => (
                  <TableCell key={c.key}>
                    {typeof row[c.key] === 'number'
                      ? number(row[c.key], 2)
                      : row[c.key] === null
                        ? '—'
                        : String(row[c.key] ?? '—')}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          {answer.rows.length === 0 ? (
            <TableRow>
              <TableCell colSpan={answer.columns.length}>
                当前范围和期间没有匹配数据。
              </TableCell>
            </TableRow>
          ) : null}
        </TableBody>
      </Table>
      {pages > 1 ? (
        <div className="table-pagination">
          <span>
            共 {answer.rows.length} 条 · 第 {safePage + 1}/{pages} 页
          </span>
          <div>
            <Button
              variant="ghost"
              size="icon"
              aria-label="上一页"
              disabled={safePage === 0}
              onClick={() => setPage((v) => v - 1)}
            >
              <ChevronLeft />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              aria-label="下一页"
              disabled={safePage === pages - 1}
              onClick={() => setPage((v) => v + 1)}
            >
              <ChevronRight />
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
export function Result({
  answer,
  onSave,
  onExport,
  canExport = false,
}: {
  answer: Answer;
  onSave?: (a: Answer) => Promise<void>;
  onExport?: (a: Answer) => Promise<void>;
  canExport?: boolean;
}) {
  // 保存与导出委托工作台调用后端；按钮状态只防止重复操作，不是安全授权层。
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [explain, setExplain] = useState(false);
  async function save() {
    setBusy(true);
    setError('');
    try {
      await onSave?.(answer);
      setSaved(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function download() {
    setBusy(true);
    setError('');
    try {
      await onExport?.(answer);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  // 澄清/拒绝只呈现解释，不把缺少真实执行结果的响应渲染成成功图表。
  if (answer.status !== 'success')
    return (
      <div className={`answer-message ${answer.status}`}>
        <ShieldCheck size={20} />
        <div>
          <strong>
            {answer.status === 'clarify'
              ? '需要补充一点信息'
              : '当前查询未执行'}
          </strong>
          <p>{answer.summary}</p>
        </div>
      </div>
    );
  const visual =
    answer.plan.kind === 'metric' &&
    answer.plan.dimension !== 'none' &&
    answer.rows.length > 0;
  return (
    <section className="result-panel">
      <div className="result-top">
        <div>
          <span className="verified">
            <Check size={14} />
            已验证查询结果
          </span>
          <h3>
            {answer.plan.kind === 'people'
              ? '人员明细'
              : answer.plan.kind === 'attendance'
                ? '考勤异常明细'
                : answer.metric.name}
          </h3>
        </div>
        <div className="result-actions">
          {onExport && canExport && answer.plan.metric !== 'avg_salary' ? (
            <Button
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={download}
            >
              <Download />
              导出
            </Button>
          ) : null}
          {onSave && answer.plan.kind === 'metric' ? (
            <Button
              size="sm"
              variant="outline"
              onClick={save}
              disabled={saved || busy}
            >
              {saved ? <Check /> : <Plus />}
              {saved ? '已保存' : '保存到看板'}
            </Button>
          ) : null}
        </div>
      </div>
      <p className="answer-summary">{answer.summary}</p>
      {answer.applied_conditions?.length ? (
        <div className="applied-conditions" aria-label="本次统计条件">
          {answer.applied_conditions.map((condition) => (
            <p key={condition}>{condition}</p>
          ))}
        </div>
      ) : null}
      <div className="result-context">
        <span>
          <ShieldCheck size={14} />
          {answer.scope.label}
        </span>
        <span>
          <Clock3 size={14} />
          {answer.period.start} 至 {answer.period.end}
        </span>
        <span>{number(answer.duration_ms, 0)} ms 查询</span>
      </div>
      {visual ? (
        <Tabs defaultValue="chart">
          <TabsList variant="line">
            <TabsTrigger value="chart">图表</TabsTrigger>
            <TabsTrigger value="data">数据表</TabsTrigger>
          </TabsList>
          <TabsContent value="chart">
            <Chart answer={answer} />
          </TabsContent>
          <TabsContent value="data">
            <DataTable answer={answer} />
          </TabsContent>
        </Tabs>
      ) : (
        <DataTable answer={answer} />
      )}
      {error ? <Failure message={error} /> : null}
      <button
        className="explain-toggle"
        onClick={() => setExplain((v) => !v)}
        aria-expanded={explain}
      >
        <BookOpen size={15} />
        <span>查看统计口径与查询依据</span>
        <ChevronDown size={15} className={explain ? 'rotated' : ''} />
      </button>
      {explain ? (
        <div className="explanation">
          <p>{answer.metric.description}</p>
          <dl>
            <div>
              <dt>业务来源</dt>
              <dd>{answer.metric.source.join(' · ')}</dd>
            </div>
            <div>
              <dt>口径版本</dt>
              <dd>
                {answer.catalog_version} · {answer.metric.owner}
              </dd>
            </div>
            <div>
              <dt>数据截止</dt>
              <dd>{answer.as_of}</dd>
            </div>
          </dl>
          {answer.warnings.map((w) => (
            <p className="note" key={w}>
              {w}
            </p>
          ))}
          <details>
            <summary>
              <Code2 size={14} />
              执行 SQL（参数由服务端绑定）
            </summary>
            <pre>{answer.sql}</pre>
          </details>
        </div>
      ) : null}
      {answer.trace ? (
        <div className="trace">
          {answer.trace.map((s, i) => (
            <span key={`${s.name}-${i}`} title={s.detail}>
              <i>{i + 1}</i>
              {s.name}
              {s.duration_ms > 0 ? (
                <small>{(s.duration_ms / 1000).toFixed(1)}s</small>
              ) : null}
            </span>
          ))}
        </div>
      ) : null}
    </section>
  );
}
