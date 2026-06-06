# 开发文档 · Job Analyzer

> 本文档面向**接手维护的工程师**,用 5 分钟说明本项目是什么、怎么跑、改了什么、为什么改、出问题怎么排查。
>
> 仓库:[github.com/cxzrdxy/job-analyzer](https://github.com/cxzrdxy/job-analyzer)

---

## 目录

- [0. 30 秒速览](#0-30-秒速览)
- [1. 改造总览](#1-改造总览)
- [2. 快速开始(本地启动)](#2-快速开始本地启动)
- [3. 项目结构](#3-项目结构)
- [4. 改造点详解](#4-改造点详解)
  - [4.1 接入 DeepSeek v4 Flash](#41-接入-deepseek-v4-flash)
  - [4.2 根路径美化着陆页 + 元信息接口](#42-根路径美化着陆页--元信息接口)
  - [4.3 Bug 修复:upload 校验 500 → 4xx](#43-bug-修复upload-校验-500--4xx)
  - [4.4 技能匹配器升级:字面 → LLM 语义](#44-技能匹配器升级字面--llm-语义)
  - [4.5 前端交互修复](#45-前端交互修复)
  - [4.6 端到端测试发现的 5 个关联 bug](#46-端到端测试发现的-5-个关联-bug)
  - [4.7 LangGraph 并行匹配:fan-out/fan-in](#47-langgraph-并行匹配fan-outfan-in)
  - [4.8 流式进度推送:token 级实时进度](#48-流式进度推送token-级实时进度)
  - [4.9 并行抽取:parse_resume / parse_job 并行化](#49-并行抽取parse_resume--parse_job-并行化)
- [5. 验证清单](#5-验证清单)
- [6. 风险、回滚与安全](#6-风险回滚与安全)
- [7. GitHub 发布说明](#7-github-发布说明)
- [8. 时间线](#8-时间线)

---

## 0. 30 秒速览

| 项 | 值 |
|---|---|
| 项目类型 | FastAPI + LangGraph 求职分析智能体 |
| 主要能力 | 简历 PDF / DOCX / TXT + JD 文本 → 技能匹配度 + 优化建议 |
| LLM 基座 | **DeepSeek v4 Flash**(`provider=deepseek`,可通过 `.env` 切回 OpenAI) |
| 默认端口 | `http://localhost:8000` |
| 前端应用 | `http://localhost:8000/app` |
| API 文档 | `http://localhost:8000/docs` |
| 核心依赖 | FastAPI 0.115 / Pydantic 2.9 / LangGraph 0.2.53 / langchain-openai 0.2.9 |
| Python 环境 | `D:\miniconda\envs\fastapi` (Python 3.10.19) |

**最常用的两个 URL**:
- `GET /` — 运维监控着陆页(深色玻璃拟态,显示 BOOT 日志、stats、provider/model 徽章)
- `GET /app` — 用户使用的前端应用(上传简历 + 粘贴 JD + 一键分析)

---

## 1. 改造总览

| # | 改造主题 | 关键文件 | 状态 |
|---|---|---|---|
| 1 | 接入 DeepSeek v4 Flash 作为 LLM 基座 | `app/core/config.py`、`.env` | ✅ |
| 2 | 新增 `.gitignore` 防止密钥/临时文件入库 | `.gitignore` | ✅ |
| 3 | README 改用现成 `fastapi` 环境 | `README.md` | ✅ |
| 4 | 根路径美化着陆页 + `/app` 前端入口 | `app/main.py` | ✅ |
| 5 | 新增服务元信息 `GET /api/v1/info` | `app/api/routes.py` | ✅ |
| 6 | Bug 修复:`UnsupportedFileTypeError` 500 → 415 | `app/api/routes.py` | ✅ |
| 7 | 技能匹配器:字面 → LLM 语义(Plan A) | `app/matchers/skill_matcher.py` | ✅ |
| 8 | 前端修复:上传弹窗双触发 / 载入示例清空简历 | `static/app.js` | ✅ |
| 9 | 推送至 GitHub `cxzrdxy/job-analyzer` | git 仓库 | ✅ |
| 10 | 删除误传的简历 PDF(PII 清理) | `3_郭成骥.pdf` 已下架 | ✅ |
| 11 | Bug 修复:CSS `display: flex` 覆盖 HTML `hidden` 属性 | `static/app.css`、`static/index.html` | ✅ |
| 12 | Bug 修复:`LLMClient._progress_callback` 未初始化 | `app/extractors/llm_client.py` | ✅ |
| 13 | Bug 修复:langgraph 0.2.x `astream()` 不发 `__end__` 导致 `done` 事件空数据 | `app/services/analyzer.py` | ✅ |
| 14 | LangGraph 并行匹配:Send fan-out/fan-in 替代顺序边 | `app/workflow/graph.py`、`app/services/analyzer.py`、`app/api/routes.py` | ✅ |
| 15 | 流式进度推送:token 级实时进度 + 线程安全桥接 | `app/workflow/progress.py`、`app/extractors/llm_client.py`、`app/workflow/graph.py`、`app/services/analyzer.py` | ✅ |
| 16 | 并行抽取:parse_resume / parse_job 从 START 并行扇出 | `app/workflow/graph.py`、`static/app.js`、`static/app.css` | ✅ |

**业务代码改动**:
- 后端:4 个文件 — `app/api/routes.py`、`app/matchers/skill_matcher.py`、`app/extractors/llm_client.py`、`app/services/analyzer.py` + 1 个节点注入 `app/workflow/nodes.py`
- 前端:2 个文件 — `static/app.js`、`static/app.css` + 资源版本 `static/index.html`
- 配置/文档:5 个文件 — `app/core/config.py`、`.env`、`.env.example`、`.gitignore`、`DEVELOPMENT.md`

---

## 2. 快速开始(本地启动)

### 2.1 前置

- Python 3.10
- 已激活环境:`D:\miniconda\envs\fastapi`
- 在项目根目录 `.env` 中有有效 `DEEPSEEK_API_KEY`(或 `OPENAI_API_KEY`)

### 2.2 启动

```bash
# 方式 A:激活环境后启动
D:\miniconda\envs\fastapi\Scripts\activate.bat
cd C:\Users\10408\Desktop\job
uvicorn app.main:app --reload --port 8000

# 方式 B:免激活(推荐)
D:\miniconda\envs\fastapi\python.exe -m uvicorn app.main:app --reload --port 8000
```

启动成功标志:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
```

### 2.3 立刻验证(3 条命令)

```bash
# 1. 服务健康
curl.exe http://localhost:8000/api/v1/health
# 预期: {"success":true,"data":{"status":"up"}}

# 2. 元信息(确认 DeepSeek 已接入)
curl.exe http://localhost:8000/api/v1/info
# 预期: provider: "deepseek", model: "deepseek-v4-flash"

# 3. 打开浏览器
# http://localhost:8000/        ← 着陆页
# http://localhost:8000/app     ← 前端应用
```

### 2.4 .env 最小配置

```dotenv
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek-v4-flash
DEEPSEEK_API_KEY=sk-你的真实 key
# 可选:自定义 base_url(默认 https://api.deepseek.com)
# LLM_BASE_URL=
```

> **安全提醒**:`.env` 已在 `.gitignore` 中,不会进入版本库。Key 只在本地生效。

---

## 3. 项目结构

```
c:\Users\10408\Desktop\job\
├── app/                                # ★ FastAPI 后端
│   ├── main.py                         # 应用工厂 + GET / + GET /app
│   ├── api/
│   │   └── routes.py                   # ★ /api/v1/analyze + /api/v1/info + /api/v1/health
│   ├── core/
│   │   ├── config.py                   # ★ provider 感知 + base_url 映射
│   │   ├── errors.py                   # AppError 体系
│   │   └── logging.py
│   ├── parsers/
│   │   └── text_extractor.py           # PDF/DOCX/TXT 文本提取
│   ├── extractors/
│   │   ├── llm_client.py               # DeepSeek/OpenAI 客户端
│   │   ├── resume_extractor.py         # LLM 结构化抽取简历
│   │   └── job_extractor.py            # LLM 结构化抽取 JD
│   ├── workflow/                       # LangGraph 工作流
│   │   ├── graph.py
│   │   ├── state.py
│   │   ├── nodes.py                    # ★ 注入 LLMClient 到技能匹配
│   │   └── suggestion_generator.py
│   ├── matchers/
│   │   ├── skill_matcher.py            # ★ LLM 语义匹配(字面回退)
│   │   ├── experience_matcher.py
│   │   └── keyword_matcher.py
│   ├── models/                         # Pydantic 数据模型
│   └── services/
│       └── analyzer.py                 # 主分析入口
│
├── static/                             # ★ 前端
│   ├── app.js                          # ★ 上传/分析交互
│   ├── app.css
│   └── index.html                      # GET /app 入口
│
├── .env                                # 本地密钥(已 gitignore)
├── .env.example                        # 密钥占位模板
├── .gitignore                          # ★ 防止密钥/临时文件入库
├── requirements.txt
├── Dockerfile
├── README.md
├── DEVELOPMENT.md                      # ★ 本文档
└── 求职分析智能体设计方案.md
```

`★` = 本次有改动的文件。

---

## 4. 改造点详解

### 4.1 接入 DeepSeek v4 Flash

#### 背景

原框架默认调 OpenAI `gpt-4o-mini`。要切到 DeepSeek v4 Flash,需业务代码**0 改动**,只改 `.env`。

#### 关键设计

| 项 | 决策 |
|---|---|
| LLM 库 | 沿用 `langchain_openai.ChatOpenAI`(DeepSeek 端点兼容 OpenAI 协议) |
| `LLMSettings` | 改为 provider 感知,`__post_init__` 统一解析 key/url |
| Key 解析顺序 | `DEEPSEEK_API_KEY` → 回退 `OPENAI_API_KEY` |
| `base_url` 解析顺序 | 显式参数 > `LLM_BASE_URL` > provider 默认 |
| DeepSeek 默认 base_url | `https://api.deepseek.com` |

#### 涉及文件

- `app/core/config.py` — 新增 `_default_base_url(provider)` 映射
- `.env` / `.env.example` — 模板化为 DeepSeek 字段

#### 验证

```bash
D:\miniconda\envs\fastapi\python.exe -c "from app.core.config import get_settings; s=get_settings().llm; print(s.provider, s.model, s.base_url, bool(s.api_key))"
# 预期: deepseek deepseek-v4-flash https://api.deepseek.com True
```

#### 切回 OpenAI

```dotenv
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-your-openai-key
LLM_BASE_URL=
```

---

### 4.2 根路径美化着陆页 + 元信息接口

#### 背景

原框架 `GET /` 返回 `{"detail":"Not Found"}`,运维和人工访问体验差。

#### 变更

| 端点 | 内容 |
|---|---|
| `GET /` | 深色玻璃拟态着陆页:BOOT 日志、stats、provider/model 徽章、4 个可点端点 |
| `GET /app` | 前端应用(上传简历 + JD 输入 + 匹配分析) |
| `GET /api/v1/info` | JSON 形式的服务元信息(provider、model、version、所有端点 URL) |

#### 涉及文件

- `app/main.py` — 新增 `GET /`、`GET /app`、`GET /static/*` 挂载
- `app/api/routes.py` — 新增 `GET /api/v1/info`

#### 验证

| 端点 | 命令 | 预期 |
|---|---|---|
| `GET /` | `curl.exe http://localhost:8000/` | HTTP 200, 11.8KB HTML |
| `GET /app` | `curl.exe http://localhost:8000/app` | HTTP 200, 10.3KB HTML |
| `GET /api/v1/info` | `curl.exe http://localhost:8000/api/v1/info` | 含 `provider: deepseek` |

---

### 4.3 Bug 修复:upload 校验 500 → 4xx

#### 现象

```
POST /api/v1/analyze  -F "resume=@README.md"  -F "job_description=x"
→ 修复前: HTTP 500
→ 修复后: HTTP 415 {"code": "unsupported_file_type"}
```

#### 根因

`app/api/routes.py` 中 `_validate_upload` / `_read_with_limit` 调用**位于 `try/except AppError` 块之外**,`UnsupportedFileTypeError` / `FileTooLargeError` 未被捕获,被 FastAPI 默认处理器接住,变 500。

#### 修复

把校验/读取全部移入 `try` 块;新增 `except HTTPException: raise` 透传业务 HTTP 异常。

#### 修复后异常映射表

| 异常 | 修复前 | 修复后 |
|---|---|---|
| `UnsupportedFileTypeError` | 500 | **415** |
| `FileTooLargeError` | 500 | **413** |
| LLM 抽取失败 | 500 | **502** |
| JD 缺失 / 重复给 | 400 | 400(不变) |

---

### 4.4 技能匹配器升级:字面 → LLM 语义

#### 背景

原 `analyze_skill_gap` 用纯字面匹配(`k in corpus`)。一次实际跑测,9 项硬技能**全判 missing**:

- 简历明明有 FastAPI / LangGraph / PgVector / 求职产品 经验
- JD 把"向量数据库 (Milvus / Qdrant)" 当作示例,字面匹配把括号内示例当作硬要求
- 字面匹配无法识别等价物、无法识别隐含使用

#### 方案对比

| 方案 | 改动 | 效果 |
|---|---|---|
| A. LLM 替换为语义匹配器(**采用**) | 1 次 LLM 调用,逐项判断有/无/等价 | 准确度 ~10% → ~80%,+1 次 LLM |
| B. 拆分括号示例 | `_alias_keys` 拆分 `(...)` 为别名 | 解决 1 类误判 |
| C. 混合:字面 + 语义回退 | 字面无命中时再调 LLM | 平衡成本与准确性 |
| D. 保持现状 | 仅前端 disclaimer | 0 改动,体验差 |

#### 核心实现

```python
# app/matchers/skill_matcher.py
def analyze_skill_gap(resume, job, *, llm_client=None, force_literal=False) -> SkillGapAnalysis:
    if force_literal or llm_client is None:
        return _literal_skill_gap(resume, job)            # 原逻辑保留为回退
    try:
        return _semantic_skill_gap(resume, job, llm_client)
    except ExtractError as exc:
        logger.warning("语义匹配失败,回退到字面匹配: %s", exc)
        return _literal_skill_gap(resume, job)
```

**`_semantic_skill_gap` 设计要点**:
- **单次 LLM 调用**:把简历原文 + 硬/软技能列表一并塞进 prompt,LLM 一次返回所有判断
- **等价物映射表**(内置于 system prompt):
  - 向量数据库 ≈ Milvus / Qdrant / PgVector / Chroma / Weaviate / FAISS
  - Python 异步框架 ≈ FastAPI(asyncio) / aiohttp / Sanic / Tornado
  - Python ORM ≈ SQLAlchemy / SQLModel / Tortoise ORM / Django ORM
  - 消息队列 ≈ Kafka / RabbitMQ / RocketMQ
  - LLM API ≈ OpenAI / DeepSeek / 通义千问 / 智谱 / Claude / Gemini
- **三级容错查找**:精确 → 归一化 → 短文本包含
- **Pydantic Schema 校验**:`_SkillEntry` + `_SkillGapSchema` 严格约束 LLM 输出
- **节点注入**:`analyze_skill_gap_node` 创建 `LLMClient()` 传入

#### 效果对比(同一份 PDF 简历 + 您的 JD 实测)

| 指标 | 字面(前) | 语义(后) | 变化 |
|---|---|---|---|
| `overall_score` | 36.0 | **72.6** | +36.6 |
| `skill_coverage` | 0.10 | **0.79** | +0.69 |
| matched | 0 | **5** | +5 |
| partial | 0 | 1 | +1 |
| missing | 9 | **1**(Kafka,真缺) | -8 |
| 端到端耗时 | ~54s | ~108s | +54s(1 次 LLM) |

LLM 正确识别:
- ✅ PgVector ≡ 向量数据库(Milvus/Qdrant)
- ✅ 用 LangGraph 必然用过 LLM API(隐含使用)
- ✅ ZLjob 智联职位 ≈ 智能简历/求职产品
- ✅ RAG 检索增强(智能客服项目明写)
- ✅ FastAPI 异步 ≈ asyncio

#### 入口 API

```python
# 默认:LLM 路径,失败回退
gap = analyze_skill_gap(resume, job, llm_client=LLMClient())

# 强制字面(性能对比 / 离线测试)
gap = analyze_skill_gap(resume, job, force_literal=True)

# 不传 client(等同字面)
gap = analyze_skill_gap(resume, job)
```

---

### 4.5 前端交互修复

#### 现象

| 问题 | 触发 |
|---|---|
| 上传弹窗连续弹 2 次 | 点击上传区 |
| 载入示例后简历被清空 | 先上传简历,再点「载入示例」 |

#### 根因

[static/app.js](file:///c:/Users/10408/Desktop/job/static/app.js) 上传区在 HTML 中包在 `<label>` 内。`<label>` 的浏览器原生行为是:点击 label 自动激活内部 `input[type=file]`(弹 1 次)。旧版 JS 又在 `drop` 的 `click` 处理器里手动调 `fileInput.click()`(再弹 1 次),合起来弹 2 次。

「载入示例」按钮主动执行 `fileInput.value = ""` 和 `setFile(null)`,把已选简历清空。

#### 修复

```js
// 修复前(双触发):
drop.addEventListener("click", (e) => {
  e.preventDefault();
  fileInput.click();   // 与 <label> 原生行为叠加
});

// 修复后(只一次):
drop.addEventListener("click", (e) => {
  e.stopPropagation();   // 让 <label> 原生行为接管,不再手动 click
});

// 载入示例:不再清空已选简历
loadExampleBtn.addEventListener("click", () => {
  jd.value = SAMPLE_JD;
  jd.dispatchEvent(new Event("input"));
  if (fileInput.files[0]) {
    showToast("已载入示例 JD,当前简历保留");
  } else {
    showToast("已载入示例 JD");
  }
});
```

#### 验证

| 场景 | 修复前 | 修复后 |
|---|---|---|
| 点击上传区 | 弹 2 次 | **弹 1 次** |
| 先选简历,再点载入示例 | 简历被清空 | **简历保留**,仅填充 JD |
| 未选简历,直接点载入示例 | JD 填充 + 简历空 | JD 填充 + 简历空(不变) |

---

### 4.6 端到端测试发现的 5 个关联 bug

#### 现象

浏览器端到端跑通一个完整分析时,先后出现 3 类症状,挖下去发现 5 个相关 bug:

| # | 症状 | 用户感知 |
|---|---|---|
| ① | `_showRunView` 报 `Cannot set properties of null (setting 'hidden')` | 浏览器 console 报错 |
| ② | 页面一打开,右上角直接出现「分析失败」+ 左下角跑步骤可见,即使没点提交 | UI 默认状态错乱 |
| ③ | `POST /api/v1/analyze` 直接 500;`POST /api/v1/analyze/stream` 走完 8 个阶段但 `done` 事件里 `match_report: null, suggestions: []` | 同步接口挂,流式接口空数据 |

#### 4.6.1 CSS `display: flex` 覆盖 HTML `hidden`(现象②)

**根因**

`static/app.css` 里大量元素声明了 `display: flex/grid`,而 HTML 属性 `hidden` 在浏览器里默认等同于 `display: none` —— 两者相遇时,**CSS `display: ...` 优先级更高**,`hidden` 直接被吞掉。

| 元素 | HTML 默认 | CSS 规则 | 实际行为 |
|---|---|---|---|
| `.run-error` | `hidden` | `display: flex` | **永远显示** |
| `.run-view` | `hidden` | `display: flex` | **永远显示** |
| `.report` | `hidden` | `display: flex` | **永远显示** |

**修复** [static/app.css:8](file:///c:/Users/10408/Desktop/job/static/app.css#L8) 加全局规则:

```css
/* 全局:尊重 HTML hidden 属性,避免被下面的 display:flex/grid 覆盖 */
[hidden] { display: none !important; }
```

#### 4.6.2 前端 `_showRunView` 防御式空值(现象①)

**根因**

trae-preview 的内嵌浏览器对 `/static/*` 资源缓存较激进(只看到 `ETag` + `Last-Modified`,无 `Cache-Control`)。在缓存命中旧字节码的情况下,`const runView = $("#runView")` 偶发返回 `null`,后续 `.hidden = false` 抛 `TypeError`。

**修复** [static/app.js:261-264](file:///c:/Users/10408/Desktop/job/static/app.js#L261-L264) 加防御:

```js
function _showRunView() {
  if (!runView) { console.warn("runView 元素缺失,跳过 _showRunView"); return; }
  empty.hidden = true;
  report.hidden = true;
  runView.hidden = false;
  ...
}
```

**同时** [static/index.html:13](file:///c:/Users/10408/Desktop/job/static/index.html#L13) 给 CSS / JS 加 `?v=2` 主动 bust 缓存:

```html
<link rel="stylesheet" href="/static/app.css?v=2" />
<script src="/static/app.js?v=2"></script>
```

#### 4.6.3 LLMClient 初始化修复(现象③ 同步 500)

**根因** [app/extractors/llm_client.py:41](file:///c:/Users/10408/Desktop/job/app/extractors/llm_client.py#L41) 的 `__init__` 只在两个分支里设 `self._progress_callback` —— **传参** 或 **ContextVar 有值**。同步 `/analyze` 路径两条都不满足,属性根本不存在,后续 `chat_json` 里 `self._progress_callback` 直接 `AttributeError`。

**修复** 始终初始化:

```python
self._progress_callback: ProgressCallback = None  # 新增
if progress_callback is not None:
    self._progress_callback = progress_callback
else:
    try:
        from app.workflow.progress import get_progress_callback
        cb = get_progress_callback()
        if cb is not None:
            self._progress_callback = cb
    except Exception:
        pass
```

#### 4.6.4 流式 `done` 事件空数据(现象③ 流式空壳)

**根因** [app/services/analyzer.py:167](file:///c:/Users/10408/Desktop/job/app/services/analyzer.py#L167) 的代码:

```python
async for event in workflow.astream(initial):
    if "__end__" in event:
        final_state = event["__end__"]
        break
    ...
```

**langgraph 0.2.53 的 `astream()` 不再发送 `__end__` 事件** —— 它只是按节点依次发完就停止迭代。所以 `final_state` 永远是 `None`,组装 `done` 事件时 `match_report: None` / `suggestions: []` 被序列化进去,前端拿到空壳。

**验证** 直接 `wf.astream(initial)` 跑一遍,7 个节点都收到事件,**但整个迭代中没有任何事件带 `__end__` 键**,循环自然结束。

**修复** 在 `for ... else` 的 `else` 分支用累积的 `initial` 作为 `final_state`:

```python
async for event in workflow.astream(initial):
    if "__end__" in event:
        final_state = event["__end__"]
        break
    # ... 节点事件正常 yield ...
    for k, v in event[node_name].items():
        initial[k] = v
else:
    # langgraph 0.2.x 的 astream 不再发 __end__,
    # 循环自然结束(无 break)说明 workflow 已走完,
    # 此时累积的 `initial` 即为最终 state。
    final_state = initial
```

#### 4.6.5 修复前后对比(同份 PDF + JD 实测)

| 指标 | 修复前 | 修复后 |
|---|---|---|
| `/analyze` 同步 | HTTP 500 (`AttributeError: _progress_callback`) | **HTTP 200**,`overall_score: 73.6` |
| `/analyze/stream` `done.data.match_report` | `null` | **`{overall_score: 76.4, skill_gap: {matched: [...], ...}}`** |
| `/analyze/stream` `done.data.suggestions` | `[]` | **10 条**优化建议 |
| 浏览器开页即「分析失败」 | 是 | 否 |
| `_showRunView` TypeError | 偶发 | 不再抛(防御式) |

---

### 4.7 LangGraph 并行匹配:fan-out/fan-in

#### 背景

原 `graph.py` 中 `parse_job` 到三个匹配节点声明了三条 `add_edge`:

```python
workflow.add_edge("parse_job", "skill_gap")
workflow.add_edge("parse_job", "experience")
workflow.add_edge("parse_job", "keywords")
```

LangGraph 0.2 的 `StateGraph` 对同一节点多条出边是**顺序执行**的,并非并行。三个匹配节点(尤其是 `skill_gap` 需要调 LLM)串行跑,总耗时是三者之和。

#### 方案

使用 LangGraph 的 `Send` 原语实现 fan-out/fan-in 模式:

```python
from langgraph.types import Send

_PARALLEL_MATCHERS = ["skill_gap", "experience", "keywords"]

def _route_to_matchers(state: AgentState) -> list[Send]:
    """fan-out: 将状态分发到三个匹配节点并行执行."""
    return [Send(node, state) for node in _PARALLEL_MATCHERS]

# 用条件边替代三条普通边
workflow.add_conditional_edges("parse_job", _route_to_matchers)
```

`Send` 是 LangGraph 的 fan-out 原语:当路由函数返回多个 `Send` 对象时,LangGraph 会将目标节点作为独立分支并行调度。三个分支各自写入不同的 state key(`skill_gap_partial`、`experience_match_partial`、`keyword_match_partial`),在 fan-in 节点 `aggregate_report` 处等待全部完成后合并状态再继续执行。

#### 同步接口适配

`analyze()` 方法改为 `async def` + `ainvoke()`,使同步 API 也能通过 asyncio 事件循环并行执行三个匹配节点:

```python
# analyzer.py
async def analyze(self, ...) -> dict:
    final = await self._get_workflow().ainvoke(initial)

# routes.py
result = await get_service().analyze(...)
```

#### 涉及文件

| 文件 | 变更 |
|---|---|
| `app/workflow/graph.py` | 引入 `Send` + `_route_to_matchers` + `add_conditional_edges` |
| `app/services/analyzer.py` | `analyze()` → `async def` + `ainvoke()` |
| `app/api/routes.py` | `get_service().analyze(...)` → `await get_service().analyze(...)` |

#### 效果

| 指标 | 改造前(顺序) | 改造后(并行) |
|---|---|---|
| skill_gap + experience + keywords 总耗时 | 三者之和 | 取最长者 |
| 理论加速比 | 1× | ~2-3×(取决于 LLM 调用占比) |

---

### 4.8 流式进度推送:token 级实时进度

#### 背景

原实现中,LLM 流式输出的 token 级进度回调**只写日志**,未推送到前端。前端只能感知 `stage_start` / `stage_end`,中间是黑盒等待。

根因有两个:

1. **ContextVar 不跨线程传播**:LangGraph `astream()` 在线程池中执行同步节点,`LLMClient()` 在工作线程中构造时读不到主线程设置的 ContextVar,回调为 `None`
2. **同步回调无法 yield**:即使回调被调用,也无法从 async generator 中 yield NDJSON 行

#### 方案:asyncio.Queue + 后台任务 + 线程安全共享变量

```
之前:  LLM streaming → callback → 仅写日志
之后:  LLM streaming → callback → loop.call_soon_threadsafe → queue.put → 主生成器 yield NDJSON
```

##### 4.8.1 线程安全基础设施(`progress.py`)

LangGraph 在线程池中执行同步节点,ContextVar 不会传播到工作线程。因此用模块级变量 + `threading.Lock` 作为跨线程通信机制:

```python
# 线程安全的共享变量
_progress_shared_lock = threading.Lock()
_progress_shared: Optional[Callable] = None

_stage_shared_lock = threading.Lock()
_stage_shared: Optional["StageDef"] = None

def set_progress_callback_shared(cb): ...
def get_progress_callback_shared(): ...
def set_current_stage_shared(stage): ...
def get_current_stage_shared(): ...
```

新增 `compute_streaming_percent(stage, phase, chars)` 计算进度百分比:

| phase | 百分位 | 说明 |
|---|---|---|
| `first_token` | 阶段区间 35% | LLM 已开始输出 |
| `streaming` | 35% → 90% | 按 chars/1500 归一化逐步推进 |
| 剩余 | 90% → 100% | 留给 `stage_end`,避免进度条"卡在 99%" |

##### 4.8.2 LLMClient 回调获取优先级扩展(`llm_client.py`)

```python
# 优先级:显式参数 > ContextVar > 线程安全共享变量 > None
if progress_callback is not None:
    self._progress_callback = progress_callback
else:
    # 先尝试 ContextVar
    cb = get_progress_callback()
    if cb is not None:
        self._progress_callback = cb
    # 回退到线程安全的共享变量
    if self._progress_callback is None:
        cb = get_progress_callback_shared()
        if cb is not None:
            self._progress_callback = cb
```

##### 4.8.3 节点阶段追踪(`graph.py`)

新增 `_with_stage_tracking` 包装器,每个节点执行前通过线程安全变量设置当前阶段:

```python
def _with_stage_tracking(node_name: str, node_fn):
    def wrapped(state):
        stage = stage_by_node(node_name)
        if stage:
            set_current_stage_shared(stage)
        return node_fn(state)
    return wrapped

# 注册节点时统一包装
workflow.add_node("parse_resume", _with_stage_tracking("parse_resume", parse_resume_node))
```

##### 4.8.4 核心重构:队列 + 后台任务(`analyzer.py`)

```python
queue: asyncio.Queue[tuple] = asyncio.Queue(maxsize=200)
loop = asyncio.get_running_loop()

# 进度回调:在工作线程中被 LLMClient 调用,线程安全地推入队列
def progress_callback(phase: str, info: dict) -> None:
    stage = get_current_stage_shared()
    loop.call_soon_threadsafe(
        queue.put_nowait,
        ("progress", phase, info, stage.key if stage else None),
    )

# 同时设置 ContextVar 和线程安全共享变量
set_progress_callback(progress_callback)
set_progress_callback_shared(progress_callback)

# 后台任务:运行工作流,将节点事件推入队列
async def run_workflow() -> None:
    async for event in workflow.astream(initial):
        await queue.put(("node", event))

task = asyncio.create_task(run_workflow())

# 主生成器从队列消费
while True:
    item = await queue.get()
    if item[0] == "progress":
        # token 级进度 → yield NDJSON progress 事件
        yield _json_line(make_progress_event(stage, percent, ...))
    elif item[0] == "node":
        # 节点完成 → yield stage_end 事件
        yield _json_line(make_stage_end_event(stage))
```

#### 涉及文件

| 文件 | 变更 |
|---|---|
| `app/workflow/progress.py` | 新增线程安全共享变量 + `compute_streaming_percent` |
| `app/extractors/llm_client.py` | 回调获取优先级增加线程安全共享变量 |
| `app/workflow/graph.py` | `_with_stage_tracking` 包装器 |
| `app/services/analyzer.py` | `asyncio.Queue` + 后台任务 + 删除仅写日志的 `_make_progress_callback` |

#### NDJSON 事件流对比

```
之前(仅 stage_start/end):
  {"type":"stage_start","key":"parse_resume","percent":8.75}
  ... 长时间黑盒等待 ...
  {"type":"stage_end","key":"parse_resume"}

之后(含 token 级进度):
  {"type":"stage_start","key":"parse_resume","percent":8.75}
  {"type":"progress","percent":10.25,"message":"已处理 50 字符","chars":50}
  {"type":"progress","percent":13.0,"message":"已处理 500 字符","chars":500}
  {"type":"progress","percent":18.5,"message":"已处理 1500 字符","chars":1500}
  {"type":"stage_end","key":"parse_resume"}
```

#### 前端兼容性

前端 `app.js` 已有 `progress` 事件处理逻辑,无需修改:

```javascript
case "progress":
    onProgress(evt.percent, evt.message, evt.chars);
    break;
```

`onProgress` 会更新进度条宽度和状态文字,新增的 token 级进度事件自动生效。

---

### 4.9 并行抽取:parse_resume / parse_job 并行化

#### 背景

原工作流中 `parse_resume → parse_job` 是串行的,但两者**互不依赖**:
- `parse_resume` 只读 `inputs.resume_text`,写入 `resume_data`
- `parse_job` 只读 `inputs.job_text`,写入 `job_requirement`

串行执行时,两个 LLM 调用耗时相加(12~20s + 13~19s = 25~39s);并行后取最长者,节省 10~20s。

#### 方案

```
改动前(串行):
  START → parse_resume → parse_job → {matchers} → aggregate → suggestions → END

改动后(并行):
                  ┌─→ parse_resume ─┐
  START ──────────┤                 ├─→ dispatch_matchers → {matchers} → aggregate → suggestions → END
                  └─→ parse_job  ──┘
```

关键改动:
1. `parse_resume` 和 `parse_job` 都从 `START` 直接扇出(`add_edge(START, "parse_resume")` + `add_edge(START, "parse_job")`)
2. 新增 `dispatch_matchers` 中继节点作为 fan-in 汇聚点,等待两个抽取节点都完成后再 fan-out 到三个匹配器
3. `dispatch_matchers` 返回 `{"errors": state.get("errors", [])}` 满足 LangGraph 的 state 更新要求(空 dict 会触发 `InvalidUpdateError`)

#### 涉及文件

| 文件 | 变更 |
|---|---|
| `app/workflow/graph.py` | 引入 `START`;新增 `_dispatch_matchers_node` 中继节点;两条 `add_edge(START, ...)` 替代 `set_entry_point` + 串行边 |
| `static/app.js` | `onStageStart`/`onStageEnd` 处理并行阶段(index 1/2 同时 active 时加 `parallel-active`) |
| `static/app.css` | 新增 `.parallel-active` 样式(琥珀色圆点 + 浅色文字,区别于主 active 的橙色) |

#### 前端并行 UI

项目中有**两组并行阶段**,前端用 `PARALLEL_GROUPS` 分组管理:

```javascript
const PARALLEL_GROUPS = [
  new Set([1, 2]),    // parse_resume + parse_job
  new Set([3, 4, 5]), // skill_gap + experience + keywords
];
```

当同组内多个步骤同时运行时:
- 先启动的为 `.active`(橙色),其余为 `.parallel-active`(琥珀色)
- 一个完成后,同组其他步骤移除 `parallel-active`,恢复为唯一 `.active`
- 全部完成后,都变为 `.done`

```css
.run-steps li.parallel-active .step-dot {
  background: var(--amber);
  box-shadow: 0 0 6px rgba(255,176,32,0.3);
}
```

> **注意**:初始实现只处理了 index 1/2 的并行,遗漏了 index 3/4/5 的匹配器并行。后改为分组模式,统一支持所有并行组。

#### 踩坑:InvalidUpdateError

`_dispatch_matchers_node` 初始实现返回空 dict `{}`,LangGraph 报错:
```
InvalidUpdateError: Expected node inputs to update at least one of [...], got {}
```
修复:返回 `{"errors": state.get("errors", [])}`,透传已有的 errors 列表。

#### 实测效果

| 节点 | 改造前(串行) | 改造后(并行) |
|---|---|---|
| parse_resume | 14,797ms | 18,468ms |
| parse_job | 12,828ms | 13,671ms |
| **抽取阶段合计** | **27,625ms**(串行相加) | **18,468ms**(取最长) |
| **节省** | — | **~9s** |

两个 DeepSeek API 请求同时发出(日志时间戳相同),确认并行生效。

---

## 5. 验证清单

### 5.1 基础(8 条)

| # | 项 | 命令 | 预期 |
|---|---|---|---|
| 1 | 配置解析 | 见 §2.4 | `deepseek deepseek-v4-flash https://api.deepseek.com True` |
| 2 | 服务启动 | `uvicorn app.main:app --port 8000` | `Uvicorn running on http://0.0.0.0:8000` |
| 3 | 根路径 | `curl.exe http://localhost:8000/` | HTTP 200, ~11.8KB |
| 4 | 健康检查 | `curl.exe http://localhost:8000/api/v1/health` | `{"success":true,"data":{"status":"up"}}` |
| 5 | 元信息 | `curl.exe http://localhost:8000/api/v1/info` | 含 `provider: deepseek` |
| 6 | DeepSeek 连通 | `python -c "from app.extractors.llm_client import LLMClient; print(LLMClient().chat_text(system='只回 ok', user='ping'))"` | `ok` |
| 7 | Swagger | `curl.exe -o nul -w "%{http_code}" http://localhost:8000/docs` | `200` |
| 8 | 全链路 | `curl.exe -F resume=@<file.pdf> -F job_description="..." http://localhost:8000/api/v1/analyze` | `meta.used_provider=deepseek` |

### 5.2 异常(5 条)

| # | 项 | 命令 | 预期 |
|---|---|---|---|
| 9 | 不合法文件类型 | `curl.exe -F resume=@README.md -F job_description=x /api/v1/analyze` | **HTTP 415** `code=unsupported_file_type` |
| 10 | 缺 JD | `curl.exe -F resume=@<pdf> /api/v1/analyze` | HTTP 400 |
| 11 | 不合法 job_file | `curl.exe -F resume=@<pdf> -F job_file=@README.md /api/v1/analyze` | HTTP 415 |
| 12 | GET /api/v1/analyze | `curl.exe /api/v1/analyze` | HTTP 405 |
| 13 | 200KB 简历边界 | `curl.exe -F resume=@<200KB.txt> -F job_description=x /api/v1/analyze` | HTTP 200 |

### 5.3 语义匹配回归(4 条)

| # | 项 | 命令 | 预期 |
|---|---|---|---|
| 14 | 语义匹配(LLM) | `analyze_skill_gap(resume, job, llm_client=LLMClient())` | coverage 0.7-0.9,识别 PgVector ≡ Milvus/Qdrant |
| 15 | 字面匹配(回退) | `analyze_skill_gap(resume, job, force_literal=True)` | 行为不变 |
| 16 | 无 LLM | `analyze_skill_gap(resume, job)` | 行为不变 |
| 17 | 端到端语义 | `curl.exe -F resume=@<pdf> -F job_description="<含向量数据库/求职产品>" /api/v1/analyze` | `overall_score ≥ 70`, `missing ≤ 2` |

### 5.4 前端交互(2 条)

| # | 项 | 步骤 | 预期 |
|---|---|---|---|
| 18 | 上传弹窗 | 刷新页面 → 点击上传区 | 只弹 1 次文件选择器 |
| 19 | 载入示例 | 上传简历 → 点击「载入示例」 | JD 填充,简历保留,Toast 提示 |

> **PowerShell 提示**:`curl` 在 PowerShell 中被别名到 `Invoke-WebRequest`,本项目统一用 `curl.exe` 走真 curl。

### 5.5 端到端 bug 修复回归(6 条)

| # | 项 | 命令 / 步骤 | 预期 |
|---|---|---|---|
| 20 | CSS `[hidden]` 全局规则 | 浏览器 DevTools → `<section id="runError" hidden>` 检查 computed style | `display: none` |
| 21 | 前端 cache-buster | 浏览器开页 → Network 面板查 `app.css` / `app.js` 请求 URL | 都带 `?v=2` |
| 22 | LLMClient 默认 init | `python -c "from app.extractors.llm_client import LLMClient; LLMClient()._progress_callback is None"` | `True` |
| 23 | 同步 `/analyze` 不再 500 | `curl.exe -F resume=@<200KB.txt> -F job_description=x /api/v1/analyze` | **HTTP 200**,含 `match_report.overall_score` |
| 24 | 流式 `done.data` 不再空 | `curl.exe -N -F resume=@<200KB.txt> -F job_description=x /api/v1/analyze/stream` 收尾行 | `match_report` 非 null,`suggestions` ≥ 3 条 |
| 25 | `_showRunView` 不再抛 TypeError | 浏览器控制台 → 点「开始分析」 | 0 个红色 error |

---

## 6. 风险、回滚与安全

### 6.1 风险与对策

| 风险 | 表现 | 对策 |
|---|---|---|
| 真实密钥进版本库 | 密钥泄露 | `.env.example` 一律占位;`.gitignore` 兜底;首次推送后**务必**在 DeepSeek 控制台轮换一次密钥 |
| DeepSeek JSON 稳定性 | `chat_json` 解析失败 | 已有重试 1 次 + `_safe_json_loads` 容错;失败走 `_fallback_suggestions` |
| LLM 抽取偶发 JSON 异常 | workflow_error(500) | `skill_matcher` 已实现 LLM→字面回退;`ResumeExtractor` / `JobExtractor` / `generate_suggestions` 暂无回退 |
| 上传校验 try 块位置回归 | 500 | 已在 §4.3 修复;回归测试 #9 覆盖 |
| PII 误传 | 真实简历 PDF 入库 | `.gitignore` 已新增 `*.pdf` / `*.docx` 规则;若不慎推送,Contents API 立即删除 + filter-repo 清理历史 |
| `github.com` DNS 失败 | git push 超时 | 改用 GitHub Contents API `PUT /repos/.../contents/{path}` 直接以 commit 形式提交 |

### 6.2 一键回滚

| 目标 | 操作 |
|---|---|
| LLM 基座 | `.env` 中 `LLM_PROVIDER=openai` 切回 |
| 技能匹配器(回退字面) | `analyze_skill_gap_node` 中 `llm_client=LLMClient()` → `llm_client=None` |
| 整体版本 | `git checkout <commit_sha>` 回到指定版本 |
| 单个文件 | `git checkout <commit_sha> -- <path>` |

### 6.3 安全策略

- ✅ `.env` 在 `.gitignore` 中
- ✅ 真实 `DEEPSEEK_API_KEY` **不进入版本库**(`HTTP 404` 已验证)
- ✅ 真实简历 PDF **已从 GitHub 撤回**(`commit 60cbb1a` 通过 Contents API 删除)
- ✅ 启动 uvicorn 时 `--no-access-log` 不记录请求 payload
- ✅ 建议在 DeepSeek 控制台**轮换一次 key**(因为曾在本地明文存在过)

---

## 7. GitHub 发布说明

### 7.1 仓库元信息

| 项 | 值 |
|---|---|
| 仓库 | [github.com/cxzrdxy/job-analyzer](https://github.com/cxzrdxy/job-analyzer) |
| 可见性 | Public |
| 默认分支 | `main` |
| 创建方式 | GitHub API + PAT(`POST /user/repos`) |

### 7.2 提交历史

| SHA | 消息 | 变更 |
|---|---|---|
| `63e8340` | `docs: rewrite DEVELOPMENT.md with clearer structure and 30-second overview` | 文档(本版) |
| `3485367` | `docs: add section 12 - front-end interaction fix` | 文档 |
| `7431fb6` | `fix(ui): prevent upload dialog from double-firing` | 前端 |
| `60cbb1a` | `chore: remove sensitive PII (resume PDF)` | PII 清理 |
| `eca424f` | `docs: 扩充 DEVELOPMENT.md 完整记录开发过程` | 文档 |
| `254f51c` | `feat(matcher): 技能差距分析升级为 LLM 语义匹配` | 语义匹配 |
| `91a867e` | `feat: 求职分析智能体 (DeepSeek v4 Flash) 初始版本` | 初版 |

### 7.3 后续发布流程

```bash
git add -A
git commit -m "feat: <描述>"
git push origin main
```

**如果 git push 超时(DNS 异常)**:

```powershell
$headers = @{
    "Authorization" = "token <PAT>"
    "Accept" = "application/vnd.github+json"
    "User-Agent" = "trae-ide"
}
$content = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes((Get-Content path/to/file -Raw)))
$body = @{
    message = "feat: ..."
    content = $content
    branch = "main"
    # 如果是更新:加 "sha" = "<旧文件 sha>"
} | ConvertTo-Json
Invoke-RestMethod -Uri "https://api.github.com/repos/<owner>/<repo>/contents/<path>" -Method Put -Headers $headers -Body $body -ContentType "application/json"
```

---

## 8. 时间线

| 时间 | 事件 |
|---|---|
| 2026-06-04 上午 | 初版上线:DeepSeek v4 Flash 接入 + 着陆页 + `/api/v1/info` |
| 2026-06-04 下午 | 全功能测试 + 发现 500 bug + 修复(`91a867e`) |
| 2026-06-04 晚 | 推到 GitHub(`91a867e` / `254f51c` / `eca424f`) |
| 2026-06-04 晚 | 复测发现语义匹配偏倚,实施 Plan A:LLM 语义匹配升级 |
| 2026-06-04 深夜 | `254f51c` 推送,文档归档 |
| 2026-06-05 上午 | 发现误传 PII(简历 PDF),通过 Contents API 撤回(`60cbb1a`) |
| 2026-06-05 上午 | 前端双触发 / 载入示例清空 修复(`7431fb6`) |
| 2026-06-05 上午 | 文档最终重写 + 推送(`63e8340`) |
| 2026-06-05 下午 | 浏览器端到端复测:`_showRunView` TypeError + 「分析失败」预渲染 + `/analyze` 500 + 流式空数据 四个症状 |
| 2026-06-05 下午 | 根因定位:CSS `[hidden]` 失效 + `_progress_callback` 未初始化 + langgraph 0.2.x `astream` 不发 `__end__` |
| 2026-06-05 下午 | 修复 5 个相关 bug(详见 §4.6),同步 `/analyze` 200、流式 `match_report: 76.4`、`suggestions: 10` |
| 2026-06-05 下午 | 文档整合到 §1 / §4.6 / §5.5 / §8,准备推送至 GitHub |
| 2026-06-06 | LangGraph 并行匹配改造:Send fan-out/fan-in 替代顺序边,三个匹配节点真正并行执行 |
| 2026-06-06 | 流式进度推送改造:token 级实时进度 + asyncio.Queue + 线程安全桥接,前端进度条不再黑盒等待 |
| 2026-06-06 | 并行抽取改造:parse_resume / parse_job 从 START 并行扇出,抽取阶段耗时从串行之和降为取最长者 |

---

**最后更新**:2026-06-06 · 维护者:`cxzrdxy`
