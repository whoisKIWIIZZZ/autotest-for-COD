"use strict";

const $ = (selector) => document.querySelector(selector);
const receiptKey = "scpu-selected-run";
const statusNames = {
  queued: "排队中",
  running: "评测中",
  accepted: "全部通过",
  wrong_answer: "未通过",
  compile_error: "编译错误",
  time_limit: "评测超时",
  judge_error: "评测环境错误",
  interrupted: "评测已中断",
};
const state = {
  config: null,
  sending: false,
  files: [],
  selectedId: null,
  revision: 0,
  run: null,
  pollTimer: null,
  historyTimer: null,
  historyRequest: 0,
  historyOffset: 0,
  historyLimit: 25,
  historyTotal: 0,
  frames: [],
  framePosition: 0,
  framesComplete: false,
  eventsComplete: false,
  caseId: null,
  logOffset: 0,
  logComplete: false,
  logText: "",
  logTrimmed: false,
  artifactsLoaded: false,
  resultSignature: "",
  playing: false,
  playbackTimer: null,
  playbackEnd: null,
  digits: [],
};

function element(tag, text, className) {
  const result = document.createElement(tag);
  if (text !== undefined && text !== null) result.textContent = String(text);
  if (className) result.className = className;
  return result;
}

function message(selector, text = "") {
  const target = $(selector);
  target.textContent = text;
  target.hidden = !text;
}

