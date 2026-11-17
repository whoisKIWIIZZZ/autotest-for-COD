"use strict";

const $ = (selector) => document.querySelector(selector);
const tokenKey = "scpu-dashboard-token";
const pageSize = 50;
const statusNames = {
  queued: "排队中",
  running: "评测中",
  accepted: "全部通过",
  wrong_answer: "未通过",
  compile_error: "编译错误",
  time_limit: "评测超时",
  judge_error: "评测环境错误",
  interrupted: "已中断",
};
const state = {
  token: "",
  generation: 0,
  controller: null,
  offset: 0,
  total: 0,
  listPending: false,
  selectedId: null,
  detail: null,
  logOffset: 0,
  logComplete: false,
  logText: "",
  logTrimmed: false,
  timer: null,
  busy: false,
  detailRevision: 0,
  artifactsLoaded: false,
};

function node(tag, text, className) {
  const result = document.createElement(tag);
  if (text !== undefined && text !== null) result.textContent = String(text);
  if (className) result.className = className;
  return result;
}

function showError(text = "") {
  $("#dashboard-error").textContent = text;
  $("#dashboard-error").hidden = !text;
}

function bytes(value) {
  if (!Number.isFinite(value)) return "—";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KiB`;
  return `${(value / (1024 * 1024)).toFixed(2)} MiB`;
}

function date(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString("zh-CN", { hour12: false });
}

function logout(message = "", abortController = true) {
  state.generation += 1;
  if (abortController) state.controller?.abort();
  clearTimeout(state.timer);
  state.token = "";
  state.controller = null;
  state.offset = 0;
  state.total = 0;
  state.listPending = false;
  state.selectedId = null;
  state.detail = null;
  state.busy = false;
  state.detailRevision += 1;
  try {
    sessionStorage.removeItem(tokenKey);
  } catch {
    // 浏览器禁止本地存储时只在内存中保存 token。
  }
  $("#dashboard-token").value = "";
  $("#runs-body").replaceChildren();
  $("#dashboard-content").hidden = true;
  $("#login-form").hidden = false;
  $("#login-button").disabled = false;
  showError(message);
}

async function api(path, generation) {
  const response = await fetch(path, {
    headers: { Authorization: `Bearer ${state.token}` },
    credentials: "omit",
    signal: state.controller.signal,
    cache: "no-store",
  });
  if (generation !== state.generation) return null;
  if (response.status === 401) {
    logout("后台 token 无效或已变更，请重新输入。", false);
    return null;
  }
  let data = {};
  const content = await response.text();
  if (content) {
    try {
      data = JSON.parse(content);
    } catch {
      throw new Error(`后台返回了无法读取的响应（HTTP ${response.status}）。`);
    }
  }
  if (generation !== state.generation) return null;
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "读取后台数据失败。");
  return data;
}

function renderStats(stats) {
  const target = $("#stats-cards");
  target.replaceChildren();
  const cards = [
    ["运行总数", stats.total],
    ["RTL 正式提交", stats.formal_runs],
    ["EDF 调试提交", stats.debug_runs],
    ["正式通过", stats.formal_accepted_runs],
    ["调试通过", stats.debug_accepted_runs],
    ["等待或运行中", stats.pending_runs],
    ["学生数", stats.students],
    ["平均评测耗时", Number.isFinite(stats.average_duration) ? `${stats.average_duration.toFixed(1)} 秒` : "—"],
  ];
  for (const [label, value] of cards) {
    const card = node("div", undefined, "card");
    card.append(node("dt", label), node("dd", value === null || value === undefined ? "—" : value));
    target.append(card);
  }
}

function renderRuns(data) {
  const target = $("#runs-body");
  target.replaceChildren();
  $("#runs-table").hidden = data.runs.length === 0;
  $("#runs-state").textContent = data.runs.length
    ? `共 ${data.total} 条运行记录，当前第 ${Math.floor(data.offset / pageSize) + 1} 页。`
    : data.total ? "本页没有记录。" : "还没有运行记录。";
  for (const run of data.runs) {
    const row = node("tr");
    row.dataset.id = String(run.id);
    if (run.id === state.selectedId) row.classList.add("selected");
    const kindCell = node("td");
    kindCell.append(node("span", run.score_label, run.is_debug ? "badge debug" : "badge"));
    const actionCell = node("td");
    const button = node("button", "查看");
    button.type = "button";
    button.addEventListener("click", () => selectRun(run.id));
    actionCell.append(button);
    const statusCell = node("td");
    statusCell.append(node("span", statusNames[run.status] || run.status, run.status === "accepted" ? "badge success" : run.state === "finished" ? "badge failure" : "badge"));
    row.append(
      node("td", `#${run.id}`),
      node("td", `${run.student_id} · ${run.student_name}`),
      kindCell,
      statusCell,
      node("td", run.score ?? "未计分"),
      node("td", Number.isFinite(run.duration_seconds) ? `${run.duration_seconds.toFixed(1)} 秒` : "—"),
      node("td", Number.isFinite(run.cycles) ? run.cycles.toLocaleString("zh-CN") : "—"),
      node("td", date(run.created_at)),
      actionCell,
    );
    target.append(row);
  }
  $("#previous").disabled = data.offset === 0;
  $("#next").disabled = data.offset + pageSize >= data.total;
  $("#page-info").textContent = `共 ${data.total} 条 · 第 ${Math.floor(data.offset / pageSize) + 1} / ${Math.max(1, Math.ceil(data.total / pageSize))} 页`;
}

