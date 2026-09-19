'use client';
/**
 * V2 关系解释与原生演示策略配置页。关系路径完全来自后端，不在浏览器递归人员表。
 * SQLite 演示模式可预览/应用策略；Superset 模式由 bootstrap 关闭 can_configure，
 * 配置入口转移到 Superset/PostgreSQL，不能把这个表单当成 Superset 角色管理器。
 */
import { useEffect, useState } from 'react';
import { request, type Bootstrap, type Policy, type Rules } from './types';
import { StaticGrid } from './grid';

type Relation = {
  person_id: string;
  employee_no: string;
  name: string;
  dept_cn_name: string;
  depth: number | null;
  reasons: { text: string; names: string[] }[];
};
type Change = {
  persona: string;
  before: number;
  after: number;
  added: string[];
  removed: string[];
};
const flags: { key: keyof Omit<Rules, 'field_groups'>; label: string }[] = [
  { key: 'reports', label: '管理线下属' },
  { key: 'hrbp', label: '本人HRBP服务' },
  { key: 'inherit_hrbp', label: '继承下属HRBP服务' },
  { key: 'details', label: '人员明细' },
  { key: 'export', label: '导出' },
];
export function Permissions({
  boot,
  onChanged,
  onError,
}: {
  boot: Bootstrap;
  onChanged: () => void;
  onError: (m: string) => void;
}) {
  const [rows, setRows] = useState<Relation[]>([]);
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [preview, setPreview] = useState<Change[] | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const c = new AbortController();
    request<{ rows: Relation[] }>(
      '/relations',
      boot.principal.csrf,
      undefined,
      c.signal,
    )
      .then((r) => setRows(r.rows))
      .catch((e) => {
        if (!c.signal.aborted) onError(e.message);
      });
    // 前端按能力隐藏编辑器；后端 policy 接口仍独立拒绝无权修改的身份。
    if (boot.principal.can_configure)
      request<Policy>('/policy', boot.principal.csrf, undefined, c.signal)
        .then(setPolicy)
        .catch((e) => {
          if (!c.signal.aborted) onError(e.message);
        });
    return () => c.abort();
  }, [boot.principal.csrf, boot.principal.can_configure, onError]);
  // 编辑会清空旧预览，要求基于最新草稿再次评估受影响人群。
  const update = (role: string, next: Rules) => {
    if (policy)
      setPolicy({ ...policy, roles: { ...policy.roles, [role]: next } });
    setPreview(null);
  };
  async function submit(apply: boolean) {
    if (!policy) return;
    setBusy(true);
    try {
      // expected_version 用于后端并发版本检查，避免覆盖其他人刚应用的权限配置。
      const r = await request<{ changes: Change[] }>(
        '/policy/' + (apply ? 'apply' : 'preview'),
        boot.principal.csrf,
        { expected_version: policy.version, roles: policy.roles },
      );
      // 应用后重新取 bootstrap，由外层指纹 key 重建页面，撤销旧结果和旧聊天上下文。
      if (apply) onChanged();
      else setPreview(r.changes);
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="d-intro">
        <h2>为什么能看到这些人</h2>
        <p>
          管理线递归与 HRBP
          服务分别计算，再取并集去重。部门主管字段当前不单独授权；以下均为待业务确认的演示规则。
        </p>
      </div>
      <div className="d-path-example">
        <strong>跨汇报线示例</strong>
        <span>王承哲 → 管理下属姜姜 → 姜姜服务王灏、冯基魁</span>
        <span>继承服务权限，不把服务人员认作管理下属。</span>
      </div>
      <StaticGrid
        columns={[
          { key: 'name', label: '姓名' },
          { key: 'employee_no', label: '工号' },
          { key: 'dept_cn_name', label: '当前部门' },
          { key: 'depth', label: '管理线层级' },
          { key: 'reason', label: '可见原因与路径' },
        ]}
        rows={rows.map((r) => ({
          ...r,
          reasons: null,
          reason: r.reasons
            .map((o) => o.text + '：' + o.names.join(' → '))
            .join('；'),
        }))}
      />
      {policy && (
        <section className="d-policy">
          <h2>权限配置 · 版本 {policy.version}</h2>
          <p className="d-muted">
            先预览受影响人数，再应用版本。配置变更后，旧权限下的历史结果会失效，追问必须重新查询。
          </p>
          <div className="d-scroll">
            <table>
              <thead>
                <tr>
                  <th>角色</th>
                  {flags.map((f) => (
                    <th key={f.key}>{f.label}</th>
                  ))}
                  <th>字段组</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(policy.roles).map(([role, r]) => (
                  <tr key={role}>
                    <td>
                      {boot.personas.find((p) => p.id === role)?.label || role}
                    </td>
                    {flags.map((f) => (
                      <td key={f.key}>
                        <input
                          aria-label={`${role} ${f.label}`}
                          type="checkbox"
                          checked={r[f.key]}
                          onChange={(e) =>
                            update(role, { ...r, [f.key]: e.target.checked })
                          }
                        />
                      </td>
                    ))}
                    <td>
                      <div className="d-checks">
                        {[
                          ['basic', '基础'],
                          ['education', '教育'],
                          ['employment', '任职'],
                          ['contract', '合同'],
                        ].map(([key, label]) => (
                          <label key={key}>
                            <input
                              type="checkbox"
                              disabled={key === 'basic'}
                              checked={r.field_groups.includes(key)}
                              onChange={() =>
                                update(role, {
                                  ...r,
                                  field_groups: r.field_groups.includes(key)
                                    ? r.field_groups.filter((x) => x !== key)
                                    : [...r.field_groups, key],
                                })
                              }
                            />
                            {label}
                          </label>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="d-actions">
            <button disabled={busy} onClick={() => submit(false)}>
              预览影响
            </button>
            <button
              className="d-primary"
              disabled={busy || !preview}
              onClick={() => submit(true)}
            >
              应用此配置
            </button>
          </div>
          {preview && (
            <div className="d-policy-preview">
              {preview.map((c) => (
                <p key={c.persona}>
                  {c.persona}：{c.before} → {c.after} 人；新增 {c.added.length}
                  ，撤回 {c.removed.length}
                </p>
              ))}
            </div>
          )}
        </section>
      )}
    </>
  );
}