function bytes(value) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KiB`;
  return `${(value / (1024 * 1024)).toFixed(2)} MiB`;
}

function number(value) {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toLocaleString("zh-CN", { maximumFractionDigits: 6 })
    : "—";
}

function date(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString("zh-CN", { hour12: false });
}

async function api(url, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch(url, { ...options, credentials: "same-origin", signal: controller.signal, cache: "no-store" });
    const content = await response.text();
    let data;
    try {
      data = content ? JSON.parse(content) : {};
    } catch {
      throw new Error(`服务器返回了无法读取的响应（HTTP ${response.status}）。`);
    }
    if (!response.ok) {
      let detail = typeof data.detail === "string" ? data.detail : "请求未完成，请检查提交内容或稍后重试。";
      if (Array.isArray(data.detail)) detail = data.detail.map((item) => item.msg || "字段不合法").join("；");
      const error = new Error(detail);
      error.status = response.status;
      throw error;
    }
    return data;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("请求超时，请检查网络连接。");
    if (error instanceof TypeError) throw new Error("网络连接失败。");
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

function runUrl(id, suffix = "") {
  return `/api/runs/${encodeURIComponent(id)}${suffix}`;
}

function saveSelection(id) {
  try {
    sessionStorage.setItem(receiptKey, String(id));
  } catch {
    // 浏览器不允许本地存储时，当前页面仍正常工作。
  }
}

function setSending(value) {
  state.sending = value;
  $("#submission-fields").disabled = value || !state.config;
  $("#submit-button").textContent = value ? "正在上传…" : "提交并评测";
  $("#submission-form").setAttribute("aria-busy", String(value));
}

function fileProblem() {
  if (!state.config) return "尚未读取评测配置。";
  if (!state.files.length) return "请选择要提交的文件。";
  if (state.files.length > state.config.max_files) return `最多可提交 ${state.config.max_files} 个文件。`;
  if (state.files.reduce((sum, file) => sum + file.size, 0) > state.config.max_total_bytes) return `提交文件总大小不得超过 ${bytes(state.config.max_total_bytes)}。`;
  const names = new Set();
  for (const file of state.files) {
    if (!file.name || /[\\/\x00-\x1f\x7f]/.test(file.name) || file.name === "." || file.name === "..") return "文件名不能包含路径或控制字符。";
    const key = file.name.toLowerCase();
    if (names.has(key)) return `文件名重复：${file.name}。请移除重复项。`;
    names.add(key);
    const allowed = $("#kind").value === "edf" ? /\.(edf|edif)$/i : /\.(v|sv|vh|svh)$/i;
    if (!allowed.test(file.name)) return `当前模式不接受文件 ${file.name}，请移除或切换模式。`;
  }
  if ($("#kind").value === "edf" && state.files.length !== 1) return "EDF 调试模式只接受一个独立的 .edf / .edif 文件。";
  if ($("#kind").value === "rtl" && !state.files.some((file) => /\.(v|sv)$/i.test(file.name))) return "RTL 模式至少需要一个 .v 或 .sv 编译文件。";
  return "";
}

function renderFiles() {
  const list = $("#selected-files");
  list.replaceChildren();
  state.files.forEach((file, index) => {
    const item = element("li");
    const remove = element("button", "移除");
    remove.type = "button";
    remove.setAttribute("aria-label", `移除 ${file.name}`);
    remove.addEventListener("click", () => {
      state.files.splice(index, 1);
      renderFiles();
    });
    item.append(element("span", file.name, "file-name"), element("span", bytes(file.size), "file-size"), remove);
    list.append(item);
  });
  $("#file-summary").textContent = state.files.length
    ? `已选择 ${state.files.length} 个文件，共 ${bytes(state.files.reduce((sum, file) => sum + file.size, 0))}。可继续选择以添加文件。`
    : "尚未选择文件。";
  message("#form-error", state.files.length ? fileProblem() : "");
}

function renderMode() {
  const debugging = $("#kind").value === "edf";
  $("#submission-debug").hidden = !debugging;
  $("#files").accept = debugging ? ".edf,.edif" : ".v,.sv,.vh,.svh";
  $("#mode-help").textContent = debugging
    ? "EDF 仅用于调试：提交一个包含 SCPU 的独立网表；调试成绩单独记录，不作为 RTL 正式成绩。"
    : "RTL 正式评测：提交定义 SCPU 的 .v / .sv 及其依赖文件，可附带 .vh / .svh 头文件。";
  if (state.config) $("#file-help").textContent = `最多 ${state.config.max_files} 个文件，总大小不超过 ${bytes(state.config.max_total_bytes)}。切换模式不会清空已选文件。`;
  renderFiles();
}

function metric(target, name, value) {
  const item = element("div");
  item.append(element("dt", name), element("dd", value));
  target.append(item);
}

function scoreText(run) {
  const score = run.score ?? run.result?.score;
  if (typeof score === "number") return `${number(score)} 分`;
  return run.state === "finished" ? "未计分" : "尚未评分";
}

function runCases(run = state.run) {
  const live = Array.isArray(run?.cases) ? run.cases : [];
  const final = Array.isArray(run?.result?.cases) ? run.result.cases : [];
  const ids = [...new Set([...live, ...final].map((item) => item.id))];
  return ids.map((id) => ({ ...live.find((item) => item.id === id), ...final.find((item) => item.id === id) }));
}

function selectedCase() {
  return runCases().find((item) => item.id === state.caseId) || null;
}

function caseTarget(item) {
  const word = item.success_word;
  if (typeof word !== "string" || !/^[0-9a-f]{8}$/i.test(word)) return "—";
  const display = { "8c889292": "PASS", "ff88c6ff": "AC" }[word.toLowerCase()];
  return `${display ? `${display} · ` : ""}0x${word}`;
}

function resetCaseFrames() {
  stopPlayback();
  state.frames = [];
  state.framePosition = 0;
  state.framesComplete = false;
  state.eventsComplete = false;
  state.playbackEnd = null;
  $("#follow-live").checked = true;
}

function renderCases() {
  const cases = runCases();
  if (!cases.some((item) => item.id === state.caseId)) {
    state.caseId = cases.find((item) => item.id === state.run?.active_case)?.id || cases[0]?.id || null;
    resetCaseFrames();
  }
  const selector = $("#testcase-select");
  if (JSON.stringify(Array.from(selector.options, (option) => option.value)) !== JSON.stringify(cases.map((item) => item.id))) {
    selector.replaceChildren(...cases.map((item) => {
      const option = element("option", `${item.label || item.id} (${item.id})`);
      option.value = item.id;
      return option;
    }));
  }
  selector.value = state.caseId || "";
  selector.disabled = cases.length === 0;
  $("#cases-empty").hidden = cases.length > 0;
  $("#cases-table").hidden = cases.length === 0;
  const body = $("#cases-body");
  body.replaceChildren();
  for (const item of cases) {
    const row = element("tr");
    row.classList.toggle("selected", item.id === state.caseId);
    const label = element("th", `${item.label || item.id} (${item.id})`);
    label.scope = "row";
    const status = item.status || "queued";
    const statusCell = element("td");
    statusCell.append(element("span", status === "accepted" ? "通过" : statusNames[status] || status, `badge${status === "accepted" ? " success" : !["queued", "running"].includes(status) ? " failure" : ""}`));
    row.append(label, statusCell, element("td", number(item.cycles)), element("td", number(item.frames)), element("td", caseTarget(item)), element("td", item.summary || (item.id === state.run?.active_case ? "正在执行该程序。" : "—")));
    body.append(row);
  }
  const item = selectedCase();
  $("#case-description").textContent = item
    ? `${item.label || item.id}：${item.id === "testac-simple" ? "首次完整显示 AC 即完成，不要求动画闭环。" : item.id === "testac" ? "完整动画用例，以评测器的最终判定为准。" : "程序自检后写入真实 PASS / FAIL 显示。"}${item.success_word ? `目标显示 ${caseTarget(item)}。` : ""}显示帧、周期与时间均从本程序自身开始。${item.summary || ""}`
    : "各程序的显示帧、时间与检查结果独立记录。";
  const signature = JSON.stringify([state.caseId, item, state.run?.result]);
  if (signature !== state.resultSignature) {
    state.resultSignature = signature;
    renderChecks(item);
  }
}

function renderRun(run) {
  state.run = run;
  $("#detail-empty").hidden = true;
  $("#run-detail").hidden = false;
  $("#run-status").hidden = false;
  const status = run.status || run.state;
  $("#run-status").textContent = statusNames[status] || status;
  $("#run-status").className = `badge${status === "accepted" ? " success" : run.state === "finished" ? " failure" : ""}`;
  $("#run-title").textContent = `提交 #${run.id} · SCPU`;
  $("#run-debug").hidden = !(run.is_debug || run.kind === "edf");
  $("#run-student").textContent = `学号 / 标识：${run.student_id}　姓名：${run.student_name}`;
  $("#score-label").textContent = run.score_label || (run.kind === "edf" ? "EDF 调试成绩" : "RTL 成绩");
  $("#run-score").textContent = scoreText(run);
  $("#run-summary").textContent = run.summary || run.result?.summary || (run.state === "queued" ? "等待评测器开始运行。" : run.state === "running" ? "正在执行真实编译与仿真，结果以最终判定为准。" : "没有结果说明。");
  const metadata = $("#run-metadata");
  metadata.replaceChildren();
  metric(metadata, "提交时间", date(run.created_at));
  metric(metadata, "开始时间", date(run.started_at));
  metric(metadata, "结束时间", date(run.finished_at));
  if (run.result?.cycles !== undefined) metric(metadata, "实际 CPU 周期总数", number(run.result.cycles));
  if (run.result?.duration_seconds !== undefined) metric(metadata, "评测耗时", `${number(run.result.duration_seconds)} 秒`);
  if (run.run_dir) metric(metadata, "运行归档目录", run.run_dir);
  renderCases();
  renderLoop();
  highlightHistory();
}