function runCases(run) {
  const live = Array.isArray(run.cases) ? run.cases : [];
  const final = Array.isArray(run.result?.cases) ? run.result.cases : [];
  const ids = [...new Set([...live, ...final].map((item) => item.id))];
  return ids.map((id) => ({ ...live.find((item) => item.id === id), ...final.find((item) => item.id === id) }));
}

function renderCases(run) {
  const cases = runCases(run);
  const body = $("#detail-cases-body");
  body.replaceChildren();
  $("#detail-cases-empty").hidden = cases.length > 0;
  $("#detail-cases-table").hidden = cases.length === 0;
  for (const item of cases) {
    const row = node("tr");
    const label = node("th", `${item.label || item.id} (${item.id})`);
    label.scope = "row";
    const status = item.status || "queued";
    const statusCell = node("td");
    statusCell.append(node("span", status === "accepted" ? "通过" : statusNames[status] || status, `badge${status === "accepted" ? " success" : !["queued", "running"].includes(status) ? " failure" : ""}`));
    const word = typeof item.success_word === "string" && /^[0-9a-f]{8}$/i.test(item.success_word) ? item.success_word : null;
    const display = word && { "8c889292": "PASS", "ff88c6ff": "AC" }[word.toLowerCase()];
    const target = word ? `${display ? `${display} · ` : ""}0x${word}` : "—";
    row.append(label, statusCell, node("td", Number.isFinite(item.cycles) ? item.cycles.toLocaleString("zh-CN") : "—"), node("td", Number.isFinite(item.frames) ? item.frames.toLocaleString("zh-CN") : "—"), node("td", target), node("td", item.summary || (item.id === run.active_case ? "正在执行该程序。" : item.id === "testac-simple" ? "首次完整显示 AC 即完成，不要求动画闭环。" : "—")));
    body.append(row);
  }
  return cases;
}

