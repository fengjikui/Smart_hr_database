const $ = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const option = (value, label, selected) => `<option value="${escapeHtml(value)}" ${value === selected ? "selected" : ""}>${escapeHtml(label)}</option>`;
const capabilities = ["reports_enabled", "hrbp_enabled", "inherit_hrbp_enabled", "private_enabled", "export_enabled"];
let state, draft, lastQuery;

function notice(message, error = false) {
  $("notice").hidden = !message;
  $("notice").textContent = message;
  $("notice").className = error ? "error" : "";
}

async function api(path, body) {
  const response = await fetch(path, {method: body ? "POST" : "GET", headers: body ? {"Content-Type": "application/json", "X-Demo-Token": state.demo_token} : {}, body: body ? JSON.stringify(body) : undefined});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
  return data;
}

async function task(action, label = "正在向 OpenFGA 请求…") {
  const controls = [...document.querySelectorAll("button, input, select, textarea")];
  const disabled = controls.map((control) => control.disabled);
  controls.forEach((control) => { control.disabled = true; });
  document.body.setAttribute("aria-busy", "true");
  notice(label);
  try { await action(); }
  catch (error) { notice(error.message, true); }
  finally {
    controls.forEach((control, index) => { control.disabled = disabled[index]; });
    document.body.removeAttribute("aria-busy");
    $("export").disabled = !lastQuery?.can_export;
  }
}

function renderConfiguration() {
  $("role-rows").innerHTML = Object.entries(draft.roles).map(([key, role]) => `<tr><td><strong>${escapeHtml(role.label)}</strong><small>${escapeHtml(key)}</small></td>${capabilities.map((cap) => `<td><input type="checkbox" data-role="${escapeHtml(key)}" data-capability="${cap}" aria-label="${escapeHtml(role.label)} ${cap}" ${role[cap] ? "checked" : ""}></td>`).join("")}</tr>`).join("");
  $("job-mappings").innerHTML = Object.entries(draft.job_roles).map(([job, role]) => `<label>${escapeHtml(job)}<select data-job="${escapeHtml(job)}" aria-label="岗位 ${escapeHtml(job)} 的角色">${Object.entries(draft.roles).map(([key, value]) => option(key, value.label, role)).join("")}</select></label>`).join("");
  $("people-rows").innerHTML = draft.people.map((person) => {
    const relations = (field) => option("", "无", person[field] || "") + draft.people.filter((p) => p.person_id !== person.person_id).map((p) => option(p.person_id, `${p.person_id} · ${p.name}`, person[field])).join("");
    return `<tr><td><strong>${escapeHtml(person.person_id)}</strong><small>${escapeHtml(person.name)}</small></td><td><input data-person="${escapeHtml(person.person_id)}" data-field="department" value="${escapeHtml(person.department)}" aria-label="${escapeHtml(person.person_id)} 部门" maxlength="60"></td><td><select data-person="${escapeHtml(person.person_id)}" data-field="job" aria-label="${escapeHtml(person.person_id)} 岗位">${Object.keys(draft.job_roles).map((job) => option(job, `${draft.roles[draft.job_roles[job]].label} (${job})`, person.job)).join("")}</select></td><td><select data-person="${escapeHtml(person.person_id)}" data-field="head_person_id" aria-label="${escapeHtml(person.person_id)} 直属主管">${relations("head_person_id")}</select></td><td><select data-person="${escapeHtml(person.person_id)}" data-field="dept_hrbp_id" aria-label="${escapeHtml(person.person_id)} HRBP">${relations("dept_hrbp_id")}</select></td><td><input type="checkbox" data-person="${escapeHtml(person.person_id)}" data-field="active" aria-label="${escapeHtml(person.person_id)} 在职" ${person.active ? "checked" : ""}></td></tr>`;
  }).join("");
}