function renderChecks(result) {
  const target = $("#result-checks");
  target.replaceChildren();
  const checks = Array.isArray(result?.checks) ? result.checks : [];
  $("#checks-empty").hidden = checks.length > 0;
  $("#checks-empty").textContent = result && !["queued", "running"].includes(result.status) ? "评测器没有返回逐项检查记录，请查看完整结果与日志。" : "本例尚无最终检查结果。";
  for (const check of checks) {
    const item = element("li");
    const label = check.passed === true ? "通过" : check.passed === false ? "未通过" : "未判定";
    item.append(element("strong", `${label} · ${check.name || "检查项"}`, check.passed === true ? "check-pass" : check.passed === false ? "check-fail" : ""));
    if (check.detail) item.append(element("p", check.detail));
    target.append(item);
  }
  $("#checks-heading").textContent = result ? `${result.label || result.id} · 结果检查` : "结果检查";
  $("#result-extra").hidden = !state.run?.result;
  $("#result-json").textContent = state.run?.result ? JSON.stringify(state.run.result, null, 2) : "";
}

function createDisplay() {
  const namespace = "http://www.w3.org/2000/svg";
  const points = [
    "15,5 55,5 62,12 55,19 15,19 8,12",
    "57,21 64,14 71,21 71,55 64,62 57,55",
    "57,69 64,62 71,69 71,103 64,110 57,103",
    "15,105 55,105 62,112 55,119 15,119 8,112",
    "0,69 7,62 14,69 14,103 7,110 0,103",
    "0,21 7,14 14,21 14,55 7,62 0,55",
    "15,55 55,55 62,62 55,69 15,69 8,62",
  ];
  for (let byte = 3; byte >= 0; byte -= 1) {
    const svg = document.createElementNS(namespace, "svg");
    svg.setAttribute("viewBox", "-2 0 91 126");
    svg.setAttribute("aria-hidden", "true");
    svg.dataset.byte = String(byte);
    const segments = points.map((shape) => {
      const segment = document.createElementNS(namespace, "polygon");
      segment.setAttribute("points", shape);
      segment.setAttribute("class", "segment");
      svg.append(segment);
      return segment;
    });
    const dot = document.createElementNS(namespace, "circle");
    dot.setAttribute("cx", "81");
    dot.setAttribute("cy", "112");
    dot.setAttribute("r", "6");
    dot.setAttribute("class", "segment");
    svg.append(dot);
    segments.push(dot);
    state.digits.push({ byte, segments });
    $("#seven-segment").append(svg);
  }
}