function renderDetail(run) {
  state.detail = run;
  $("#run-detail").hidden = false;
  $("#detail-heading").textContent = `运行 #${run.id} · SCPU`;
  $("#detail-debug").hidden = !run.is_debug;
  $("#detail-status").textContent = statusNames[run.status] || run.status;
  $("#detail-status").className = `badge${run.status === "accepted" ? " success" : run.state === "finished" ? " failure" : ""}`;
  $("#detail-title").textContent = `${run.student_id} · ${run.student_name} · ${run.score_label} · ${date(run.created_at)}`;
  const metadata = $("#detail-metadata");
  metadata.replaceChildren();
  const items = [
    ["状态", statusNames[run.status] || run.status],
    ["分数", run.score ?? "未计分"],
    ["开始时间", date(run.started_at)],
    ["结束时间", date(run.finished_at)],
    ["评测耗时", Number.isFinite(run.duration_seconds) ? `${run.duration_seconds.toFixed(3)} 秒` : "—"],
    ["CPU 周期", Number.isFinite(run.cycles) ? run.cycles.toLocaleString("zh-CN") : "—"],
    ["实际显示帧数", Number.isFinite(run.frames) ? run.frames : "—"],
    ["归档目录", run.run_dir],
  ];
  for (const [label, value] of items) {
    const item = node("div");
    item.append(node("dt", label), node("dd", value));
    metadata.append(item);
  }
  $("#detail-summary").textContent = run.summary || "没有结果说明。";
  const cases = renderCases(run);
  FirstDiff.render($("#detail-first-diffs"), cases, { finished: run.state === "finished" });
  const groups = cases.map((item) => ({ label: item.label || item.id, checks: Array.isArray(item.checks) ? item.checks : [] }));
  if (!groups.some((group) => group.checks.length)) groups.push({ label: "整体评测", checks: Array.isArray(run.result?.checks) ? run.result.checks : [] });
  const list = $("#detail-checks");
  list.replaceChildren();
  $("#detail-checks-empty").hidden = groups.some((group) => group.checks.length);
  for (const group of groups) {
    for (const check of group.checks) {
      const item = node("li");
      const passed = check.passed === true;
      item.append(node("strong", `${group.label} · ${passed ? "通过" : check.passed === false ? "未通过" : "未判定"} · ${check.name || "检查项"}`,
                       passed ? "check-pass" : check.passed === false ? "check-fail" : ""));
      if (check.detail) item.append(node("p", check.detail));
      list.append(item);
    }
  }
  const inputs = $("#detail-inputs");
  inputs.replaceChildren();
  for (const name of Array.isArray(run.inputs) ? run.inputs : []) {
    const item = node("li");
    item.append(node("span", name, "file-name"));
    inputs.append(item);
  }
  $("#detail-json").textContent = run.result ? JSON.stringify(run.result, null, 2) : "无结果。";
  renderArtifacts(run, Array.isArray(run.artifacts) ? run.artifacts : []);
}

function renderArtifacts(run, files) {
  const target = $("#artifacts-body");
  target.replaceChildren();
  $("#artifacts-table").hidden = files.length === 0;
  $("#artifacts-state").textContent = files.length
    ? `共 ${files.length} 个归档文件，${run.state === "finished" ? "已生成完整索引。" : "评测仍在运行，结束后更新索引。"}`
    : run.state === "finished" ? "该次运行没有归档文件。" : "评测结束前文件索引可能为空。";
  for (const file of files) {
    const row = node("tr");
    row.append(node("td", file.path), node("td", bytes(file.size)), node("td", file.sha256 ? node("code", file.sha256, "hash") : "—"));
    const cell = node("td");
    const button = node("button", "下载");
    button.type = "button";
    button.addEventListener("click", () => downloadArtifact(run.id, file.path, button));
    cell.append(button);
    row.append(cell);
    target.append(row);
  }
}

async function downloadArtifact(runId, path, button) {
  const generation = state.generation;
  button.disabled = true;
  try {
    const url = `/api/dashboard/runs/${runId}/files/${path.split("/").map(encodeURIComponent).join("/")}`;
    const response = await fetch(url, {
      headers: { Authorization: `Bearer ${state.token}` },
      credentials: "omit",
      signal: state.controller.signal,
    });
    if (generation !== state.generation) return;
    if (!response.ok) throw new Error(`下载失败（HTTP ${response.status}）`);
    const blob = await response.blob();
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = path.split("/").pop() || "artifact";
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 10000);
  } catch (error) {
    if (generation === state.generation) showError(`下载 ${path} 失败：${error.message}`);
  } finally {
    if (generation === state.generation) button.disabled = false;
  }
}

async function loadList() {
  const generation = state.generation;
  const parameters = new URLSearchParams({ offset: String(state.offset), limit: String(pageSize) });
  const query = $("#filter-query").value.trim();
  if (query) parameters.set("q", query);
  for (const [element, name] of [["#filter-kind", "kind"], ["#filter-status", "status"], ["#filter-debug", "debug"]]) {
    const value = $(element).value;
    if (value !== "") parameters.set(name, value);
  }
  const data = await api(`/api/dashboard/runs?${parameters}`, generation);
  if (!data || generation !== state.generation) return null;
  state.total = data.total;
  state.listPending = data.runs.some((run) => run.state !== "finished");
  renderStats(data.stats);
  renderRuns(data);
  $("#login-form").hidden = true;
  $("#dashboard-content").hidden = false;
  showError();
  return data;
}

async function loadDetail(runId) {
  const generation = state.generation;
  const revision = ++state.detailRevision;
  const run = await api(`/api/dashboard/runs/${runId}`, generation);
  if (!run || generation !== state.generation || revision !== state.detailRevision) return;
  renderDetail(run);
  return run;
}

