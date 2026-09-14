'use client';
import { useState } from 'react';
import { Plus, X, Play } from 'lucide-react';
import type { Bootstrap, Filter, Plan } from './types';

export function PlanBuilder({
  value,
  onChange,
  onRun,
  catalog,
  busy,
}: {
  value: Plan;
  onChange: (p: Plan) => void;
  onRun: () => void;
  catalog: Bootstrap['catalog'];
  busy: boolean;
}) {
  const [field, setField] = useState('school_name');
  const [op, setOp] = useState<Filter['op']>('eq');
  const [text, setText] = useState('');
  const patch = (p: Partial<Plan>) => onChange({ ...value, ...p, page: 1 });
  const toggle = (
    key: 'departments' | 'columns' | 'metrics' | 'group_by',
    v: string,
  ) =>
    patch({
      [key]: value[key].includes(v)
        ? value[key].filter((x) => x !== v)
        : [...value[key], v],
    });
  const name = (f: string) =>
    catalog.fields.find((x) => x.key === f)?.label || f;
  return (
    <section className="d-builder" aria-label="查询条件编辑器">
      <div className="d-control-row">
        <label>
          查询方式
          <select
            value={value.kind}
            onChange={(e) =>
              patch(
                e.target.value === 'people'
                  ? { kind: 'people', group_by: [], order_by: [] }
                  : {
                      kind: 'aggregate',
                      group_by: ['dept_cn_name'],
                      order_by: [],
                    },
              )
            }
          >
            <option value="people">人员明细</option>
            <option value="aggregate">分组统计</option>
          </select>
        </label>
        <label>
          人员范围
          <select
            value={value.scope}
            onChange={(e) => patch({ scope: e.target.value })}
          >
            <option value="all">全部授权范围</option>
            <option value="reports">直属与间接下属</option>
            <option value="direct">直属下属</option>
            <option value="indirect">间接下属</option>
            <option value="hrbp">本人 HRBP 服务</option>
            <option value="inherited_hrbp">下属 HRBP 服务</option>
            <option value="self">本人</option>
          </select>
        </label>
        <label>
          人员状态
          <select
            value={value.population}
            onChange={(e) => patch({ population: e.target.value })}
          >
            <option value="active">当前在职</option>
            <option value="all">全部状态（含离职）</option>
            <option value="confirmed">实际已转正</option>
          </select>
        </label>
        <button className="d-primary" onClick={onRun} disabled={busy}>
          <Play size={15} />
          应用条件
        </button>
      </div>
      <div className="d-control-row">
        <label>
          期间依据
          <select
            value={value.date_field || ''}
            onChange={(e) =>
              patch({
                date_field: e.target.value || null,
                start_date: e.target.value
                  ? value.start_date || '2026-01-01'
                  : null,
                end_date: e.target.value
                  ? value.end_date || catalog.as_of
                  : null,
              })
            }
          >
            <option value="">不限制日期</option>
            {catalog.fields
              .filter((f) =>
                [
                  'onboard_date',
                  'termin_date',
                  'contract_end_date',
                  'confirmation_date',
                  'current_employment_start_date',
                ].includes(f.key),
              )
              .map((f) => (
                <option key={f.key} value={f.key}>
                  {f.label}
                </option>
              ))}
            <option value="employment_events">入职与离职组合</option>
          </select>
        </label>
        {value.date_field && (
          <>
            <label>
              开始日期
              <input
                type="date"
                value={value.start_date || ''}
                onChange={(e) => patch({ start_date: e.target.value })}
              />
            </label>
            <label>
              结束日期
              <input
                type="date"
                value={value.end_date || ''}
                onChange={(e) => patch({ end_date: e.target.value })}
              />
            </label>
          </>
        )}
      </div>
      <details>
        <summary>
          部门 ·{' '}
          {value.departments.length
            ? value.departments.join('、')
            : '全部授权部门'}
        </summary>
        <div className="d-checks">
          {catalog.departments.map((d) => (
            <label key={d}>
              <input
                type="checkbox"
                checked={value.departments.includes(d)}
                onChange={() => toggle('departments', d)}
              />
              {d}
            </label>
          ))}
        </div>
      </details>
      <details open>
        <summary>
          {value.kind === 'people'
            ? `显示字段 · ${value.columns.length} 项`
            : `统计维度 ${value.group_by.length}/2 · 指标 ${value.metrics.length}/5`}
        </summary>
        {value.kind === 'people' ? (
          <div className="d-checks">
            {catalog.fields.map((f) => (
              <label key={f.key}>
                <input
                  type="checkbox"
                  disabled={
                    !value.columns.includes(f.key) && value.columns.length >= 12
                  }
                  checked={value.columns.includes(f.key)}
                  onChange={() => toggle('columns', f.key)}
                />
                {f.label}
              </label>
            ))}
          </div>
        ) : (
          <>
            <div className="d-checks">
              {Object.entries(catalog.dimensions).map(([k, v]) => (
                <label key={k}>
                  <input
                    type="checkbox"
                    disabled={
                      !value.group_by.includes(k) && value.group_by.length >= 2
                    }
                    checked={value.group_by.includes(k)}
                    onChange={() => toggle('group_by', k)}
                  />
                  {v}
                </label>
              ))}
            </div>
            <div className="d-checks d-metric-choices">
              {catalog.metrics.map((m) => (
                <label key={m.key} title={m.definition}>
                  <input
                    type="checkbox"
                    disabled={
                      !value.metrics.includes(m.key) &&
                      value.metrics.length >= 5
                    }
                    checked={value.metrics.includes(m.key)}
                    onChange={() => toggle('metrics', m.key)}
                  />
                  {m.label}
                </label>
              ))}
            </div>
          </>
        )}
      </details>
      <div className="d-filter-list">
        {value.filters.map((f, i) => (
          <span className="d-filter" key={i}>
            {name(f.field)}{' '}
            {
              {
                eq: '等于',
                in: '属于',
                gte: '≥',
                lte: '≤',
                contains: '包含',
                not_null: '不为空',
              }[f.op]
            }{' '}
            {f.values.join(' 或 ')}
            <button
              aria-label={`删除${name(f.field)}筛选`}
              onClick={() =>
                patch({ filters: value.filters.filter((_, j) => j !== i) })
              }
            >
              <X size={13} />
            </button>
          </span>
        ))}
      </div>
      <form
        className="d-control-row"
        onSubmit={(e) => {
          e.preventDefault();
          if (value.filters.length >= 12) return;
          patch({
            filters: [
              ...value.filters,
              {
                field,
                op,
                values:
                  op === 'not_null'
                    ? []
                    : text
                        .split(/[，,、]/)
                        .map((x) => x.trim())
                        .filter(Boolean),
              },
            ],
          });
          setText('');
        }}
      >
        <label>
          添加筛选
          <select value={field} onChange={(e) => setField(e.target.value)}>
            {catalog.fields.map((f) => (
              <option key={f.key} value={f.key}>
                {f.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          条件
          <select
            value={op}
            onChange={(e) => setOp(e.target.value as Filter['op'])}
          >
            <option value="eq">等于</option>
            <option value="in">属于（多个值 OR）</option>
            <option value="contains">包含</option>
            <option value="gte">大于或等于</option>
            <option value="lte">小于或等于</option>
            <option value="not_null">不为空</option>
          </select>
        </label>
        {op !== 'not_null' && (
          <label className="d-grow">
            筛选值
            <input
              required
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={
                op === 'in'
                  ? '多个值用逗号分隔'
                  : '日期为 YYYY-MM-DD；学历如硕士研究生'
              }
            />
          </label>
        )}
        <button type="submit" disabled={value.filters.length >= 12}>
          <Plus size={15} />
          添加
        </button>
      </form>
      <p className="d-muted">
        条件之间为 AND；“属于”中的多个值为 OR。列头筛选会与此处条件同时生效。
      </p>
    </section>
  );
}
