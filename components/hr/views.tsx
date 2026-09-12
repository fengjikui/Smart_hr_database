'use client';
import { useEffect, useRef, useState } from 'react';
import {
  ArrowRight,
  BookOpen,
  Bug,
  Check,
  CircleCheck,
  Database,
  GitBranch,
  LayoutDashboard,
  LockKeyhole,
  RefreshCw,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  Trash2,
  UserRound,
  Users,
  X,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { api, ApiError, mutation, number, useResource } from './client';
import { Chart, DataTable, Failure, LoadingBlock, Result } from './results';
import type {
  Answer,
  Bootstrap,
  Dashboard,
  Department,
  GovernanceData,
  Metric,
  OrganizationData,
  OverviewData,
} from './types';

export function PageHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        {description ? <p className="page-description">{description}</p> : null}
      </div>
      {action}
    </div>
  );
}

export function Overview({
  boot,
  onAsk,
}: {
  boot: Bootstrap;
  onAsk: (q: string) => void;
}) {
  const { data, loading, error, reload } = useResource<OverviewData>(
    '/overview',
    boot.principal.id,
  );
  const [question, setQuestion] = useState('');
  return (
    <>
      <PageHeading
        eyebrow="PEOPLE OVERVIEW"
        title="团队概览"
        description={`${boot.principal.scope_label} · 数据截至 ${boot.dataset.as_of}`}
        action={
          <Button variant="outline" onClick={reload} disabled={loading}>
            <RefreshCw size={15} />
            刷新数据
          </Button>
        }
      />
      <form
        className="overview-ask"
        onSubmit={(e) => {
          e.preventDefault();
          onAsk(question || '我的直属和间接下属分别有多少人？');
        }}
      >
        <span className="ask-symbol">
          <Sparkles size={21} />
        </span>
        <Input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          aria-label="向澄观提问"
          placeholder="问一个关于团队的问题，例如：我的直属和间接下属分别有多少人？"
        />
        <Button type="submit">
          开始问数
          <ArrowRight size={16} />
        </Button>
      </form>
      {error ? (
        <Failure message={error} retry={reload} />
      ) : loading || !data ? (
        <LoadingBlock />
      ) : (
        <>
          <div className="kpi-band">
            {data.kpis.map((a, i) => (
              <div className="kpi" key={a.metric.id}>
                <div className="kpi-label">
                  {a.metric.name}
                  <span className={i === 0 ? 'kpi-mark green' : 'kpi-mark'}>
                    {i === 0 ? '当前' : '本月'}
                  </span>
                </div>
                <div className="kpi-value">
                  {number(a.rows[0]?.value)}
                  <span>{a.metric.unit}</span>
                </div>
                <p>
                  {i === 0
                    ? '按入离职日期去重统计'
                    : i === 1
                      ? '排除已批准整日请假'
                      : i === 2
                        ? '仅包含审批通过的申请'
                        : '同一人同一天仅计一次'}
                </p>
              </div>
            ))}
          </div>
          <div className="overview-charts">
            <section className="chart-panel">
              <div className="panel-heading">
                <div>
                  <h2>人员规模趋势</h2>
                  <p>近六个月 · 各月末在职人数</p>
                </div>
                <span className="legend">
                  <i />
                  在职人数
                </span>
              </div>
              <Chart answer={data.trend} />
              <div className="panel-foot">
                <span>本月统计至 {boot.dataset.as_of}</span>
                <button onClick={() => onAsk('近半年每月在职人数趋势')}>
                  进一步分析
                  <ArrowRight size={14} />
                </button>
              </div>
            </section>
            <section className="chart-panel">
              <div className="panel-heading">
                <div>
                  <h2>人员分布</h2>
                  <p>按事业部 · 当前授权范围</p>
                </div>
                <Users size={18} />
              </div>
              <Chart answer={data.distribution} />
            </section>
          </div>
          <div className="overview-bottom">
            <section className="chart-panel">
              <div className="panel-heading">
                <div>
                  <h2>本月迟到趋势</h2>
                  <p>晚于 09:30 上班打卡</p>
                </div>
                <span className="subtle-tag">人次 / 日</span>
              </div>
              <Chart answer={data.attendance_trend} />
            </section>
            <section className="scope-panel">
              <span className="mini-icon">
                <ShieldCheck size={22} />
              </span>
              <h2>每一次查询，都有明确边界。</h2>
              <p>
                当前可查看 <strong>{boot.principal.scope_count} 人</strong>{' '}
                的基础信息与获准指标。
              </p>
              <div className="relationship-counts">
                <div>
                  <span>直属下属</span>
                  <strong>
                    {boot.principal.direct_count}
                    <small>人</small>
                  </strong>
                </div>
                <div>
                  <span>间接下属</span>
                  <strong>
                    {boot.principal.indirect_count}
                    <small>人</small>
                  </strong>
                </div>
              </div>
              <button
                className="text-link"
                onClick={() => onAsk('我的直属和间接下属分别有多少人？')}
              >
                用自然语言验证范围
                <ArrowRight size={15} />
              </button>
              <p className="scope-footnote">
                切换演示身份后，结果按新身份重新计算。
              </p>
            </section>
          </div>
        </>
      )}
    </>
  );
}

