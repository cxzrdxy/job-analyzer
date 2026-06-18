# 开发文档 · Job Analyzer

> 本文档面向**接手维护的工程师**,用 5 分钟说明本项目是什么、怎么跑、改了什么、为什么改、出问题怎么排查。
>
> 仓库:[github.com/cxzrdxy/job-analyzer](https://github.com/cxzrdxy/job-analyzer)

---

## 📌 最新变更(2026-06-18)

### v0.3 — 三线并发更新

| 线 | 关键变化 | 详见 |
|---|---|---|
| 🧪 **测试套件** | `tests/` 67 单元 + 9 E2E + 30 用例压测,真实 LLM,Markdown 报告 | §4.12 |
| ⚙️ **后端 workflow / extractors** | 移除 `eval`、新增流式回调、进度共享、强结构化 prompt + fallback | §4.13 |
| 🎨 **前端运行态 + 历史面板** | 8 步骤进度视图、`sessionStorage` + URL `?trace_id=` 双轨状态恢复、报告顶部 CTA | §4.14 |
| 🔗 **前后端契约** | `trace_id` 主键贯穿 URL / sessionStorage / 跳转 / 历史;NDJSON 6 类事件 | §4.15 |

**质量基线**(2026-06-18,30 用例压测):通过率 **96.7%**,同岗位评分 56.2 vs 跨岗位 24.0(差 +32.1),单次分析 avg 92s。

**已知 P1**:`aggregate_report` 节点旧 `eval` 路径在 LLM 输出含 `List[...]` 字面量时 `NameError`(本次改造已移除 `eval`,待回归验证)。

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
  - [4.10 面试题预测:独立页面 + 持久化缓存](#410-面试题预测独立页面--持久化缓存)
  - [4.11 工作台持久化 + 面试台贯通(本次更新)](#411-工作台持久化--面试台贯通本次更新)
- [4.12 全流程测试套件(v0.3+)](#412-全流程测试套件v03)
- [4.13 后端 workflow / extractors 改造(2026-06-18)](#413-后端-workflow--extractors-改造2026-06-18)
- [4.14 前端运行态视图 + 历史面板贯通(2026-06-18)](#414-前端运行态视图--历史面板贯通2026-06-18)
- [4.15 前后端契约:trace_id 与 NDJSON 事件流(2026-06-18)](#415-前后端契约trace_id-与-ndjson-事件流2026-06-18)
- [5. 验证清单](#5-验证清单)
- [6. 风险、回滚与安全](#6-风险回滚与安全)
- [7. GitHub 发布说明](#7-github-发布说明)
- [8. 时间线](#8-时间线)

---

## 0. 30 秒速览

| 项 | 值 |
|---|---|
| 项目类型 | FastAPI + LangGraph 求职分析智能体 |
| 主要能力 | 简历 PDF / DOCX / TXT + JD 文本 → 技能匹配度 + 优化建议 + 预测面试题 + **历史报告回看(URL 持久化)** |
| LLM 基座 | **DeepSeek v4 Flash**(`provider=deepseek`,可通过 `.env` 切回 OpenAI) |
| 默认端口 | `http://localhost:8000` |
| 前端应用 | `http://localhost:8000/app` · 面试题预测 `http://localhost:8000/interview` |
| API 文档 | `http://localhost:8000/docs` |
| 核心依赖 | FastAPI 0.115 / Pydantic 2.9 / LangGraph 0.2.53 / langchain-openai 0.2.9 / **SQLAlchemy 2.0 async + asyncpg + alembic** |
| Python 环境 | `D:\miniconda\envs\fastapi` (Python 3.10.19) |
| 数据持久化 | PostgreSQL 16(可选,缓存/面试题;不可用时主分析正常) |

**最常用的 URL**:
- `GET /` — 运维监控着陆页(深色玻璃拟态,显示 BOOT 日志、stats、provider/model 徽章)
- `GET /app` — 用户使用的前端应用(上传简历 + 粘贴 JD + 一键分析)
- `GET /interview` — 面试题预测页面(基于 `?trace_id=xxx` 加载分析摘要)

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
| 17 | 面试题预测(独立页面 + 缓存层 + 工作流零改动) | `app/services/interview_service.py`、`app/api/routes_interview.py`、`app/core/database.py`、`app/core/cache.py`、`app/models/interview.py`、`app/models/cache.py`、`alembic/`、`static/interview.{html,css,js}`、`static/{index.html,app.js,app.css}`、`app/main.py`、`app/services/analyzer.py` | ✅ |
| 18 | 工作台持久化:历史记录面板 + 报告 CTA 跳转 + 面试台 trace_id 兜底表单 | `app/api/routes_interview.py`、`static/{app,interview}.{js,html,css}` | ✅ |
| 19 | Bug 修复:面试台 `renderSummary` 读错字段(`job.title` → `job.position`) | `static/interview.js` | ✅ |

**业务代码改动(累计)**:
- 后端:7 个新文件 + 4 个改文件 — 新增 `interview_service.py` / `routes_interview.py` / `database.py` / `cache.py` / `models/interview.py` / `models/cache.py` / `alembic/`;改 `main.py` / `analyzer.py` / `core/config.py` / `core/errors.py`
- 前端:3 个新文件 + 3 个改文件 — 新增 `interview.html` / `interview.css` / `interview.js`;改 `index.html` / `app.js` / `app.css`
- 配置/文档:5 个文件 — `requirements.txt` / `.env.example` / `README.md` / `DEVELOPMENT.md` / `求职分析智能体设计方案.md`

---

## 2. 快速开始(本地启动)

### 2.1 前置

- Python 3.10
- 已激活环境:`D:\miniconda\envs\fastapi`
- 在项目根目录 `.env` 中有有效 `DEEPSEEK_API_KEY`(或 `OPENAI_API_KEY`)
- **可选**:PostgreSQL 16(用于面试题预测的分析缓存;不安装也不影响主分析)

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

# ---- 数据库(面试题预测 / 缓存) ----
# 主分析不需要这条;启动时检测到无 asyncpg/PG 时会降级跳过缓存
DATABASE_URL=postgresql+asyncpg://job:job@localhost:5432/job_analyzer
CACHE_TTL_DAYS=7
```

> **安全提醒**:`.env` 已在 `.gitignore` 中,不会进入版本库。Key 只在本地生效。

### 2.5 可选:启动 PostgreSQL(面试题预测)

```bash
# 方式 A:Docker 快速跑一个(推荐)
docker run -d --name job-pg -e POSTGRES_USER=job -e POSTGRES_PASSWORD=job \
  -e POSTGRES_DB=job_analyzer -p 5432:5432 postgres:16-alpine

# 方式 B:本机已装 PostgreSQL,创建用户和库后跳过
```

初始化数据库表(只跑一次):

```bash
alembic upgrade head
# 预期: Running upgrade  -> 0001_add_analysis_cache
```

**降级行为**:
- 没装 `asyncpg` → 主分析正常,缓存/面试题端点返回 `503 cache_unavailable`
- 没启 PostgreSQL → 启动时日志警告 `数据库不可用,缓存层降级`,主分析正常,缓存写入静默失败
- 启动后数据库恢复 → 下次分析自动写入缓存(无需重启)

---

## 3. 项目结构

```
c:\Users\10408\Desktop\job\
├── app/                                # ★ FastAPI 后端
│   ├── main.py                         # 应用工厂 + GET / + GET /app + GET /interview + 路由注册
│   ├── api/
│   │   ├── routes.py                   # /api/v1/analyze + /api/v1/info + /api/v1/health
│   │   └── routes_interview.py         # ★ 面试题预测 + 缓存管理 API
│   ├── core/
│   │   ├── config.py                   # provider 感知 + base_url 映射 + DatabaseSettings
│   │   ├── errors.py                   # AppError 体系(新增 NotFoundError)
│   │   ├── database.py                 # ★ SQLAlchemy 2.0 async 引擎 + session 工厂
│   │   ├── cache.py                    # ★ 分析缓存服务:save/load/list/delete/cleanup
│   │   └── logging.py
│   ├── parsers/
│   │   └── text_extractor.py           # PDF/DOCX/TXT 文本提取
│   ├── extractors/
│   │   ├── llm_client.py               # DeepSeek/OpenAI 客户端
│   │   ├── resume_extractor.py         # LLM 结构化抽取简历
│   │   └── job_extractor.py            # LLM 结构化抽取 JD
│   ├── workflow/                       # LangGraph 工作流(本次未改动)
│   │   ├── graph.py
│   │   ├── state.py
│   │   ├── nodes.py
│   │   └── suggestion_generator.py
│   ├── matchers/
│   │   ├── skill_matcher.py            # LLM 语义匹配(字面回退)
│   │   ├── experience_matcher.py
│   │   └── keyword_matcher.py
│   ├── models/                         # Pydantic 数据模型
│   │   ├── resume.py / job_requirement.py / suggestion.py / response.py
│   │   ├── interview.py                # ★ 面试题数据模型
│   │   └── cache.py                    # ★ AnalysisCache ORM
│   └── services/
│       ├── analyzer.py                 # ★ 主分析入口(末尾写入缓存)
│       └── interview_service.py        # ★ 面试题预测服务
│
├── alembic/                            # ★ 数据库迁移
│   ├── env.py                          # 异步迁移环境
│   ├── script.py.mako                  # 迁移模板
│   └── versions/
│       └── 0001_add_analysis_cache.py  # 初始迁移
├── alembic.ini                         # ★ Alembic 配置
│
├── static/                             # ★ 前端
│   ├── app.js                          # 上传/分析交互(末尾添加预测 CTA)
│   ├── app.css                         # 共享设计令牌 + predict-cta 样式
│   ├── index.html                      # GET /app 入口(添加 predict CTA 区域)
│   ├── interview.html                  # ★ 面试题预测页面
│   ├── interview.css                   # ★ 页面专属样式
│   └── interview.js                    # ★ 页面交互(URL trace_id → NDJSON 渲染)
│
├── .env                                # 本地密钥(已 gitignore)
├── .env.example                        # 密钥占位模板(含 DATABASE_URL)
├── .gitignore
├── requirements.txt                    # 新增 sqlalchemy/asyncpg/alembic
├── Dockerfile
├── README.md                           # 更新:增加面试题章节
├── DEVELOPMENT.md                      # 本文档
└── 求职分析智能体设计方案.md           # 主方案设计
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

### 4.10 面试题预测:独立页面 + 持久化缓存

#### 背景

主分析完成后,用户希望立即看到「如果我去面试这家公司,会被问什么题」。直接复用分析结果生成面试题,比再传一遍简历+JD 让 LLM 推理更精准(LLM 已有结构化数据可用,无信息损耗)。

#### 设计目标

| 目标 | 决策 |
|---|---|
| 工作流影响 | **零改动**(`graph.py` 不动) |
| 数据来源 | 主分析完成后中间结果自动入库 |
| 入口 | 独立页面 `/interview`,与 `/app` 解耦 |
| 端点 | `/api/v1/interview/predict[/stream]`(独立,不复用 `/analyze`) |
| 数据库 | PostgreSQL 16 + JSONB(必填) |
| 失败降级 | DB 不可用时主分析正常,缓存层静默失败 |

#### 4.10.1 缓存层设计(`cache.py` + `cache.py:ORM`)

**为什么选 PostgreSQL+JSONB 而不是 SQLite?**
- 列表查询需要 `JSONB` 上做表达式索引(待二期 RAG 扩展)
- SQLAlchemy 2.0 async + asyncpg 性能优于 aiosqlite
- 与生产部署对齐(避免本地 SQLite / 生产 PG 行为分裂)

**表结构** `app/models/cache.py`:

```python
class AnalysisCache(Base):
    __tablename__ = "analysis_cache"
    trace_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # 标量摘要(列表查询无需反序列化 JSONB)
    resume_name: Mapped[Optional[str]] = mapped_column(String(200))
    job_title: Mapped[Optional[str]] = mapped_column(String(200))
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
    # 完整数据(JSONB)
    resume_data: Mapped[Optional[dict]] = mapped_column(JSONB)
    job_requirement: Mapped[Optional[dict]] = mapped_column(JSONB)
    match_report: Mapped[Optional[dict]] = mapped_column(JSONB)
    suggestions: Mapped[Optional[list]] = mapped_column(JSONB)
    meta: Mapped[Optional[dict]] = mapped_column(JSONB)
    __table_args__ = (
        Index("ix_analysis_cache_created_at", "created_at"),
        Index("ix_analysis_cache_job_title", "job_title"),
    )
```

**为什么标量摘要 + JSONB 双轨?**
- 列表页 `GET /api/v1/cache` 只返回 trace_id / 时间 / 候选人 / 岗位 / 综合分 5 个字段
- 如果全存 JSONB,每条记录要反序列化 4 个 JSONB 字段(整体~5KB),分页 50 条 = 250KB → 50ms+
- 拆出标量后,单条记录只读 ~50 字节,分页 50 条 < 5KB → 5ms
- 详情页 `GET /api/v1/cache/{trace_id}` 才读 JSONB,只有用户点进去才付代价

**服务接口** `app/core/cache.py`:

| 函数 | 用途 | 失败行为 |
|---|---|---|
| `save_analysis(session, trace_id, ...)` | 写入/覆盖一条缓存 | raise |
| `load_analysis(session, trace_id)` | 读完整数据(给面试题用) | 返回 None |
| `load_summary(session, trace_id)` | 读标量摘要(给列表/详情页用) | 返回 None |
| `list_analyses(session, limit, offset)` | 分页列表 | raise |
| `delete_analysis(session, trace_id)` | 删除一条 | raise |
| `cleanup_expired(session, ttl_days)` | 清理过期 | raise |
| **`safe_save_analysis(trace_id, ...)`** | 降级包装:DB 不可用时**不抛** | **返回 False,日志 warning** |

#### 4.10.2 集成进 analyzer(零侵入)

`analyze()` 和 `analyze_stream()` 末尾各加一个 `_persist_cache()` 调用:

```python
# app/services/analyzer.py
def _persist_cache(trace_id: str, final_state: Optional[dict]) -> None:
    """分析完成后把中间结果写入缓存(异步后台任务)."""
    if final_state is None:
        return
    resume_data = _dump_model(final_state.get("resume_data"))
    job_requirement = _dump_model(final_state.get("job_requirement"))
    match_report = _dump_model(final_state.get("match_report"))
    suggestions = [s.model_dump() if hasattr(s, "model_dump") else s
                   for s in (final_state.get("suggestions") or [])]

    async def _do():
        await safe_save_analysis(
            trace_id,
            resume_data=resume_data,
            job_requirement=job_requirement,
            match_report=match_report,
            suggestions=suggestions,
            meta={"provider": ..., "model": ...},
        )

    # 后台写入,不阻塞主流程
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_do())
    except RuntimeError:
        pass  # 同步入口无 loop,跳过
```

**关键设计**:
- `loop.create_task(_do())` 不 await,主流程返回时缓存可能还在写,但用户感知不到
- DB 故障在 `safe_save_analysis` 内部 `except Exception: logger.warning(...)`,主流程完全无感
- Pydantic v2 的 `model_dump()` 在提取层用,dict 在缓存层用,统一在 `_dump_model` 适配

#### 4.10.3 面试题服务(`interview_service.py`)

**核心思路**:
1. 读缓存 → 拿到结构化 `resume_data` / `job_requirement` / `match_report`(全是 dict,无需再调抽取 LLM)
2. 构造针对性 prompt,把 missing/partial 技能、JD 硬技能、项目经历精简化后塞入
3. **只调 1 次 LLM** 生成 8–12 道题,LLMClient 自动重试 1 次

**prompt 设计要点** `app/services/interview_service.py`:

| 维度 | 规则 |
|---|---|
| 总数 | 8–12 道 |
| 分类比例 | 技术 4–6 + 行为 2–3 + 项目深挖 2–3 + 情景 0–1 |
| 难度分配 | missing → hard · partial → medium/hard · matched → easy(仅补量) |
| 必含字段 | category / difficulty / question / intent / suggested_answer_direction |
| 选填字段 | related_skill(关联技能缺口) · related_jd_requirement(关联 JD 原文) |
| 措辞 | 面试官口吻,具体有深度,< 100 字 |
| 答题方向 | 3–5 个关键要点,**非完整答案** |

**服务签名**:
```python
class InterviewService:
    def __init__(self, llm: Optional[LLMClient] = None): ...
    async def predict(self, trace_id: str) -> dict:
        # 1. 读缓存(NotFoundError if 不存在)
        # 2. 构造 prompt
        # 3. LLM.chat_json(schema=InterviewPredictionOutput, max_retries=1)
        # 4. 返回 {"trace_id": ..., "interview_questions": {...}}
```

#### 4.10.4 API 设计

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/v1/interview/predict` | 非流式(等 LLM 完成一次性返回) |
| `POST` | `/api/v1/interview/predict/stream` | NDJSON 流式(与主分析同事件格式) |
| `GET`  | `/api/v1/cache` | 列表(分页) |
| `GET`  | `/api/v1/cache/{trace_id}` | 单条摘要 |
| `DELETE` | `/api/v1/cache/{trace_id}` | 删除单条 |
| `DELETE` | `/api/v1/cache` | 清理过期(基于 CACHE_TTL_DAYS) |

**流式事件格式**(与 `/analyze/stream` 对齐):

```json
{"type":"meta","trace_id":"...","stages":[...]}
{"type":"stage_start","stage":"predict"}
{"type":"progress","stage":"predict","percent":10,"message":"读取分析缓存…"}
{"type":"progress","stage":"predict","percent":45,"message":"LLM 已生成 1200 字符"}
{"type":"progress","stage":"predict","percent":100,"message":"生成完成"}
{"type":"stage_end","stage":"predict"}
{"type":"done","data":{"trace_id":"...","interview_questions":{...}},"duration_ms":12345}
```

**错误码映射**:

| 异常 | HTTP | code |
|---|---|---|
| DB 不可用(未装 asyncpg/未启 PG) | 503 | `cache_unavailable` / `service_unavailable` |
| trace_id 不存在或已过期 | 404 | `not_found` |
| LLM 输出无法解析(重试 1 次后仍失败) | 500 | `extract_error` |

#### 4.10.5 前端页面(`interview.{html,css,js}`)

**页面布局**(单页 SPA 风格):报头 → 摘要卡 → 启动区 → 进度条(生成中) → 分类卡(技术/行为/项目/情景) → 备考建议。

**JS 关键点** `static/interview.js`:

- 入口:URL `?trace_id=xxx` → `GET /api/v1/cache/{trace_id}` 拉摘要
- 降级:无 trace_id / 缓存不存在 → 显示"请先在分析台完成分析"卡 + "前往分析台" CTA
- 流式:复用 NDJSON 消费模式(与 `app.js` 的 `consumeStream` 同构)
- 渲染:固定 4 类顺序(技术 → 行为 → 项目 → 情景),空类自动跳过
- 交互:分类卡默认展开,点头部可折叠;`details` 元素展开意图/答题方向
- 模板:用 `<template>` + `cloneNode` 复用 DOM 模板(避免 innerHTML 注入)

**主页面入口** `static/index.html`:

报告尾部新增 CTA 区(分析完成后由 `app.js` 渲染时显示):

```html
<section class="predict-cta" id="predictCta" hidden>
  <div class="pcta-ico">🎯</div>
  <div class="pcta-body">
    <h3>预测面试题</h3>
    <p>基于本次分析结果,生成 8–12 道针对性面试题…</p>
  </div>
  <a class="pcta-btn" id="predictBtn" href="#">前往预测 →</a>
</section>
```

`app.js` 报告渲染完成时:
```js
if (predictCta && predictBtn && traceId) {
  predictBtn.href = `/interview?trace_id=${encodeURIComponent(traceId)}`;
  predictCta.hidden = false;
}
```

#### 4.10.6 关键设计决策对照

| 决策 | 备选 | 理由 |
|---|---|---|
| 独立页面 `/interview` | 嵌入主报告尾部 | 题目量大(8–12 道),独立 URL 便于分享/刷新/独立调试 |
| 独立 API `/interview/predict` | 复用 `/analyze` | 复用 analyze 必须传完整文件,缓存 + 一次 LLM 优势尽失 |
| `safe_save_analysis` 降级 | 主流程 try/except | 业务异常语义清晰:DB 不可用 ≠ 主分析失败 |
| JSONB 存完整数据 | 每字段一列 | Pydantic 模型字段多且演进频繁,JSONB 避免列爆炸 |
| 标量摘要 + JSONB 双轨 | 全 JSONB | 列表页性能差(250KB → 5KB 优化) |
| 后台 `create_task` 写缓存 | 同步 `await save` | 不阻塞主流程返回,DB 慢也不影响用户体验 |
| 流式端点用 queue + 后台线程 | 改成同步 | 与主分析接口事件格式一致,前端可复用 NDJSON 消费代码 |
| 缓存端点失败时返 503 | 返 500 | 业务语义明确:`cache_unavailable` 是临时性,可重试 |

#### 4.10.7 端到端冒烟测试结果

| # | 端点 | DB 不可用 | DB 可用 | 期望 |
|---|---|---|---|---|
| 1 | `GET /app` | 200 | 200 | 主分析入口(原功能不变) |
| 2 | `GET /interview` | 200 | 200 | 预测页面(新) |
| 3 | `GET /interview?trace_id=不存在` | 200(降级提示) | 200(降级提示) | 显示"请先在分析台分析" |
| 4 | `POST /api/v1/interview/predict` | **503** | 200 | DB 不可用时降级,可用时正常 |
| 5 | `POST /api/v1/interview/predict/stream` | 200(NDJSON error) | 200(NDJSON done) | 流式事件正确 |
| 6 | `GET /api/v1/cache` | **503** | 200 | 列表分页 |
| 7 | `GET /api/v1/cache/{id}` | 503 | 200 / 404 | 摘要/不存在 |
| 8 | `DELETE /api/v1/cache/{id}` | 503 | 200 / 404 | 删除 |
| 9 | `DELETE /api/v1/cache` | 503 | 200 | 清理过期 |
| 10 | `GET /api/v1/health` | 200 | 200 | 主分析(原功能不变) |
| 11 | `POST /api/v1/analyze` | 200 | 200 | **主分析不受 DB 状态影响** |

**核心降级验证**(DB 不可用):

```
2026-06-10 17:52:03 | INFO    | app.main | 应用启动: 求职分析智能体 v0.2.0
2026-06-10 17:52:03 | WARNING | app.main | 数据库不可用,缓存层降级(不影响主分析): No module named 'asyncpg'
```

启动日志明示降级,主分析端点仍正常返回,符合设计预期。

---

### 4.11 工作台持久化 + 面试台贯通(本次更新)

#### 背景

上一版(§4.10)只让数据库"有数据",但**没有把数据用起来**。用户实际反馈的两个问题:

| 症状 | 根因 |
|---|---|
| 「点面试台时岗位显示『未指定岗位』」 | `interview.js` 用错字段名(`job.title` 不存在,真实字段是 `job.position`) |
| 「工作台看不到历史,刷新就没了」 | 完全没有 UI 入口,前端从未调过 `GET /api/v1/cache`;`/api/v1/cache/{trace_id}` 也只返回 5 字段摘要,前端拿不到完整数据 |
| 「分析完跳面试台失败」 | `/interview` 没 trace_id 时只显示"请先分析"卡,**死路** |

#### 4.11.1 后端:`/api/v1/cache/{trace_id}` 改全量返回

**修改前**(只返 5 字段摘要):
```json
{
  "trace_id": "...",
  "created_at": "...",
  "resume_name": "张三",
  "job_title": "Python 后端工程师",
  "overall_score": 64.1
}
```

**修改后**(返 `load_analysis` 全量,嵌套结构):
```json
{
  "trace_id": "...",
  "created_at": "...",
  "resume_data": { "name": "张三", "skills": [...], ... },
  "job_requirement": { "position": "Python 后端工程师", "hard_skills": [...], ... },
  "match_report": { "overall_score": 64.1, "skill_gap": {...}, ... },
  "suggestions": [...],
  "meta": { "provider": "deepseek", "model": "deepseek-v4-flash" }
}
```

**实现** [app/api/routes_interview.py:305-321](file:///c:/Users/10408/Desktop/job/app/api/routes_interview.py#L305):

```python
@router.get("/cache/{trace_id}")
async def get_cache(trace_id: str):
    """获取单次分析的全量数据(resume_data / job_requirement / match_report / suggestions / meta)."""
    try:
        factory = get_session_factory()
        async with factory() as session:
            data = await load_analysis(session, trace_id)  # ← 改这里
    except Exception as exc:
        raise HTTPException(status_code=503, detail={...})
    if data is None:
        raise HTTPException(status_code=404, detail={...})
    return ApiResponse(success=True, data=data)
```

**权衡**:`load_summary` 暂时没人用但保留(后端零成本兼容),避免破坏其他端点。

#### 4.11.2 前端:工作台历史记录面板

**设计目标**:
- 历史数据**自动可见**(用户打开 `/app` 就能看到过去跑过的报告)
- 加载历史报告**无需重新调用 LLM**(直接调 `/api/v1/cache/{trace_id}` 拿全量)
- 报告可**通过 URL 定位**(刷新/分享都能还原)
- 当前报告项**高亮**

**实现** [static/app.js:137-239](file:///c:/Users/10408/Desktop/job/static/app.js#L137):

1. **面板注入**:在 `col-main` 最顶端(`#empty` / `#runView` / `#report` 之上)动态插入 `<section class="history-panel">`。
2. **数据拉取**:`_loadHistory()` → `GET /api/v1/cache?limit=50` → 渲染每条为 `.hp-item`。
3. **点击加载**:`.hp-item` 的 click 事件 → `_loadHistoricalReport(traceId)` → `GET /api/v1/cache/{traceId}` → 调现有 `renderReport(data, traceId, "—")` 渲染。
4. **URL 持久化**:加载后 `history.replaceState({}, "", "?trace_id=xxx")`;启动时检查 URL 自动还原。
5. **当前高亮**:`_highlightActiveInHistory()` 在 `_loadHistory` 末尾 + `renderReport` 末尾调用,当前报告项加 `.is-active`(绿色左边框)。

**样式** [static/app.css:383-450](file:///c:/Users/10408/Desktop/job/static/app.css#L383):

- 卡片式布局,深色背景与项目主色一致
- 分数颜色:≥80 绿 / ≥60 琥珀 / <60 红
- 当前项绿色左边框 + 浅绿底色
- 滚动:`max-height: 220px` + `overflow-y: auto`

#### 4.11.3 前端:报告顶部"生成面试题"跳转按钮

**位置**:在 `#report` 容器**最顶端**(`<header class="report-head">` 之上),作为醒目操作栏。

**HTML 占位** [static/index.html:138-141](file:///c:/Users/10408/Desktop/job/static/index.html#L138):

```html
<article class="report" id="report" hidden>
  <div class="report-actions" id="reportActions" hidden>
    <a class="btn-iv" id="btnGoInterview" href="#">🎯 基于此报告生成面试题 →</a>
  </div>
  <header class="report-head">...</header>
  ...
</article>
```

**JS 绑定** [static/app.js:407-413](file:///c:/Users/10408/Desktop/job/static/app.js#L407):

```js
_currentTraceId = traceId || data.trace_id || null;
if (_currentTraceId) {
  $("#btnGoInterview").href = `/interview?trace_id=${encodeURIComponent(_currentTraceId)}`;
  $("#reportActions").hidden = false;
}
```

**样式**:`.btn-iv` 用主橙色 `--orange`,带 hover 亮度变化,符合 CTA 视觉惯例。

#### 4.11.4 前端:面试台无 trace_id 兜底表单

**修改前**(死路):
```html
<section id="fallback">
  <p>请先在分析台完成分析</p>
  <a href="/app">前往分析台</a>
</section>
```

**修改后**(给 trace_id 输入框):
```html
<section id="fallback">
  <p id="fallbackMsg">...</p>
  <form id="traceForm">
    <input id="traceInput" placeholder="例如:68454ea0-..." />
    <button>加载 →</button>
  </form>
  <div>不知道 trace_id?回 <a href="/app">/app</a> 工作台历史面板点击任一条报告即可。</div>
</section>
```

**JS 提交** [static/interview.js:79-97](file:///c:/Users/10408/Desktop/job/static/interview.js#L79):

```js
form.addEventListener("submit", (e) => {
  e.preventDefault();
  const v = $("#traceInput").value.trim();
  if (!v) return;
  const url = new URL(location.href);
  url.searchParams.set("trace_id", v);
  location.href = url.toString();   // 触发 reload + bootstrap 重跑
});
```

**防重复绑定**:用 `form._wired` 标记位(因为 `showFallback` 可能被多次调用)。

#### 4.11.5 Bug 修复:`renderSummary` 字段名错配

**现象**

打开 `/interview?trace_id=xxx` 时,摘要卡显示「**未指定岗位**」,即使库里 `job_requirement.position` 有值。

**根因** [static/interview.js:102-119](file:///c:/Users/10408/Desktop/job/static/interview.js#L102) 的 `renderSummary`:

```js
// 错的
const title = raw.job_title || job.title || "未指定岗位";
//                              ^^^^^^^^^^ ← 真实字段是 job.position
```

数据库 `job_requirement` 字段(由 `job_extractor.py` 决定):
```json
{
  "position": "Python 后端工程师 (LLM 方向)",  // ← 真实存在
  "company": null, "location": null,
  "keywords": [...], "hard_skills": [...], "soft_skills": [...],
  "responsibilities": [...], "experience": [...], "education": [...],
  "salary_range": null, "confidence": 1.0
  // 没有 "title" 字段
}
```

**修复**:按 `position` → `title` → 摘要格式 `job_title` 顺序回退:

```js
const title = raw.job_title || job.position || job.title || "未指定岗位";
```

**调试方法**:`python -c "import asyncio, asyncpg; ..."` 直接查 DB 的 `job_requirement` 字段,**不要靠 IDE 自动补全猜字段名**。

#### 4.11.6 涉及文件清单

| 文件 | 变更 |
|---|---|
| `app/api/routes_interview.py` | `get_cache` 改用 `load_analysis` 返全量 |
| `static/app.js` | +110 行(历史面板、加载函数、URL 持久化、操作栏跳转) |
| `static/index.html` | +5 行(reportActions 占位) |
| `static/app.css` | +70 行(.history-panel / .btn-iv 样式) |
| `static/interview.js` | renderSummary 字段名修复;showFallback 绑 form |
| `static/interview.html` | fallback 区加 traceForm |
| `static/interview.css` | +25 行(.fb-form 等兜底表单样式) |

#### 4.11.7 端到端验证清单

| # | 步骤 | 预期 |
|---|---|---|
| ① | `curl /api/v1/cache?limit=10` | 200,返回 items 列表(标量摘要) |
| ② | `curl /api/v1/cache/{trace_id}` | 200,**7 keys**:trace_id/created_at/resume_data/job_requirement/match_report/suggestions/meta |
| ③ | 浏览器 `/app`,硬刷 | 顶部"历史分析"面板显示 2 条记录,带分数 + 候选人 + 岗位 + 时间 |
| ④ | 点击任一条历史 | 报告区加载并渲染,URL 变为 `?trace_id=xxx`,该项高亮 |
| ⑤ | 刷新页面 | URL 仍带 trace_id,报告**自动还原** |
| ⑥ | 报告顶部 CTA | 显示「🎯 基于此报告生成面试题 →」橙色按钮 |
| ⑦ | 点击 CTA | 跳 `/interview?trace_id=xxx`,摘要卡岗位名**正确显示** |
| ⑧ | 直接访问 `/interview`(无 trace_id) | 显示输入框 + "去工作台"提示 |
| ⑨ | 输入框填 trace_id 提交 | URL 跳转,bootstrap 重新跑,摘要卡正常显示 |

#### 4.11.8 决策回顾(为什么这样做)

| 决策 | 备选 | 理由 |
|---|---|---|
| `get_cache` 改全量 | 保留摘要 + 加新端点 `/cache/{id}/full` | 一个端点一次拿够,前端不用两次请求;列表页继续用 `list_analyses` 返摘要不变 |
| 历史面板 JS 动态注入 | 改 `index.html` 加静态结构 | 静态 HTML 改动会扩散到 git diff,JS 注入把"实现"留在 JS 文件 |
| URL 持久化(`?trace_id=xxx`) | localStorage | URL 是**分享友好**的,localStorage 受同源限制;`history.replaceState` 不刷页 |
| 报告上方 CTA | 报告下方 CTA | 用户分析完第一反应是"下一步做什么",上方 CTA 第一眼可见;`report-actions` 容器有渐变背景突出 |
| 面试台输入 trace_id 兜底 | 历史报告下拉列表 | UI 更轻,实现更小;**下拉需要再调一次 `/api/v1/cache`**,输入框一行提交就完事 |
| `position` 字段名 | 重命名 DB 列 | 影响所有历史数据 + LLM 抽取 prompt,改前端更便宜 |
| 不加 `--reload-include` 改 uvicorn reload 配置 | 加配置防 WatchFiles 误触 | 测试脚本放项目根目录会触发 reload,改 watch 规则治标不治本;直接禁止根目录放临时文件 |

---

### 4.12 全流程测试套件(v0.3+)

#### 4.12.1 动机与目标

| 目标 | 实现 |
|---|---|
| 把"代码跑通"升级为"质量可量化" | 三层测试 + Markdown 报告 |
| 覆盖解析 → 抽取 → 匹配 → 建议全链路 | E2E 测试 + 批量压测 |
| 同/跨岗位匹配分有显著差异,验证模型有效 | 批量压测同岗位 vs 跨岗位对比 |
| 失败可重现可定位 | 每条用例独立 trace_id + 详细 JSON 日志 |
| 离线/CI 友好 | 单元测试 0 LLM 依赖,< 1s 跑完 |

#### 4.12.2 目录结构

```
tests/
├── README.md                   # 使用文档
├── runner.py                   # 轻量测试运行器(@unit/@e2e 装饰器)
├── run_all.py                  # 一站式入口:单元 → E2E → 压测 → 报告
├── generate_report.py          # 聚合所有产物 → full_report.md
├── fixtures/
│   ├── resumes.py              # 27 份简历(9 类目)
│   └── jobs.py                 # 12 个 JD(覆盖同类目)
├── unit/                       # 67 单元测试(< 1s)
│   ├── test_parsers.py
│   ├── test_llm_client.py
│   ├── test_matchers.py
│   ├── test_suggestion_generator.py
│   ├── test_models.py
│   ├── test_progress.py
│   ├── test_config.py
│   └── test_errors.py
├── e2e/                        # 9 E2E(真实 LLM,~7min)
│   ├── test_e2e_pipeline.py
│   └── test_e2e_extractors.py
└── loadtest/
    └── batch_e2e.py            # 批量压测(异步并发)
```

#### 4.12.3 关键设计

| 决策 | 备选 | 理由 |
|---|---|---|
| 自研轻量 runner + `@unit`/`@e2e` 装饰器 | pytest | 离线环境无法 pip install pytest;装饰器方式更轻,符合"最小依赖"原则 |
| 测试数据用 dataclass fixture(代码构造) | JSON/YAML 文件 | 简历/JD 字段嵌套多,JSON/YAML 易错;代码构造自带类型提示 + IDE 补全 |
| `ResumeFixture.text` 字段统一为 Markdown 文本 | .pdf/.docx | LLM 抽取对纯文本友好,避免被解析器差异干扰;真实场景下解析路径已由 `test_e2e_extractors.py` 覆盖 |
| 压测并发度默认 4 | 单条顺序 | DeepSeek 限流 ~10 RPM,并发 4 在 30 用例下总耗时 ~12min,远低于限流 |
| JSON + CSV + Markdown 三种报告 | 仅 JSON | JSON 给程序消费、CSV 给 Excel、Markdown 给 git diff 与 PR review |
| LLM 输出错误时**不重试整流程**,只 fallback 建议 | 整个用例失败 | 抽取成功但建议生成失败是 LLM 偶发问题,不应影响整体可用性 |

#### 4.12.4 指标与门禁

最近一轮(2026-06-18,30 用例)结果作为**质量基线**:

| 指标 | 当前值 | 门禁(参考) |
|---|---:|---|
| 单元测试通过率 | **100%** (67/67) | ≥ 95% |
| E2E 测试通过率 | **100%** (9/9) | ≥ 90% |
| 批量压测通过率 | **96.7%** (29/30) | ≥ 90% |
| 同岗位评分均值 | **56.2** | ≥ 50 |
| 跨岗位评分均值 | **24.0** | ≤ 30 |
| 同/跨差异 | **+32.1 分** | ≥ 20 |
| 单次分析平均耗时 | 92s | ≤ 120s |
| 建议数量均值 | 6.4 条 | 5-8 条(满足 schema) |

后续每次发布前必须跑 `tests/run_all.py --loadtest-limit 30`,基线差异 > 10% 需回归。

#### 4.12.5 发现的问题与跟进

| # | 问题 | 触发场景 | 跟进优先级 |
|---|---|---|---|
| 1 | `aggregate_report` 节点 LLM 输出含 `List[...]` 字面量触发 `eval` → `NameError` | 跨类目简历 / JD,LLM 倾向输出 Python 字面量 | **P1**(影响 3.3% 用例) |
| 2 | P95 耗时 188s,长尾严重 | LLM 偶发限流/重试 | P2(缓存层优化可缓解) |
| 3 | 经验匹配 0.603 vs 技能覆盖 0.208,匹配规则偏严 | 缺别名(`Postgres → PostgreSQL`) | P3 |

#### 4.12.6 如何添加新测试

```python
# tests/unit/test_my_module.py
from tests.runner import unit

@unit
def test_my_function():
    from app.my_module import my_func
    result = my_func("input")
    assert result["status"] == "ok"
```

跑一遍即可被自动收集。E2E 同理,加 `@e2e` 装饰器。

---

### 4.13 后端 workflow / extractors 改造(2026-06-18)

#### 4.13.1 动机

v0.2 留有 3 类遗留问题:**评分路径用 `eval` 解析 LLM 输出**(安全风险 + 注入可能)、**LLM 进度无法跨线程回调**(ContextVar 在 LangGraph `astream` 失效)、**建议生成 prompt 自由度过高**(LLM 幻觉频繁、字段常常为空)。

本次针对这三类问题做了一轮集中加固。

#### 4.13.2 `aggregate_report` 移除 `eval`,改 Pydantic 强校验

```python
# app/workflow/nodes.py(改造前)
score_dict = eval(content)   # ⚠️ 安全风险

# app/workflow/nodes.py(改造后)
class LLMScoreOutput(BaseModel):
    overall_score: float
    @field_validator("overall_score")
    @classmethod
    def clamp_score(cls, v):
        return max(0.0, min(100.0, round(v, 1)))

raw = llm.chat_json(
    system=_SCORE_SYSTEM_PROMPT,
    user=_build_score_prompt(resume, job, skill_gap, experience, keywords),
    schema=LLMScoreOutput,
)
score = raw["overall_score"]
```

配套 `_SCORE_SYSTEM_PROMPT` 给出 5 档评分锚点(90+ / 75-89 / 60-74 / 40-59 / <40),让 LLM 输出可量化。

#### 4.13.3 `generate_suggestions` 双层 fallback

```python
# 第一层:nodes.py 节点兜底
try:
    suggestions = generate_suggestions(resume, job, report, LLMClient())
except Exception:
    logger.exception("generate_suggestions 失败,降级")
    from app.workflow.suggestion_generator import _fallback_suggestions
    suggestions = _fallback_suggestions(resume, job, report)

# 第二层:suggestion_generator.py 模块内
def generate_suggestions(...):
    try:
        raw = llm.chat_json(schema=SuggestionListOutput, max_retries=2)
    except Exception:
        return _fallback_suggestions(resume, job, report)
```

`_fallback_suggestions` 覆盖三类缺口:缺失技能(取 `skill_gap.missing[:3]` → HIGH)、经验不足(→ HIGH)、关键词缺失(→ MEDIUM)。

#### 4.13.4 `LLMClient` 流式 + 三阶段回调

```python
# app/extractors/llm_client.py
def _invoke_stream(self, system, user, hint, callback):
    for chunk in self._get_model().stream([...]) :
        text = chunk.content or ""
        if first_chunk:
            callback("first_token", {"chars": len(text)})
        elif total_chars % _STREAMING_CHARS_THRESHOLD < len(text):
            callback("streaming", {"chars": total_chars})
```

- 首 chunk 触发 `first_token` 事件,前端"立即转圈"
- 每累计 80 字符触发 `streaming` 事件,前端进度条平滑推进
- 异常触发 `error` 事件,前端切到失败视图

`chat_json()` 与 `chat_text()` 都支持显式 `progress_callback` 参数,优先级高于 contextvar 兜底。

#### 4.13.5 `progress.py` 从 ContextVar 改为 Lock + 共享变量

```python
# 旧版(失败场景)
_ctx_var = ContextVar("progress")    # LangGraph astream 跨线程取不到

# 新版
_lock = threading.Lock()
_progress_shared: dict | None = None
def set_progress_callback(cb):
    global _progress_shared
    with _lock:
        _progress_shared = cb
```

配套 `StageDef` 数据类与 8 阶段表(`upload / parse_resume / parse_job / dispatch_matchers / skill_gap / experience / keywords / aggregate / suggestions`),`compute_streaming_percent` 把字符数映射到百分比,前端进度条能稳定显示。

#### 4.13.6 `graph.py` 节点装饰器统一接入 stage

```python
def _with_stage_tracking(node_func):
    def wrapper(state):
        stage = stage_by_node(node_func.__name__)
        set_current_stage(stage)
        t0 = time.monotonic()
        result = node_func(state)
        logger.info(f"节点 {node_func.__name__} 完成, 耗时 {(time.monotonic()-t0)*1000:.0f}ms")
        return result
    return wrapper
```

所有节点注册时统一套用包装器,LangGraph 节点与 progress 系统的 stage 自动打通,无需每个节点手动 `set_current_stage`。

#### 4.13.7 `analyzer.py` 同步/流式入口分离

- **同步 `analyze()`**:走 `ainvoke` 全量结果 → `_persist_cache` 后台 `asyncio.create_task(safe_save_analysis(...))`
- **流式 `analyze_stream()`**:`asyncio.Queue` + 后台任务 + `loop.call_soon_threadsafe` 串联 LangGraph `astream` 节点事件和 LLM token 进度,逐行 yield NDJSON

流式 `analyze_stream` 通过 `started_stages` 去重补发 `stage_start`,确保前端 8 步骤视图完整点亮。

#### 4.13.8 决策回顾

| 决策 | 备选 | 理由 |
|---|---|---|
| 移除 `eval` 改 Pydantic Schema | 加 `ast.literal_eval` 白名单 | 任何 `eval` 都是攻击面,直接消除;Pydantic 还能做字段验证 |
| 三阶段回调 vs 单回调 | 只发 `progress` | 首 chunk 单独通知 `first_token` 让前端能立即转圈,优于等 80 字 |
| Lock + 共享变量 vs ContextVar | 继续 ContextVar + 加 thread local 桥接 | LangGraph astream 工作线程 ≠ 事件循环线程,ContextVar 在跨线程不可靠 |
| 双层 fallback | 只在节点层兜底 | 模块层也兜底,允许 `analyzer` 直接调用 `generate_suggestions` 时也安全 |

---

### 4.14 前端运行态视图 + 历史面板贯通(2026-06-18)

#### 4.14.1 运行态视图(`<section class="run-view">`)

```html
<!-- static/index.html(新增骨架) -->
<section class="run-view" id="runView" hidden>
  <div class="run-header">
    <span class="run-title">运行中</span>
    <span class="run-timer">00:00</span>
  </div>
  <div class="run-bar-track">
    <div class="run-bar-fill" id="runBar"></div>
  </div>
  <ol class="run-steps" id="runSteps">
    <!-- 8 步由 JS 动态生成 -->
  </ol>
  <div class="run-status" id="runStatus"><span class="status-icon spin"></span>正在抽取简历...</div>
  <div class="run-error" id="runError" hidden></div>
</section>
```

JS 端 `streamAnalyze()`:

```js
async function streamAnalyze() {
  const res = await fetch('/api/v1/analyze/stream', { method: 'POST', body: formData });
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    for (const line of buffer.split('\n')) {
      if (!line.trim()) continue;
      const event = JSON.parse(line);
      dispatchEvent(event);   // 路由 6 类事件
    }
  }
}
```

事件路由:

```js
const PARALLEL_GROUPS = [{1, 2}, {3, 4, 5}];   // parse 阶段 + match 阶段
function dispatchEvent(e) {
  switch (e.type) {
    case 'meta':         setTraceId(e.trace_id); break;
    case 'stage_start':  onStageStart(e.index, e.label); break;
    case 'progress':     onProgress(e.percent, e.message); break;
    case 'stage_end':    onStageEnd(e.index); break;
    case 'done':         renderReport(e.data); _hideRunView(); break;
    case 'error':        onError(e.stage, e.message); break;
  }
}
```

并行阶段用 `.parallel-active`(琥珀色)区分同组两个 active 步骤,组结束后回到单一 active。

#### 4.14.2 历史面板子系统

```js
// static/app.js
function injectHistoryPanel() {
  // 在 .report-actions 上方插入 .history-panel 容器
}

async function _loadHistory() {
  const res = await fetch('/api/v1/cache?limit=50');
  const { data } = await res.json();
  // 渲染列表,每项:trace_id / name / title / score / time
}

function _highlightActiveInHistory() {
  document.querySelectorAll('.history-item').forEach(el =>
    el.classList.toggle('is-active', el.dataset.traceId === _currentTraceId));
}

async function _loadHistoricalReport(traceId) {
  const res = await fetch(`/api/v1/cache/${traceId}`);
  const { data } = await res.json();
  renderReport(data);
  history.replaceState({}, '', `?trace_id=${traceId}`);
  _highlightActiveInHistory();
}
```

评分颜色按 80/60 分档:`.hp-score.ok` / `.warn` / `.bad`。

#### 4.14.3 页面状态恢复双轨

```js
// 启动顺序
async function bootstrap() {
  await _loadHistory();
  const urlTrace = new URLSearchParams(location.search).get('trace_id');
  if (urlTrace) {
    await _loadHistoricalReport(urlTrace);     // 1. URL 优先
  } else {
    const lastTid = sessionStorage.getItem('last_trace_id');
    if (lastTid) {
      try { await _loadHistoricalReport(lastTid); }
      catch { /* 404 降级到 empty */ }
    }
  }
}

// 分析完成后
sessionStorage.setItem('last_trace_id', tid);
history.replaceState({}, '', `?trace_id=${tid}`);   // 同步到 URL
```

#### 4.14.4 报告顶部 CTA(跨页贯通)

```html
<!-- static/index.html -->
<div class="report-actions" id="reportActions" hidden>
  <a class="btn-iv" id="btnGoInterview">基于此报告生成面试题 →</a>
</div>
```

```js
// renderReport 末尾
const tid = data.trace_id || _currentTraceId;
document.getElementById('btnGoInterview').href = `/interview?trace_id=${tid}`;
document.getElementById('reportActions').hidden = false;
```

CSS:

```css
.report-actions {
  background: linear-gradient(135deg, rgba(255,165,0,0.12), rgba(255,140,0,0.05));
  border: 1px solid rgba(255,165,0,0.25);
  padding: 14px 20px;
  border-radius: 12px;
  margin-bottom: 16px;
}
.btn-iv {
  background: var(--orange);
  color: #fff;
  padding: 8px 16px;
  border-radius: 8px;
}
.btn-iv:hover { filter: brightness(1.1); }
```

#### 4.14.5 决策回顾

| 决策 | 备选 | 理由 |
|---|---|---|
| 流式 fetch + TextDecoder | SSE EventSource | SSE 对自定义 `meta`/`stage_start` 协议不够灵活;NDJSON 简单可控 |
| 历史面板 JS 注入而非静态 HTML | 改 `index.html` 加 `<div class="history-panel">` | 静态 HTML 改动扩散到 git diff,JS 注入把"实现"留在 JS |
| URL `?trace_id=` + sessionStorage 双轨 | 只用 sessionStorage | URL 分享友好 + 刷新不丢;sessoinStorage 受同源限制但能跨页签 |
| 报告顶部 CTA | 报告下方按钮 | 用户分析完第一反应是"下一步",上方第一眼可见 |
| `[hidden]{display:none !important}` | `.hidden { display: none }` 类 | `[hidden]` 是 HTML5 标准属性;`!important` 兜底防止 `display:flex/grid` 把它露出来 |
| 并行阶段用 `.parallel-active` 琥珀色 | 只显示单一 active | 用户能直观看到"这一步是并行的",不会以为步骤卡住 |

---

### 4.15 前后端契约:`trace_id` 与 NDJSON 事件流(2026-06-18)

#### 4.15.1 `trace_id` 主键贯穿四端

```text
   [URL ?trace_id=xxx]
          │
          ├── 刷新 / 分享 → bootstrap() 自动 _loadHistoricalReport(tid)
          │
   [sessionStorage.last_trace_id]
          │
          ├── 跨页签 / 关闭浏览器 → fallback
          │
   [后端 AnalysisCache.trace_id PK]
          │
          ├── /api/v1/cache/{trace_id} → 完整报告
          ├── /api/v1/interview/predict?trace_id=xxx → 面试题预测
          │
   [报告顶部 CTA /interview?trace_id=xxx]
```

#### 4.15.2 NDJSON 事件契约(`POST /api/v1/analyze/stream`)

```typescript
type StreamEvent =
  | { type: 'meta',          trace_id: string }
  | { type: 'stage_start',   index: number, label: string, key: string }
  | { type: 'progress',      percent: number, message: string, chars: number }
  | { type: 'stage_end',     index: number, key: string }
  | { type: 'done',          data: AnalysisResult, trace_id: string }
  | { type: 'error',         stage: string, code: string, message: string };
```

每行一个 JSON 对象,以 `\n` 分隔。前端严格按 `type` 字段分发,不允许依赖顺序。

#### 4.15.3 失败语义

| 场景 | 触发 | 事件 | 前端反应 |
|---|---|---|---|
| LLM 解析失败 | `chat_json` 抛 JSONDecodeError | `error` | 切到 `.run-error` 红色视图,toast 提示 |
| 阶段超时 | `compute_streaming_percent` 超阈值未推进 | `progress` 不再增长 | 进度条停留,文案"分析中,请稍候" |
| 流式 fetch 失败 | `ReadableStream` 抛错 | — | `try/fallback` 调 `POST /api/v1/analyze` 同步兜底 |
| 缓存读不到 | `/cache/{tid}` 返 404 | — | 降级到 empty 视图,清空 `sessionStorage.last_trace_id` |

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

### 5.6 面试题预测(11 条)

| # | 项 | 命令 / 步骤 | 预期 |
|---|---|---|---|
| 26 | 面试题页面可达 | `curl.exe -o nul -w "%{http_code}" http://localhost:8000/interview` | `200` |
| 27 | 主分析入口不变 | `curl.exe -o nul -w "%{http_code}" http://localhost:8000/app` | `200` |
| 28 | 缓存不可用降级(无 PG) | `curl.exe http://localhost:8000/api/v1/cache` | `503 {"code":"cache_unavailable",...}` |
| 29 | 面试题预测降级(无 PG) | `curl.exe -X POST http://localhost:8000/api/v1/interview/predict -H "Content-Type: application/json" -d "{\"trace_id\":\"x\"}"` | `503 {"code":"service_unavailable",...}` |
| 30 | 流式预测降级(无 PG) | `curl.exe -N -X POST http://localhost:8000/api/v1/interview/predict/stream -H "Content-Type: application/json" -d "{\"trace_id\":\"x\"}"` | `200`,首行 `{"type":"meta",...}`,后续 `{"type":"error",...}` |
| 31 | 主分析端点不受 DB 状态影响 | `curl.exe -F resume=@<200KB.txt> -F job_description=x http://localhost:8000/api/v1/analyze` | `200`,正常返回分析结果 |
| 32 | 启动日志明示降级 | 启动时观察日志 | `WARNING 数据库不可用,缓存层降级(不影响主分析)` |
| 33 | Alembic 迁移 | `alembic upgrade head` | `Running upgrade -> 0001_add_analysis_cache` |
| 34 | 表结构验证 | `psql -U job -d job_analyzer -c "\d analysis_cache"` | 含 `trace_id` / `resume_data(JSONB)` / `created_at` 等列 |
| 35 | ORM 模型导入 | `python -c "from app.models.cache import AnalysisCache; print(AnalysisCache.__tablename__)"` | `analysis_cache` |
| 36 | 缓存服务接口导入 | `python -c "from app.core.cache import save_analysis, load_analysis, list_analyses, delete_analysis, cleanup_expired, safe_save_analysis"` | 静默无报错 |

### 5.7 工作台持久化(本次更新 9 条)

| # | 项 | 命令 / 步骤 | 预期 |
|---|---|---|---|
| 37 | 缓存列表接口 | `curl.exe http://localhost:8000/api/v1/cache?limit=10` | `200`,`items: [...]`(摘要列表) |
| 38 | 缓存单条返全量 | `curl.exe http://localhost:8000/api/v1/cache/{trace_id}` | `200`,**7 keys**:trace_id/created_at/resume_data/job_requirement/match_report/suggestions/meta |
| 39 | 历史面板渲染 | 浏览器 `/app` + `Ctrl+Shift+R` | 顶部「历史分析」面板出现,显示 2 条记录,带分数 + 候选人 + 岗位 + 时间 |
| 40 | 点击历史加载报告 | 点击 `.hp-item` | 报告区渲染,URL 变为 `?trace_id=xxx`,该项 `.is-active` 高亮 |
| 41 | URL 持久化(刷新) | 加载报告后按 F5 | URL 仍带 `?trace_id=xxx`,报告**自动还原** |
| 42 | 报告顶部 CTA | 报告加载后 | 顶部显示「🎯 基于此报告生成面试题 →」橙色按钮 |
| 43 | CTA 跳转 | 点击 CTA | 跳 `/interview?trace_id=xxx`,摘要卡**岗位名正确**(验证 `job.position` 字段) |
| 44 | 面试台无 trace_id 兜底 | 直接访问 `/interview` | 显示 `trace_id` 输入框 + 回 `/app` 提示 |
| 45 | trace_id 提交加载 | 输入框填 trace_id + 提交 | URL 跳转,bootstrap 重跑,摘要卡正常显示 |

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
| 2026-06-10 | 面试题预测模块上线:独立 `/interview` 页面 + PostgreSQL 持久化缓存层 + 工作流零侵入,详见 §4.10 |
| 2026-06-11 | 工作台持久化打通:历史记录面板 + 报告顶部"生成面试题"CTA + URL 持久化(`?trace_id=xxx`)+ 面试台 trace_id 兜底表单,详见 §4.11 |
| 2026-06-11 | Bug 修复:面试台 `renderSummary` 用错字段(`job.title` 改为 `job.position`),见 §4.11.5 |
| 2026-06-18 | **v0.3 全流程测试套件上线**:`tests/` 目录,67 单元 + 9 E2E + 30 用例压测,真实 LLM,详见 §4.12。发现 `aggregate_report` 节点 `eval` 触发的 `NameError`(1/30 失败) |
| 2026-06-18 | **后端 workflow / extractors 改造**:`aggregate_report` 移除 `eval` 改 `LLMScoreOutput` Pydantic Schema;`generate_suggestions` 双层 fallback;`LLMClient._invoke_stream` 流式 + 三阶段回调;`progress.py` Lock + 共享变量替代 ContextVar;`graph.py` 节点装饰器统一接入 stage;`analyzer.py` 同步/流式入口分离,详见 §4.13 |
| 2026-06-18 | **前端运行态视图 + 历史面板贯通**:`<section class="run-view">` 8 步骤进度视图;`streamAnalyze()` 拉 `/api/v1/analyze/stream` NDJSON;历史面板子系统;`sessionStorage` + URL `?trace_id=` 双轨状态恢复;报告顶部 CTA,详见 §4.14 |
| 2026-06-18 | **前后端契约**:`trace_id` 主键贯穿 URL / sessionStorage / 跳转 CTA / 历史面板;NDJSON 6 类事件契约,详见 §4.15 |

---

**最后更新**:2026-06-18 · 维护者:`cxzrdxy`