function loopBounds() {
  const loop = selectedCase()?.loop || (state.caseId === "testac" ? state.run?.result?.loop : null);
  if (!loop || !Number.isInteger(loop.start_frame) || !Number.isInteger(loop.end_frame)) return null;
  const start = state.frames.findIndex((frame) => frame.index === loop.start_frame);
  const end = state.frames.findIndex((frame) => frame.index === loop.end_frame);
  return start >= 0 && end >= start ? { start, end } : null;
}

function renderLoop() {
  const loop = selectedCase()?.loop || (state.caseId === "testac" ? state.run?.result?.loop : null);
  const target = $("#loop-summary");
  target.hidden = !loop;
  target.classList.toggle("observed", Boolean(loop));
  $("#loop-replay").hidden = !loopBounds();
  if (!loop) {
    target.textContent = "";
    return;
  }
  const details = [];
  if (loop.start_frame !== undefined && loop.end_frame !== undefined) details.push(`帧索引 ${loop.start_frame} → ${loop.end_frame}`);
  if (loop.period_frames !== undefined) details.push(`周期 ${loop.period_frames} 帧`);
  if (loop.right_moves !== undefined) details.push(`右移 ${loop.right_moves} 次`);
  if (loop.blinks !== undefined) details.push(`闪烁 ${loop.blinks} 次`);
  const bounds = loopBounds();
  if (bounds) {
    const first = state.frames[bounds.start];
    const last = state.frames[bounds.end];
    if (Number.isFinite(first.cycle) && Number.isFinite(last.cycle)) details.push(`周期区间 ${number(first.cycle)} → ${number(last.cycle)}`);
    if (Number.isFinite(first.time_ns) && Number.isFinite(last.time_ns)) details.push(`仿真时间 ${number(first.time_ns)} → ${number(last.time_ns)} ns（${number((last.time_ns - first.time_ns) / 1e9)} 秒）`);
  }
  target.textContent = `评测器记录的循环：${details.length ? details.join("；") : "详见完整评测结果"}。最终是否通过以评测状态为准。`;
}

