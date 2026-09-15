'use client';
import Link from 'next/link';
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';
import {
  BookOpen,
  Database,
  History,
  MessageSquare,
  Menu,
  X,
  Network,
  Plus,
  ArrowUp,
  Table2,
} from 'lucide-react';
import { PlanBuilder } from './builder';
import { Permissions } from './permissions';
import { ResultView } from './result';
import { DebugWorkspace } from './debug-workspace';
import { RunDebugLink } from './debug-link';
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

export default function DemoWorkspace({ debug = false }: { debug?: boolean }) {
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
      {loading ? (
        <output className="d-loading">正在加载身份、权限和数据目录…</output>
      ) : error ? (
        <div className="d-error" role="alert">
          {error}
          <button onClick={() => void refresh()}>重新连接</button>
          <label>
            演示身份
            <select
              aria-label="切换演示身份"
              defaultValue=""
              onChange={(e) => void refresh(e.target.value)}
            >
              <option value="" disabled>
                选择身份重新连接
              </option>
              {fallbackPersonas.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      ) : (
        boot &&
        (debug ? (
          <DebugWorkspace
            key={`${boot.principal.id}-${boot.principal.policy_version}-${boot.fingerprint}`}
            boot={boot}
            onPersonaChanged={(id) => void refresh(id)}
          />
        ) : (
          <Workspace
            key={`${boot.principal.id}-${boot.principal.policy_version}-${boot.fingerprint}`}
            boot={boot}
            onChanged={() => void refresh()}
            onPersonaChanged={(id) => void refresh(id)}
          />
        ))
      )}
    </div>
  );
}

