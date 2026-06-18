"""FastAPI 入口."""
from __future__ import annotations

import datetime
import sys
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.api.routes_interview import router as interview_router
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.core.metrics import metrics

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info(
        "应用启动: %s v%s · pid=%d · provider=%s model=%s",
        settings.app_name,
        settings.version,
        metrics.pid,
        settings.llm.provider,
        settings.llm.model,
    )
    # 启动时尝试初始化数据库(失败不阻塞主流程,缓存为可选)
    try:
        from app.core.database import get_session_factory

        get_session_factory()
        logger.info("数据库引擎就绪")
    except Exception as exc:  # noqa: BLE001
        logger.warning("数据库不可用,缓存层降级(不影响主分析): %s", exc)
    yield
    # 关闭数据库引擎
    try:
        from app.core.database import close_db

        await close_db()
    except Exception:  # noqa: BLE001
        pass
    logger.info("应用关闭")


# ---------------------------------------------------------------------------
# 工具:版本探测 / 时长格式化 / 实时指标聚合
# ---------------------------------------------------------------------------

def _safe_version(modname: str) -> str:
    """读取已安装模块版本.

    优先级:模块自带 `__version__` / `VERSION` > `importlib.metadata` > `—`。
    """
    try:
        mod = __import__(modname)
        v = getattr(mod, "__version__", None) or getattr(mod, "VERSION", None)
        if v:
            return str(v)
    except Exception:
        pass
    try:
        import importlib.metadata as md

        return md.version(modname)
    except Exception:
        return "—"


def _format_duration(ms: float) -> str:
    if ms < 1:
        return f"{ms * 1000:.0f}µs"
    if ms < 1000:
        return f"{ms:.1f}ms"
    return f"{ms / 1000:.2f}s"


def _format_latency_for(path: str, avg_latency: Dict[str, float]) -> str:
    if path in avg_latency:
        return f"~{_format_duration(avg_latency[path])}"
    return "—"


def _build_recent_log_html(recent: List[Any]) -> str:
    if not recent:
        return '<div class="line empty">-- no requests recorded yet --</div>'
    items = list(reversed(recent))[-6:]
    parts: List[str] = []
    for log in items:
        verb_class = "post" if log.method == "POST" else "get"
        ts = datetime.datetime.fromtimestamp(log.ts).strftime("%H:%M:%S")
        parts.append(
            f'<div class="line">'
            f'<span class="ts">{ts}</span>'
            f'<span class="verb {verb_class}">{log.method}</span>'
            f'<span class="uri">{log.path}</span>'
            f'<span class="code">{log.status}</span>'
            f'<span class="lat">{_format_duration(log.duration_ms)}</span>'
            f'</div>'
        )
    return "\n      ".join(parts)


# ---------------------------------------------------------------------------
# 根路径 HTML 模板(全部数据通过 .format() 注入)
# ---------------------------------------------------------------------------

_INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<title>{name} · service</title>
<meta name="viewport" content="width=device-width,initial-scale=1" />
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:ital,wght@0,400;0,500;0,700;0,800;1,400&display=swap" rel="stylesheet" />
<style>
  :root {{
    --bg:          #0a0a0a;
    --bg-alt:      #111111;
    --border:      #2a2a2a;
    --border-hi:   #3a3a3a;
    --text:        #e5e5e5;
    --text-dim:    #8a8a8a;
    --text-mute:   #5a5a5a;
    --green:       #00ff88;
    --green-dim:   #00aa55;
    --red:         #ff3355;
    --amber:       #ffaa00;
    --cyan:        #00ddff;
  }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; padding: 0; background: var(--bg); color: var(--text); }}
  body {{
    font-family: "JetBrains Mono", "Cascadia Code", "Source Code Pro", Consolas, monospace;
    font-size: 13px;
    line-height: 1.55;
    padding: 20px;
    min-height: 100vh;
  }}
  .container {{ max-width: 1080px; margin: 0 auto; }}

  /* ===== Boot console ===== */
  .boot {{
    border: 1px solid var(--border);
    background: var(--bg-alt);
    padding: 12px 16px;
    margin-bottom: 16px;
  }}
  .boot .line {{ display: block; white-space: pre-wrap; }}
  .boot .prompt {{ color: var(--green); }}
  .boot .ok {{ color: var(--green); font-weight: 700; }}
  .boot .dim {{ color: var(--text-dim); }}
  .boot .cursor {{
    display: inline-block;
    width: 7px;
    height: 14px;
    background: var(--green);
    margin-left: 6px;
    vertical-align: -1px;
    animation: blink 1s step-end infinite;
  }}
  @keyframes blink {{ 0%, 50% {{ opacity: 1; }} 50.01%, 100% {{ opacity: 0; }} }}

  /* ===== Banner ===== */
  .banner {{
    border: 1px solid var(--border);
    border-left: 3px solid var(--green);
    background: var(--bg-alt);
    padding: 20px 24px;
    margin-bottom: 16px;
  }}
  .banner-head {{
    display: flex; justify-content: space-between; align-items: baseline;
    flex-wrap: wrap; gap: 12px;
    margin-bottom: 4px;
  }}
  .banner h1 {{
    font-size: 30px; font-weight: 800; margin: 0;
    color: var(--text); letter-spacing: -0.01em;
  }}
  .banner h1 .ver {{
    color: var(--green); font-size: 14px; font-weight: 500;
    margin-left: 12px; letter-spacing: 0.05em;
  }}
  .banner .ascii {{
    color: var(--text-mute); font-size: 10px; letter-spacing: 0.2em;
  }}
  .banner .sub {{
    color: var(--text-dim); font-size: 12px; margin: 0 0 16px;
  }}
  .stats {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 1px; background: var(--border); border: 1px solid var(--border);
  }}
  .stat {{ background: var(--bg); padding: 8px 12px; }}
  .stat .k {{
    color: var(--text-mute); font-size: 10px;
    text-transform: uppercase; letter-spacing: 0.12em;
  }}
  .stat .v {{ color: var(--text); font-size: 13px; margin-top: 2px; word-break: break-all; }}
  .stat .v.green {{ color: var(--green); }}
  .stat .v.red   {{ color: var(--red); }}
  .stat .v.amber {{ color: var(--amber); }}
  .stat .v.cyan  {{ color: var(--cyan); }}

  /* ===== Panel ===== */
  .panel {{
    border: 1px solid var(--border);
    background: var(--bg-alt);
    margin-bottom: 16px;
  }}
  .panel-head {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 8px 14px;
    border-bottom: 1px solid var(--border);
    background: rgba(255,255,255,0.015);
  }}
  .panel-head .title {{
    color: var(--text); font-size: 11px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.18em;
  }}
  .panel-head .title::before {{
    content: "▸ "; color: var(--green);
  }}
  .panel-head .meta {{
    color: var(--text-mute); font-size: 11px;
  }}
  .panel-head .meta .live {{
    color: var(--green); margin-right: 6px;
  }}
  .panel-head .meta .live::before {{
    content: "●"; margin-right: 4px; animation: blink 1.5s step-end infinite;
  }}

  /* ===== Endpoints table ===== */
  table.endpoints {{ width: 100%; border-collapse: collapse; font-size: 12.5px; }}
  table.endpoints th, table.endpoints td {{
    padding: 11px 14px; text-align: left; border-bottom: 1px solid var(--border);
  }}
  table.endpoints th {{
    color: var(--text-mute); font-weight: 500;
    text-transform: uppercase; font-size: 10px; letter-spacing: 0.1em;
  }}
  table.endpoints tbody tr {{ transition: background 0.1s; cursor: pointer; }}
  table.endpoints tbody tr:hover {{ background: rgba(0, 255, 136, 0.05); }}
  table.endpoints tbody tr:last-child td {{ border-bottom: none; }}
  table.endpoints .id     {{ color: var(--text-mute); width: 36px; }}
  table.endpoints .method {{ width: 70px; }}
  table.endpoints .path   {{ color: var(--text); }}
  table.endpoints .desc   {{ color: var(--text-dim); font-size: 11.5px; }}
  table.endpoints .status {{ width: 90px; }}
  table.endpoints .latency {{ color: var(--text-mute); width: 90px; text-align: right; font-size: 12px; }}
  .method .tag {{
    display: inline-block; padding: 2px 8px; font-size: 10px; font-weight: 700;
    border-radius: 1px; letter-spacing: 0.08em;
  }}
  .method .tag.get  {{ color: var(--green); border: 1px solid var(--green-dim); background: rgba(0,255,136,0.08); }}
  .method .tag.post {{ color: var(--red);   border: 1px solid var(--red);     background: rgba(255,51,85,0.08); }}
  .status .ready {{ color: var(--green); font-weight: 700; }}
  .status .ready::before {{ content: "● "; }}

  /* ===== Log tail ===== */
  .log {{ font-size: 12px; }}
  .log .line {{
    padding: 5px 14px; border-bottom: 1px solid var(--border); color: var(--text-dim);
    display: flex; gap: 12px; align-items: baseline;
  }}
  .log .line.empty {{
    color: var(--text-mute); font-style: italic; justify-content: center; padding: 14px;
  }}
  .log .line:last-child {{ border-bottom: none; }}
  .log .ts   {{ color: var(--text-mute); width: 70px; flex-shrink: 0; }}
  .log .verb {{ width: 50px; flex-shrink: 0; font-weight: 700; letter-spacing: 0.05em; }}
  .log .verb.get  {{ color: var(--green); }}
  .log .verb.post {{ color: var(--red); }}
  .log .uri  {{ color: var(--text); flex: 1; }}
  .log .code {{ color: var(--green); font-weight: 700; width: 40px; flex-shrink: 0; }}
  .log .lat  {{ color: var(--amber); width: 70px; text-align: right; flex-shrink: 0; }}

  /* ===== Footer ===== */
  .footer {{
    margin-top: 16px; padding: 10px 16px;
    border: 1px solid var(--border); background: var(--bg-alt);
    color: var(--text-mute); font-size: 11px;
    display: flex; justify-content: space-between; flex-wrap: wrap; gap: 12px;
  }}
  .footer .blink {{
    color: var(--green); animation: blink 1.1s step-end infinite;
    margin-right: 6px;
  }}

  /* ===== Responsive ===== */
  @media (max-width: 720px) {{
    body {{ padding: 12px; }}
    .banner h1 {{ font-size: 22px; }}
    .banner h1 .ver {{ display: block; margin-left: 0; margin-top: 4px; }}
    table.endpoints th, table.endpoints td {{ padding: 8px 10px; }}
    .latency, th.lt-h {{ display: none; }}
    .log .lat {{ display: none; }}
  }}