function renderFrame() {
  const frame = state.frames[state.framePosition];
  const available = Boolean(frame);
  $("#seven-segment").classList.toggle("no-frame", !available);
  $("#frames-empty").hidden = available;
  $("#frame-slider").disabled = !available;
  $("#frame-slider").max = String(Math.max(0, state.frames.length - 1));
  $("#frame-slider").value = String(state.framePosition);
  $("#play-toggle").disabled = !available;
  $("#frame-first").disabled = !available || state.framePosition === 0;
  $("#frame-previous").disabled = !available || state.framePosition === 0;
  $("#frame-next").disabled = !available || state.framePosition >= state.frames.length - 1;
  $("#play-toggle").textContent = state.playing ? "暂停" : "播放";
  $("#play-toggle").setAttribute("aria-pressed", String(state.playing));
  $("#frames-state").textContent = `${selectedCase()?.label || state.caseId || "测试程序"} · ${state.frames.length} 个实际帧 · ${state.framesComplete ? "本例记录结束" : "持续读取"}`;
  const wordValid = available && typeof frame.word === "string" && /^[0-9a-f]{8}$/i.test(frame.word);
  const word = wordValid ? Number.parseInt(frame.word, 16) >>> 0 : null;
  for (const digit of state.digits) {
    const value = word === null ? 255 : (word >>> (digit.byte * 8)) & 255;
    digit.segments.forEach((segment, bit) => segment.classList.toggle("on", (value & (1 << bit)) === 0));
  }
  $("#seven-segment").setAttribute("aria-label", wordValid ? `实际显示字 0x${frame.word}，从左到右为字节 3、2、1、0，低电平点亮。` : "尚无有效实际显示字");
  const bounds = loopBounds();
  const inside = available && bounds && state.framePosition >= bounds.start && state.framePosition <= bounds.end;
  $("#frame-number").textContent = available ? `${state.framePosition + 1} / ${state.frames.length}（索引 ${frame.index}）${inside ? " · 循环区间" : ""}` : "—";
  $("#frame-cycle").textContent = available ? number(frame.cycle) : "—";
  $("#frame-time").textContent = available && Number.isFinite(frame.time_ns) ? `${number(frame.time_ns)} ns / ${number(frame.time_ns / 1e9)} s` : "—";
  $("#frame-word").textContent = wordValid ? `0x${frame.word}` : "—";
  $("#frame-pc").textContent = available && frame.pc ? `0x${frame.pc}` : "—";
  $("#frame-phase").textContent = available ? ({ selftest: "启动自检", animation: "显示动画" }[frame.phase] || frame.phase || "未标记") : "—";
}

function stopPlayback() {
  clearTimeout(state.playbackTimer);
  state.playbackTimer = null;
  state.playing = false;
}

function schedulePlayback() {
  clearTimeout(state.playbackTimer);
  state.playbackTimer = null;
  if (!state.playing) return;
  const end = state.playbackEnd ?? state.frames.length - 1;
  if (state.framePosition >= end) {
    if (state.playbackEnd !== null || state.framesComplete) {
      stopPlayback();
      renderFrame();
    }
    return;
  }
  const current = state.frames[state.framePosition];
  const next = state.frames[state.framePosition + 1];
  const gap = Math.max(0, next.time_ns - current.time_ns) / 1e6 / Number($("#play-speed").value);
  // 每个实际帧都展示一次；短于刷新间隔的写入不被合并或删除。
  const delay = Math.max(16, Number.isFinite(gap) ? gap : 16);
  state.playbackTimer = setTimeout(() => {
    state.playbackTimer = null;
    if (!state.playing) return;
    state.framePosition += 1;
    renderFrame();
    schedulePlayback();
  }, Math.min(delay, 2147483647));
}

function seekFrame(position) {
  stopPlayback();
  state.playbackEnd = null;
  $("#follow-live").checked = false;
  state.framePosition = Math.max(0, Math.min(position, state.frames.length - 1));
  renderFrame();
}

function receiveFrames(data) {
  if (state.run && Array.isArray(data.cases)) {
    state.run.cases = data.cases;
    state.run.active_case = data.active_case;
    renderCases();
  }
  state.eventsComplete = data.complete === true;
  if (data.case_id !== state.caseId) return;
  state.frames = Array.isArray(data.frames) ? data.frames : [];
  state.framesComplete = data.case_complete === true;
  if ($("#follow-live").checked && !state.playing) state.framePosition = Math.max(0, state.frames.length - 1);
  else state.framePosition = Math.min(state.framePosition, Math.max(0, state.frames.length - 1));
  renderLoop();
  renderFrame();
  if (state.playing && state.playbackTimer === null) schedulePlayback();
}

function receiveLog(data) {
  state.logOffset = data.next_offset;
  state.logComplete = data.complete === true;
  state.logText += data.text || "";
  const maxCharacters = 524288;
  if (state.logText.length > maxCharacters) {
    state.logText = state.logText.slice(-maxCharacters);
    state.logTrimmed = true;
  }
  $("#run-log").textContent = `${state.logTrimmed ? "【页面仅保留最近日志；全部内容可在运行文件中下载 logs/run.log。】\n" : ""}${state.logText}`;
  $("#log-state").textContent = `${state.logComplete ? "日志读取完成" : "持续增量读取日志"} · 已读取 ${bytes(state.logOffset)}${!state.logText ? " · 暂无输出" : ""}`;
  if ($("#follow-log").checked) $("#run-log").scrollTop = $("#run-log").scrollHeight;
}