function Workspace({
  boot,
  onChanged,
  onPersonaChanged,
}: {
  boot: Bootstrap;
  onChanged: () => void;
  onPersonaChanged: (id: string) => void;
}) {
  const [tab, setTab] = useState<Tab>('chat');
  const [question, setQuestion] = useState('');
  const [replies, setReplies] = useState<Result[]>([]);
  const [pendingQuestion, setPendingQuestion] = useState('');
  const chatEpoch = useRef(0);
  const composing = useRef(false);
  const compositionEndedAt = useRef(0);
  const [mobileOpen, setMobileOpen] = useState(false);
  const sidebar = useRef<HTMLElement | null>(null);
  const menuButton = useRef<HTMLButtonElement | null>(null);
  const latestTurn = useRef<HTMLDivElement | null>(null);
  const composerInput = useRef<HTMLTextAreaElement | null>(null);
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
  const ask = async () => {
    const text = question.trim();
    if (busy || text.length < 2) return;
    const requestVersion = ++chatEpoch.current;
    setPendingQuestion(text);
    await perform(
      (signal) =>
        request<Result>(
          '/chat',
          boot.principal.csrf,
          {
            question: text,
            previous_id: previous?.id || null,
          },
          signal,
        ),
      (r) => {
        setReplies((items) => [...items, r]);
        if (r.status === 'success') setPrevious(r);
        setQuestion('');
      },
    );
    if (requestVersion === chatEpoch.current) {
      setPendingQuestion('');
    }
  };
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
        setReplies([r]);
        setPrevious(r.status === 'success' ? r : null);
        setTab('chat');
      },
    );
  function newConversation() {
    chatEpoch.current += 1;
    aborter.current?.abort();
    setBusy(false);
    setPrevious(null);
    setReplies([]);
    setPendingQuestion('');
    setMobileOpen(false);
    setQuestion('');
    setError('');
    setTab('chat');
  }
  useLayoutEffect(() => {
    const input = composerInput.current;
    if (!input) return;
    input.style.height = '0px';
    input.style.height = `${Math.min(Math.max(input.scrollHeight, 48), 104)}px`;
  }, [question, tab]);
  useEffect(() => {
    if (tab === 'chat') latestTurn.current?.scrollIntoView({ block: 'start' });
  }, [tab, replies.length, pendingQuestion]);
  useEffect(() => {
    if (tab === 'chat' && !pendingQuestion && replies.length)
      composerInput.current?.focus({ preventScroll: true });
  }, [tab, replies.length, pendingQuestion]);
  useEffect(() => {
    if (mobileOpen)
      sidebar.current
        ?.querySelector<HTMLButtonElement>('.d-mobile-close')
        ?.focus();
  }, [mobileOpen]);
  useEffect(() => {
    const desktop = window.matchMedia('(min-width: 701px)');
    const close = () => {
      if (desktop.matches) setMobileOpen(false);
    };
    desktop.addEventListener('change', close);
    return () => desktop.removeEventListener('change', close);
  }, []);
  const closeMenu = useCallback(() => {
    setMobileOpen(false);
    menuButton.current?.focus();
  }, []);
  useEffect(() => {
    if (!mobileOpen) return;
    const keyboard = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        closeMenu();
        return;
      }
      if (e.key !== 'Tab') return;
      const controls = Array.from(
        sidebar.current?.querySelectorAll<HTMLElement>(
          'a[href],button:not([disabled]),select,summary',
        ) || [],
      ).filter((node) => {
        const closedDetails = node.closest('details:not([open])');
        return (
          node.getClientRects().length > 0 &&
          (!closedDetails ||
            (node.tagName === 'SUMMARY' &&
              node.parentElement === closedDetails))
        );
      });
      if (!controls.length) return;
      const first = controls[0],
        last = controls[controls.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', keyboard);
    return () => document.removeEventListener('keydown', keyboard);
  }, [mobileOpen, closeMenu]);
  return (
    <div className="d-shell">
      <button
        ref={menuButton}
        className="d-mobile-menu"
        aria-label="打开导航和身份设置"
        aria-expanded={mobileOpen}
        aria-controls="demo-sidebar"
        onClick={() => setMobileOpen(true)}
      >
        <Menu size={20} />
      </button>
      {mobileOpen && (
        <button
          className="d-sidebar-backdrop"
          aria-label="关闭导航"
          onClick={closeMenu}
        />
      )}
      <aside
        id="demo-sidebar"
        ref={sidebar}
        className={`d-sidebar${mobileOpen ? ' is-open' : ''}`}
        aria-label="工作台导航与身份"
      >
        <div className="d-sidebar-brand">
          <Link href="/demo" className="d-brand">
            <span>澄观</span>
            <small>HR 智能问数</small>
          </Link>
          <button
            className="d-mobile-close"
            aria-label="收起导航"
            onClick={closeMenu}
          >
            <X size={18} />
          </button>
        </div>
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
                setMobileOpen(false);
                setError('');
              }}
            >
              <t.icon size={18} />
              {t.label}
            </button>
          ))}
          <RunDebugLink navigation />
        </nav>
        <div className="d-account">
          <label htmlFor="demo-persona">演示身份</label>
          <select
            id="demo-persona"
            aria-label="切换演示身份"
            value={boot.principal.id}
            onChange={(e) => onPersonaChanged(e.target.value)}
          >
            {boot.personas.map((p) => (
              <option value={p.id} key={p.id}>
                {p.label}
              </option>
            ))}
          </select>
          <div className="d-scope-note">
            <span>{boot.principal.count} 位可见在职员工</span>
            <span className="d-synthetic">合成数据 · {boot.catalog.as_of}</span>
            <details>
              <summary>权限与模型状态</summary>
              <div className="d-account-details">
                <span>
                  候选人员 {boot.principal.candidate_count} 位（含离职）
                </span>
                <span>权限版本 {boot.principal.policy_version}</span>
                <span className={boot.model.connected ? 'd-model-ok' : ''}>
                  ●{' '}
                  {boot.model.connected
                    ? boot.model.display_name
                    : '模型未连接'}
                </span>
                <Link href="/">打开原版工作台</Link>
              </div>
            </details>
          </div>
        </div>
      </aside>
      <main
        className={`d-main${tab === 'chat' ? ' d-main-chat' : ''}`}
        inert={mobileOpen}
      >
        {tab === 'chat' ? (
          <h1 className="d-sr-only">智能问数</h1>
        ) : (
          <div className="d-page-title">
            <h1>
              {tab === 'explore'
                ? '自助核验'
                : tabs.find((t) => t.key === tab)?.label}
            </h1>
          </div>
        )}
        {error && (
          <div className="d-error" role="alert">
            {error}
            <button onClick={() => setError('')}>关闭</button>
          </div>
        )}
        {busy && tab !== 'chat' && (
          <output className="d-working">正在处理…</output>
        )}
        {tab === 'chat' && (
          <>
            <div className="d-chat-scroll" aria-label="问数对话">
              {replies.length === 0 && !pendingQuestion && (
                <div className="d-empty-chat">
                  <h2>今天想了解哪些人员信息？</h2>
                  <p>
                    直接提问，或从下面的示例开始。每个结果都可以查看条件、明细与计算依据。
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
              {replies.map((r, index) => (
                <div
                  key={r.id || index}
                  ref={
                    index === replies.length - 1 && !pendingQuestion
                      ? latestTurn
                      : undefined
                  }
                >
                  <ChatExchange
                    reply={r}
                    latest={index === replies.length - 1 && !pendingQuestion}
                    boot={boot}
                    onExplore={explore}
                    onError={onError}
                  />
                </div>
              ))}
              {pendingQuestion && (
                <div ref={latestTurn} className="d-chat-exchange">
                  <div className="d-user-question">
                    <span className="d-sr-only">你的问题</span>
                    <p>{pendingQuestion}</p>
                  </div>
                  <output className="d-working">
                    澄观正在理解问题、核对条件并查询…
                  </output>
                </div>
              )}
            </div>
            <div className="d-composer-dock">
              <form
                className="d-composer"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (question.trim().length >= 2 && !busy) void ask();
                }}
              >
                {previous && (
                  <div className="d-context">
                    <span title={previous.question}>
                      继续追问：{previous.question}
                    </span>
                    <button
                      type="button"
                      aria-label="清除上下文"
                      title="清除上下文"
                      onClick={() => setPrevious(null)}
                    >
                      <X size={14} aria-hidden="true" />
                    </button>
                  </div>
                )}
                <label className="d-sr-only" htmlFor="hr-question">
                  输入HR业务问题
                </label>
                <div className="d-input-surface">
                  <textarea
                    id="hr-question"
                    ref={composerInput}
                    aria-describedby="hr-input-help"
                    disabled={!!pendingQuestion}
                    onCompositionStart={() => {
                      composing.current = true;
                    }}
                    onCompositionEnd={(e) => {
                      composing.current = false;
                      compositionEndedAt.current = e.timeStamp;
                    }}
                    onKeyDown={(e) => {
                      if (
                        e.key !== 'Enter' ||
                        e.nativeEvent.isComposing ||
                        composing.current ||
                        e.timeStamp - compositionEndedAt.current < 50
                      )
                        return;
                      e.preventDefault();
                      if (e.ctrlKey) {
                        const input = e.currentTarget;
                        const start = input.selectionStart,
                          end = input.selectionEnd;
                        if (question.length - (end - start) >= 800) return;
                        const nextText =
                          question.slice(0, start) + '\n' + question.slice(end);
                        setQuestion(nextText);
                        requestAnimationFrame(() => {
                          if (input.value === nextText)
                            input.setSelectionRange(start + 1, start + 1);
                        });
                      } else if (!busy) void ask();
                    }}
                    rows={1}
                    maxLength={800}
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    placeholder={previous ? '继续追问…' : '输入 HR 问题…'}
                  />
                  {!question && (
                    <span className="d-composer-hint" aria-hidden="true">
                      <span className="d-local-hint">本地模型 · </span>
                      当前授权范围
                      <span className="d-shortcut-hint">
                        {' '}
                        · Enter 发送 / Ctrl+Enter 换行
                      </span>
                    </span>
                  )}
                  <span id="hr-input-help" className="d-sr-only">
                    Enter 发送，Ctrl 加 Enter 换行。仅查询当前授权范围。
                  </span>
                  <button
                    className="d-primary d-send"
                    aria-label="发送"
                    title="发送（Enter）"
                    disabled={busy || question.trim().length < 2}
                    type="submit"
                  >
                    <ArrowUp size={20} aria-hidden="true" />
                  </button>
                </div>
              </form>
            </div>
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

function ChatExchange({
  reply,
  latest,
  boot,
  onExplore,
  onError,
}: {
  reply: Result;
  latest: boolean;
  boot: Bootstrap;
  onExplore: (r: Result) => void;
  onError: (message: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <article
      className="d-chat-exchange"
      aria-label={reply.question || '查询回答'}
    >
      <div className="d-user-question">
        <span className="d-sr-only">你的问题</span>
        <p>{reply.question}</p>
      </div>
      <div className="d-assistant-label">
        <MessageSquare size={16} />
        <span>澄观</span>
      </div>
      {reply.status === 'success' ? (
        latest || expanded ? (
          <>
            {!latest && (
              <button
                className="d-collapse-result"
                onClick={() => setExpanded(false)}
              >
                收起这次结果
              </button>
            )}
            <ResultView
              seed={reply}
              boot={boot}
              onExplore={onExplore}
              onError={onError}
            />
          </>
        ) : (
          <div className="d-previous-answer">
            <p className="d-answer">{reply.summary}</p>
            <button onClick={() => setExpanded(true)}>查看这次的表格</button>
            <RunDebugLink runId={reply.id} />
          </div>
        )
      ) : (
        <div className="d-clarify">
          <strong>
            {reply.status === 'blocked' ? '权限限制' : '需要进一步说明'}
          </strong>
          <p>{reply.message}</p>
          {reply.id && <RunDebugLink runId={reply.id} />}
        </div>
      )}
    </article>
  );
}