</style>
</head>
<body>
<div class="container">

  <div class="boot">
    <span class="line"><span class="prompt">$</span> tail -f /var/log/job-analyzer.log</span>
    <span class="line"><span class="prompt">BOOT </span> <span class="dim">{started_str}</span>  process started · pid={pid} · {python_version}</span>
    <span class="line"><span class="prompt">INIT </span> <span class="dim">{started_str}</span>  config: provider={provider} model={model}</span>
    <span class="line"><span class="prompt">INIT </span> <span class="dim">{started_str}</span>  base_url: {base_url} · timeout: {timeout}s</span>
    <span class="line"><span class="prompt">INIT </span> <span class="dim">{started_str}</span>  {framework_version} · {orchestrator_version} · {schema_version}</span>
    <span class="line"><span class="prompt">READY</span> <span class="dim">{started_str}</span>  <span class="ok">listening on 0.0.0.0:8000</span> · {uvi_version}</span>
    <span class="line"><span class="prompt">STAT </span> <span class="dim">{now_str}</span>      uptime={uptime} · requests={request_count} · errors={error_count}</span>
    <span class="line"><span class="prompt">$</span><span class="cursor"></span></span>
  </div>

  <div class="banner">
    <div class="banner-head">
      <h1>{name}<span class="ver">v{version}</span></h1>
      <span class="ascii">JOB_ANALYZER · PID {pid}</span>
    </div>
    <p class="sub"># Resume &amp; JD analysis service · OpenAI-compatible LLM backend</p>
    <div class="stats">
      <div class="stat"><div class="k">status</div><div class="v green">● ONLINE</div></div>
      <div class="stat"><div class="k">uptime</div><div class="v">{uptime}</div></div>
      <div class="stat"><div class="k">provider</div><div class="v">{provider}</div></div>
      <div class="stat"><div class="k">model</div><div class="v">{model}</div></div>
      <div class="stat"><div class="k">requests</div><div class="v cyan">{request_count}</div></div>
      <div class="stat"><div class="k">errors</div><div class="v {error_class}">{error_count}</div></div>
      <div class="stat"><div class="k">pid</div><div class="v cyan">{pid}</div></div>
      <div class="stat"><div class="k">listen</div><div class="v">0.0.0.0:8000</div></div>
    </div>
  </div>

  <div class="panel">
    <div class="panel-head">
      <span class="title">endpoints</span>
      <span class="meta"><span class="live"></span>10 routes · {request_count} reqs · {error_count} errors</span>
    </div>
    <table class="endpoints">
      <thead>
        <tr>
          <th>id</th>
          <th>method</th>
          <th>path</th>
          <th>description</th>
          <th>status</th>
          <th class="lt-h">avg latency</th>
        </tr>
      </thead>
      <tbody>
        <tr onclick="location.href='/docs'">
          <td class="id">01</td>
          <td class="method"><span class="tag get">GET</span></td>
          <td class="path">/docs</td>
          <td class="desc">interactive swagger ui</td>
          <td class="status"><span class="ready">ready</span></td>
          <td class="latency">{lat_docs}</td>
        </tr>
        <tr onclick="location.href='/api/v1/info'">
          <td class="id">02</td>
          <td class="method"><span class="tag get">GET</span></td>
          <td class="path">/api/v1/info</td>
          <td class="desc">service metadata · json</td>
          <td class="status"><span class="ready">ready</span></td>
          <td class="latency">{lat_info}</td>
        </tr>
        <tr onclick="location.href='/api/v1/health'">
          <td class="id">03</td>
          <td class="method"><span class="tag get">GET</span></td>
          <td class="path">/api/v1/health</td>
          <td class="desc">liveness probe</td>
          <td class="status"><span class="ready">ready</span></td>
          <td class="latency">{lat_health}</td>
        </tr>
        <tr onclick="location.href='/docs#/default/analyze_resume_api_v1_analyze_post'">
          <td class="id">04</td>
          <td class="method"><span class="tag post">POST</span></td>
          <td class="path">/api/v1/analyze</td>
          <td class="desc">resume · jd analysis · multipart</td>
          <td class="status"><span class="ready">ready</span></td>
          <td class="latency">{lat_analyze}</td>
        </tr>
        <tr onclick="location.href='/docs#/default/analyze_resume_stream_api_v1_analyze_stream_post'">
          <td class="id">05</td>
          <td class="method"><span class="tag post">POST</span></td>
          <td class="path">/api/v1/analyze/stream</td>
          <td class="desc">resume · jd analysis · ndjson stream</td>
          <td class="status"><span class="ready">ready</span></td>
          <td class="latency">{lat_analyze_stream}</td>
        </tr>
        <tr onclick="location.href='/docs#/default/predict_interview_api_v1_interview_predict_post'">
          <td class="id">06</td>
          <td class="method"><span class="tag post">POST</span></td>
          <td class="path">/api/v1/interview/predict</td>
          <td class="desc">interview questions prediction</td>
          <td class="status"><span class="ready">ready</span></td>
          <td class="latency">{lat_interview_predict}</td>
        </tr>
        <tr onclick="location.href='/docs#/default/predict_interview_stream_api_v1_interview_predict_stream_post'">
          <td class="id">07</td>
          <td class="method"><span class="tag post">POST</span></td>
          <td class="path">/api/v1/interview/predict/stream</td>
          <td class="desc">interview questions · ndjson stream</td>
          <td class="status"><span class="ready">ready</span></td>
          <td class="latency">{lat_interview_predict_stream}</td>
        </tr>
        <tr onclick="location.href='/docs#/default/list_cache_api_v1_cache_get'">
          <td class="id">08</td>
          <td class="method"><span class="tag get">GET</span></td>
          <td class="path">/api/v1/cache</td>
          <td class="desc">list cached analyses</td>
          <td class="status"><span class="ready">ready</span></td>
          <td class="latency">{lat_cache_list}</td>
        </tr>
        <tr onclick="location.href='/docs#/default/get_cache_api_v1_cache__trace_id__get'">
          <td class="id">09</td>
          <td class="method"><span class="tag get">GET</span></td>
          <td class="path">/api/v1/cache/{{trace_id}}</td>
          <td class="desc">get cached analysis by trace_id</td>
          <td class="status"><span class="ready">ready</span></td>
          <td class="latency">{lat_cache_get}</td>
        </tr>
        <tr onclick="location.href='/docs#/default/delete_cache_api_v1_cache__trace_id__delete'">
          <td class="id">10</td>
          <td class="method"><span class="tag post">DELETE</span></td>
          <td class="path">/api/v1/cache/{{trace_id}}</td>
          <td class="desc">delete cached analysis</td>
          <td class="status"><span class="ready">ready</span></td>
          <td class="latency">{lat_cache_delete}</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="panel">
    <div class="panel-head">
      <span class="title">recent.log</span>
      <span class="meta"><span class="live"></span>{recent_count} entries · following</span>
    </div>
    <div class="log">
      {recent_log_html}
    </div>
  </div>

  <div class="footer">
    <span>build: {name}@{version} · {python_version} · {uvi_version}</span>
    <span><span class="blink">█</span>listening</span>
  </div>

