/* ============================================================
   JOB_ANALYZER · app.js
   行为:健康检查 → 流式投递分析(NDJSON) → 渲染诊断报告
   ============================================================ */
(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  // ---- 时钟 ----
  const ts = $("#ts");
  const tick = () => {
    const d = new Date();
    const p = (n) => String(n).padStart(2, "0");
    ts.textContent =
      `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ` +
      `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
  };
  tick();
  setInterval(tick, 1000);

  // ---- 服务元信息 ----
  const setMeta = (k, v) => {
    $$("#svcMeta [data-k]").forEach((el) => {
      if (el.dataset.k === k) el.textContent = v || "—";
    });
  };
  fetch("/api/v1/info")
    .then((r) => r.json())
    .then((j) => {
      if (j && j.data) {
        setMeta("provider", j.data.provider);
        setMeta("model", j.data.model);
        setMeta("version", "v" + j.data.version);
      }
    })
    .catch(() => {});

  // ---- 拖拽上传 ----
  const drop = $("#drop");
  const fileInput = $("#resume");
  const dropSub = $("#dropSub");

  const setFile = (f) => {
    if (!f) {
      drop.classList.remove("has-file");
      dropSub.textContent = "或点击此处选择文件 · 最大 20MB";
      return;
    }
    const kb = (f.size / 1024).toFixed(1);
    drop.classList.add("has-file");
    dropSub.textContent = `${f.name} · ${kb} KB · ${f.type || "binary"}`;
  };
  // 上传区包在 label 内,浏览器点击会默认激活 input[type=file];
  // 不再手动 click(),让浏览器原生走一次即可(否则某些浏览器会弹两次)。
  drop.addEventListener("click", (e) => {
    // 阻止事件冒泡,避免与任何外层 click 处理器重复触发
    e.stopPropagation();
  });
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("drag"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("drag"));
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    drop.classList.remove("drag");
    if (e.dataTransfer.files[0]) {
      fileInput.files = e.dataTransfer.files;
      setFile(fileInput.files[0]);
    }
  });
  fileInput.addEventListener("change", () => setFile(fileInput.files[0]));

  // ---- 字符计数 ----
  const jd = $("#jd");
  const jdHint = $("#jdHint");
  jd.addEventListener("input", () => {
    jdHint.textContent = `${jd.value.length} 字符 · 推荐 200-2000 字`;
  });

  // ---- 示例数据 ----
  $("#loadSample").addEventListener("click", () => {
    jd.value =
`职位:高级 Python 后端工程师 (AI Agent 方向)

岗位职责:
1. 负责面向求职者的大模型应用后端开发,基于 FastAPI / LangGraph 构建智能体工作流
2. 与算法团队协作,把简历分析、岗位匹配、面试题生成等能力落地为 API
3. 设计高并发会话存储与缓存方案,保障 SLA

任职要求:
- 3 年以上 Python 后端经验,熟悉 FastAPI、asyncio、SQLAlchemy
- 熟悉 LLM 工程化,使用过 OpenAI / DeepSeek / 通义千问 等至少一种
- 了解 LangChain / LangGraph,能设计多步 Agent 流程
- 有 Redis、Kafka、向量数据库 (Milvus / Qdrant) 实战经验
- 加分:有大模型 RAG、智能简历 / 求职产品经验

我们提供:
- 真实生产场景的智能体落地
- 与 985 高校实验室的算法合作通道
- 弹性工作制 · 14 薪 · 股票期权`;
    jd.dispatchEvent(new Event("input"));
    showToast(fileInput.files[0] ? "已载入示例 JD，当前简历保留" : "已载入示例 JD，请再选择简历文件");
  });

  // ---- Toast ----
  const toast = $("#toast");
  const showToast = (msg, isErr = false) => {
    toast.hidden = false;
    toast.classList.toggle("error", isErr);
    $(".t-msg", toast).textContent = msg;
    clearTimeout(toast._t);
    toast._t = setTimeout(() => (toast.hidden = true), 3500);
  };

  // ---- 提交(流式) ----
  const form = $("#intake");
  const runBtn = $("#runBtn");
  const empty = $("#empty");
  const report = $("#report");

  // 运行态视图元素
  const runView = $("#runView");
  const runBarFill = $("#runBarFill");
  const runTimer = $("#runTimer");
  const runMsg = $("#runMsg");
  const runStatus = $("#runStatus");
  const runError = $("#runError");
  const runErrorMsg = $("#runErrorMsg");
  const runErrorStage = $("#runErrorStage");
  const runSteps = $("#runSteps");

  let timerInterval = null;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const file = fileInput.files[0];
    if (!file) { showToast("请先选择简历文件", true); return; }
    if (!jd.value.trim()) { showToast("请粘贴岗位 JD 文本", true); return; }

    const fd = new FormData();
    fd.append("resume", file);
    fd.append("job_description", jd.value);

    // 切换到运行态
    $(".run-label", runBtn).hidden = true;
    $(".run-run", runBtn).hidden = false;
    runBtn.disabled = true;

    _showRunView();

    const t0 = performance.now();
    try {
      await streamAnalyze(fd, t0);
    } catch (err) {
      // 网络层错误:降级到同步接口重试
      console.warn("流式请求失败,尝试降级到同步接口:", err);
      try {
        const r = await fetch("/api/v1/analyze", { method: "POST", body: fd });
        const dt = ((performance.now() - t0) / 1000).toFixed(2);
        if (!r.ok) {
          let msg = `请求失败 ${r.status}`;
          try { const j = await r.json(); msg = typeof j.detail === "string" ? j.detail : j.detail?.message || msg; } catch {}
          showToast(msg, true); _hideRunView(); return;
        }
        const j = await r.json();
        renderReport(j.data, j.trace_id, dt);
        showToast(`分析完成 · 用时 ${dt}s`);
      } catch (fallbackErr) {
        showToast(fallbackErr.message || "网络错误", true);
      } finally {
        _hideRunView();
      }
    } finally {
      $(".run-label", runBtn).hidden = false;
      $(".run-run", runBtn).hidden = true;
      runBtn.disabled = false;
    }
  });

  // ---- 快捷键 Cmd/Ctrl + Enter ----
  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  // ============================================================
  // 流式分析核心
  // ============================================================

  async function streamAnalyze(fd, t0) {
    const r = await fetch("/api/v1/analyze/stream", { method: "POST", body: fd });
    if (!r.ok) {
      let msg = `流式请求失败 ${r.status}`;
      try { const j = await r.json(); msg = j.message || msg; } catch {}
      throw new Error(msg);
    }

    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buf += decoder.decode(value, { stream: true });

      // 按 \n 切割,最后一行可能不完整,保留
      const lines = buf.split("\n");
      buf = lines.pop() || "";

      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const evt = JSON.parse(line);
          dispatchEvent(evt, t0);
        } catch (_) {
          console.warn("无法解析 NDJSON 行:", line.slice(0, 120));
        }
      }
    }
  }

  function dispatchEvent(evt, t0) {
    switch (evt.type) {
      case "meta":
        // 阶段表已由 HTML 定义,这里仅记录 trace_id
        console.log("[stream] meta, trace_id:", evt.trace_id);
        break;

      case "stage_start":
        onStageStart(evt.index, evt.label || evt.key);
        break;

      case "progress":
        onProgress(evt.percent, evt.message, evt.chars);
        break;

      case "stage_end":
        onStageEnd(evt.index, evt.key);
        break;

      case "done": {
        const dt = ((performance.now() - t0) / 1000).toFixed(2);
        renderReport(evt.data, evt.data.trace_id, dt);
        showToast(`分析完成 · 用时 ${dt}s`);
        _hideRunView();
        break;
      }

      case "error":
        onError(evt.stage, evt.code, evt.message);
        break;
    }
  }

  // ---- 运行态视图控制 ----

  function _showRunView() {
    if (!runView) { console.warn("runView 元素缺失,跳过 _showRunView"); return; }
    empty.hidden = true;
    report.hidden = true;
    runView.hidden = false;
    runError.hidden = true;
    runStatus.hidden = false;

    // 重置所有步骤状态
    $$("#runSteps li").forEach((li) => {
      li.className = "";
    });
    if (runBarFill) runBarFill.style.width = "0%";
    if (runMsg) runMsg.textContent = "准备中…";

    // 启动计时器
    const start = performance.now();
    clearInterval(timerInterval);
    timerInterval = setInterval(() => {
      if (!runTimer) return;
      const s = ((performance.now() - start) / 1000).toFixed(1);
      runTimer.textContent = s + "s";
    }, 200);
  }

  function _hideRunView() {
    clearInterval(timerInterval);
    timerInterval = null;
    runView.hidden = true;
  }

  // 并行阶段分组:同组内的步骤同时运行,需要 parallel-active 样式
  const PARALLEL_GROUPS = [
    new Set([1, 2]),   // parse_resume + parse_job
    new Set([3, 4, 5]), // skill_gap + experience + keywords
  ];

  function _findParallelGroup(index) {
    return PARALLEL_GROUPS.find(g => g.has(index)) || null;
  }

  function onStageStart(index, label) {
    const steps = $$("#runSteps li");
    if (steps[index]) {
      steps[index].classList.add("active");
    }
    // 如果当前启动的是并行阶段之一,给同组其他 active 步骤加 parallel-active
    const group = _findParallelGroup(index);
    if (group) {
      for (const i of group) {
        if (i !== index && steps[i] && steps[i].classList.contains("active")) {
          steps[i].classList.add("parallel-active");
        }
      }
    }
    runMsg.textContent = label + "…";
    runError.hidden = true;
    runStatus.hidden = false;
  }

  function onProgress(percent, message, chars) {
    // 更新进度条
    runBarFill.style.width = Math.min(percent, 99.5) + "%";

    // 如果有消息,更新状态文字
    if (message) {
      runMsg.textContent = message;
    } else if (chars) {
      runMsg.textContent = `已处理 ${chars} 字符…`;
    }
  }

  function onStageEnd(index, key) {
    const steps = $$("#runSteps li");
    if (steps[index]) {
      steps[index].classList.remove("active");
      steps[index].classList.remove("parallel-active");
      steps[index].classList.add("done");
    }
    // 并行阶段:一个结束后,同组其他步骤移除 parallel-active(恢复为唯一 active)
    const group = _findParallelGroup(index);
    if (group) {
      for (const i of group) {
        if (i !== index && steps[i] && steps[i].classList.contains("parallel-active")) {
          steps[i].classList.remove("parallel-active");
          // 保持 active 状态(仍在运行)
        }
      }
    }
  }

  function onError(stage, code, message) {
    clearInterval(timerInterval);

    // 标记出错步骤为 error
    $$("#runSteps li").forEach((li) => {
      if (li.dataset.stage === stage) {
        li.classList.remove("active");
        li.classList.add("error");
      } else if (li.classList.contains("active")) {
        li.classList.remove("active");
        li.classList.add("done");
      }
    });

    runStatus.hidden = true;
    runError.hidden = false;
    runErrorMsg.textContent = message;
    runErrorStage.textContent = `[${stage}] ${code}`;

    showToast(message, true);
  }

  // ============================================================
  // 渲染报告
  // ============================================================
  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }
  function setText(sel, txt) { const n = $(sel); if (n) n.textContent = txt ?? "—"; }
  function pct(x) {
    const v = Math.max(0, Math.min(100, Number(x) || 0));
    return v.toFixed(1) + "%";
  }
  function fmtScore(x) {
    const v = Math.max(0, Math.min(100, Number(x) || 0));
    return v.toFixed(1);
  }
  function escape(s) { return String(s ?? "").replace(/[&<>"]/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c])); }

  function renderReport(data, traceId, durSec) {
    if (!data) return;
    const mr = data.match_report || {};
    const sg = mr.skill_gap || {};
    const ex = mr.experience || {};
    const kw = mr.keywords || {};
    const sug = Array.isArray(data.suggestions) ? data.suggestions : [];
    const meta = data.meta || {};

    // 报头
    setText("#r_position", "岗位匹配诊断");
    setText("#r_trace", traceId || (meta && meta.trace_id) || "—");
    setText("#r_time", new Date().toLocaleString("zh-CN", { hour12: false }));

    // 评分
    const score = Math.round(Number(mr.overall_score) || 0);
    setText("#r_score", fmtScore(mr.overall_score));
    const ring = $("#scoreRing");
    ring.setAttribute("data-score", String(score));
    const fg = $("#ringFg");
    const C = 2 * Math.PI * 52; // ≈ 326.7
    const offset = C * (1 - Math.max(0, Math.min(100, score)) / 100);
    fg.style.strokeDashoffset = String(offset);

    // 综合判定 · 摘要
    const verdict = judge(score, sg.coverage);
    $("#r_verdict").textContent = verdict;

    // 第一屏 stat grid
    const grid = $("#r_stats");
    grid.innerHTML = "";
    grid.append(
      statCell("综合分", fmtScore(mr.overall_score), scoreColor(score)),
      statCell("技能覆盖", pct(sg.coverage), covColor(sg.coverage)),
      statCell("经验匹配", pct(ex.score), covColor(ex.score)),
      statCell("关键词", pct(kw.coverage), covColor(kw.coverage)),
    );

    // 02 技能
    setText("#r_skill_cov", `coverage ${pct(sg.coverage)}`);
    setText("#r_skill_matched", (sg.matched || []).length);
    setText("#r_skill_missing", (sg.missing || []).length);
    setText("#r_skill_partial", (sg.partial || []).length);
    renderChips("#r_skill_matched_list", (sg.matched || []).map(skillName));
    renderChips("#r_skill_missing_list", (sg.missing || []).map(skillName), "bad");
    renderChips("#r_skill_partial_list", (sg.partial || []).map(skillName), "warn");
    setText("#r_hard_gaps_n", (mr.hard_requirements_gaps || []).length);
    renderBullets("#r_hard_gaps", mr.hard_requirements_gaps || []);

    // 03 经验
    setText("#r_exp_score", `score ${pct(ex.score)}`);
    setText("#r_exp_required", ex.years_required != null ? `${ex.years_required} 年` : "未指定");
    setText("#r_exp_estimated", ex.years_estimated != null ? `${ex.years_estimated} 年` : "—");
    setText("#r_exp_industries", (ex.matched_industries || []).join(" / ") || "—");
    setText("#r_exp_roles", (ex.related_roles || []).join(" / ") || "—");
    renderBullets("#r_exp_notes", ex.notes || []);

    // 04 关键词
    setText("#r_kw_cov", `coverage ${pct(kw.coverage)}`);
    setText("#r_kw_matched_n", (kw.matched || []).length);
    setText("#r_kw_missing_n", (kw.missing || []).length);
    renderChips("#r_kw_matched", kw.matched || []);
    renderChips("#r_kw_missing", kw.missing || [], "bad");

    // 05 建议
    setText("#r_sug_n", `${sug.length} 条`);
    const ol = $("#r_suggestions");
    ol.innerHTML = "";
    sug.forEach((s) => ol.append(renderSuggestion(s)));

    // 报尾
    setText("#r_provider", meta.used_provider || "—");
    setText("#r_model", meta.used_model || "—");

    // 切换显示
    empty.hidden = true;
    report.hidden = false;
    report.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function statCell(k, v, cls) {
    const d = el("div", "stat");
    d.append(el("div", "k", k), el("div", "v " + (cls || ""), v));
    return d;
  }
  function renderChips(sel, items, variant) {
    const ul = $(sel);
    ul.innerHTML = "";
    if (!items.length) {
      const li = el("li");
      li.textContent = "无";
      ul.appendChild(li);
      return;
    }
    items.forEach((t) => {
      if (!t) return;
      const li = el("li");
      li.textContent = typeof t === "string" ? t : (t.skill || JSON.stringify(t));
      ul.appendChild(li);
    });
    if (variant === "bad") ul.classList.add("bad");
    if (variant === "warn") ul.classList.add("warn");
  }
  function renderBullets(sel, items) {
    const ul = $(sel);
    ul.innerHTML = "";
    if (!items.length) {
      const li = el("li"); li.textContent = "—"; ul.appendChild(li); return;
    }
    items.forEach((t) => { const li = el("li"); li.textContent = t; ul.appendChild(li); });
  }
  function skillName(x) {
    if (typeof x === "string") return x;
    if (x && x.skill) return x.skill;
    return "";
  }
  function renderSuggestion(s) {
    const li = el("li", "suggestion");
    const body = el("div", "body");
    const top = el("div", "top-row");
    top.append(el("h4", null, s.suggestion || s.title || "建议"));
    body.appendChild(top);
    if (s.reason) body.appendChild(el("p", "reason", s.reason));
    if (s.example) body.appendChild(el("div", "example", s.example));
    if (s.related_jd_requirement) {
      const r = el("p", "reason");
      r.textContent = "对应 JD: " + s.related_jd_requirement;
      body.appendChild(r);
    }
    const tags = el("div", "tags");
    if (s.priority) tags.append(el("span", "tag " + s.priority, s.priority));
    if (s.section) tags.append(el("span", "tag section", s.section));
    if (s.type) tags.append(el("span", "tag", s.type));
    li.append(document.createTextNode(""), body, tags);
    return li;
  }

  function scoreColor(s) { return s >= 80 ? "ok" : s >= 60 ? "warn" : "bad"; }
  function covColor(c) {
    const n = Number(c) || 0;
    return n >= 0.8 ? "ok" : n >= 0.5 ? "warn" : "bad";
  }
  function judge(score, cov) {
    const s = Number(score) || 0;
    const c = Number(cov) || 0;
    if (s >= 80 && c >= 0.8) return "综合匹配度高,建议在简历中针对岗位职责进一步量化项目成果,并补足关键词密度。";
    if (s >= 65) return "整体方向匹配,但存在若干技能或经验缺口,可通过针对性项目与表达补强。";
    if (s >= 50) return "部分匹配。建议重写自我评价与项目段,突出与 JD 强相关的可量化成果。";
    return "匹配度较低,建议先评估是否投递;若投递,需大改简历结构、补足核心硬技能项目经验。";
  }
})();
