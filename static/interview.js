/* ============================================================
   面试题预测页面 — 交互逻辑 (v2: 优先级筛选 + 新字段展示)
   ============================================================ */
(() => {
  "use strict";

  // ---- 工具 ----
  const $ = (sel, root = document) => root.querySelector(sel);

  function escape(s) {
    return String(s ?? "").replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])
    );
  }

  // ---- 顶栏时钟 ----
  (function tickTs() {
    const ts = $("#ts");
    if (!ts) return;
    const update = () =>
      (ts.textContent = new Date().toLocaleTimeString("zh-CN", { hour12: false }));
    update();
    setInterval(update, 1000);
  })();

  // ---- 类别定义 ----
  const CATEGORIES = [
    { key: "technical", num: "01", title: "技术题" },
    { key: "behavioral", num: "02", title: "行为题" },
    { key: "project", num: "03", title: "项目深挖" },
    { key: "situational", num: "04", title: "情景题" },
  ];

  // 优先级排序权重
  const PRIORITY_ORDER = { high: 0, medium: 1, low: 2 };

  // 优先级中文标签
  const PRIORITY_LABELS = { high: "高优先", medium: "中优先", low: "低优先" };

  // ---- DOM ----
  const fallback = $("#fallback");
  const ivShell = $("#ivShell");
  const summaryCard = $("#summaryCard");
  const startCard = $("#startCard");
  const btnPredict = $("#btnPredict");
  const progressCard = $("#progressCard");
  const pcPct = $("#pcPct");
  const pcFill = $("#pcFill");
  const pcMsg = $("#pcMsg");
  const errCard = $("#errCard");
  const errMsg = $("#errMsg");
  const result = $("#result");
  const catList = $("#catList");
  const adviceText = $("#adviceText");
  const resCount = $("#resCount");
  const resTime = $("#resTime");

  // 筛选栏
  const filterBar = $("#filterBar");
  const filterAll = $("#filterAll");
  const filterHigh = $("#filterHigh");
  const filterMedium = $("#filterMedium");
  const filterLow = $("#filterLow");

  // 当前筛选状态
  let currentFilter = "all";
  // 所有题目(扁平列表)
  let allQuestions = [];

  // ---- URL 参数 ----
  const params = new URLSearchParams(location.search);
  const traceId = params.get("trace_id");

  // ============================================================
  // 1. 入口:从 URL 读取 trace_id,加载摘要
  // ============================================================
  async function bootstrap() {
    if (!traceId) {
      showFallback("缺少 trace_id 参数,请先在分析台完成简历-JD 分析。");
      return;
    }
    try {
      const resp = await fetch(`/api/v1/cache/${encodeURIComponent(traceId)}`);
      const json = await resp.json();
      if (!resp.ok || !json.success) {
        showFallback(json.detail?.message || json.message || "分析结果不存在或已过期");
        return;
      }
      renderSummary(json.data);
      ivShell.hidden = false;
    } catch (err) {
      showFallback(`无法连接到服务: ${err.message}`);
    }
  }

  function showFallback(msg) {
    const msgEl = $("#fallbackMsg");
    if (msgEl) msgEl.textContent = msg;
    fallback.hidden = false;

    const form = $("#traceForm");
    if (form && !form._wired) {
      form._wired = true;
      form.addEventListener("submit", (e) => {
        e.preventDefault();
        const v = $("#traceInput").value.trim();
        if (!v) return;
        const url = new URL(location.href);
        url.searchParams.set("trace_id", v);
        location.href = url.toString();
      });
    }
  }

  // ============================================================
  // 2. 渲染摘要
  // ============================================================
  function renderSummary(raw) {
    const resume = raw.resume_data || {};
    const job = raw.job_requirement || {};
    const report = raw.match_report || {};

    const name = raw.resume_name || resume.name || "未命名候选人";
    const title = raw.job_title || job.position || job.title || "未指定岗位";
    const score = Number(raw.overall_score ?? report.overall_score) || 0;
    const tid = raw.trace_id || traceId || "—";

    $("#scName").textContent = name;
    $("#scJob").textContent = title;
    $("#scScore").textContent = score.toFixed(1);
    $("#scTrace").textContent = tid;
  }

  // ============================================================
  // 3. 点击"开始预测"
  // ============================================================
  btnPredict.addEventListener("click", async () => {
    if (btnPredict.disabled) return;
    btnPredict.disabled = true;
    startCard.hidden = true;
    progressCard.hidden = false;
    errCard.hidden = true;
    result.hidden = true;

    try {
      const resp = await fetch("/api/v1/interview/predict/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ trace_id: traceId }),
      });
      if (!resp.ok || !resp.body) {
        throw new Error(`HTTP ${resp.status}`);
      }
      await consumeStream(resp.body);
    } catch (err) {
      showError(`请求失败: ${err.message}`);
      btnPredict.disabled = false;
      progressCard.hidden = true;
      startCard.hidden = false;
    }
  });

  function showError(msg) {
    errMsg.textContent = msg;
    errCard.hidden = false;
  }

  function setProgress(percent, message) {
    pcPct.textContent = `${Math.round(percent)}%`;
    pcFill.style.width = `${Math.max(0, Math.min(100, percent))}%`;
    if (message) pcMsg.textContent = message;
  }

  // ============================================================
  // 4. 消费 NDJSON 流
  // ============================================================
  async function consumeStream(body) {
    const reader = body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    let questions = [];
    let summary = "";
    let durMs = 0;

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.trim()) continue;
        let evt;
        try {
          evt = JSON.parse(line);
        } catch {
          continue;
        }
        handleEvent(evt, state => {
          questions = state.questions ?? questions;
          summary = state.summary ?? summary;
          durMs = state.duration_ms ?? durMs;
        });
      }
    }
    if (buffer.trim()) {
      try {
        handleEvent(JSON.parse(buffer), state => {
          questions = state.questions ?? questions;
          summary = state.summary ?? summary;
          durMs = state.duration_ms ?? durMs;
        });
      } catch {}
    }

    if (questions.length > 0) {
      allQuestions = questions;
      renderResult(questions, summary, durMs);
    } else if (errCard.hidden) {
      showError("未返回任何题目,请稍后重试。");
      btnPredict.disabled = false;
      progressCard.hidden = true;
      startCard.hidden = false;
    }
  }

  function handleEvent(evt, sink) {
    if (!evt || !evt.type) return;
    switch (evt.type) {
      case "meta":
        break;
      case "stage_start":
        setProgress(0, `开始:${evt.label || "预测面试题"}`);
        break;
      case "progress":
        setProgress(evt.percent ?? 0, evt.message || "");
        break;
      case "stage_end":
        setProgress(99, "正在整理结果…");
        break;
      case "done":
        setProgress(100, "生成完成");
        if (evt.data && evt.data.interview_questions) {
          sink({
            questions: evt.data.interview_questions.questions || [],
            summary: evt.data.interview_questions.summary || "",
            duration_ms: evt.duration_ms || 0,
          });
        }
        break;
      case "error":
        showError(`[${evt.code || "error"}] ${evt.message || "未知错误"}`);
        break;
    }
  }

  // ============================================================
  // 5. 优先级筛选
  // ============================================================
  function applyFilter(filter) {
    currentFilter = filter;
    // 更新按钮状态
    [filterAll, filterHigh, filterMedium, filterLow].forEach(btn => {
      if (btn) btn.classList.remove("active");
    });
    const activeBtn = { all: filterAll, high: filterHigh, medium: filterMedium, low: filterLow }[filter];
    if (activeBtn) activeBtn.classList.add("active");

    // 筛选题目
    const filtered = filter === "all"
      ? allQuestions
      : allQuestions.filter(q => (q.priority || "medium") === filter);

    // 重新渲染
    const summary = adviceText.textContent || "";
    renderQuestionList(filtered, summary);
  }

  if (filterAll) filterAll.addEventListener("click", () => applyFilter("all"));
  if (filterHigh) filterHigh.addEventListener("click", () => applyFilter("high"));
  if (filterMedium) filterMedium.addEventListener("click", () => applyFilter("medium"));
  if (filterLow) filterLow.addEventListener("click", () => applyFilter("low"));

  // ============================================================
  // 6. 渲染结果(按优先级排序 + 按类别分组)
  // ============================================================
  function renderResult(questions, summary, durMs) {
    progressCard.hidden = true;

    // 按优先级排序(high → medium → low)
    const sorted = [...questions].sort(
      (a, b) => (PRIORITY_ORDER[a.priority] ?? 1) - (PRIORITY_ORDER[b.priority] ?? 1)
    );

    allQuestions = sorted;
    renderQuestionList(sorted, summary);

    resCount.textContent = `${questions.length} 道题`;
    resTime.textContent = durMs > 0 ? `耗时 ${(durMs / 1000).toFixed(1)}s` : "—";

    result.hidden = false;
    filterBar.hidden = false;
  }

  function renderQuestionList(questions, summary) {
    // 按类别分组
    const grouped = {};
    for (const c of CATEGORIES) grouped[c.key] = [];
    for (const q of questions) {
      const k = q.category || "technical";
      if (!grouped[k]) grouped[k] = [];
      grouped[k].push(q);
    }

    catList.innerHTML = "";
    const tplCat = $("#tplCat");
    const tplQ = $("#tplQ");

    for (const c of CATEGORIES) {
      const items = grouped[c.key] || [];
      if (items.length === 0) continue;

      const node = tplCat.content.firstElementChild.cloneNode(true);
      $(".cat-num", node).textContent = c.num;
      $(".cat-title", node).textContent = c.title;
      $(".cat-count", node).textContent = `${items.length} 道`;

      const body = $("[data-body]", node);
      for (const q of items) {
        body.appendChild(buildQuestionNode(q, tplQ));
      }

      const head = $("[data-toggle]", node);
      head.addEventListener("click", () => {
        node.classList.toggle("expanded");
      });
      node.classList.add("expanded");

      catList.appendChild(node);
    }

    adviceText.textContent = summary || "暂无备考建议。";
  }

  function buildQuestionNode(q, tpl) {
    const node = tpl.content.firstElementChild.cloneNode(true);

    const diff = (q.difficulty || "medium").toLowerCase();
    const diffEl = $("[data-diff]", node);
    diffEl.textContent = diff;
    diffEl.classList.add(diff);

    // 优先级标签
    const priority = q.priority || "medium";
    const priEl = $("[data-priority]", node);
    if (priEl) {
      priEl.textContent = PRIORITY_LABELS[priority] || priority;
      priEl.classList.add(priority);
    }

    const skillEl = $("[data-skill]", node);
    if (q.related_skill) {
      skillEl.textContent = q.related_skill;
      skillEl.hidden = false;
    }

    $("[data-q]", node).textContent = q.question || "—";
    $("[data-intent]", node).textContent = q.intent || "—";
    $("[data-direction]", node).textContent = q.suggested_answer_direction || "—";

    // 出题原因
    const reasonEl = $("[data-reason]", node);
    if (reasonEl && q.reason) {
      $("[data-reason-text]", node).textContent = q.reason;
      reasonEl.hidden = false;
    }

    // 简历证据
    const resumeEvidenceEl = $("[data-resume-evidence]", node);
    if (resumeEvidenceEl && q.evidence_from_resume) {
      $("[data-resume-evidence-text]", node).textContent = q.evidence_from_resume;
      resumeEvidenceEl.hidden = false;
    }

    // JD 证据
    const jdEvidenceEl = $("[data-jd-evidence]", node);
    if (jdEvidenceEl && q.evidence_from_jd) {
      $("[data-jd-evidence-text]", node).textContent = q.evidence_from_jd;
      jdEvidenceEl.hidden = false;
    }

    // 原 JD 关联字段
    const jdEl = $("[data-jd]", node);
    if (q.related_jd_requirement) {
      $("[data-jd-text]", node).textContent = q.related_jd_requirement;
      jdEl.hidden = false;
    }
    return node;
  }

  // ============================================================
  // 启动
  // ============================================================
  bootstrap();
})();