async function loadState() {
  const selected = $("viewer").value || "D";
  const target = $("target").value || "G";
  state = await api("/api/state");
  draft = structuredClone(state.config);
  $("version").textContent = `配置 v${state.version}`;
  $("model").value = state.model_source;
  $("viewer").innerHTML = state.config.people.map((p) => option(p.person_id, `${p.person_id} · ${p.name}${p.active ? "" : "（离职）"}`, selected)).join("") + option("UNMAPPED", "未映射身份（拒绝）", selected);
  $("target").innerHTML = state.config.people.map((p) => option(p.person_id, `${p.person_id} · ${p.name}`, target)).join("");
  $("department").innerHTML = option("", "全部授权部门", "") + [...new Set(state.config.people.map((p) => p.department))].map((value) => option(value, value)).join("");
  $("engine-state").textContent = JSON.stringify({engine_version: state.engine_version, store_id: state.store_id, model_id: state.model_id, model: state.model_json}, null, 2);
  $("tuples").textContent = JSON.stringify(state.tuples, null, 2);
  $("history").innerHTML = state.history.map((item) => `<div class="history-row"><span><strong>v${item.version}</strong> ${escapeHtml(item.reason)}<small>${escapeHtml(new Date(item.published_at).toLocaleString())}</small></span><button data-rollback="${item.version}" ${item.version === state.version ? "disabled" : ""}>恢复此配置</button></div>`).join("");
  renderConfiguration();
  $("check-result").textContent = "尚未核验";
}

async function query() {
  lastQuery = undefined;
  $("roster-rows").replaceChildren();
  $("roster-trace").textContent = "";
  $("scope").textContent = "正在请求完整授权判断；失败时不会显示旧名单。";
  try {
    const parameters = new URLSearchParams({user: $("viewer").value, department: $("department").value});
    lastQuery = await api(`/api/roster?${parameters}`);
    $("scope").textContent = `授权范围 ${lastQuery.visible_total} 人 · 当前筛选 ${lastQuery.matched_total} 人 · 配置 v${lastQuery.version}`;
    $("roster-rows").innerHTML = lastQuery.rows.length ? lastQuery.rows.map((p) => `<tr><td><strong>${escapeHtml(p.person_id)} · ${escapeHtml(p.name)}</strong>${p.active ? "" : "<small>已离职记录</small>"}</td><td>${escapeHtml(p.department)}</td><td>${escapeHtml(p.education)}<small>${escapeHtml(p.school)}</small></td><td>${p.salary === null ? '<span class="muted">未获授权</span>' : escapeHtml(p.salary.toLocaleString())}</td><td>${p.sources.map((label) => `<span class="tag">${escapeHtml(label)}</span>`).join("")}</td></tr>`).join("") : '<tr><td colspan="5" class="empty">没有可见的匹配员工。权限由 OpenFGA 实际判断。</td></tr>';
    $("roster-trace").textContent = JSON.stringify(lastQuery.trace, null, 2);
    $("health").textContent = `OpenFGA ${state.engine_version} · 查询成功`;
    $("export").disabled = !lastQuery.can_export;
  } catch (error) {
    $("scope").textContent = "查询未完成，未返回名单或人数。";
    $("health").textContent = "权限查询失败";
    throw error;
  }
}

async function publish() {
  await api("/api/publish", {config: draft, model_source: $("model").value, expected_version: state.version});
  await loadState();
  await query();
  notice(`配置 v${state.version} 已由 OpenFGA 接受并启用。名单已按新配置刷新。`);
}

document.querySelectorAll("[data-tab]").forEach((button) => button.addEventListener("click", () => {
  document.querySelectorAll(".tab").forEach((section) => { section.hidden = section.id !== button.dataset.tab; });
  document.querySelectorAll("[data-tab]").forEach((item) => item.removeAttribute("aria-current"));
  button.setAttribute("aria-current", "page");
  $("page-title").textContent = button.textContent;
}));