async function loadLog(reset = false) {
  if (state.selectedId === null) return;
  const generation = state.generation;
  const id = state.selectedId;
  if (reset) {
    state.logOffset = 0;
    state.logComplete = false;
    state.logText = "";
    state.logTrimmed = false;
    $("#detail-log").textContent = "";
  }
  if (state.logComplete) return;
  const data = await api(`/api/dashboard/runs/${id}/log?offset=${state.logOffset}&limit=65536`, generation);
  if (!data || generation !== state.generation || id !== state.selectedId) return;
  state.logOffset = data.next_offset;
  state.logComplete = data.complete === true;
  state.logText += data.text || "";
  if (state.logText.length > 1048576) {
    state.logText = state.logText.slice(-1048576);
    state.logTrimmed = true;
  }
  $("#detail-log").textContent = `${state.logTrimmed ? "【后台仅保留最近日志；完整内容请下载 logs/run.log。】\n" : ""}${state.logText}`;
  $("#log-state").textContent = `${state.logComplete ? "日志读取完成" : "持续增量读取"} · ${bytes(data.next_offset)} / ${bytes(data.size)}`;
  if ($("#follow-log").checked) $("#detail-log").scrollTop = $("#detail-log").scrollHeight;
}

function selectRun(runId) {
  if (state.selectedId === runId && state.detail) return;
  state.selectedId = runId;
  state.detail = null;
  state.detailRevision += 1;
  state.logOffset = 0;
  state.logComplete = false;
  state.logText = "";
  $("#run-detail").hidden = false;
  $("#detail-heading").textContent = `运行 #${runId}`;
  $("#detail-summary").textContent = "正在读取运行详情…";
  $("#detail-log").textContent = "";
  $("#log-state").textContent = "";
  $("#artifacts-body").replaceChildren();
  $("#artifacts-table").hidden = true;
  for (const row of $("#runs-body").children) row.classList.toggle("selected", row.dataset.id === String(runId));
  poll(true);
}

async function poll(resetLog = false) {
  if (!state.token || state.busy) return;
  clearTimeout(state.timer);
  state.busy = true;
  const generation = state.generation;
  try {
    await loadList();
    if (state.selectedId !== null) {
      await loadDetail(state.selectedId);
      await loadLog(resetLog);
    }
  } catch (error) {
    if (generation === state.generation) showError(`读取后台数据失败：${error.message} 将自动重试。`);
  } finally {
    if (generation === state.generation) {
      state.busy = false;
      $("#refresh").disabled = false;
      const detailPending = state.detail !== null && state.detail.state !== "finished";
      state.timer = setTimeout(() => poll(), state.listPending || detailPending ? 2000 : 8000);
    }
  }
}

$("#login-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const token = $("#dashboard-token").value.trim();
  if (!token) return;
  logout();
  state.token = token;
  state.controller = new AbortController();
  $("#login-button").disabled = true;
  try {
    sessionStorage.setItem(tokenKey, token);
  } catch {
    // 无法持久化时仅本次页面使用该 token。
  }
  poll(true);
});
$("#logout").addEventListener("click", () => logout());
$("#refresh").addEventListener("click", () => {
  $("#refresh").disabled = true;
  poll();
});
$("#log-refresh").addEventListener("click", () => loadLog(false).catch((error) => showError(`读取日志失败：${error.message}`)));
$("#previous").addEventListener("click", () => {
  if (state.offset === 0) return;
  state.offset = Math.max(0, state.offset - pageSize);
  poll();
});
$("#next").addEventListener("click", () => {
  if (state.offset + pageSize >= state.total) return;
  state.offset += pageSize;
  poll();
});
for (const selector of ["#filter-query", "#filter-kind", "#filter-debug", "#filter-status"]) {
  const reload = () => {
    state.offset = 0;
    poll();
  };
  $(selector).addEventListener("change", reload);
}
$("#filter-query").addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    state.offset = 0;
    poll();
  }
});

(() => {
  let token = "";
  try {
    token = sessionStorage.getItem(tokenKey) || "";
  } catch {
    token = "";
  }
  if (!token) return;
  state.token = token;
  state.controller = new AbortController();
  $("#dashboard-token").value = token;
  $("#login-button").disabled = true;
  poll(true);
})();
