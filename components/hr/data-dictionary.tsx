'use client';
import { useState } from 'react';
import { Database, KeyRound, Search } from 'lucide-react';
import { Input } from '@/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useResource } from './client';
import { Failure, LoadingBlock } from './results';
import { JsonView } from './debug-panel';
import type {
  Bootstrap,
  DataDictionary as Inventory,
  SchemaTable,
} from './types';

function TableDetail({ table }: { table: SchemaTable }) {
  return (
    <div className="schema-detail">
      <div className="schema-detail-heading">
        <p>
          {table.database === 'business'
            ? '业务库 hr.sqlite'
            : '应用库 app.sqlite'}
        </p>
        <h2>{table.name}</h2>
        <p>{table.description}</p>
        <span>
          {table.fields.length} 个字段 · {table.foreign_keys.length} 个外键 ·{' '}
          {table.indexes.length} 个索引
          {table.row_count !== null
            ? ` · ${table.row_count.toLocaleString('zh-CN')} 条记录`
            : ''}
        </span>
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>字段 / 类型</TableHead>
            <TableHead>约束 / 关联</TableHead>
            <TableHead>业务含义</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {table.fields.map((f) => (
            <TableRow key={f.name}>
              <TableCell>
                <code>{f.name}</code>
                <small className="schema-field-type">{f.type}</small>
              </TableCell>
              <TableCell>
                {f.primary_key_position ? (
                  <span className="schema-key">
                    <KeyRound size={12} />
                    PK {f.primary_key_position}
                  </span>
                ) : null}
                {f.not_null ? (
                  <small className="schema-field-type">NOT NULL</small>
                ) : null}
                {f.default !== null ? (
                  <small className="schema-field-type">默认 {f.default}</small>
                ) : null}
                {table.foreign_keys
                  .filter((k) => k.from === f.name)
                  .map((k, i) => (
                    <small key={i} className="schema-field-type">
                      → {k.table}.{k.to}
                    </small>
                  ))}
              </TableCell>
              <TableCell>{f.description}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <details className="schema-ddl">
        <summary>完整建表语句（包括 CHECK / UNIQUE）</summary>
        <JsonView label="CREATE TABLE" value={table.create_sql} />
      </details>
      <details className="schema-ddl">
        <summary>索引与外键详情</summary>
        <JsonView label="索引 INDEXES" value={table.indexes} />
        <JsonView label="外键 FOREIGN KEYS" value={table.foreign_keys} />
      </details>
    </div>
  );
}

export function DataDictionary({ boot }: { boot: Bootstrap }) {
  const { data, error, loading, reload } = useResource<Inventory>(
    '/data-dictionary',
    boot.principal.id,
  );
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState('business:employees');
  if (error) return <Failure message={error} retry={reload} />;
  if (loading || !data) return <LoadingBlock />;
  const term = query.trim().toLowerCase();
  const tables = data.tables.filter(
    (t) =>
      !term ||
      `${t.name} ${t.description} ${t.fields.map((f) => `${f.name} ${f.description}`).join(' ')}`
        .toLowerCase()
        .includes(term),
  );
  const table =
    tables.find((t) => `${t.database}:${t.name}` === selected) ?? tables[0];
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">DATA REFERENCE</p>
          <h1>数据库与口径</h1>
          <p>实际表结构、完整字段、指标公式和当前实现边界。</p>
        </div>
      </div>
      <div className="schema-summary">
        <span>
          <strong>{data.summary.business_tables}</strong> 业务表
        </span>
        <span>
          <strong>{data.summary.application_tables}</strong> 应用表与索引
        </span>
        <span>
          <strong>{data.summary.fields}</strong> 字段
        </span>
        <span>
          <strong>{data.summary.metrics}</strong> 指标
        </span>
        <span>数据截止 {data.dataset.as_of}</span>
      </div>
      <Tabs defaultValue="tables">
        <TabsList variant="line">
          <TabsTrigger value="tables">表与字段</TabsTrigger>
          <TabsTrigger value="metrics">指标与公式</TabsTrigger>
          <TabsTrigger value="rules">口径与存储</TabsTrigger>
        </TabsList>
        <TabsContent value="tables">
          <div className="schema-search">
            <Search size={16} />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="搜索表或字段"
              placeholder="搜索表名、字段名或中文含义"
            />
            <span>{tables.length} 张表</span>
          </div>
          <div className="schema-layout">
            <nav className="schema-table-list" aria-label="数据库表">
              {['business', 'application'].map((db) => (
                <div key={db}>
                  <h3>
                    <Database size={14} />
                    {db === 'business' ? '业务库' : '应用库'}
                  </h3>
                  {tables
                    .filter((t) => t.database === db)
                    .map((t) => (
                      <button
                        key={t.name}
                        onClick={() => setSelected(`${db}:${t.name}`)}
                        className={table?.name === t.name ? 'selected' : ''}
                      >
                        <code>{t.name}</code>
                        <small>{t.description.split('；')[0]}</small>
                      </button>
                    ))}
                </div>
              ))}
            </nav>
            {table ? (
              <TableDetail table={table} />
            ) : (
              <p className="debug-empty">没有匹配的表或字段。</p>
            )}
          </div>
        </TabsContent>
        <TabsContent value="metrics">
          <p className="schema-note">
            名称和描述来自已发布指标目录，SQL表达式从当前编译器提取。每项仅支持列明的单个分组维度；结果始终先限制到授权人员。
          </p>
          <div className="schema-metrics">
            {data.metrics.map((m) => (
              <details key={m.id}>
                <summary>
                  <span>{m.domain}</span>
                  <strong>{m.name}</strong>
                  <code>{m.id}</code>
                  <span>{m.unit}</span>
                </summary>
                <div className="schema-metric-body">
                  <p>{m.description}</p>
                  <dl>
                    <dt>分组维度</dt>
                    <dd>{Object.values(m.dimension_labels).join('、')}</dd>
                    <dt>来源表</dt>
                    <dd>{m.source.join('、')}</dd>
                    <dt>责任人与版本</dt>
                    <dd>
                      {m.owner} · v{m.version}
                    </dd>
                    <dt>分级与群体阈值</dt>
                    <dd>
                      {m.sensitivity} · 最少{m.minimum_group_size}人
                    </dd>
                    <dt>别名</dt>
                    <dd>{m.aliases.join('、')}</dd>
                  </dl>
                  <JsonView
                    label="实际聚合表达式"
                    value={m.sql_expression ?? m.example_error}
                  />
                  <details className="schema-ddl">
                    <summary>示例查询计划与编译 SQL</summary>
                    <JsonView label="示例计划" value={m.example_plan} />
                    <JsonView
                      label="编译 SQL（未执行）"
                      value={m.example_sql}
                    />
                  </details>
                </div>
              </details>
            ))}
          </div>
        </TabsContent>
        <TabsContent value="rules">
          <div className="schema-rules">
            <h2>口径约定与能力边界</h2>
            <dl>
              {data.conventions.map((c) => (
                <div key={c.name}>
                  <dt>{c.name}</dt>
                  <dd>{c.value}</dd>
                </div>
              ))}
            </dl>
            <h2>存储职责</h2>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>内容</TableHead>
                  <TableHead>位置</TableHead>
                  <TableHead>职责</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.storage.map((s) => (
                  <TableRow key={s.name}>
                    <TableCell>{s.name}</TableCell>
                    <TableCell>
                      <code>{s.location}</code>
                    </TableCell>
                    <TableCell>{s.purpose}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </TabsContent>
      </Tabs>
      <p className="schema-note">{data.note}</p>
    </>
  );
}