$("configure").addEventListener("change", (event) => {
  const input = event.target;
  if (input.dataset.role) draft.roles[input.dataset.role][input.dataset.capability] = input.checked;
  if (input.dataset.job) draft.job_roles[input.dataset.job] = input.value;
  if (input.dataset.person) {
    const person = draft.people.find((p) => p.person_id === input.dataset.person);
    const field = input.dataset.field;
    person[field] = field === "active" ? input.checked : (field.endsWith("_id") ? input.value || null : input.value);
  }
  notice("存在尚未发布的配置。点击“校验并发布配置”后生效。");
});
$("add-person").addEventListener("submit", (event) => {
  event.preventDefault();
  const values = new FormData(event.target);
  const person_id = values.get("person_id").trim();
  if (draft.people.some((p) => p.person_id === person_id) || draft.people.length >= 50) return notice("ID 不能重复，且演示最多 50 人。", true);
  draft.people.push({person_id, name: values.get("name").trim(), department: "待分配部门", head_person_id: null, dept_hrbp_id: null, education: "本科", school: "模拟学校", job: "employee", active: true, salary: 10000});
  renderConfiguration();
  event.target.reset();
  notice("新员工已加入待发布配置，请设置关系后发布。");
});
document.querySelectorAll(".publish").forEach((button) => button.addEventListener("click", () => task(publish, "官方模型校验与全样本执行检查中…")));
$("reset").addEventListener("click", () => task(async () => {await api("/api/reset", {expected_version: state.version}); await loadState(); await query(); notice("已恢复初始合成样本。");}, "正在恢复样本…"));
$("history").addEventListener("click", (event) => {
  const version = event.target.dataset.rollback;
  if (version) void task(async () => {await api("/api/rollback", {version: Number(version), expected_version: state.version}); await loadState(); await query(); notice(`已恢复旧配置并发布为 v${state.version}。`);});
});
for (const id of ["viewer", "department"]) $(id).addEventListener("change", () => task(async () => {$("check-result").textContent = "尚未核验"; await query(); notice("");}));
$("refresh").addEventListener("click", () => task(async () => {await query(); notice("");}));
$("check").addEventListener("click", () => task(async () => {
  $("check-result").textContent = "正在核验…";
  try {
    const result = await api(`/api/check?${new URLSearchParams({user: $("viewer").value, target: $("target").value, relation: $("action").value})}`);
    $("check-result").textContent = `${result.allowed ? "允许" : "拒绝"} · ${$("viewer").value} → ${$("target").value} · ${$("action").selectedOptions[0].textContent} · 配置 v${result.version}`;
    $("roster-trace").textContent = JSON.stringify(result, null, 2);
    notice("核验完成，展开下方真实请求与响应可查看引擎结果。");
  } catch (error) {$("check-result").textContent = "核验失败，未作出允许判断。"; throw error;}
}));
for (const [id, relation] of [["direct", "direct_manager"], ["recursive", "management_chain"]]) $(id).addEventListener("click", () => {
  const source = $("model").value;
  const pattern = /define report_grant: (management_chain|direct_manager) and reports_capability/;
  if (!pattern.test(source)) return notice("模型已自定义，请直接编辑 report_grant 后发布。", true);
  $("model").value = source.replace(pattern, `define report_grant: ${relation} and reports_capability`);
  notice("模型已修改，发布后生效。management_chain 的递归由 OpenFGA 执行。");
});
$("model").addEventListener("input", () => notice("模型存在尚未发布的修改。"));
$("download").addEventListener("click", () => {
  const blob = new Blob([JSON.stringify({config: state.config, model_source: state.model_source, version: state.version}, null, 2)], {type: "application/json"});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a"); link.href = url; link.download = `hr-fga-v${state.version}.json`; link.click(); URL.revokeObjectURL(url);
});
$("export").addEventListener("click", () => task(async () => {
  const response = await fetch(`/api/export?${new URLSearchParams({user: $("viewer").value, department: $("department").value})}`);
  if (!response.ok) throw new Error((await response.json()).detail);
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a"); link.href = url; link.download = "synthetic-roster.csv"; link.click(); URL.revokeObjectURL(url);
  notice("已在服务器重新校验当前权限后导出。");
}));

void task(async () => {await loadState(); await query(); notice("");}, "正在连接本机 OpenFGA…");
