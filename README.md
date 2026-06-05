# 求职分析智能体

基于 LangGraph + FastAPI 的轻量化求职分析服务,用于解析简历与岗位 JD,生成针对性修改建议。

## 演示

[![演示视频](assets/demo.mp4)](assets/demo.mp4)

> 完整操作流程(12 秒,2.7 MB):上传简历 → 粘贴 JD → 一键分析 → 匹配报告。
> 部分浏览器不直接播放 MP4,可[点此下载](assets/demo.mp4)后查看。

## 项目结构

```
job/
├── app/
│   ├── main.py                # FastAPI 入口
│   ├── api/routes.py          # 路由层
│   ├── core/                  # 配置/日志/异常
│   ├── models/                # Pydantic 数据模型
│   ├── parsers/               # 文档文本提取
│   ├── extractors/            # LLM 结构化抽取
│   ├── matchers/              # 技能/经验/关键词匹配
│   ├── workflow/              # LangGraph 工作流
│   └── services/analyzer.py   # 业务编排入口
├── uploads/                   # 临时文件目录
├── requirements.txt
├── .env.example
└── 求职分析智能体设计方案.md
```

## 快速开始

> **环境约定(Windows + Miniconda)**:本项目复用一个现成的 `fastapi` 环境,位置 `D:\miniconda\envs\fastapi`(Python 3.10.19)。

```bash
# 1. 激活现成的 fastapi 环境
D:\miniconda\envs\fastapi\Scripts\activate.bat
# 终端前缀变成 (fastapi) 即激活成功

# 2. 进入项目根目录并安装依赖(仅首次或新增依赖时执行)
cd <项目根目录>
pip install -r requirements.txt

# 3. 复制并填写环境变量(仅首次)
copy .env.example .env
# 编辑 .env 填入 DEEPSEEK_API_KEY (默认走 DeepSeek v4 Flash);
# 如需切回 OpenAI,把 LLM_PROVIDER 改为 openai 并填入 OPENAI_API_KEY

# 4. 启动服务
uvicorn app.main:app --reload --port 8000
```

> 不想每次激活,也可以直接走绝对路径(无需 activate):
> `D:\miniconda\envs\fastapi\python.exe -m uvicorn app.main:app --reload --port 8000`

## 核心 API

### POST /api/v1/analyze
- `resume`: 简历文件 (PDF / DOCX / TXT)
- `job_description`: JD 文本 (与 `job_file` 二选一)
- `job_file`: JD 文件 (与 `job_description` 二选一)
- `trace_id`: 可选,链路追踪 ID

返回:

```json
{
  "success": true,
  "code": "ok",
  "message": "分析完成",
  "data": {
    "meta": {"resume_chars": 1200, "job_chars": 800, "used_provider": "deepseek", "used_model": "deepseek-v4-flash"},
    "match_report": {
      "overall_score": 78.5,
      "skill_gap": {"matched": [], "missing": [], "partial": [], "coverage": 0.8},
      "experience": {"score": 0.7, "notes": []},
      "keywords": {"matched": [], "missing": [], "coverage": 0.6},
      "hard_requirements_gaps": []
    },
    "suggestions": [
      {"type": "content", "priority": "high", "section": "skills", "suggestion": "...", "reason": "..."}
    ]
  },
  "trace_id": "..."
}
```

### GET /api/v1/health
健康检查,返回 `{ "success": true, "data": { "status": "up" } }`。

## 设计要点

- **输入闭环**: 文本和文件都走统一 `extract_text` 解析器。
- **结构化输出**: 所有 LLM 调用通过 `chat_json(schema=...)` 校验,失败自动重试一次。
- **轻量化匹配**: 技能/经验/关键词基于规则匹配,仅在“建议生成”一步调用 LLM,降低 token 消耗。
- **可降级**: LLM 调用失败时,自动降级为基于匹配证据的启发式建议。
- **可观测**: 全流程 trace_id,统一日志输出到控制台 + 文件。