function renderArtifacts(data) {
  const files = Array.isArray(data.files) ? data.files : [];
  const target = $("#artifacts-body");
  target.replaceChildren();
  for (const file of files) {
    const row = element("tr");
    const pathCell = element("td");
    let url = null;
    try {
      const candidate = new URL(file.url, location.origin);
      if (candidate.origin === location.origin && candidate.pathname.startsWith(`${runUrl(state.selectedId)}/files/`)) url = candidate.href;
    } catch {
      // 无效下载链接只显示文件名，不执行任何外部协议。
    }
    if (url) {
      const link = element("a", file.path);
      link.href = url;
      link.download = "";
      pathCell.append(link);
    } else pathCell.append(element("span", file.path));
    const hashCell = element("td");
    hashCell.append(element("code", file.sha256 || "—", "hash"));
    row.append(pathCell, element("td", bytes(file.size)), hashCell);
    target.append(row);
  }
  $("#artifacts-table").hidden = files.length === 0;
  $("#artifacts-state").textContent = files.length ? `共 ${files.length} 个归档文件，点击文件路径下载。${state.run?.state !== "finished" ? "评测仍在运行，结束后将更新完整索引。" : ""}` : state.run?.state === "finished" ? "文件索引为空。" : "评测仍在运行；结束后将生成完整文件索引。";
  state.artifactsLoaded = state.run?.state === "finished";
}

async function refreshArtifacts() {
  if (state.selectedId === null) return;
  const revision = state.revision;
  $("#artifacts-refresh").disabled = true;
  try {
    const data = await api(runUrl(state.selectedId, "/artifacts"));
    if (revision === state.revision) renderArtifacts(data);
  } catch (error) {
    if (revision === state.revision) $("#artifacts-state").textContent = `读取文件失败：${error.message} 可点击刷新文件重试。`;
  } finally {
    if (revision === state.revision) $("#artifacts-refresh").disabled = false;
  }
}

async function pollRun(id, revision) {
  if (revision !== state.revision) return;
  const tasks = [
    ["状态", () => api(runUrl(id)), renderRun],
    ["显示帧", () => api(runUrl(id, `/events${state.caseId ? `?case_id=${encodeURIComponent(state.caseId)}` : ""}`)), receiveFrames],
  ];
  if (!state.logComplete) tasks.push(["日志", () => api(runUrl(id, `/log?offset=${state.logOffset}&limit=65536`)), receiveLog]);
  if (state.run?.state === "finished" && !state.artifactsLoaded) tasks.push(["文件索引", () => api(runUrl(id, "/artifacts")), renderArtifacts]);
  const results = await Promise.allSettled(tasks.map((task) => task[1]()));
  if (revision !== state.revision) return;
  const errors = [];
  let inaccessible = false;
  results.forEach((result, index) => {
    if (result.status === "fulfilled") tasks[index][2](result.value);
    else {
      errors.push(`${tasks[index][0]}：${result.reason.message}`);
      if (index === 0 && [403, 404].includes(result.reason.status)) inaccessible = true;
    }
  });
  message("#detail-error", errors.length ? `${errors.join("；")}${inaccessible ? "。当前浏览器无权查看此记录，请选择其他记录。" : " 正在自动重试，已有内容与已选文件不会清空。"}` : "");
  const complete = state.run?.state === "finished" && state.eventsComplete && state.framesComplete && state.logComplete && state.artifactsLoaded;
  if (!inaccessible && (!complete || errors.length)) {
    state.pollTimer = setTimeout(() => pollRun(id, revision), errors.length ? 4000 : 1200);
  }
}

function selectRun(id, initialRun = null) {
  if (String(state.selectedId) === String(id) && state.run) return;
  clearTimeout(state.pollTimer);
  stopPlayback();
  state.revision += 1;
  state.selectedId = id;
  state.run = null;
  state.caseId = null;
  resetCaseFrames();
  state.logOffset = 0;
  state.logComplete = false;
  state.logText = "";
  state.logTrimmed = false;
  state.artifactsLoaded = false;
  state.resultSignature = "";
  state.playbackEnd = null;
  $("#follow-live").checked = true;
  $("#run-log").textContent = "";
  $("#log-state").textContent = "正在读取日志…";
  $("#artifacts-body").replaceChildren();
  $("#artifacts-table").hidden = true;
  $("#artifacts-refresh").disabled = false;
  $("#artifacts-state").textContent = "运行结束后生成完整文件索引，也可手动刷新。";
  $("#run-detail").hidden = !initialRun;
  $("#detail-empty").hidden = Boolean(initialRun);
  $("#detail-empty").textContent = "正在读取所选记录…";
  $("#run-status").hidden = true;
  renderCases();
  renderChecks(null);
  renderLoop();
  renderFrame();
  message("#detail-error");
  if (initialRun) renderRun(initialRun);
  saveSelection(id);
  highlightHistory();
  pollRun(id, state.revision);
}