const EXAMPLES = [
  {
    icon: Users,
    label: '看清管理范围',
    question: '我的直属和间接下属分别有多少人？',
  },
  {
    icon: GitBranch,
    label: '了解人员结构',
    question: '按事业部统计当前在职人数',
  },
  {
    icon: CircleCheck,
    label: '分析考勤情况',
    question: '本月各部门已批准加班多少小时？',
  },
  { icon: BookOpen, label: '查看人员趋势', question: '近半年每月在职人数趋势' },
];
type Exchange = {
  question: string;
  answer?: Answer;
  error?: string;
  debugRunId?: string;
};
export function Chat({
  boot,
  initialQuestion,
  onSave,
  onExport,
  onDebug,
}: {
  boot: Bootstrap;
  initialQuestion: string;
  onSave: (a: Answer) => Promise<void>;
  onExport: (a: Answer) => Promise<void>;
  onDebug: (id?: string) => void;
}) {
  const [question, setQuestion] = useState(initialQuestion);
  const [messages, setMessages] = useState<Exchange[]>([]);
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [previous, setPrevious] = useState<string | undefined>();
  const controller = useRef<AbortController | null>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    if (!busy) return;
    const t = setInterval(() => setElapsed((v) => v + 1), 1000);
    return () => clearInterval(t);
  }, [busy]);
  async function ask(value = question) {
    if (busy || value.trim().length < 2) return;
    const clean = value.trim();
    setQuestion('');
    setBusy(true);
    setElapsed(0);
    setMessages((v) => [...v, { question: clean }]);
    const activeRequest = new AbortController();
    controller.current = activeRequest;
    try {
      const answer = await api<Answer>('/chat', {
        ...mutation(boot.principal.csrf, {
          question: clean,
          previous_id: previous,
        }),
        signal: activeRequest.signal,
      });
      if (activeRequest.signal.aborted || controller.current !== activeRequest)
        return;
      setMessages((v) =>
        v.map((m, i) => (i === v.length - 1 ? { ...m, answer } : m)),
      );
      if (answer.status === 'success') setPrevious(answer.conversation_id);
    } catch (e) {
      if (!activeRequest.signal.aborted && controller.current === activeRequest)
        setMessages((v) =>
          v.map((m, i) =>
            i === v.length - 1
              ? {
                  ...m,
                  error: (e as Error).message,
                  debugRunId: e instanceof ApiError ? e.debugRunId : undefined,
                }
              : m,
          ),
        );
    } finally {
      if (!activeRequest.signal.aborted && controller.current === activeRequest)
        setBusy(false);
    }
  }
  function fresh() {
    controller.current?.abort();
    setMessages([]);
    setQuestion('');
    setPrevious(undefined);
    setBusy(false);
    textarea.current?.focus();
  }
  return (
    <>
      <PageHeading
        eyebrow="ASK CHENGGUAN"
        title="智能问数"
        description="用日常语言提问，获得有口径、有依据的数据答案。"
        action={
          <Button variant="outline" onClick={fresh}>
            <PlusMark />
            新对话
          </Button>
        }
      />
      <div className="chat-workspace">
        <div className="chat-scope">
          <ShieldCheck size={16} />
          <span>
            {boot.principal.scope_label} · 当前在职 {boot.principal.scope_count}{' '}
            人
          </span>
          <span className="scope-divider" />
          <span>数据截至 {boot.dataset.as_of}</span>
        </div>
        {messages.length === 0 ? (
          <div className="chat-welcome">
            <div className="welcome-mark">
              <Sparkles size={27} />
            </div>
            <h2>今天，想了解团队的哪一面？</h2>
            <p>从组织规模到考勤变化，把问题交给澄观。</p>
            <div className="question-examples">
              {EXAMPLES.map(({ icon: Icon, label, question: q }) => (
                <button key={label} onClick={() => ask(q)}>
                  <Icon size={18} />
                  <span>
                    <strong>{label}</strong>
                    <small>{q}</small>
                  </span>
                  <ArrowRight size={15} />
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="conversation" aria-live="polite">
            {messages.map((m, i) => (
              <div className="exchange" key={i}>
                <div className="user-question">
                  <span className="user-avatar">
                    <UserRound size={16} />
                  </span>
                  <p>{m.question}</p>
                </div>
                {m.answer ? (
                  <Result
                    answer={m.answer}
                    onSave={onSave}
                    onExport={onExport}
                    canExport={boot.principal.can_export}
                  />
                ) : m.error ? (
                  <Failure message={m.error} retry={() => ask(m.question)} />
                ) : (
                  <div className="thinking">
                    <span className="thinking-dot" />
                    <div>
                      <strong>正在理解问题并生成查询计划</strong>
                      <p>
                        本地 Qwen3.8 27B · {elapsed} 秒 · 完成后将再次校验权限
                      </p>
                    </div>
                  </div>
                )}
                {m.answer?.debug_run_id || m.debugRunId ? (
                  <Button
                    className="open-debug-link"
                    variant="ghost"
                    onClick={() =>
                      onDebug(m.answer?.debug_run_id ?? m.debugRunId)
                    }
                  >
                    <Bug size={15} />
                    查看本次节点输入与输出
                  </Button>
                ) : null}
              </div>
            ))}
          </div>
        )}
        <form
          className="chat-composer"
          onSubmit={(e) => {
            e.preventDefault();
            void ask();
          }}
        >
          <Textarea
            ref={textarea}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            maxLength={600}
            aria-label="输入查询问题"
            placeholder={
              previous
                ? '继续追问，例如：再按岗位序列分组'
                : '例如：列出我的直属下属，或者本月各事业部的出勤率'
            }
            onKeyDown={(e) => {
              if (
                e.key === 'Enter' &&
                !e.shiftKey &&
                !e.nativeEvent.isComposing
              ) {
                e.preventDefault();
                void ask();
              }
            }}
          />
          <div className="composer-bottom">
            <span>
              <LockKeyhole size={13} />
              {boot.model.display_name} · 本地运行
            </span>
            <div>
              <small>{question.length}/600</small>
              <Button
                type="submit"
                disabled={busy || question.trim().length < 2}
                aria-label="发送问题"
              >
                <Send size={16} />
                {busy ? '分析中' : '发送'}
              </Button>
            </div>
          </div>
        </form>
        <p className="composer-hint">
          Enter 发送 · Shift + Enter 换行 ·
          不支持的条件会请求澄清，所有数字由数据库计算
        </p>
      </div>
    </>
  );
}
function PlusMark() {
  return (
    <span aria-hidden="true" style={{ fontSize: 20, lineHeight: 1 }}>
      +
    </span>
  );
}

export function Boards({
  boot,
  onAsk,
  onExport,
}: {
  boot: Bootstrap;
  onAsk: (q: string) => void;
  onExport: (a: Answer) => Promise<void>;
}) {
  const { data, loading, error, reload } = useResource<{
    dashboards: Dashboard[];
  }>('/dashboards', boot.principal.id);
  const [removing, setRemoving] = useState('');
  const [actionError, setActionError] = useState('');
  const [confirm, setConfirm] = useState('');
  async function remove(id: string) {
    setRemoving(id);
    try {
      await api(
        `/dashboards/${id}`,
        mutation(boot.principal.csrf, undefined, 'DELETE'),
      );
      setConfirm('');
      reload();
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setRemoving('');
    }
  }
  return (
    <>
      <PageHeading
        eyebrow="MY DASHBOARDS"
        title="我的看板"
        description="把常用问题保存下来，随时按最新数据与当前权限刷新。"
        action={
          <Button variant="outline" onClick={reload}>
            <RefreshCw size={15} />
            刷新全部
          </Button>
        }
      />
      {error || actionError ? (
        <Failure message={error || actionError} retry={reload} />
      ) : null}
      {loading ? (
        <LoadingBlock />
      ) : data?.dashboards.length ? (
        <div className="saved-boards">
          {data.dashboards.map((card) => (
            <section className="saved-board" key={card.id}>
              <div className="saved-board-header">
                <h2>{card.title}</h2>
                <div>
                  {confirm === card.id ? (
                    <>
                      <span>移除这张卡片？</span>
                      <Button
                        size="sm"
                        variant="destructive"
                        disabled={removing === card.id}
                        onClick={() => remove(card.id)}
                      >
                        移除
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setConfirm('')}
                      >
                        取消
                      </Button>
                    </>
                  ) : (
                    <Button
                      size="icon"
                      variant="ghost"
                      onClick={() => setConfirm(card.id)}
                      aria-label={`移除${card.title}`}
                    >
                      <Trash2 size={15} />
                    </Button>
                  )}
                </div>
              </div>
              {card.result ? (
                <Result
                  answer={card.result}
                  onExport={onExport}
                  canExport={boot.principal.can_export}
                />
              ) : (
                <Failure message={card.error || '卡片需要重新验证。'} />
              )}
            </section>
          ))}
        </div>
      ) : (
        <div className="empty-state">
          <LayoutDashboard size={42} />
          <h2>把有用的问题留下来。</h2>
          <p>
            在查询结果上点击“保存到看板”。这里保存指标与条件，每次打开重新查询，只有你能访问。
          </p>
          <Button onClick={() => onAsk('按事业部统计当前在职人数')}>
            创建第一个看板
            <ArrowRight size={16} />
          </Button>
        </div>
      )}
    </>
  );
}

function OrgBranch({
  department,
  all,
  selected,
  onSelect,
}: {
  department: Department;
  all: Department[];
  selected: number | null;
  onSelect: (d: Department) => void;
}) {
  const children = all.filter((d) => d.parent_id === department.id);
  return (
    <li>
      <details open={department.level < 3}>
        <summary aria-label={`展开${department.name}`}>
          <button
            onClick={(e) => {
              e.preventDefault();
              onSelect(department);
            }}
            className={
              selected === department.id ? 'org-node selected' : 'org-node'
            }
          >
            <span>
              <GitBranch size={15} />
              {department.name}
            </span>
            <strong>
              {department.count}
              <small>人</small>
            </strong>
          </button>
        </summary>
        {children.length ? (
          <ul>
            {children.map((d) => (
              <OrgBranch
                key={d.id}
                department={d}
                all={all}
                selected={selected}
                onSelect={onSelect}
              />
            ))}
          </ul>
        ) : null}
      </details>
    </li>
  );
}
export function Organization({ boot }: { boot: Bootstrap }) {
  const { data, loading, error, reload } = useResource<OrganizationData>(
    '/organization',
    boot.principal.id,
  );
  const [selected, setSelected] = useState<Department | null>(null);
  const [people, setPeople] = useState<Answer | null>(null);
  const [loadingPeople, setLoadingPeople] = useState(false);
  const [errorPeople, setErrorPeople] = useState('');
  const seq = useRef(0);
  async function select(d: Department) {
    const n = ++seq.current;
    setSelected(d);
    setLoadingPeople(true);
    setErrorPeople('');
    try {
      const r = await api<Answer>(
        '/query',
        mutation(boot.principal.csrf, {
          kind: 'people',
          metric: 'headcount',
          period: 'as_of',
          department: d.name,
          limit: 100,
        }),
      );
      if (n === seq.current) setPeople(r);
    } catch (e) {
      if (n === seq.current) setErrorPeople((e as Error).message);
    } finally {
      if (n === seq.current) setLoadingPeople(false);
    }
  }
  return (
    <>
      <PageHeading
        eyebrow="ORGANIZATION & ACCESS"
        title="组织与权限"
        description="沿组织层级查看人员，验证直属、间接下属和授权边界。"
      />
      {error ? (
        <Failure message={error} retry={reload} />
      ) : loading || !data ? (
        <LoadingBlock />
      ) : (
        <>
          <div className="organization-layout">
            <section className="chart-panel org-tree">
              <div className="panel-heading">
                <div>
                  <h2>组织结构</h2>
                  <p>仅显示有授权人员的组织</p>
                </div>
                <GitBranch size={18} />
              </div>
              <ul>
                {data.departments
                  .filter(
                    (d) => !data.departments.some((x) => x.id === d.parent_id),
                  )
                  .map((d) => (
                    <OrgBranch
                      key={d.id}
                      department={d}
                      all={data.departments}
                      selected={selected?.id ?? null}
                      onSelect={select}
                    />
                  ))}
              </ul>
            </section>
            <section className="access-detail">
              <span className="mini-icon">
                <ShieldCheck size={23} />
              </span>
              <h2>{boot.principal.title}</h2>
              <p className="muted">{boot.principal.label}</p>
              <dl className="access-rules">
                <div>
                  <dt>授权范围</dt>
                  <dd>{boot.principal.scope_label}</dd>
                </div>
                <div>
                  <dt>当前在职</dt>
                  <dd>{boot.principal.scope_count} 人</dd>
                </div>
                <div>
                  <dt>直属下属</dt>
                  <dd>{boot.principal.direct_count} 人</dd>
                </div>
                <div>
                  <dt>间接下属</dt>
                  <dd>{boot.principal.indirect_count} 人</dd>
                </div>
                <div>
                  <dt>人员基础信息</dt>
                  <dd className="allowed">
                    <Check size={14} />
                    允许
                  </dd>
                </div>
                <div>
                  <dt>薪酬汇总</dt>
                  <dd>
                    {boot.principal.salary_aggregate
                      ? '允许，受分组人数限制'
                      : '未授权'}
                  </dd>
                </div>
                <div>
                  <dt>查询结果导出</dt>
                  <dd>{boot.principal.can_export ? '按指标授权' : '未授权'}</dd>
                </div>
                <div>
                  <dt>个人敏感字段</dt>
                  <dd>
                    <LockKeyhole size={13} />
                    未开放
                  </dd>
                </div>
              </dl>
              <p className="note">
                范围由服务端根据身份与管理关系确定。修改问题、部门名称或前端请求均不能扩大权限。
              </p>
              <div className="demo-reminder">
                演示身份可在右上角切换。企业上线时需替换为 SSO 与正式授权源。
              </div>
            </section>
          </div>
          <section className="chart-panel people-panel">
            <div className="panel-heading">
              <div>
                <h2>{selected ? selected.name : '授权范围内的人员'}</h2>
                <p>当前在职 · 基础信息 · 最多展示 100 条</p>
              </div>
              {selected ? (
                <Button
                  variant="ghost"
                  onClick={() => {
                    seq.current++;
                    setSelected(null);
                    setPeople(null);
                    setLoadingPeople(false);
                    setErrorPeople('');
                  }}
                >
                  <X size={15} />
                  清除筛选
                </Button>
              ) : null}
            </div>
            {errorPeople ? (
              <Failure message={errorPeople} />
            ) : loadingPeople ? (
              <LoadingBlock />
            ) : (
              <DataTable
                key={selected?.id ?? 'all'}
                answer={people ?? data.people}
              />
            )}
          </section>
        </>
      )}
    </>
  );
}

export function Catalog({
  boot,
  onAsk,
}: {
  boot: Bootstrap;
  onAsk: (q: string) => void;
}) {
  const { data, loading, error, reload } = useResource<{
    metrics: Metric[];
    version: string;
    storage: string;
  }>('/catalog', boot.principal.id);
  const [query, setQuery] = useState('');
  const metrics = data?.metrics.filter((m) =>
    [m.name, m.description, m.domain, ...m.aliases].join(' ').includes(query),
  );
  return (
    <>
      <PageHeading
        eyebrow="SEMANTIC CATALOG"
        title="指标字典"
        description="同一个指标，始终使用同一套业务定义。"
      />
      <div className="catalog-toolbar">
        <div className="search-input">
          <Search size={17} />
          <Input
            placeholder="搜索指标、口径或关键词"
            aria-label="搜索指标"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <span className="muted">
          {metrics?.length ?? 0} 个可用指标 · {data?.version}
        </span>
      </div>
      {error ? (
        <Failure message={error} retry={reload} />
      ) : loading ? (
        <LoadingBlock />
      ) : (
        <div className="metric-list">
          {metrics?.map((m) => (
            <details className="metric-item" key={m.id}>
              <summary>
                <span
                  className={`domain-tag ${m.domain === '薪酬' ? 'restricted' : ''}`}
                >
                  {m.domain}
                </span>
                <div>
                  <strong>{m.name}</strong>
                  <p>{m.description}</p>
                </div>
                <span className="metric-unit">{m.unit}</span>
                <span className="metric-version">v{m.version}</span>
              </summary>
              <div className="metric-expanded">
                <dl>
                  <div>
                    <dt>数据来源</dt>
                    <dd>{m.source.join(' · ')}</dd>
                  </div>
                  <div>
                    <dt>口径负责人</dt>
                    <dd>{m.owner}</dd>
                  </div>
                  <div>
                    <dt>数据分级</dt>
                    <dd>
                      {m.sensitivity === 'internal'
                        ? '内部使用'
                        : '敏感汇总，至少 5 人'}
                    </dd>
                  </div>
                  <div>
                    <dt>别名</dt>
                    <dd>{m.aliases.join('、')}</dd>
                  </div>
                </dl>
                <Button variant="outline" onClick={() => onAsk(m.example)}>
                  用这个指标提问
                  <ArrowRight size={15} />
                </Button>
              </div>
            </details>
          ))}
          {metrics?.length === 0 ? (
            <p className="empty-inline">
              没有匹配指标，试试“迟到”“人数”或“加班”。
            </p>
          ) : null}
        </div>
      )}
      <div className="catalog-foot">
        <Database size={16} />
        <span>
          {data?.storage ?? '指标目录加载中'}
          。搜索索引可重建，权限不由检索结果决定。
        </span>
      </div>
    </>
  );
}

const TABLE_NAMES: Record<string, string> = {
  employees: '员工基本信息',
  assignments: '任职历史',
  departments: '组织部门',
  reporting_closure: '管理关系闭包',
  attendance_daily: '每日考勤',
  leave_requests: '请假申请',
  overtime_requests: '加班审批',
  compensation: '基本薪资',
  performance_reviews: '绩效评审',
  training_enrollments: '培训记录',
  recruitment_requisitions: '招聘需求',
  work_calendar: '工作日历',
  legal_entities: '法人主体',
  locations: '工作地点',
  job_families: '岗位序列',
  grades: '职级',
  positions: '岗位',
  employee_private: '敏感信息（模拟）',
  shift_policies: '班次规则',
  training_courses: '培训课程',
  dataset_meta: '数据集元信息',
};
export function Governance({ boot }: { boot: Bootstrap }) {
  const { data, loading, error, reload } = useResource<GovernanceData>(
    '/governance',
    boot.principal.id,
  );
  return (
    <>
      <PageHeading
        eyebrow="DATA GOVERNANCE"
        title="数据治理"
        description="从源数据到查询结果，每一层都有可验证的依据。"
        action={
          <Button variant="outline" onClick={reload}>
            <RefreshCw size={15} />
            重新校验
          </Button>
        }
      />
      {error ? (
        <Failure message={error} retry={reload} />
      ) : loading || !data ? (
        <LoadingBlock />
      ) : (
        <>
          <div className="validation-banner">
            <CircleCheck size={28} />
            <div>
              <h2>
                {data.validation.passed
                  ? '数据校验全部通过'
                  : '发现需要处理的数据问题'}
              </h2>
              <p>
                {data.validation.checks.length} 项检查 ·{' '}
                {number(data.validation.total_employees)} 名模拟员工 ·{' '}
                {number(data.validation.counts.attendance_daily)} 条考勤记录 ·
                种子 {data.validation.seed}
              </p>
            </div>
            <span className="subtle-tag">100% 合成数据</span>
          </div>
          <div className="governance-columns">
            <section className="chart-panel">
              <div className="panel-heading">
                <h2>质量检查</h2>
                <span className="muted">
                  {data.validation.checks.length} 项
                </span>
              </div>
              <div className="validation-checks">
                {data.validation.checks.map((c) => (
                  <div key={c.name}>
                    <Check size={15} />
                    <span>{c.name}</span>
                    <small>
                      {c.passed ? '通过' : `${c.violations} 个问题`}
                    </small>
                  </div>
                ))}
              </div>
            </section>
            <section className="chart-panel">
              <div className="panel-heading">
                <h2>关系数据模型</h2>
                <span className="muted">
                  {Object.keys(data.validation.counts).length} 张表
                </span>
              </div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>业务主题</TableHead>
                    <TableHead>记录数</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {Object.entries(data.validation.counts).map(
                    ([name, count]) => (
                      <TableRow key={name}>
                        <TableCell>
                          {TABLE_NAMES[name] ?? name}
                          <small className="table-subline">{name}</small>
                        </TableCell>
                        <TableCell>{number(count)}</TableCell>
                      </TableRow>
                    ),
                  )}
                </TableBody>
              </Table>
            </section>
          </div>
          <section className="storage-panel">
            <h2>口径、权限与数据分别存在哪里</h2>
            <div>
              {Object.entries(data.storage).map(([k, v]) => (
                <p key={k}>
                  <Database size={17} />
                  {v}
                </p>
              ))}
            </div>
            <p className="note">{data.boundaries.join('；')}。</p>
          </section>
          <section className="chart-panel">
            <div className="panel-heading">
              <h2>当前身份的查询审计</h2>
              <span className="muted">最近 30 次</span>
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>时间</TableHead>
                  <TableHead>操作</TableHead>
                  <TableHead>指标</TableHead>
                  <TableHead>结果</TableHead>
                  <TableHead>耗时</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.audit.map((e, i) => (
                  <TableRow key={i}>
                    <TableCell>
                      {new Date(e.created_at).toLocaleTimeString('zh-CN')}
                    </TableCell>
                    <TableCell>{e.action}</TableCell>
                    <TableCell>{e.metric_id ?? '—'}</TableCell>
                    <TableCell>
                      <span
                        className={
                          e.outcome === 'allowed' ? 'allowed' : 'muted'
                        }
                      >
                        {e.outcome === 'allowed'
                          ? '已允许'
                          : e.outcome === 'denied'
                            ? '已拒绝'
                            : e.outcome}
                      </span>
                    </TableCell>
                    <TableCell>{number(e.duration_ms)} ms</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </section>
        </>
      )}
    </>
  );
}
