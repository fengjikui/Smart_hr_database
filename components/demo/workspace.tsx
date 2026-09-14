'use client';
import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  BookOpen,
  Database,
  History,
  MessageSquare,
  Network,
  Plus,
  Send,
  Table2,
} from 'lucide-react';
import { PlanBuilder } from './builder';
import { Permissions } from './permissions';
import { ResultView } from './result';
import {
  defaultPlan,
  request,
  type Bootstrap,
  type Case,
  type Plan,
  type Result,
} from './types';
import './workspace.css';

type Tab = 'chat' | 'explore' | 'permissions' | 'cases' | 'history' | 'catalog';
const tabs: { key: Tab; label: string; icon: typeof Table2 }[] = [
  { key: 'chat', label: '智能问数', icon: MessageSquare },
  { key: 'explore', label: '自助核验', icon: Table2 },
  { key: 'permissions', label: '关系与权限', icon: Network },
  { key: 'cases', label: '演示题单', icon: BookOpen },
  { key: 'history', label: '历史对话', icon: History },
  { key: 'catalog', label: '字段与口径', icon: Database },
];
const fallbackPersonas = [
  { id: 'hr_lead', label: 'HR主管 · 王承哲' },
  { id: 'hrbp', label: 'HRBP · 姜姜' },
  { id: 'manager', label: '部门主管 · 王灏' },
  { id: 'employee', label: '员工 · 冯基魁' },
  { id: 'admin', label: '配置管理员 · 集团管理线' },
];

