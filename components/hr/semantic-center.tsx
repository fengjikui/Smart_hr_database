'use client';
import { useState } from 'react';
import { ArrowRight, Bug, Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useResource } from './client';
import { Failure, LoadingBlock } from './results';
import { JsonView } from './debug-panel';
import type { Bootstrap } from './types';

type Entry = {
  id: string;
  kind: string;
  name: string;
  status: string;
  aliases: string[];
  summary: string;
  meaning?: string;
  not_meaning?: string;
  question?: string;
  examples?: (string | number | null | { question?: string; note?: string })[];
  field_ids?: string[];
  metric_ids?: string[];
  [key: string]: unknown;
};
type Registry = {
  version: string;
  revision: string;
  documents: Entry[];
  counts: Record<string, number>;
  metric_status: { available: number; planned: number };
  storage: Record<string, string>;
  policy: string;
};
type Workflow = {
  framework: string;
  version: string;
  nodes: { id: string; label: string }[];
  edges: { source: string; target: string; conditional: boolean }[];
  limits: Record<string, number>;
  mermaid: string;
  persistence: string;
};
const KINDS = [
  ['metric', '指标口径'],
  ['field', '字段定义'],
  ['question', '问题库'],
  ['table', '数据表'],
  ['relationship', '表间关系'],
  ['workflow', '查询流程'],
];
const STATUS: Record<string, string> = {
  available: '已支持',
  planned: '待建设',
  reference_only: '仅供参考',
  clarification_or_denial: '需澄清或拦截',
};
const LABELS: Record<string, string> = {
  description: '详细说明',
  table_id: '所属表 ID',
  field_id: '字段 ID',
  data_type: '数据类型',
  unit: '单位',
  nullable: '允许空值',
  grain: '统计粒度',
  definition: '公式与计算口径',
  time_rule: '时间口径',
  inclusions: '纳入范围',
  exclusions: '排除范围',
  null_rule: '空值与分母为零',
  grouping_rule: '分组口径',
  permission_rule: '权限与保护',
  missing_requirements: '开放查询前还需完成',
  usage: '当前查询能力',
  examples_policy: '示例说明',
  relations: '字段关联',
  from_field: '源字段',
  to_field: '目标字段',
  cardinality: '关联基数',
  join_rule: '关联条件',
  fanout_warning: '关联去重约束',
  owner: '口径负责人',
  version: '版本',
  semantic_version: '语义版本',
  rationale: '问题的业务目的',
};
function textValue(value: unknown): string {
  if (typeof value === 'boolean') return value ? '是' : '否';
  if (Array.isArray(value)) return value.map(textValue).join('；');
  if (value && typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function EntryDetail({
  id,
  identity,
  onSelect,
  onAsk,
}: {
  id: string;
  identity: string;
  onSelect: (id: string) => void;
  onAsk: (question: string) => void;
}) {
  const { data, error, loading, reload } = useResource<Entry>(
    `/semantics/documents/${encodeURIComponent(id)}`,
    identity,
  );
  if (error) return <Failure message={error} retry={reload} />;
  if (loading || !data) return <LoadingBlock />;
  const questions = data.question
    ? [data.question]
    : (data.examples ?? []).flatMap((value) =>
        value !== null && typeof value === 'object' && value.question
          ? [value.question]
          : [],
      );
  const exampleValues = (data.examples ?? []).filter(
    (value) =>
      data.kind === 'field' || value === null || typeof value !== 'object',
  );
  return (
    <article
      className="schema-detail semantic-detail"
      aria-label="语义定义详情"
    >
      <div className="semantic-detail-title">
        <span className={`semantic-status ${data.status}`}>
          {STATUS[data.status] ?? data.status}
        </span>
        <code>{data.id}</code>
      </div>
      <h2>{data.name}</h2>
      {data.aliases.length ? (
        <div className="semantic-aliases">
          <strong>口语别名</strong>
          <p>{data.aliases.join('、')}</p>
        </div>
      ) : null}
      <dl className="semantic-definitions">
        <div>
          <dt>表示什么</dt>
          <dd>{data.meaning}</dd>
        </div>
        <div>
          <dt>不表示什么</dt>
          <dd>{data.not_meaning}</dd>
        </div>
        {Object.entries(LABELS)
          .filter(
            ([key]) =>
              data[key] !== undefined &&
              data[key] !== null &&
              !(Array.isArray(data[key]) && data[key].length === 0) &&
              !(key === 'description' && data.description === data.meaning),
          )
          .map(([key, label]) => (
            <div key={key}>
              <dt>{label}</dt>
              <dd>{textValue(data[key])}</dd>
            </div>
          ))}
        {exampleValues.length ? (
          <div>
            <dt>示例值</dt>
            <dd>
              {exampleValues
                .map((value) =>
                  value === null ? 'NULL（空值）' : textValue(value),
                )
                .join('、')}
            </dd>
          </div>
        ) : null}
      </dl>
      {data.field_ids?.length ? (
        <section className="semantic-related">
          <h3>依赖字段 · 点击继续查看</h3>
          <div>
            {data.field_ids.map((field) => (
              <button key={field} onClick={() => onSelect(field)}>
                <code>{field}</code>
                <ArrowRight size={12} />
              </button>
            ))}
          </div>
        </section>
      ) : null}
      {data.metric_ids?.length ? (
        <section className="semantic-related">
          <h3>对应指标</h3>
          <div>
            {data.metric_ids.map((metric) => (
              <button key={metric} onClick={() => onSelect(`metric:${metric}`)}>
                <code>{metric}</code>
                <ArrowRight size={12} />
              </button>
            ))}
          </div>
        </section>
      ) : null}
      {questions.length ? (
        <section className="semantic-examples">
          <h3>可以怎样提问</h3>
          {questions.map((question) => (
            <div key={question}>
              <p>{question}</p>
              {data.status === 'available' ? (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onAsk(question)}
                >
                  去提问 <ArrowRight size={14} />
                </Button>
              ) : (
                <span>{STATUS[data.status]}</span>
              )}
            </div>
          ))}
        </section>
      ) : null}
      <details className="schema-ddl">
        <summary>查看完整发布定义</summary>
        <JsonView label="语义文档" value={data} />
      </details>
    </article>
  );
}

function QueryWorkflow({
  identity,
  onDebug,
}: {
  identity: string;
  onDebug: () => void;
}) {
  const { data, error, loading, reload } = useResource<Workflow>(
    '/workflow',
    identity,
  );
  if (error) return <Failure message={error} retry={reload} />;
  if (loading || !data) return <LoadingBlock />;
  const labels = Object.fromEntries(data.nodes.map((n) => [n.id, n.label]));
  labels.__end__ = '结束';
  return (
    <section className="semantic-workflow">
      <div className="semantic-workflow-heading">
        <div>
          <h2>
            {data.framework} {data.version}
          </h2>
          <p>以下节点和连接来自服务端实际编译的查询图。</p>
        </div>
        <Button onClick={onDebug} variant="outline">
          <Bug size={15} />
          查看真实节点输入输出
        </Button>
      </div>
      <div className="semantic-run-info">
        <span>最多补充读取 {data.limits.metadata_expansions} 轮</span>
        <span>结构修复 {data.limits.schema_repairs} 次</span>
        <span>模型最多调用 {data.limits.model_calls} 次</span>
        <span>
          定义预算 {data.limits.disclosure_characters.toLocaleString()} 字符
        </span>
      </div>
      <ol className="semantic-flow">
        {data.nodes.map((node, i) => (
          <li key={node.id}>
            <span>{String(i + 1).padStart(2, '0')}</span>
            <div>
              <strong>{node.label}</strong>
              <code>{node.id}</code>
            </div>
            <div className="semantic-flow-next">
              <ArrowRight size={14} />
              <p>
                {data.edges
                  .filter((e) => e.source === node.id)
                  .map(
                    (edge) =>
                      `${edge.conditional ? '条件分支：' : ''}${labels[edge.target] ?? edge.target}`,
                  )
                  .join(' / ')}
              </p>
            </div>
          </li>
        ))}
      </ol>
      <p className="schema-note">
        {data.persistence} 外部追踪关闭。查询节点内保留 SQL
        编译、只读执行、结果保护、格式化与审计的独立调试记录。
      </p>
      <details className="schema-ddl">
        <summary>查看实际图的 Mermaid 定义</summary>
        <JsonView label="编译图定义" value={data.mermaid} />
      </details>
    </section>
  );
}

export function SemanticCenter({
  boot,
  onAsk,
  onDebug,
}: {
  boot: Bootstrap;
  onAsk: (question: string) => void;
  onDebug: () => void;
}) {
  const [kind, setKind] = useState('metric');
  const [draft, setDraft] = useState('');
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState('metric:education_ratio');
  const { data, error, loading, reload } = useResource<Registry>(
    `/semantics?q=${encodeURIComponent(query)}`,
    boot.principal.id,
  );
  const docs = data?.documents.filter((d) => d.kind === kind) ?? [];
  if (kind === 'question' && !query) {
    docs.sort(
      (a, b) =>
        Number(b.status === 'available') - Number(a.status === 'available'),
    );
  }
  const current = docs.find((d) => d.id === selected)?.id ?? docs[0]?.id;
  function select(id: string) {
    setSelected(id);
    setKind(
      id.startsWith('metric:')
        ? 'metric'
        : id.startsWith('table:')
          ? 'table'
          : 'field',
    );
    setDraft('');
    setQuery('');
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">SEMANTIC REGISTRY</p>
          <h1>语义知识库</h1>
          <p>把业务问题、指标口径与数据字段连起来，让每次回答都有明确依据。</p>
        </div>
      </div>
      {data ? (
        <div className="schema-summary">
          <span>
            <strong>{data.metric_status.available}</strong> 可执行指标
          </span>
          <span>
            <strong>{data.metric_status.planned}</strong> 规划指标
          </span>
          <span>
            <strong>{data.counts.field}</strong> 可查看字段
          </span>
          <span>
            <strong>{data.counts.question}</strong> 示例问题
          </span>
          <span>{data.version}</span>
        </div>
      ) : null}
      <Tabs value={kind} onValueChange={setKind}>
        <TabsList variant="line" className="semantic-tabs">
          {KINDS.map(([value, label]) => (
            <TabsTrigger key={value} value={value}>
              {label}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value={kind}>
          {kind === 'workflow' ? (
            <QueryWorkflow identity={boot.principal.id} onDebug={onDebug} />
          ) : (
            <>
              <form
                className="schema-search"
                onSubmit={(event) => {
                  event.preventDefault();
                  setQuery(draft.trim());
                }}
              >
                <Search size={16} />
                <Input
                  aria-label="搜索语义定义"
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  maxLength={120}
                  placeholder="搜索名称、口语别名、含义或完整 ID，如“硕士”“晚离岗”"
                />
                <Button type="submit" variant="outline" size="sm">
                  搜索
                </Button>
                {query ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setDraft('');
                      setQuery('');
                    }}
                  >
                    清除
                  </Button>
                ) : null}
                <span>{docs.length} 项</span>
              </form>
              {error ? (
                <Failure message={error} retry={reload} />
              ) : loading || !data ? (
                <LoadingBlock />
              ) : docs.length ? (
                <div className="schema-layout semantic-layout">
                  <nav
                    className="schema-table-list semantic-list"
                    aria-label="语义条目"
                  >
                    {docs.map((doc) => (
                      <button
                        key={doc.id}
                        onClick={() => setSelected(doc.id)}
                        className={current === doc.id ? 'selected' : ''}
                        aria-current={current === doc.id ? 'true' : undefined}
                      >
                        <span>{doc.name}</span>
                        <code>{doc.id}</code>
                        <small>{STATUS[doc.status] ?? doc.status}</small>
                      </button>
                    ))}
                  </nav>
                  {current ? (
                    <EntryDetail
                      key={current}
                      id={current}
                      identity={boot.principal.id}
                      onSelect={select}
                      onAsk={onAsk}
                    />
                  ) : null}
                </div>
              ) : (
                <div className="debug-empty">
                  <h2>没有匹配的定义</h2>
                  <p>
                    试试更短的业务词，或切换字段与指标分类。这里只显示当前身份可查看的内容。
                  </p>
                </div>
              )}
            </>
          )}
        </TabsContent>
      </Tabs>
      {data ? (
        <details className="semantic-storage">
          <summary>定义存在哪里，模型怎样读取</summary>
          <dl>
            {Object.entries(data.storage).map(([key, value]) => (
              <div key={key}>
                <dt>
                  {
                    {
                      source: '定义源',
                      published: '发布库',
                      index: '召回索引',
                      vector: '向量检索',
                    }[key]
                  }
                </dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
          <p>{data.policy}</p>
          <code title={data.revision}>
            发布指纹 SHA-256 · {data.revision.slice(0, 16)}
          </code>
        </details>
      ) : null}
    </>
  );
}
