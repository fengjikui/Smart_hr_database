'use client';
/**
 * V2 独立节点调试页：读取已保存历史的 trace，展示每一步真实记录的输入、输出和耗时。
 * 本页不重新触发模型推理；缺失 trace 时明确显示未记录，不能补造一条执行链。
 * 与 V1 可主动发起/轮询运行的 DebugPanel 是两套接口。
 */
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useEffect, useState } from 'react';
import { ArrowLeft, Clock3, RefreshCw, Workflow } from 'lucide-react';
import { request, type Bootstrap, type Result } from './types';
import './debug-workspace.css';

type RunSummary = {
  id: string;
  question: string;
  status: string;
  created_at: string;
};
type SavedRun = Pick<
  Result,
  'id' | 'status' | 'question' | 'parent_id' | 'trace' | 'summary' | 'message'
> &
  Partial<Result>;
const statusLabels: Record<string, string> = {
  success: '已完成',
  clarify: '需要澄清',
  blocked: '权限限制',
  error: '运行失败',
};

function statusLabel(status: string) {
  return statusLabels[status] || status;
}
function formatTime(value: string) {
  return new Date(value).toLocaleString('zh-CN', { hour12: false });
}

export function DebugWorkspace({
  boot,
  onPersonaChanged,
}: {
  boot: Bootstrap;
  onPersonaChanged: (id: string) => void;
}) {
  const search = useSearchParams();
  const requestedId = search.get('run') || '';
  const [listState, setListState] = useState<{
    revision: number;
    rows: RunSummary[] | null;
    error: string;
  } | null>(null);
  const [runState, setRunState] = useState<{
    key: string;
    data: SavedRun | null;
    error: string;
  } | null>(null);
  const [revision, setRevision] = useState(0);
  const history = listState?.revision === revision ? listState.rows : null;
  const listError = listState?.revision === revision ? listState.error : '';
  // URL 指定记录优先，否则选当前身份的最新记录；不存在/无权访问交给后端拒绝。
  const selectedId = requestedId || history?.[0]?.id || '';
  // 切换记录或刷新期间不展示上一个请求的数据；外层另以身份/权限指纹负责整页重建。
  const requestKey = `${selectedId}:${revision}`;
  const run = runState?.key === requestKey ? runState.data : null;
  const runError = runState?.key === requestKey ? runState.error : '';
  useEffect(() => {
    const c = new AbortController();
    request<RunSummary[]>('/history', boot.principal.csrf, undefined, c.signal)
      .then((data) => {
        if (!c.signal.aborted)
          setListState({ revision, rows: data, error: '' });
      })
      .catch((e) => {
        if (!c.signal.aborted)
          setListState({ revision, rows: null, error: e.message });
      });
    return () => c.abort();
  }, [boot.principal.csrf, revision]);
  useEffect(() => {
    // 列表和详情分别可取消，避免快速点击历史记录时较慢的旧响应覆盖新选择。
    const c = new AbortController();
    if (selectedId) {
      request<SavedRun>(
        '/history/' + encodeURIComponent(selectedId),
        boot.principal.csrf,
        undefined,
        c.signal,
      )
        .then((data) => {
          if (!c.signal.aborted)
            setRunState({ key: requestKey, data, error: '' });
        })
        .catch((e) => {
          if (!c.signal.aborted)
            setRunState({ key: requestKey, data: null, error: e.message });
        });
    }
    return () => c.abort();
  }, [selectedId, boot.principal.csrf, requestKey]);
  const current = run?.id === selectedId ? run : null;
  const timestamp = history?.find((item) => item.id === selectedId)?.created_at;
  return (
    <div className="d-trace-page">
      <aside className="d-trace-history" aria-label="节点调试导航与查询记录">
        <Link href="/demo" className="d-trace-back">
          <ArrowLeft size={16} />
          返回问数
        </Link>
        <h1>
          <Workflow size={23} />
          节点调试
        </h1>
        <div className="d-trace-list-heading">
          <h2>查询记录</h2>
          <button
            aria-label="刷新查询记录"
            title="刷新查询记录"
            onClick={() => setRevision((v) => v + 1)}
          >
            <RefreshCw size={16} />
          </button>
        </div>
        <p className="d-muted">当前身份最近 100 次已保存的查询</p>
        <nav aria-label="选择查询记录" className="d-trace-records">
          {listError ? (
            <p role="alert">{listError}</p>
          ) : history === null ? (
            <output>正在加载查询记录…</output>
          ) : history.length === 0 ? (
            <p>暂无记录。先在问数页面发送一个问题。</p>
          ) : (
            history.map((item) => (
              <Link
                key={item.id}
                href={`/demo/debug?run=${encodeURIComponent(item.id)}`}
                prefetch={false}
                aria-current={selectedId === item.id ? 'page' : undefined}
              >
                <span>{item.question}</span>
                <small>
                  {statusLabel(item.status)} · {formatTime(item.created_at)}
                </small>
              </Link>
            ))
          )}
        </nav>
        <div className="d-account">
          <label htmlFor="debug-persona">演示身份</label>
          <select
            id="debug-persona"
            aria-label="切换演示身份"
            value={boot.principal.id}
            onChange={(e) => onPersonaChanged(e.target.value)}
          >
            {boot.personas.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
          <p className="d-muted">
            权限版本 {boot.principal.policy_version} · 合成数据
          </p>
        </div>
      </aside>
      <main className="d-trace-main" aria-label="本次查询的节点调试">
        {runError ? (
          <div className="d-error" role="alert">
            <strong>无法读取这次查询</strong>
            <p>{runError}</p>
            <p>请从左侧选择当前身份可访问的记录。</p>
            <button onClick={() => setRevision((v) => v + 1)}>重新加载</button>
          </div>
        ) : selectedId ? (
          current ? (
            <RunInspector
              key={current.id}
              run={current}
              timestamp={timestamp}
            />
          ) : (
            <output className="d-loading">正在加载节点输入与输出…</output>
          )
        ) : (
          <div className="d-trace-empty">
            <Workflow size={30} />
            <h2>选择一次查询，查看执行过程</h2>
            <p>从聊天结果点击“查看节点调试”，可直接定位到对应记录。</p>
            <Link href="/demo">去问一个问题</Link>
          </div>
        )}
      </main>
    </div>
  );
}

function RunInspector({
  run,
  timestamp,
}: {
  run: SavedRun;
  timestamp?: string;
}) {
  // 选中节点只影响展示；记录顺序、输出内容和耗时均使用服务端保存值。
  const [selected, setSelected] = useState(0);
  const steps = run.trace || [];
  const step = steps[selected];
  const duration = steps.reduce((sum, item) => sum + item.duration_ms, 0);
  return (
    <>
      <header className="d-trace-run-header">
        <div className="d-trace-meta">
          <span className="d-trace-status">{statusLabel(run.status)}</span>
          {timestamp && (
            <time dateTime={timestamp}>{formatTime(timestamp)}</time>
          )}
          <span>{steps.length} 个节点</span>
          <span>
            <Clock3 size={14} />
            节点累计{' '}
            {duration.toLocaleString('zh-CN', {
              maximumFractionDigits: 2,
            })}{' '}
            ms
          </span>
        </div>
        <h2>{run.question || '查询记录'}</h2>
        <p className="d-trace-summary">{run.summary || run.message}</p>
        <div className="d-trace-meta">
          <span>记录 ID：{run.id}</span>
          {run.parent_id && (
            <Link
              href={`/demo/debug?run=${encodeURIComponent(run.parent_id)}`}
              prefetch={false}
            >
              查看上一轮查询
            </Link>
          )}
        </div>
      </header>
      {step ? (
        <div className="d-trace-inspector">
          <nav className="d-trace-steps" aria-label="选择执行节点">
            <h3>执行顺序</h3>
            {steps.map((item, index) => (
              <button
                key={index}
                onClick={() => setSelected(index)}
                aria-pressed={selected === index}
                aria-controls="debug-step-detail"
              >
                <span className="d-trace-number">{index + 1}</span>
                <span>
                  {item.name}
                  <small>{item.duration_ms.toLocaleString('zh-CN')} ms</small>
                </span>
              </button>
            ))}
          </nav>
          <section
            id="debug-step-detail"
            className="d-trace-detail"
            aria-label="选中节点的输入与输出"
          >
            <div className="d-trace-node-heading">
              <h3>
                {selected + 1}. {step.name}
              </h3>
              <span className="d-muted">
                {step.duration_ms.toLocaleString('zh-CN')} ms
              </span>
            </div>
            <div className="d-trace-io">
              <JsonPanel title="输入" value={step.input} />
              <JsonPanel title="输出" value={step.output} />
            </div>
          </section>
        </div>
      ) : (
        <p className="d-trace-no-steps">
          这条记录没有保存节点信息，无法补造执行过程。
        </p>
      )}
      <details className="d-trace-response">
        <summary>查看完整返回结果</summary>
        <JsonPanel
          title="返回给问数页面的结果（节点记录见上方）"
          value={Object.fromEntries(
            Object.entries(run).filter(([key]) => key !== 'trace'),
          )}
        />
      </details>
    </>
  );
}

function JsonPanel({ title, value }: { title: string; value: unknown }) {
  // 通过 React 文本节点展示 JSON，不把节点内容当 HTML 执行；长内容可键盘聚焦滚动。
  return (
    <section className="d-trace-json">
      <h4>{title}</h4>
      {/* Keyboard users must be able to focus and scroll long JSON payloads. */}
      {/* oxlint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
      <pre tabIndex={0} aria-label={title}>
        {value === undefined ? '未记录' : JSON.stringify(value, null, 2)}
      </pre>
    </section>
  );
}