export default function DemoWorkspace() {
  const [boot, setBoot] = useState<Bootstrap | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const epoch = useRef(0);
  const refresh = useCallback(async (persona?: string) => {
    const version = ++epoch.current;
    setLoading(true);
    setError('');
    try {
      if (persona) await request('/session', '', { persona_id: persona });
      let response = await fetch('/api/v2/bootstrap');
      if (response.status === 401) {
        await request('/session', '', { persona_id: 'hr_lead' });
        response = await fetch('/api/v2/bootstrap');
      }
      if (!response.ok)
        throw new Error('HR 数据服务暂未连接，请检查系统是否启动。');
      const data: Bootstrap = await response.json();
      if (version === epoch.current) setBoot(data);
    } catch (e) {
      if (version === epoch.current) setError((e as Error).message);
    } finally {
      if (version === epoch.current) setLoading(false);
    }
  }, []);
  useEffect(() => {
    let disposed = false;
    async function start() {
      try {
        let response = await fetch('/api/v2/bootstrap');
        if (response.status === 401) {
          await request('/session', '', { persona_id: 'hr_lead' });
          response = await fetch('/api/v2/bootstrap');
        }
        if (!response.ok)
          throw new Error('HR 数据服务暂未连接，请检查系统是否启动。');
        const data: Bootstrap = await response.json();
        if (!disposed) setBoot(data);
      } catch (e) {
        if (!disposed) setError((e as Error).message);
      } finally {
        if (!disposed) setLoading(false);
      }
    }
    void start();
    return () => {
      disposed = true;
    };
  }, []);
  // Invalidate mounted views after changes made in another tab; no background model calls.
  useEffect(() => {
    if (!boot) return;
    let disposed = false;
    const timer = setInterval(async () => {
      const requestEpoch = epoch.current;
      try {
        const next = await request<Bootstrap>('/bootstrap', '');
        if (disposed || requestEpoch !== epoch.current) return;
        if (
          next.principal.id !== boot.principal.id ||
          next.principal.policy_version !== boot.principal.policy_version ||
          next.fingerprint !== boot.fingerprint
        ) {
          setBoot(next);
        }
      } catch {
        if (disposed || requestEpoch !== epoch.current) return;
        setBoot(null);
        setError('会话已失效，请选择演示身份。');
      }
    }, 30000);
    return () => {
      disposed = true;
      clearInterval(timer);
    };
  }, [boot]);
  return (
    <div className="d-app">
      <header className="d-header">
        <Link href="/demo" className="d-brand">
          <span>澄观</span>
          <span>HR 数据工作台</span>
          <small>演示 V2</small>
        </Link>
        <div className="d-header-right">
          <span className="d-synthetic">合成数据 · 2026-09-11</span>
          <label>
            演示身份
            <select
              aria-label="切换演示身份"
              disabled={loading}
              value={boot?.principal.id || 'hr_lead'}
              onChange={(e) => void refresh(e.target.value)}
            >
              {(boot?.personas || fallbackPersonas).map((p) => (
                <option value={p.id} key={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </header>
      {loading ? (
        <output className="d-loading">正在加载身份、权限和数据目录…</output>
      ) : error ? (
        <div className="d-error" role="alert">
          {error}
          <button onClick={() => void refresh()}>重新连接</button>
        </div>
      ) : (
        boot && (
          <Workspace
            key={`${boot.principal.id}-${boot.principal.policy_version}-${boot.fingerprint}`}
            boot={boot}
            onChanged={() => void refresh()}
          />
        )
      )}
    </div>
  );
}

function Workspace({
  boot,
  onChanged,
}: {
  boot: Bootstrap;
  onChanged: () => void;
}) {
  const [tab, setTab] = useState<Tab>('chat');
  const [question, setQuestion] = useState('');
  const [reply, setReply] = useState<Result | null>(null);
  const [previous, setPrevious] = useState<Result | null>(null);
  const [draft, setDraft] = useState<Plan>(defaultPlan);
  const [seed, setSeed] = useState<Result | null>(null);
  const [seedKey, setSeedKey] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [cases, setCases] = useState<Case[]>([]);
  const [history, setHistory] = useState<
    { id: string; question: string; created_at: string; status: string }[]
  >([]);
  const aborter = useRef<AbortController | null>(null);
  const onError = useCallback((m: string) => setError(m), []);
  useEffect(() => {
    const controller = new AbortController();
    request<{ cases: Case[] }>(
      '/cases',
      boot.principal.csrf,
      undefined,
      controller.signal,
    )
      .then((r) => setCases(r.cases))
      .catch((e) => {
        if (!controller.signal.aborted) onError(e.message);
      });
    return () => {
      controller.abort();
      aborter.current?.abort();
    };
  }, [boot.principal.csrf, onError]);
  useEffect(() => {
    if (tab !== 'history') return;
    const c = new AbortController();
    request<typeof history>(
      '/history',
      boot.principal.csrf,
      undefined,
      c.signal,
    )
      .then(setHistory)
      .catch((e) => {
        if (!c.signal.aborted) onError(e.message);
      });
    return () => c.abort();
  }, [tab, boot.principal.csrf, onError]);
  async function perform<T>(
    fn: (signal: AbortSignal) => Promise<T>,
    done: (value: T) => void,
  ) {
    aborter.current?.abort();
    const c = new AbortController();
    aborter.current = c;
    setBusy(true);
    setError('');
    try {
      const r = await fn(c.signal);
      if (!c.signal.aborted) done(r);
    } catch (e) {
      if (!c.signal.aborted) setError((e as Error).message);
    } finally {
      if (!c.signal.aborted) setBusy(false);
    }
  }
  const explore = useCallback((r: Result) => {
    setDraft({ ...r.plan, page: 1 });
    setSeed(r);
    setSeedKey((k) => k + 1);
    setTab('explore');
    setError('');
  }, []);
  const ask = () =>
    void perform(
      (signal) =>
        request<Result>(
          '/chat',
          boot.principal.csrf,
          { question, previous_id: previous?.id || null },
          signal,
        ),
      (r) => {
        setReply(r);
        if (r.status === 'success') setPrevious(r);
        setQuestion('');
      },
    );
  const run = () =>
    void perform(
      (signal) => request<Result>('/query', boot.principal.csrf, draft, signal),
      (r) => {
        setSeed(r);
        setSeedKey((k) => k + 1);
      },
    );
  const load = (id: string) =>
    void perform(
      (signal) =>
        request<Result>(
          '/history/' + id,
          boot.principal.csrf,
          undefined,
          signal,
        ),
      (r) => {
        setReply(r);
        setPrevious(r.status === 'success' ? r : null);
        setTab('chat');
      },
    );
  function newConversation() {
    aborter.current?.abort();
    setBusy(false);
    setPrevious(null);
    setReply(null);
    setQuestion('');
    setError('');
    setTab('chat');
  }
  return (
    <div className="d-shell">
      <aside className="d-sidebar">
        <button className="d-new" onClick={newConversation}>
          <Plus size={17} />
          新建查询
        </button>
        <nav>
          {tabs.map((t) => (
            <button
              key={t.key}
              className={tab === t.key ? 'active' : ''}
              aria-current={tab === t.key ? 'page' : undefined}
              onClick={() => {
                setTab(t.key);
                setError('');
              }}
            >
              <t.icon size={18} />
              {t.label}
            </button>
          ))}
        </nav>
        <div className="d-scope-note">
          <strong>{boot.principal.count} 位可见在职员工</strong>
          <span>候选人员 {boot.principal.candidate_count} 位（含离职）</span>
          <span>权限版本 {boot.principal.policy_version}</span>
          <span className={boot.model.connected ? 'd-model-ok' : ''}>
            ● {boot.model.connected ? boot.model.display_name : '模型未连接'}
          </span>
          <Link href="/">打开原版工作台</Link>
        </div>
      </aside>
      <main className="d-main">
        <div className="d-page-title">
          <div>
            <p className="d-eyebrow">
              HR ANALYTICS / {tabs.find((t) => t.key === tab)?.label}
            </p>
            <h1>
              {tab === 'chat'
                ? '从业务问题，到可核验的答案'
                : tab === 'explore'
                  ? '像操作表格一样，核对每一个结果'
                  : tabs.find((t) => t.key === tab)?.label}
            </h1>
          </div>
          <span className="d-muted">{boot.principal.label}</span>
        </div>
        {error && (
          <div className="d-error" role="alert">
            {error}
            <button onClick={() => setError('')}>关闭</button>
          </div>
        )}
        {busy && (
          <output className="d-working">
            正在处理
            {tab === 'chat' ? ' · 本地模型生成计划、校验条件并查询' : ''}…
          </output>
        )}
        {tab === 'chat' && (
          <>
            {!reply && (
              <div className="d-empty-chat">
                <h2>输入问题，也可以从演示题单开始</h2>
                <p>
                  查询当前授权内的人员、教育背景及入离职信息。答案会附上筛选条件、统计口径和计算依据。
                </p>
                <div className="d-suggestions">
                  {cases
                    .filter((c) =>
                      (boot.principal.role === 'employee'
                        ? []
                        : boot.principal.role === 'hrbp'
                          ? ['HR-02', 'HR-10']
                          : boot.principal.role === 'manager'
                            ? ['HR-01', 'HR-15']
                            : ['HR-05', 'HR-09', 'HR-10', 'HR-15']
                      ).includes(c.id),
                    )
                    .map((c) => (
                      <button
                        key={c.id}
                        onClick={() => setQuestion(c.question)}
                      >
                        {c.question}
                        <span>↗</span>
                      </button>
                    ))}
                </div>
              </div>
            )}
            {reply && (
              <>
                <div className="d-user-question">
                  <span>你的问题</span>
                  <p>{reply.question}</p>
                </div>
                {reply.status === 'success' ? (
                  <ResultView
                    key={reply.id}
                    seed={reply}
                    boot={boot}
                    onExplore={explore}
                    onError={onError}
                  />
                ) : (
                  <div className="d-clarify">
                    <strong>
                      {reply.status === 'blocked'
                        ? '权限限制'
                        : '需要进一步说明'}
                    </strong>
                    <p>{reply.message}</p>
                    {reply.trace && (
                      <details>
                        <summary>查看节点记录</summary>
                        <pre>{JSON.stringify(reply.trace, null, 2)}</pre>
                      </details>
                    )}
                  </div>
                )}
              </>
            )}
            <form
              className="d-composer"
              onSubmit={(e) => {
                e.preventDefault();
                if (question.trim().length >= 2 && !busy) ask();
              }}
            >
              {previous && (
                <div className="d-context">
                  继续追问：{previous.question}
                  <button type="button" onClick={() => setPrevious(null)}>
                    清除上下文
                  </button>
                </div>
              )}
              <label className="d-sr-only" htmlFor="hr-question">
                输入HR业务问题
              </label>
              <textarea
                id="hr-question"
                rows={2}
                maxLength={800}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder={
                  previous
                    ? '例如：把学校改成浙江大学，其他条件不变…'
                    : '例如：平台研发部和智能产品部目前硕士及以上占比各是多少？'
                }
              />
              <div>
                <span>本地模型 · 回答受当前权限与字段范围约束</span>
                <button
                  className="d-primary"
                  disabled={busy || question.trim().length < 2}
                  type="submit"
                >
                  <Send size={16} />
                  发送
                </button>
              </div>
            </form>
          </>
        )}
        {tab === 'explore' && (
          <>
            <p className="d-description">
              从聊天带入条件，或自行选择字段与统计口径。表格只返回授权后的数据，统计始终覆盖全部匹配记录。
            </p>
            <PlanBuilder
              value={draft}
              onChange={setDraft}
              onRun={run}
              catalog={boot.catalog}
              busy={busy}
            />
            {seed ? (
              <ResultView
                key={seedKey}
                seed={seed}
                boot={boot}
                onExplore={explore}
                onError={onError}
              />
            ) : (
              <div className="d-placeholder">
                <Table2 size={26} />
                <p>选择条件后点击“应用条件”加载人员表</p>
              </div>
            )}
          </>
        )}
        {tab === 'permissions' && (
          <Permissions boot={boot} onChanged={onChanged} onError={onError} />
        )}
        {tab === 'cases' && (
          <>
            <p className="d-description">
              20
              个沟通与验收问题。每题只用相关字段，以下列出业务条件，实际结果通过查询及独立对账检验。
            </p>
            <div className="d-case-list">
              {cases.map((c) => (
                <article key={c.id}>
                  <div className="d-case-id">
                    {c.id}
                    <small>{c.actor}</small>
                  </div>
                  <div>
                    <h2>{c.question}</h2>
                    {c.previous_case_id && (
                      <p className="d-muted">
                        需要先完成 {c.previous_case_id}
                        ，再从该历史记录继续追问。
                      </p>
                    )}
                    <details>
                      <summary>字段依赖与验收口径</summary>
                      <p>
                        {c.required_source_fields
                          .map(
                            (f) =>
                              boot.catalog.fields.find((x) => x.key === f)
                                ?.label || f,
                          )
                          .join('、')}
                      </p>
                      <ul>
                        {c.acceptance_checks.map((x) => (
                          <li key={x}>{x}</li>
                        ))}
                      </ul>
                    </details>
                  </div>
                  <button
                    onClick={() => {
                      setQuestion(c.question);
                      setTab('chat');
                    }}
                  >
                    带入提问
                  </button>
                </article>
              ))}
            </div>
          </>
        )}
        {tab === 'history' && (
          <>
            <p className="d-description">
              仅展示当前身份和权限版本可访问的记录。打开成功记录即可恢复条件继续追问。
            </p>
            {history.length === 0 ? (
              <div className="d-placeholder">暂无可恢复的查询记录</div>
            ) : (
              <div className="d-history">
                {history.map((h) => (
                  <button key={h.id} onClick={() => load(h.id)}>
                    <History size={18} />
                    <span>
                      {h.question}
                      <small>
                        {new Date(h.created_at).toLocaleString('zh-CN')} ·{' '}
                        {h.status === 'success'
                          ? '已完成'
                          : h.status === 'blocked'
                            ? '权限限制'
                            : '待澄清'}
                      </small>
                    </span>
                    <span>恢复 →</span>
                  </button>
                ))}
              </div>
            )}
          </>
        )}
        {tab === 'catalog' && (
          <>
            <p className="d-description">{boot.catalog.storage}</p>
            <p className="d-muted">
              数据结构：人员当前宽表 people · {boot.catalog.fields.length}{' '}
              个可见字段 · 字段 ID = 表 ID + 字段 ID。以下解释为可调整演示假设。
            </p>
            <h2>字段定义</h2>
            <div className="d-scroll">
              <table className="d-catalog">
                <thead>
                  <tr>
                    <th>字段 / ID</th>
                    <th>口语别名</th>
                    <th>含义</th>
                    <th>不代表什么</th>
                  </tr>
                </thead>
                <tbody>
                  {boot.catalog.fields.map((f) => (
                    <tr key={f.key}>
                      <td>
                        <strong>{f.label}</strong>
                        <code>{f.id}</code>
                        <small>
                          {f.type} · {f.group}
                        </small>
                      </td>
                      <td>{f.aliases.join('、')}</td>
                      <td>{f.description}</td>
                      <td>{f.not_meaning}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <h2>指标口径</h2>
            <div className="d-scroll">
              <table className="d-catalog">
                <thead>
                  <tr>
                    <th>指标 / ID</th>
                    <th>计算定义</th>
                    <th>依赖字段</th>
                  </tr>
                </thead>
                <tbody>
                  {boot.catalog.metrics.map((m) => (
                    <tr key={m.key}>
                      <td>
                        <strong>
                          {m.label}（{m.unit}）
                        </strong>
                        <code>{m.id}</code>
                      </td>
                      <td>
                        {m.definition}
                        <small>{m.null_rule}</small>
                      </td>
                      <td>{m.fields.join('、')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
