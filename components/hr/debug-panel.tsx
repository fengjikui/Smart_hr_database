'use client';
/**
 * V1 内嵌运行调试器：可发起一次 /chat，并轮询 /debug/runs 观察尚在执行的节点。
 * 区别于 V2 独立页只读取已保存历史 trace；两者都以服务端真实记录为准。
 */
import { useEffect, useRef, useState } from 'react';
import {
  Bug,
  Check,
  ChevronRight,
  CircleAlert,
  Clock3,
  Play,
  RefreshCw,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { api, ApiError, mutation } from './client';
import { Failure } from './results';
import type { Answer, Bootstrap, DebugRun, DebugRunSummary } from './types';

const STATUS: Record<string, string> = {
  running: '执行中',
  success: '成功',
  error: '失败',
  blocked: '已拦截',
  clarify: '需澄清',
  refuse: '已拒绝',
  interrupted: '已中断',
};
function duration(ms: number) {
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)} s` : `${ms.toFixed(1)} ms`;
}
export function JsonView({ value, label }: { value: unknown; label: string }) {
  // 只读文本展示，传入的字符串/JSON 不作为 HTML 或脚本执行。
  return (
    <section className="debug-json">
      <div className="debug-json-heading">
        <strong>{label}</strong>
        <span>JSON / TEXT</span>
      </div>
      <Textarea
        readOnly
        aria-label={label}
        value={
          value === null || value === undefined
            ? '尚无输出'
            : typeof value === 'string'
              ? value
              : JSON.stringify(value, null, 2)
        }
      />
    </section>
  );
}

export function DebugPanel({
  boot,
  initialRunId,
}: {
  boot: Bootstrap;
  initialRunId?: string;
}) {
  const [runs, setRuns] = useState<DebugRunSummary[]>([]);
  const [selected, setSelected] = useState(initialRunId ?? '');
  const [loaded, setLoaded] = useState<{ id: string; value: DebugRun } | null>(
    null,
  );
  const [selection, setSelection] = useState<{
    run: string;
    node: string;
  } | null>(null);
  const [question, setQuestion] = useState('我的直属和间接下属分别有多少人？');
  const questionSource = useRef<string | null>(initialRunId ?? null);
  const [previous, setPrevious] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [queryError, setQueryError] = useState('');
  const [revision, setRevision] = useState(0);
  // 新提问尚未拿到调试 ID 时，用本次开始时间辅助定位；最终 ID 仍以后端响应为准。
  const pendingSince = useRef<number | null>(null);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    const cancel = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    // 每次完成后再安排下一轮，避免慢请求叠加；换身份/选中记录或卸载时取消请求和定时器。
    async function poll() {
      try {
        const list = await api<{ runs: DebugRunSummary[] }>('/debug/runs', {
          signal: cancel.signal,
        });
        if (cancel.signal.aborted) return;
        setRuns(list.runs);
        const id =
          selected ||
          (pendingSince.current === null
            ? list.runs[0]?.id
            : list.runs.find(
                (r) =>
                  new Date(r.started_at).getTime() >=
                  (pendingSince.current ?? 0),
              )?.id);
        if (id) {
          const detail = await api<DebugRun>(
            `/debug/runs/${encodeURIComponent(id)}`,
            { signal: cancel.signal },
          );
          if (cancel.signal.aborted) return;
          setLoaded({ id, value: detail });
          if (questionSource.current === id) {
            setQuestion(detail.question);
            questionSource.current = null;
          }
          if (!selected) setSelected(id);
        } else setLoaded(null);
        setError('');
      } catch (e) {
        if (!cancel.signal.aborted) {
          setError((e as Error).message);
          setLoaded(null);
        }
      } finally {
        if (!cancel.signal.aborted) timer = setTimeout(() => void poll(), 2500);
      }
    }
    void poll();
    return () => {
      cancel.abort();
      clearTimeout(timer);
    };
  }, [boot.principal.id, selected, revision]);
  const run =
    loaded && (!selected || loaded.id === selected) ? loaded.value : null;
  // 优先保留用户选中的节点，否则选择运行中、失败或模型节点，便于定位实际卡点。
  const node =
    run?.nodes.find(
      (n) => selection?.run === run.id && selection.node === n.id,
    ) ??
    run?.nodes.find((n) => n.status === 'running') ??
    run?.nodes.find((n) => n.status === 'error') ??
    run?.nodes.find((n) => n.key === 'model') ??
    run?.nodes[0];
  async function submit() {
    // 调试提问仍走正式聊天 API；失败响应可带 debugRunId，以便查看被拦截或异常的节点。
    if (busy || question.trim().length < 2) return;
    const request = new AbortController();
    controller.current = request;
    setBusy(true);
    setQueryError('');
    setSelected('');
    pendingSince.current = Date.now();
    setLoaded(null);
    setSelection(null);
    try {
      const answer = await api<Answer>('/chat', {
        ...mutation(boot.principal.csrf, {
          question: question.trim(),
          ...(previous ? { previous_id: previous } : {}),
        }),
        signal: request.signal,
      });
      if (request.signal.aborted) return;
      setSelected(answer.debug_run_id ?? '');
    } catch (e) {
      if (request.signal.aborted) return;
      setQueryError((e as Error).message);
      if (e instanceof ApiError && e.debugRunId) setSelected(e.debugRunId);
    } finally {
      if (!request.signal.aborted) {
        setBusy(false);
        pendingSince.current = null;
        setRevision((v) => v + 1);
      }
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">PIPELINE DEBUGGER</p>
          <h1>节点调试</h1>
          <p>查看真实请求经过的每个节点，定位问题从哪一步开始。</p>
        </div>
        <Button variant="outline" onClick={() => setRevision((v) => v + 1)}>
          <RefreshCw size={16} />
          刷新记录
        </Button>
      </div>
      <form
        className="debug-query"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <label htmlFor="debug-question">
          调试问题{' '}
          <span>
            {boot.principal.label} · {boot.principal.scope_label}
          </span>
        </label>
        <div className="debug-query-row">
          <Textarea
            id="debug-question"
            value={question}
            maxLength={600}
            onChange={(e) => {
              questionSource.current = null;
              setQuestion(e.target.value);
            }}
            placeholder="输入要排查的问题"
          />
          <Button type="submit" disabled={busy || question.trim().length < 2}>
            <Play size={16} />
            {busy ? '正在执行…' : '运行并查看节点'}
          </Button>
        </div>
        <div className="debug-context">
          <span>本地模型 {boot.model.model} · 实时更新 · 最近50次</span>
          <label htmlFor="debug-previous">
            <Checkbox
              id="debug-previous"
              checked={Boolean(previous)}
              disabled={
                !previous &&
                (!run?.result?.conversation_id ||
                  run.result.status !== 'success')
              }
              onCheckedChange={(checked) =>
                setPrevious(checked ? (run?.result?.conversation_id ?? '') : '')
              }
            />
            继承当前成功查询作为追问上下文
          </label>
        </div>
        {previous ? <small>追问上下文：{previous}</small> : null}
        {queryError ? (
          <p className="debug-error" role="alert">
            {queryError}
          </p>
        ) : null}
      </form>
      <div className="debug-run-picker">
        <label htmlFor="debug-run-select">选择查询记录</label>
        <Select
          value={selected}
          onValueChange={(v) => {
            if (v) {
              questionSource.current = v;
              setSelected(v);
              setSelection(null);
            }
          }}
        >
          <SelectTrigger id="debug-run-select" aria-label="选择调试记录">
            <SelectValue>
              {runs.find((r) => r.id === selected)?.question ??
                '选择最近一次查询'}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {runs.map((r) => (
              <SelectItem key={r.id} value={r.id}>
                {new Date(r.started_at).toLocaleTimeString('zh-CN')} ·{' '}
                {STATUS[r.status] ?? r.status} · {r.question.slice(0, 60)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {error ? (
        <Failure
          message={error}
          retry={() => {
            setSelected('');
            setRevision((v) => v + 1);
          }}
        />
      ) : null}
      {!run && !error ? (
        <div className="debug-empty">
          <Bug size={28} />
          <h2>{busy ? '正在建立调试记录' : '还没有当前身份的调试记录'}</h2>
          <p>
            在这里运行一个问题，或到智能问数提问。新查询才会产生逐节点输入输出，历史查询不会补造记录。
          </p>
        </div>
      ) : null}
      {run ? (
        <>
          <div className="debug-run-summary">
            <span className={`debug-status ${run.status}`}>
              {STATUS[run.status] ?? run.status}
            </span>
            <strong>{run.question}</strong>
            <span>
              <Clock3 size={14} />
              {duration(run.duration_ms)}
            </span>
            <code title={run.id}>{run.id.slice(0, 12)}</code>
          </div>
          {run.result?.orchestration ? (
            <div className="semantic-run-info">
              <strong>LangGraph {run.result.orchestration.version}</strong>
              <span>模型调用 {run.result.orchestration.model_calls} 次</span>
              <span>
                补充读取 {run.result.orchestration.metadata_expansions} / 2 次
              </span>
              <span>
                实际披露 {run.result.orchestration.disclosed_ids.length} 个定义
              </span>
              <span title={run.result.orchestration.semantic_revision}>
                口径版本{' '}
                {run.result.orchestration.semantic_revision.slice(0, 10)}
              </span>
            </div>
          ) : null}
          <div className="debug-layout">
            <nav className="debug-node-list" aria-label="执行节点">
              {run.nodes.map((n, i) => (
                <button
                  key={n.id}
                  className={node?.id === n.id ? 'selected' : ''}
                  onClick={() => setSelection({ run: run.id, node: n.id })}
                  aria-current={node?.id === n.id ? 'step' : undefined}
                >
                  <span className={`node-state ${n.status}`}>
                    {n.status === 'error' ? (
                      <CircleAlert size={15} />
                    ) : n.status === 'running' ? (
                      <Clock3 size={15} />
                    ) : (
                      <Check size={15} />
                    )}
                  </span>
                  <span>
                    <strong>
                      {String(i + 1).padStart(2, '0')} {n.name}
                    </strong>
                    <small>
                      {STATUS[n.status] ?? n.status} · {duration(n.duration_ms)}
                    </small>
                  </span>
                  <ChevronRight size={13} />
                </button>
              ))}
            </nav>
            <div className="debug-node-detail" key={node?.id}>
              {node ? (
                <>
                  <div className="debug-detail-heading">
                    <div>
                      <p>
                        节点 {run.nodes.indexOf(node) + 1} / {run.nodes.length}
                      </p>
                      <h2>{node.name}</h2>
                    </div>
                    <span>
                      {STATUS[node.status]} · {duration(node.duration_ms)}
                    </span>
                  </div>
                  {node.error ? (
                    <JsonView label="错误与校验详情" value={node.error} />
                  ) : null}
                  <JsonView label="输入 INPUT" value={node.input} />
                  <JsonView label="输出 OUTPUT" value={node.output} />
                </>
              ) : (
                <p>等待第一个节点。</p>
              )}
            </div>
          </div>
          <details className="debug-final">
            <summary>最终响应与运行错误</summary>
            <JsonView label="最终响应" value={run.result} />
            {run.error ? <JsonView label="运行错误" value={run.error} /> : null}
          </details>
          <p className="debug-policy">
            {run.capture_policy}{' '}
            未出现的节点表示没有执行。节点耗时包含记录写入开销。
          </p>
        </>
      ) : null}
    </>
  );
}