</div>
</body>
</html>
"""


def build_index_html() -> str:
    settings = get_settings()
    snap = metrics.snapshot()
    avg = snap["avg_latency"]
    return _INDEX_HTML.format(
        name=settings.app_name,
        version=settings.version,
        provider=settings.llm.provider,
        model=settings.llm.model,
        base_url=settings.llm.base_url or "—",
        timeout=settings.llm.timeout,
        pid=snap["pid"],
        uptime=snap["uptime"],
        started_str=snap["started_str"],
        now_str=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        request_count=snap["request_count"],
        error_count=snap["error_count"],
        error_class="red" if snap["error_count"] > 0 else "green",
        framework_version=f"fastapi {_safe_version('fastapi')}",
        orchestrator_version=f"langgraph {_safe_version('langgraph')}",
        schema_version=f"pydantic {_safe_version('pydantic')}",
        python_version=f"python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        uvi_version=f"uvicorn {_safe_version('uvicorn')}",
        lat_docs="—",
        lat_info=_format_latency_for("/api/v1/info", avg),
        lat_health=_format_latency_for("/api/v1/health", avg),
        lat_analyze=_format_latency_for("/api/v1/analyze", avg),
        lat_analyze_stream=_format_latency_for("/api/v1/analyze/stream", avg),
        lat_interview_predict=_format_latency_for("/api/v1/interview/predict", avg),
        lat_interview_predict_stream=_format_latency_for("/api/v1/interview/predict/stream", avg),
        lat_cache_list=_format_latency_for("/api/v1/cache", avg),
        lat_cache_get=_format_latency_for("/api/v1/cache/{trace_id}", avg),
        lat_cache_delete=_format_latency_for("/api/v1/cache/{trace_id}", avg),
        recent_log_html=_build_recent_log_html(snap["recent"]),
        recent_count=len(snap["recent"]),
    )


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        lifespan=lifespan,
        debug=settings.debug,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router, prefix="/api/v1")
    app.include_router(interview_router, prefix="/api/v1")

    # 静态资源:/static/...
    app.mount("/static", StaticFiles(directory="static"), name="static")

    # 前端应用入口
    @app.get("/app", response_class=HTMLResponse, include_in_schema=False)
    async def app_page() -> FileResponse:
        return FileResponse("static/index.html")

    @app.get("/interview", response_class=HTMLResponse, include_in_schema=False)
    async def interview_page() -> FileResponse:
        return FileResponse("static/interview.html")

    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        start = time.time()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.time() - start) * 1000
            # 根路径自访问不计入,避免日志被自身刷新污染
            if request.url.path != "/":
                metrics.record(request.method, request.url.path, 500, duration_ms)
            raise
        duration_ms = (time.time() - start) * 1000
        if request.url.path != "/":
            metrics.record(request.method, request.url.path, response.status_code, duration_ms)
        return response

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def index() -> HTMLResponse:
        return HTMLResponse(build_index_html())

    return app


app = create_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    settings = get_settings()
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.debug)