function highlightHistory() {
  for (const row of $("#history-body").children) {
    const selected = row.dataset.id === String(state.selectedId);
    row.classList.toggle("selected", selected);
    const button = row.querySelector("button");
    button.setAttribute("aria-current", selected ? "true" : "false");
    button.textContent = `${selected ? "查看中" : "查看"} #${row.dataset.id}`;
  }
}

function renderHistory(data) {
  const runs = Array.isArray(data.runs) ? data.runs : [];
  state.historyTotal = data.total;
  const target = $("#history-body");
  target.replaceChildren();
  $("#history-empty").hidden = runs.length > 0;
  $("#history-empty").textContent = state.historyTotal ? "本页暂无记录，请返回上一页。" : "当前浏览器尚无提交记录。";
  $("#history-table").hidden = runs.length === 0;
  for (const run of runs) {
    const row = element("tr");
    row.dataset.id = String(run.id);
    const actionCell = element("td");
    const button = element("button", `查看 #${run.id}`);
    button.type = "button";
    button.addEventListener("click", () => selectRun(run.id, run));
    actionCell.append(button);
    const kindCell = element("td");
    kindCell.append(element("span", run.score_label || (run.kind === "edf" ? "EDF 调试成绩" : "RTL 成绩"), run.is_debug || run.kind === "edf" ? "badge debug" : "badge"));
    row.append(actionCell, element("td", `${run.student_id} · ${run.student_name}`), kindCell, element("td", statusNames[run.status || run.state] || run.status || run.state), element("td", scoreText(run)), element("td", date(run.created_at)));
    target.append(row);
  }
  $("#history-previous").disabled = state.historyOffset === 0;
  $("#history-next").disabled = state.historyOffset + state.historyLimit >= state.historyTotal;
  $("#history-page").textContent = `共 ${number(state.historyTotal)} 条 · 第 ${Math.floor(state.historyOffset / state.historyLimit) + 1} 页`;
  highlightHistory();
  return runs;
}

async function loadHistory(restoreSelection = false) {
  const request = ++state.historyRequest;
  try {
    const data = await api(`/api/runs?offset=${state.historyOffset}&limit=${state.historyLimit}`);
    if (request !== state.historyRequest) return;
    message("#history-error");
    const runs = renderHistory(data);
    if (restoreSelection && state.selectedId === null) {
      let receipt = null;
      try {
        receipt = sessionStorage.getItem(receiptKey);
      } catch {
        // 浏览器禁止存储时，使用历史列表的最新记录。
      }
      const previous = runs.find((run) => String(run.id) === receipt);
      if (previous) selectRun(previous.id, previous);
      else if (receipt && /^[a-zA-Z0-9_-]+$/.test(receipt)) selectRun(receipt);
      else if (runs.length) selectRun(runs[0].id, runs[0]);
    }
  } catch (error) {
    if (request === state.historyRequest) {
      message("#history-error", `读取历史记录失败：${error.message} 将自动重试，也可点击刷新记录。`);
      if (!$("#history-body").children.length) $("#history-empty").textContent = "暂时无法读取历史记录。";
    }
  }
}

async function historyLoop() {
  await loadHistory(state.selectedId === null);
  state.historyTimer = setTimeout(historyLoop, 5000);
}

