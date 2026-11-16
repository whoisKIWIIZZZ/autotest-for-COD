"use strict";

const $ = (selector) => document.querySelector(selector);
const refreshInterval = 30000;

function node(tag, text, className) {
  const result = document.createElement(tag);
  if (text !== undefined && text !== null) result.textContent = String(text);
  if (className) result.className = className;
  return result;
}

function date(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString("zh-CN", { hour12: false });
}

function showError(text = "") {
  $("#leader-error").textContent = text;
  $("#leader-error").hidden = !text;
}

function renderStats(stats, data) {
  const target = $("#leader-stats");
  target.replaceChildren();
  const cards = [
    ["学生数", stats.students],
    ["RTL 正式提交", stats.formal_runs],
    ["正式通过", stats.formal_accepted_runs],
    ["等待或运行中", stats.pending_runs],
    ["EDF 调试提交", data.debug_runs],
  ];
  for (const [label, value] of cards) {
    const card = node("div", undefined, "card");
    card.append(node("dt", label), node("dd", value === null || value === undefined ? "—" : value));
    target.append(card);
  }
}

function render(data) {
  const entries = Array.isArray(data.entries) ? data.entries : [];
  $("#leader-rule").textContent = data.rule || "";
  $("#leader-debug").textContent = `EDF 调试提交共 ${data.debug_runs ?? 0} 次，单独记录，不计入排名。`;
  const body = $("#leader-body");
  body.replaceChildren();
  $("#leader-table").hidden = entries.length === 0;
  $("#leader-empty").hidden = entries.length > 0;
  for (const entry of entries) {
    const row = node("tr");
    row.append(
      node("td", entry.rank, entry.rank <= 3 ? `rank rank-${entry.rank}` : "rank"),
      node("td", entry.student_id),
      node("td", entry.student_name || "—"),
      node("td", entry.best_score === null ? "未计分" : entry.best_score),
      node("td", entry.accepted_runs),
      node("td", entry.formal_runs),
      node("td", date(entry.first_accepted_at)),
      node("td", date(entry.last_finished_at)),
    );
    body.append(row);
  }
  if (data.stats) renderStats(data.stats, data);
  $("#leader-updated").textContent = `更新于 ${new Date().toLocaleTimeString("zh-CN", { hour12: false })}`;
}

async function load() {
  $("#leader-refresh").disabled = true;
  try {
    const response = await fetch("/api/leaderboard?limit=50", { cache: "no-store" });
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "读取排行榜失败。");
    render(data);
    showError();
  } catch (error) {
    showError(`读取排行榜失败：${error.message} 将自动重试，也可点击刷新。`);
  } finally {
    $("#leader-refresh").disabled = false;
  }
}

render({ entries: [], debug_runs: 0 });
load();
$("#leader-refresh").addEventListener("click", load);
setInterval(() => {
  if (!document.hidden) load();
}, refreshInterval);
