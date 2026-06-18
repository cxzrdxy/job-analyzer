<div align="center">

# 🚀 求职分析智能体

**LangGraph + FastAPI 驱动的简历 ↔ 岗位 JD 智能匹配服务,一键产出可落地的修改建议。**

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2-1C3C3C?logo=langchain&logoColor=white)](https://langchain-ai.github.io/langgraph/)
[![LLM](https://img.shields.io/badge/LLM-DeepSeek%20v4%20Flash-4D6BFE?logo=openai&logoColor=white)](#-切换模型)
[![License](https://img.shields.io/badge/license-MIT-blue)](#-license)

把简历 PDF / DOCX / TXT 和岗位 JD 丢进去,几秒钟得到一份带分数、可解释、可执行的差距分析与改写建议。

[快速开始](#-快速开始) · [核心能力](#-核心能力) · [架构](#-架构) · [API](#-api-参考) · [路线图](#-路线图)

</div>

---

## 📸 运行截图

<div align="center">
  <img src="assets/preview.png" alt="求职分析智能体 - 工作台" width="100%">
  <br>
  <sub>工作台:左提交简历 + JD,右侧实时回显匹配报告与建议。</sub>
</div>

> 也可观看 12 秒的端到端流程演示:[`assets/demo.mp4`](assets/demo.mp4)。

---

## ✨ 核心能力

| 能力 | 说明 |
|---|---|
| 📄 **多格式解析** | PDF / DOCX / TXT 统一走 `extract_text`,输入闭环,无需预处理。 |
| 🧠 **结构化抽取** | 简历 / JD 全部经 LLM `chat_json(schema=…)` 强校验,失败自动重试一次。 |
| 🎯 **轻量化匹配** | 技能 / 经验 / 关键词三层规则匹配,Token 消耗低、可解释。 |
| 🪜 **可降级建议** | LLM 抽取失败时,自动 fallback 到基于匹配证据的启发式建议。 |
| 🔁 **LangGraph 编排** | 8 阶段流式工作流,`trace_id` 全链路可观测,同步 / 流式双通道。 |
| ⚡ **并行执行** | 抽取阶段(parse_resume ∥ parse_job)和匹配阶段(skill_gap ∥ experience ∥ keywords)均并行执行,端到端耗时大幅缩短。 |
| 📊 **Token 级进度** | 流式接口推送 LLM token 级实时进度,前端进度条不再黑盒等待。 |
| 🔌 **Provider 透明** | 默认 DeepSeek v4 Flash,改一行 `.env` 即可切 OpenAI(0 业务代码改动)。 |
| 🛡 **错误分级** | 业务异常(415/413/422/502)与系统异常(500)分别落点,Swagger 友好。 |
| 🎯 **面试题预测**(v0.2+) | 分析完成后可一键生成 8–12 道针对性面试题(技术/行为/项目/情景四类),基于分析缓存避免重复解析。 |
| 🧪 **全流程测试**(v0.3+) | 67 单元测试 + 9 E2E + 30-200 用例压测,真实 LLM,产出版本化质量报告。 |

---

## 🧱 架构

<div align="center">

```mermaid
flowchart LR
  A[POST /analyze] --> B[parsers.text_extractor]
  B --> C[extractors.LLMClient.chat_json]
  C --> D[extractors.resume_extractor]
  C --> E[extractors.job_extractor]
  D & E -->|并行抽取| F[dispatch_matchers · fan-in]
  F -->|fan-out| G1[matchers.skill_gap]
  F -->|fan-out| G2[matchers.experience]
  F -->|fan-out| G3[matchers.keywords]
  G1 & G2 & G3 -->|并行匹配| H[aggregate_report]
  H --> I[generate_suggestions · LLM]
  I --> J[response.match_report + suggestions]
  J --> K[JSON / SSE]
```

</div>

**分层职责**

- `app/parsers/` — 文档 → 文本
- `app/extractors/` — 文本 → 结构化 Pydantic 对象
- `app/matchers/` — 规则匹配(无 LLM 依赖,纯计算)
- `app/workflow/` — LangGraph 状态机 + 节点
- `app/services/analyzer.py` — 业务编排入口
- `app/api/routes.py` — FastAPI 路由

---

## 🚀 快速开始

> **环境约定**:Windows + Miniconda,复用现成的 `fastapi` 环境(Python 3.10.19)。

### 初次运行

```bash
# 1. 激活环境
D:\miniconda\envs\fastapi\Scripts\activate.bat

# 2. 安装依赖
cd <项目根目录>
pip install -r requirements.txt

# 3. 配置环境变量
copy .env.example .env
# 编辑 .env,填入 DEEPSEEK_API_KEY(默认走 DeepSeek v4 Flash)
# 如需切回 OpenAI:LLM_PROVIDER=openai + OPENAI_API_KEY

# 4. 安装并配置 PostgreSQL(面试题预测功能需要)
conda --no-plugins install -n fastapi -c conda-forge postgresql -y --solver=classic
D:\miniconda\envs\fastapi\Library\bin\initdb.exe -D "D:\pgdata" -U postgres -E UTF8 --locale=C
D:\miniconda\envs\fastapi\Library\bin\postgres.exe -D "D:/pgdata" -p 5432   # 前台启动
# 另开终端创建用户和数据库:
D:\miniconda\envs\fastapi\Library\bin\psql.exe -U postgres -h 127.0.0.1 -p 5432 \
  -c "CREATE USER job WITH PASSWORD 'job';" \
  -c "CREATE DATABASE job_analyzer OWNER job;" \
  -c "GRANT ALL PRIVILEGES ON DATABASE job_analyzer TO job;"
D:\miniconda\envs\fastapi\Scripts\alembic.exe upgrade head   # 执行数据库迁移

# 5. 启动服务
uvicorn app.main:app --reload --port 8000
```

### 日常启动

```bash
# 1. 激活环境
D:\miniconda\envs\fastapi\Scripts\activate.bat

# 2. 启动 PostgreSQL(前台进程,关闭终端后需重新启动)
D:\miniconda\envs\fastapi\Library\bin\postgres.exe -D "D:/pgdata" -p 5432

# 3. 启动服务
uvicorn app.main:app --reload --port 8000
```

> PostgreSQL 也可用 Docker:`docker run -d --name job-pg -e POSTGRES_USER=job -e POSTGRES_PASSWORD=job -e POSTGRES_DB=job_analyzer -p 5432:5432 postgres:16-alpine`
> 数据库不可用时主分析流程不受影响,仅面试题预测功能降级。

启动成功后:

| 路径 | 用途 |
|---|---|
| <http://127.0.0.1:8000/> | 美化着陆页 |
| <http://127.0.0.1:8000/docs> | Swagger UI(在线调试) |
| <http://127.0.0.1:8000/api/v1/health> | 健康检查 |
| <http://127.0.0.1:8000/api/v1/info> | 服务元信息(provider / model) |
| <http://127.0.0.1:8000/api/v1/analyze> | 简历 ↔ JD 分析(POST) |
| <http://127.0.0.1:8000/app> | 主分析页面 |
| <http://127.0.0.1:8000/interview> | 面试题预测页面(需 `?trace_id=xxx`) |

---

## 🎯 面试题预测(v0.2+)

分析完成后可一键生成 8–12 道针对性面试题(技术/行为/项目/情景四类),基于 PostgreSQL 缓存避免重复解析。详细设计见 `.trae/documents/PROPOSAL_interview_questions.md`。

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/v1/interview/predict` | 生成面试题(非流式) |
| `POST` | `/api/v1/interview/predict/stream` | 生成面试题(NDJSON 流式) |
| `GET`  | `/api/v1/cache` | 列出所有缓存的分析 |
| `GET`  | `/api/v1/cache/{trace_id}` | 获取单次分析详情 |
| `DELETE` | `/api/v1/cache/{trace_id}` | 删除单次缓存 |

---

## 📡 API 参考

### `POST /api/v1/analyze`

**表单字段**

| 字段 | 必填 | 类型 | 说明 |
|---|:-:|---|---|
| `resume` | ✅ | File | 简历文件(PDF / DOCX / TXT),最大 20 MB |
| `job_description` | ◻ | string | JD 文本(与 `job_file` 二选一) |
| `job_file` | ◻ | File | JD 文件(与 `job_description` 二选一) |
| `trace_id` | ◻ | string | 链路追踪 ID,不传则自动生成 |

**响应**

```json
{
  "success": true,
  "code": "ok",
  "message": "分析完成",
  "data": {
    "meta": {
      "resume_chars": 1200,
      "job_chars": 800,
      "used_provider": "deepseek",
      "used_model": "deepseek-v4-flash"
    },
    "match_report": {
      "overall_score": 78.5,
      "skill_gap": { "matched": [], "missing": [], "partial": [], "coverage": 0.8 },
      "experience": { "score": 0.7, "notes": [] },
      "keywords": { "matched": [], "missing": [], "coverage": 0.6 },
      "hard_requirements_gaps": []
    },
    "suggestions": [
      {
        "type": "content",
        "priority": "high",
        "section": "skills",
        "suggestion": "...",
        "reason": "..."
      }
    ]
  },
  "trace_id": "..."
}
```

### `POST /api/v1/analyze/stream`

SSE 流式输出,逐阶段推送进度(8 个 stage + 1 个 `done` 事件),适合长任务前端可视化。

### `POST /api/v1/interview/predict`

**JSON Body**

| 字段 | 必填 | 类型 | 说明 |
|---|:-:|---|---|
| `trace_id` | ✅ | string | 已完成分析的 trace_id |

**响应**

```json
{
  "success": true,
  "data": {
    "trace_id": "...",
    "interview_questions": {
      "questions": [
        {
          "type": "technical",
          "difficulty": "hard",
          "question": "...",
          "related_skill": "Kubernetes",
          "suggested_answer_direction": "...",
          "follow_up": "..."
        }
      ],
      "summary": "..."
    }
  }
}
```

### `POST /api/v1/interview/predict/stream`

面试题预测的 NDJSON 流式版本,事件格式与 `/analyze/stream` 一致。

### `GET /api/v1/cache`

列出所有缓存的分析记录(分页,`?limit=50&offset=0`)。

### `GET /api/v1/cache/{trace_id}`

获取单次分析的完整缓存数据(含 match_report / suggestions),用于页面状态恢复。

### `DELETE /api/v1/cache/{trace_id}`

删除指定缓存记录。

### `GET /api/v1/health`

```json
{ "success": true, "code": "ok", "message": "ok", "data": { "status": "up" } }
```

---

## 🗂 项目结构

```
job/
├── app/
│   ├── main.py                   # FastAPI 入口 + lifespan + 静态资源
│   ├── api/
│   │   ├── routes.py             # 主分析路由(analyze / stream / health / info)
│   │   └── routes_interview.py   # 面试题预测 + 缓存管理路由
│   ├── core/
│   │   ├── config.py             # provider 感知配置 + DATABASE_URL
│   │   ├── database.py           # SQLAlchemy 2.0 async 引擎 + session 工厂
│   │   ├── cache.py              # 缓存服务(save / load / list / delete)
│   │   ├── errors.py             # AppError 体系 → 4xx/5xx 映射
│   │   ├── logging.py            # 控制台 + 滚动文件日志
│   │   └── metrics.py            # 进程内请求计数/最近日志/平均耗时
│   ├── models/
│   │   ├── resume.py             # ResumeData / ContactInfo / WorkExperience …
│   │   ├── job_requirement.py    # JobRequirement / Requirement …
│   │   ├── suggestion.py         # MatchReport / SkillGapAnalysis / ResumeSuggestion …
│   │   ├── response.py           # ApiResponse[T] / AnalysisResult
│   │   ├── interview.py          # InterviewQuestion / InterviewPredictionOutput
│   │   └── cache.py              # AnalysisCache ORM 模型(JSONB)
│   ├── parsers/
│   │   └── text_extractor.py     # PDF/DOCX/TXT → 文本
│   ├── extractors/
│   │   ├── llm_client.py         # 统一 LLM 客户端(流式 + 回调 + ContextVar/共享变量双轨)
│   │   ├── resume_extractor.py   # 简历结构化抽取
│   │   └── job_extractor.py      # JD 结构化抽取
│   ├── matchers/
│   │   ├── skill_matcher.py      # LLM 语义匹配 + 字面回退
│   │   ├── experience_matcher.py # 规则 + 年限匹配
│   │   └── keyword_matcher.py    # 关键词规则匹配
│   ├── workflow/
│   │   ├── graph.py              # LangGraph 拓扑(Send fan-out/fan-in + 并行抽取)
│   │   ├── state.py              # AgentState + _keep_last reducer
│   │   ├── nodes.py              # 节点实现
│   │   ├── progress.py           # 阶段表 + 线程安全进度回调 + compute_streaming_percent
│   │   └── suggestion_generator.py # 建议生成(LLM + 启发式回退)
│   └── services/
│       ├── analyzer.py           # AnalyzerService(同步 ainvoke + 流式 Queue 模式)
│       └── interview_service.py  # InterviewService(缓存读取 + LLM 面试题生成)
├── alembic/                      # 数据库迁移
│   └── versions/0001_add_analysis_cache.py
├── tests/                        # 全流程测试套件(v0.3+)
│   ├── README.md
│   ├── runner.py                 # 轻量测试运行器(替代 pytest)
│   ├── run_all.py                # 一站式入口(单元 + E2E + 压测)
│   ├── generate_report.py        # 聚合产物 → full_report.md
│   ├── fixtures/                 # 27 简历 + 12 JD 数据集
│   ├── unit/                     # 67 个单元测试(无 LLM)
│   ├── e2e/                      # 9 个 E2E 测试(真实 LLM)
│   └── loadtest/                 # 批量压测脚本
├── static/
│   ├── index.html                # 主分析页面
│   ├── app.js / app.css          # 主页面交互 + 暗色玻璃拟态
│   ├── interview.html            # 面试题预测页面
│   └── interview.js / interview.css
├── uploads/                      # 临时文件目录
├── requirements.txt
├── .env.example
├── Dockerfile
├── README.md                     # 本文档
├── DEVELOPMENT.md                # 开发规范 / 常见任务指引
└── 求职分析智能体设计方案.md     # 设计文档(对齐实现)
```

---

## ⚙️ 切换模型

默认走 DeepSeek v4 Flash,切换 OpenAI 只需改 `.env`:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

业务代码不感知 provider,所有 LLM 调用统一经过 `app/extractors/llm_client.py`。

---

## 🧪 设计要点

- **输入闭环** — 文本和文件走同一 `extract_text` 解析器,逻辑零分叉。
- **强校验输出** — LLM 全部走 `chat_json(schema=...)`,字段缺失会重试一次再降级。
- **双层并行** — 抽取阶段(parse_resume ∥ parse_job)和匹配阶段(skill_gap ∥ experience ∥ keywords)均通过 LangGraph Send fan-out 并行执行。
- **Token 级进度** — 流式接口推送 LLM token 级实时进度,通过 `loop.call_soon_threadsafe` 桥接工作线程与主线程的 asyncio.Queue。
- **分析缓存** — PostgreSQL + JSONB 持久化分析结果,支持跨页面/跨会话复用,面试题预测零重复解析。
- **可降级** — LLM 失败时自动 fallback 启发式建议;数据库不可用时主分析不受影响,缓存层静默降级。
- **可观测** — 全流程 `trace_id`,节点级耗时日志,日志同步输出到控制台 + 文件。

---

## 🧪 测试(v0.3+)

提供三层测试覆盖,默认调用真实 LLM,产出可版本化的质量报告。

| 层级 | 路径 | 用例 | LLM | 速度 |
|---|---|---:|---|---|
| 单元测试 | `tests/unit/` | 67 | ❌ | < 1s |
| E2E 测试 | `tests/e2e/` | 9 | ✅ | ~1 min/条 |
| 批量压测 | `tests/loadtest/` | 30-324 | ✅ | ~12s/条(并发 4) |

### 测试数据规模

- **简历**:`tests/fixtures/resumes.py` 共 27 份,覆盖 9 个细分类目
  - 互联网研发:后端 / 前端 / 算法 / 全栈
  - 数据/分析:数据分析师 / 产品经理
  - 传统行业:金融 / 咨询 / 快消
- **JD**:`tests/fixtures/jobs.py` 共 12 个,覆盖同类目
- **笛卡尔积**:27 × 12 = **324 个组合**,支撑中规模批量压测

### 快速运行

```bash
# 单元测试(秒级)
D:\miniconda\envs\fastapi\python.exe tests/runner.py --tag unit

# E2E 测试(7-10 分钟,真实 LLM)
D:\miniconda\envs\fastapi\python.exe tests/runner.py --tag e2e

# 一站式:单元 + E2E + 50 用例压测
D:\miniconda\envs\fastapi\python.exe tests/run_all.py --loadtest-limit 50 --concurrency 4
```

### 最近一轮压测结果(2026-06-18,30 用例)

| 指标 | 数值 |
|---|---|
| 通过率 | **96.7%** (29/30) |
| 同岗位评分均值 | **56.2** |
| 跨岗位评分均值 | **24.0** |
| 同/跨评分差 | **+32.1 分**(模型有效区分) |
| 综合评分区间 | 10 - 85 |
| 单次分析平均耗时 | 92s(P95 = 188s) |
| 建议数量均值 | 6.4 条(5-8 条 schema) |

### 产物清单

| 路径 | 用途 |
|---|---|
| `tests/output/test_report.json` | 单元测试详细报告 |
| `tests/output/e2e_report.json` | E2E 测试详细报告 |
| `tests/output/loadtest/batch_detail.json` | 压测详细 JSON |
| `tests/output/loadtest/batch_detail.csv` | 压测 CSV(Excel 可打开) |
| `tests/output/loadtest/batch_summary.json` | 压测汇总统计 |
| `tests/output/full_report.md` | **一站式 Markdown 总报告** |

详细使用文档见 [`tests/README.md`](tests/README.md)。

---

## 📦 本次更新要点(2026-06-18)

### 后端工作流(workflow/)

| 模块 | 改动 |
|---|---|
| [app/workflow/nodes.py](file:///C:/Users/10408/Desktop/job/app/workflow/nodes.py) | 新增 `aggregate_report_node` 的 `_llm_score` 评分,带 `LLMScoreOutput` Pydantic Schema + `clamp_score` 校验;`generate_suggestions_node` 双层 fallback(LLM 失败 → 规则建议);**彻底移除 `eval`,消除 v0.2 安全风险** |
| [app/workflow/suggestion_generator.py](file:///C:/Users/10408/Desktop/job/app/workflow/suggestion_generator.py) | 强结构化 prompt:`current`/`example`/`reason`/`suggestion` 字段非空,合并缺失关键词,约束 5-8 条;新增 `_build_resume_text` / `_build_job_text` 模板化输入;`_fallback_suggestions` 启发式覆盖三类缺口 |
| [app/workflow/graph.py](file:///C:/Users/10408/Desktop/job/app/workflow/graph.py) | 新增 `_with_stage_tracking` 装饰器 + `_dispatch_matchers_node` fan-in 汇聚点,所有节点注册统一套用包装器,把 LangGraph 节点与 progress 系统的 stage 打通 |
| [app/workflow/progress.py](file:///C:/Users/10408/Desktop/job/app/workflow/progress.py) | 从 ContextVar 改为 `Lock + 模块级变量`,解决 LangGraph `astream` 跨线程进度回调问题;新增 `StageDef` 数据类与 8 阶段表,`compute_streaming_percent` 字符数→百分比映射 |

### 后端抽取层(extractors/)

| 模块 | 改动 |
|---|---|
| [app/extractors/llm_client.py](file:///C:/Users/10408/Desktop/job/app/extractors/llm_client.py) | 新增 `chat_text()` 纯文本接口;`chat_json()` 支持 `max_retries + progress_callback` 关键字参数;新增 `_invoke_stream()` 流式核心 + 三阶段回调(`first_token` / `streaming` / `error`),首 chunk + 每 80 字符触发;`_safe_json_loads` 支持 ```json``` 包裹、文本嵌套、前后解释三种边界 |

### 后端服务层 + 数据层

| 模块 | 改动 |
|---|---|
| [app/services/analyzer.py](file:///C:/Users/10408/Desktop/job/app/services/analyzer.py) | 同步 `analyze` 与流式 `analyze_stream` 入口分离,统一走 `_persist_cache` 后台写缓存;流式入口用 `asyncio.Queue` + 后台任务 + `loop.call_soon_threadsafe` 串联 LangGraph 节点事件与 LLM token 进度 |
| [app/models/suggestion.py](file:///C:/Users/10408/Desktop/job/app/models/suggestion.py) | 新增 `ResumeSection` 枚举(SKILLS/WORK_EXPERIENCE/PROJECT 等 7 项);`ResumeSuggestion` 增加 `section` / `current` / `example` / `related_jd_requirement` 字段;新增 `SuggestionListOutput` Pydantic Schema 约束 5-8 条 |
| [app/core/cache.py](file:///C:/Users/10408/Desktop/job/app/core/cache.py) | 精简实现;list 接口只 SELECT 摘要列避免反序列化 JSONB;`safe_save_analysis` 保留数据库不可用时降级语义 |
| [app/main.py](file:///C:/Users/10408/Desktop/job/app/main.py) | `lifespan` 新增数据库 session factory 初始化(失败仅 warning 不阻塞),关闭时 `close_db` |
| [app/api/routes_interview.py](file:///C:/Users/10408/Desktop/job/app/api/routes_interview.py) | 面试题流式入口透传 `set_current_stage`,使 LLMClient 在工作线程中能查到 stage 上下文 |

### 前端(static/)

| 模块 | 改动 |
|---|---|
| [static/index.html](file:///C:/Users/10408/Desktop/job/static/index.html) | 报告顶部新增 CTA 操作栏(基于此报告生成面试题按钮);中间列嵌入完整运行态视图(8 步步骤列表 + 进度条 + 状态条 + 错误态) |
| [static/app.css](file:///C:/Users/10408/Desktop/job/static/app.css) | 顶部新增 `[hidden]{display:none !important}` 兜底;运行态容器、计时器、进度条(橙→亮橙渐变)、步骤四种状态点(active / parallel-active / done / error);历史面板 + 报告顶部 CTA 渐变按钮;toast `@keyframes toast-in` 上滑入场 |
| [static/app.js](file:///C:/Users/10408/Desktop/job/static/app.js) | **历史面板子系统**:`injectHistoryPanel()` + `_loadHistory()` + `_highlightActiveInHistory()` + `_loadHistoricalReport()`;**流式分析核心**:`streamAnalyze()` 拉 `/api/v1/analyze/stream` 按 NDJSON 分发 6 类事件;**并行阶段组** `PARALLEL_GROUPS = [{1,2}, {3,4,5}]` 用琥珀色 `.parallel-active` 区分;**降级策略**:流式失败 → 同步接口兜底;**页面状态恢复**:`sessionStorage.last_trace_id` + URL `?trace_id=` 双轨 |

### 前后端贯通关键契约

| 字段 | 流向 | 用途 |
|---|---|---|
| `trace_id` | URL / sessionStorage / 跳转 CTA / 历史面板项 | **前后端共用主键**,刷新恢复 / 跨页跳转 / 复看历史 |
| `/api/v1/analyze/stream` NDJSON 事件 | `meta` / `stage_start` / `progress` / `stage_end` / `done` / `error` | 前端严格按类型分发,驱动运行态视图 |
| `/api/v1/cache?limit=50` | 后端 → 前端 | 历史面板数据源 |
| `/api/v1/cache/{trace_id}` | 后端 → 前端 | 单条报告回放(URL 持久化) |

---

## 🛣 路线图

- [x] **全流程测试套件**(v0.3) — 67 单元 + 9 E2E + 批量压测,产出 Markdown 质量报告
- [ ] 简历 ↔ JD 多对多批量匹配
- [ ] 建议生成多轮 LLM 反思(自评 + 改写)
- [ ] 引入本地向量库,支持"先按公司聚类再分析"
- [ ] Dockerfile 多阶段构建 + GitHub Actions CI
- [ ] 前端拆为独立 Vite + React 项目,后端仅作 API

---

## 📄 License

MIT