$("#files").addEventListener("change", () => {
  const added = Array.from($("#files").files);
  state.files.push(...added);
  $("#files").value = "";
  renderFiles();
});
$("#kind").addEventListener("change", renderMode);
$("#submission-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (state.sending || !state.config) return;
  const studentId = $("#student-id").value.trim();
  const studentName = $("#student-name").value.trim();
  const error = !studentId || !studentName ? "请填写学号 / 标识和姓名。" : fileProblem();
  if (error) {
    message("#form-error", error);
    return;
  }
  const form = new FormData();
  form.set("student_id", studentId);
  form.set("student_name", studentName);
  form.set("kind", $("#kind").value);
  for (const file of state.files) form.append("files", file, file.name);
  message("#form-error");
  setSending(true);
  try {
    const run = await api("/api/runs", { method: "POST", body: form });
    selectRun(run.id, run);
    state.historyOffset = 0;
    loadHistory();
  } catch (failure) {
    message("#form-error", `提交失败：${failure.message} 已保留文件选择。若上传过程中断，请先查看历史记录，避免重复提交。`);
  } finally {
    setSending(false);
  }
});
$("#testcase-select").addEventListener("change", () => {
  const id = $("#testcase-select").value;
  if (id === state.caseId || !runCases().some((item) => item.id === id)) return;
  clearTimeout(state.pollTimer);
  state.revision += 1;
  state.caseId = id;
  resetCaseFrames();
  state.resultSignature = "";
  $("#artifacts-refresh").disabled = false;
  renderCases();
  renderLoop();
  renderFrame();
  message("#detail-error");
  pollRun(state.selectedId, state.revision);
});
$("#play-toggle").addEventListener("click", () => {
  if (state.playing) stopPlayback();
  else if (state.frames.length) {
    $("#follow-live").checked = false;
    state.playbackEnd = null;
    if (state.framePosition >= state.frames.length - 1) state.framePosition = 0;
    state.playing = true;
    schedulePlayback();
  }
  renderFrame();
});
$("#frame-first").addEventListener("click", () => seekFrame(0));
$("#frame-previous").addEventListener("click", () => seekFrame(state.framePosition - 1));
$("#frame-next").addEventListener("click", () => seekFrame(state.framePosition + 1));
$("#frame-slider").addEventListener("input", () => seekFrame(Number($("#frame-slider").value)));
$("#play-speed").addEventListener("change", schedulePlayback);
$("#follow-live").addEventListener("change", () => {
  if ($("#follow-live").checked) {
    stopPlayback();
    state.playbackEnd = null;
    state.framePosition = Math.max(0, state.frames.length - 1);
    renderFrame();
  }
});
$("#loop-replay").addEventListener("click", () => {
  const bounds = loopBounds();
  if (!bounds) return;
  stopPlayback();
  $("#follow-live").checked = false;
  state.framePosition = bounds.start;
  state.playbackEnd = bounds.end;
  state.playing = true;
  renderFrame();
  schedulePlayback();
});
$("#follow-log").addEventListener("change", () => {
  if ($("#follow-log").checked) $("#run-log").scrollTop = $("#run-log").scrollHeight;
});
$("#artifacts-refresh").addEventListener("click", refreshArtifacts);
$("#history-refresh").addEventListener("click", () => loadHistory(state.selectedId === null));
$("#history-previous").addEventListener("click", () => {
  state.historyOffset = Math.max(0, state.historyOffset - state.historyLimit);
  loadHistory();
});
$("#history-next").addEventListener("click", () => {
  state.historyOffset += state.historyLimit;
  loadHistory();
});

async function loadConfig() {
  $("#config-retry").disabled = true;
  try {
    const config = await api("/api/config");
    if (config.problem !== "SCPU" || !Array.isArray(config.kinds) || !config.kinds.includes("rtl") || !config.kinds.includes("edf") || !(config.max_files > 0) || !(config.max_total_bytes > 0)) throw new Error("服务器评测配置不完整。");
    if (!Array.isArray(config.cases) || !config.cases.length || config.cases.some((item) => !item.id || !item.label || !/^[0-9a-f]{8}$/i.test(item.success_word))) throw new Error("服务器未返回完整的测试程序配置。");
    state.config = config;
    $("#submission-cases").textContent = `默认依次评测：${config.cases.map((item) => `${item.label} (${item.id})，目标 ${caseTarget(item)}`).join("；")}。每例独立仿真，全部通过方可得分。`;
    message("#page-error");
    $("#config-retry").hidden = true;
    renderMode();
    setSending(state.sending);
  } catch (error) {
    message("#page-error", `加载评测配置失败：${error.message} 历史记录仍会继续读取。`);
    $("#config-retry").hidden = false;
  } finally {
    $("#config-retry").disabled = false;
  }
}

$("#config-retry").addEventListener("click", loadConfig);
createDisplay();
renderMode();
renderFrame();
loadConfig();
historyLoop();
