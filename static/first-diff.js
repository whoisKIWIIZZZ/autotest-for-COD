"use strict";

window.FirstDiff = (() => {
  const columns = [
    ["cycle", "CPU 周期"], ["time_ns", "时间 (ns)"], ["pc", "PC"],
    ["next_pc", "next_pc"], ["instruction", "指令"], ["mem_w", "Mem W"],
    ["address", "地址"], ["dm_ctrl", "DM Ctrl"], ["store_data", "写数据"],
    ["load_data", "读数据"], ["display_word", "显示字"], ["registers", "寄存器快照"],
  ];
  const fieldNames = {
    pc: "PC", next_pc: "next_pc", instruction: "指令", mem_w: "写使能",
    address: "访存地址", dm_ctrl: "访存控制", store_data: "有效写数据",
    load_data: "读数据", display_word: "显示字", eof: "执行流结束（EOF）",
    expected_eof: "预期执行流结束（EOF）", actual_eof: "提交执行流结束（EOF）",
  };
  const registers = ["ra", "sp", "s0", "s1", "a0", "a1", "a2", "a3", "s2", "s3"];

  function node(tag, text, className) {
    const result = document.createElement(tag);
    if (text !== undefined && text !== null) result.textContent = String(text);
    if (className) result.className = className;
    return result;
  }

  function number(value) {
    return Number.isFinite(value) ? value.toLocaleString("zh-CN") : "—";
  }

  function windowRows(report, side) {
    const rows = Array.isArray(report[side]) ? report[side] : [];
    if (report.status !== "different" || !Number.isFinite(report.first_cycle)) return rows.slice(-10);
    return [
      ...rows.filter((row) => row.cycle < report.first_cycle).slice(-10),
      ...rows.filter((row) => row.cycle === report.first_cycle).slice(0, 1),
      ...rows.filter((row) => row.cycle > report.first_cycle).slice(0, 10),
    ];
  }

  function registerCell(row, side) {
    const cell = node("td", undefined, "first-diff-registers");
    if (!row.registers || typeof row.registers !== "object") {
      cell.append(node("span", side === "actual" ? "未提供内部 RF 接口" : "未记录参考寄存器", "muted"));
      return cell;
    }
    for (const name of registers) {
      if (row.registers[name] !== undefined) cell.append(node("div", `${name}=${row.registers[name]}`));
    }
    if (!cell.childNodes.length) cell.append(node("span", "无寄存器快照", "muted"));
    return cell;
  }

  function renderSide(report, side) {
    const expected = side === "expected";
    const label = expected ? "[预期行为]" : "[错误行为]";
    const rows = windowRows(report, side);
    const first = report.status === "different" && Number.isFinite(report.first_cycle) ? report.first_cycle : null;
    const eof = report[`${side}_eof`] === true;
    const section = node("section", undefined, "first-diff-side");
    section.dataset.side = side;
    section.append(node("h5", label));
    section.append(node("p", expected ? "可信 EDF 参考执行。" : "提交 CPU 实际执行。", "muted small"));
    const scroll = node("div", undefined, "table-scroll first-diff-scroll");
    scroll.tabIndex = 0;
    scroll.setAttribute("role", "region");
    scroll.setAttribute("aria-label", `${label}上下文，可横向滚动`);
    const table = node("table", undefined, "first-diff-table");
    table.append(node("caption", `${label} · ${first === null ? "已观测上下文" : "首差异前后各最多 10 个 CPU 周期"}`, "sr-only"));
    const head = node("thead");
    const header = node("tr");
    for (const [, title] of columns) {
      const cell = node("th", title);
      cell.scope = "col";
      header.append(cell);
    }
    head.append(header);
    const body = node("tbody");
    for (const row of rows) {
      const tr = node("tr");
      tr.dataset.cycle = String(row.cycle);
      if (first !== null && row.cycle === first) tr.className = "first-diff-row";
      for (const [key] of columns) {
        if (key === "registers") {
          tr.append(registerCell(row, side));
          continue;
        }
        const cell = node(key === "cycle" ? "th" : "td", key === "cycle" || key === "time_ns" ? number(row[key]) : row[key] ?? "—");
        if (key === "cycle") {
          cell.scope = "row";
          if (first !== null && row.cycle === first) cell.append(node("span", "首差异", "first-diff-marker"));
        }
        tr.append(cell);
      }
      body.append(tr);
    }
    if (first !== null && !rows.some((row) => row.cycle === first)) {
      const tr = node("tr", undefined, "first-diff-row");
      tr.dataset.cycle = String(first);
      const cell = node("td", `首差异 · CPU 周期 ${number(first)}：${eof ? "本侧执行流已结束（EOF），无该周期指令。" : "本侧没有该周期记录。"}`);
      cell.colSpan = columns.length;
      tr.append(cell);
      body.append(tr);
    } else if (!rows.length) {
      const tr = node("tr");
      const cell = node("td", "没有可用记录。", "muted");
      cell.colSpan = columns.length;
      tr.append(cell);
      body.append(tr);
    }
    table.append(head, body);
    scroll.append(table);
    section.append(scroll);
    if (first !== null) {
      const before = rows.filter((row) => row.cycle < first).length;
      const after = rows.filter((row) => row.cycle > first).length;
      section.append(node("p", `已记录前 ${before} / 10、后 ${after} / 10 个周期。${before < 10 || after < 10 ? "窗口在执行起点、终点或采集边界处不足十条。" : ""}`, "muted small first-diff-context"));
    } else {
      section.append(node("p", `展示已观测范围末尾的 ${rows.length} 个周期；没有首差异行。`, "muted small first-diff-context"));
    }
    if (eof) section.append(node("p", "本侧执行流已结束（EOF）；结束后的指令与寄存器值不可用。", "muted small first-diff-eof"));
    return section;
  }

  function renderCase(item, finished) {
    const card = node("article", undefined, "first-diff-case");
    card.dataset.caseId = String(item.id || "");
    card.append(node("h4", `${item.label || item.id || "测试程序"} · 首个可观察差异`));
    const report = item.first_diff;
    if (!report || typeof report !== "object") {
      card.dataset.status = "absent";
      const text = item.status === "accepted"
        ? "本程序已通过；没有失败诊断记录。"
        : !finished
          ? "正在等待首差异诊断。"
          : "该历史记录尚无首差异诊断。";
      card.append(node("p", text, "muted small first-diff-status"));
      return card;
    }
    card.dataset.status = report.status || "error";
    const different = report.status === "different";
    let summary;
    if (different) {
      const fields = Array.isArray(report.fields) ? report.fields : [];
      const names = fields.map((field) => fieldNames[field] ? `${fieldNames[field]} (${field})` : String(field));
      summary = `首个可观察差异：CPU 周期 ${number(report.first_cycle)}；字段：${names.length ? names.join("、") : "未提供"}。`;
    } else if (report.status === "identical_prefix") {
      summary = `截至 CPU 周期 ${number(report.compared_through_cycle)}，已比较的公开接口相同。原评测失败原因见检查项。`;
    } else if (report.status === "unavailable") {
      summary = "首差异诊断不可用；没有可用于定位首差异的硬件执行证据。";
    } else {
      summary = report.status === "error" ? "首差异诊断失败。" : "无法读取此版本的首差异诊断，原评测结果保持不变。";
    }
    card.append(node("p", summary, `first-diff-status${different ? " check-fail" : ""}`));
    if (report.reason) card.append(node("p", `诊断说明：${report.reason}`, "small first-diff-reason"));
    if (report.version !== 1) {
      card.append(node("p", "诊断格式版本不受支持，未解释执行窗口。请下载原始报告。", "muted small"));
      return card;
    }
    card.append(node("p", "按 CPU 周期比较 PC 转移、写使能、显示字及有效访存行为。参考寄存器取自 EDF 触发器；提交侧展示 SCPU 公开接口。流水线或停顿策略会影响首差位置。", "muted small first-diff-scope"));
    if (report.reference) {
      const reference = node("p", undefined, "muted small first-diff-reference");
      reference.append(node("span", `参考：${report.reference.source || "edf_file/SCPU.edf"}`));
      if (report.reference.sha256) reference.append(node("code", `SHA-256 ${report.reference.sha256}`));
      if (report.reference.cache_key) reference.append(node("code", `构建键 ${report.reference.cache_key}`));
      card.append(reference);
    }
    if (different || report.status === "identical_prefix") {
      card.append(node("p", "指令、PC 与总线值采于 CPU 上升沿前；next_pc、显示字与参考寄存器采于该上升沿后。表格可横向滚动查看全部字段。", "muted small"));
      const sides = node("div", undefined, "first-diff-sides");
      sides.append(renderSide(report, "expected"), renderSide(report, "actual"));
      card.append(sides);
    }
    card.append(node("p", "运行文件提供 first_diff.txt / first_diff.json 下载。", "muted small"));
    return card;
  }

  function render(target, cases, { finished = false } = {}) {
    target.replaceChildren();
    if (!cases.length) {
      target.append(node("p", finished ? "本记录没有测试程序首差异诊断；请查看原有评测结果与日志。" : "等待测试程序诊断。", "muted small"));
      return;
    }
    for (const item of cases) target.append(renderCase(item, finished));
  }

  return { render };
})();
