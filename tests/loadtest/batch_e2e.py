"""批量端到端压测.

目标:
- 把 27 份简历 × 12 个 JD 的笛卡尔积切成 N 次实际分析
- 控制并发度,避免打爆 LLM 限流
- 输出每条结果到 JSON 报告 + 汇总统计 CSV
- 输出质量分析(同岗位 vs 跨岗位 评分分布、建议数量分布等)

使用方式:
    python tests/loadtest/batch_e2e.py --limit 100 --concurrency 4
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import statistics
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

# 允许从项目根目录执行
TESTS_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = TESTS_ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.analyzer import AnalyzerService
from tests.fixtures.resumes import get_all_resumes
from tests.fixtures.jobs import get_all_jobs


@dataclass
class BatchCase:
    """单个测试用例."""
    case_id: str
    resume_id: str
    resume_category: str
    resume_role: str
    resume_years: float
    job_id: str
    job_title: str
    job_category: str
    is_same_field: bool   # 简历 target_role 与 JD 类别是否匹配
    status: str = "pending"
    duration_ms: float = 0.0
    error: str = ""
    overall_score: Optional[float] = None
    skill_coverage: Optional[float] = None
    experience_score: Optional[float] = None
    keyword_coverage: Optional[float] = None
    matched_skills: List[str] = field(default_factory=list)
    missing_skills: List[str] = field(default_factory=list)
    suggestions_count: int = 0
    hard_gaps: List[str] = field(default_factory=list)
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)


def build_cases(limit: Optional[int]) -> List[BatchCase]:
    """构造测试用例列表."""
    resumes = get_all_resumes()
    jobs = get_all_jobs()

    cases: List[BatchCase] = []
    for r in resumes:
        for j in jobs:
            is_same = r.target_role in j.title or j.category.split("-")[-1] in r.target_role \
                      or r.category.split("-")[-1] == j.category.split("-")[-1]
            cases.append(BatchCase(
                case_id=f"{r.id}__{j.id}",
                resume_id=r.id,
                resume_category=r.category,
                resume_role=r.target_role,
                resume_years=r.years,
                job_id=j.id,
                job_title=j.title,
                job_category=j.category,
                is_same_field=is_same,
            ))

    # 限制数量
    if limit is not None and limit > 0:
        cases = cases[:limit]
    return cases


def _category_match(case: BatchCase) -> bool:
    """判断简历类目和 JD 类目是否属于同一大类."""
    cat_map = {
        "互联网研发-后端": "tech",
        "互联网研发-前端": "tech",
        "互联网研发-算法": "tech",
        "互联网研发-全栈": "tech",
        "数据/分析": "data",
        "数据/分析-产品": "data",
        "传统行业-金融": "trad",
        "传统行业-咨询": "trad",
        "传统行业-快消": "trad",
    }
    return cat_map.get(case.resume_category) == cat_map.get(case.job_category)


async def run_one(
    service: AnalyzerService,
    sem: asyncio.Semaphore,
    resume_text: str,
    job_text: str,
    case: BatchCase,
) -> None:
    """执行单个用例."""
    async with sem:
        t0 = time.monotonic()
        try:
            result = await service.analyze(
                resume_bytes=resume_text.encode("utf-8"),
                resume_suffix=".txt",
                job_text=job_text,
                job_suffix=".txt",
                trace_id=case.case_id,
            )
            case.duration_ms = (time.monotonic() - t0) * 1000
            case.status = "passed"

            mr = result.get("match_report") or {}
            case.overall_score = mr.get("overall_score")
            case.skill_coverage = (mr.get("skill_gap") or {}).get("coverage")
            case.experience_score = (mr.get("experience") or {}).get("score")
            case.keyword_coverage = (mr.get("keywords") or {}).get("coverage")
            case.matched_skills = [s.get("skill") for s in (mr.get("skill_gap") or {}).get("matched", [])]
            case.missing_skills = [s.get("skill") for s in (mr.get("skill_gap") or {}).get("missing", [])]
            case.hard_gaps = mr.get("hard_requirements_gaps", []) or []
            case.strengths = mr.get("strengths", []) or []
            case.weaknesses = mr.get("weaknesses", []) or []

            suggestions = result.get("suggestions") or []
            case.suggestions_count = len(suggestions)

        except Exception as exc:  # noqa: BLE001
            case.duration_ms = (time.monotonic() - t0) * 1000
            case.status = "failed"
            case.error = f"{type(exc).__name__}: {str(exc)[:200]}"


async def run_batch(
    cases: List[BatchCase],
    concurrency: int = 4,
) -> None:
    """批量执行用例."""
    service = AnalyzerService()
    sem = asyncio.Semaphore(concurrency)

    # 预加载所有 JD 文本
    job_text_map = {j.id: j.text for j in get_all_jobs()}
    resume_text_map = {r.id: r.text for r in get_all_resumes()}

    async def wrapped(case: BatchCase):
        await run_one(
            service,
            sem,
            resume_text=resume_text_map.get(case.resume_id, ""),
            job_text=job_text_map.get(case.job_id, ""),
            case=case,
        )

    tasks = [wrapped(case) for case in cases]

    # 用 tqdm 进度条(若可用)
    try:
        from tqdm import tqdm
        for coro in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="E2E"):
            await coro
    except ImportError:
        total = len(tasks)
        done = 0
        for coro in asyncio.as_completed(tasks):
            await coro
            done += 1
            if done % 10 == 0 or done == total:
                passed = sum(1 for c in cases if c.status == "passed")
                failed = sum(1 for c in cases if c.status == "failed")
                print(f"\r>> 进度: {done}/{total} (passed={passed}, failed={failed})", end="", flush=True)
        print()


def write_reports(cases: List[BatchCase], output_dir: Path) -> None:
    """输出 JSON + CSV 报告."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. 详细 JSON
    detail_json = output_dir / "batch_detail.json"
    detail_json.write_text(
        json.dumps([asdict(c) for c in cases], ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f">> 详细 JSON: {detail_json}")

    # 2. 简明 CSV(可导入 Excel)
    detail_csv = output_dir / "batch_detail.csv"
    with detail_csv.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "case_id", "status", "duration_ms",
            "resume_id", "resume_category", "resume_role", "resume_years",
            "job_id", "job_title", "job_category", "is_same_field",
            "overall_score", "skill_coverage", "experience_score", "keyword_coverage",
            "suggestions_count", "matched_skills", "missing_skills", "hard_gaps",
            "strengths", "weaknesses", "error",
        ])
        for c in cases:
            writer.writerow([
                c.case_id, c.status, f"{c.duration_ms:.0f}",
                c.resume_id, c.resume_category, c.resume_role, c.resume_years,
                c.job_id, c.job_title, c.job_category, c.is_same_field,
                c.overall_score, c.skill_coverage, c.experience_score, c.keyword_coverage,
                c.suggestions_count,
                "; ".join(c.matched_skills), "; ".join(c.missing_skills), "; ".join(c.hard_gaps),
                "; ".join(c.strengths), "; ".join(c.weaknesses),
                c.error,
            ])
    print(f">> CSV 报告: {detail_csv}")

    # 3. 汇总统计
    summary = build_summary(cases)
    summary_path = output_dir / "batch_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f">> 汇总报告: {summary_path}")

    # 4. 汇总打印
    print_summary(summary)


def build_summary(cases: List[BatchCase]) -> Dict[str, Any]:
    """汇总统计."""
    total = len(cases)
    passed = sum(1 for c in cases if c.status == "passed")
    failed = sum(1 for c in cases if c.status == "failed")

    durations = [c.duration_ms for c in cases if c.status == "passed"]
    scores = [c.overall_score for c in cases if c.overall_score is not None]
    skill_cov = [c.skill_coverage for c in cases if c.skill_coverage is not None]
    exp_scores = [c.experience_score for c in cases if c.experience_score is not None]
    kw_cov = [c.keyword_coverage for c in cases if c.keyword_coverage is not None]
    sug_counts = [c.suggestions_count for c in cases]

    def percentile(xs: List[float], p: float) -> Optional[float]:
        if not xs:
            return None
        xs_sorted = sorted(xs)
        k = max(0, min(len(xs_sorted) - 1, int(round(p / 100 * (len(xs_sorted) - 1)))))
        return xs_sorted[k]

    # 同岗位 vs 跨岗位 评分对比
    same_scores = [c.overall_score for c in cases if c.is_same_field and c.overall_score is not None]
    cross_scores = [c.overall_score for c in cases if not c.is_same_field and c.overall_score is not None]

    # 错误明细
    error_buckets: Dict[str, int] = {}
    for c in cases:
        if c.status == "failed" and c.error:
            key = c.error.split(":")[0]
            error_buckets[key] = error_buckets.get(key, 0) + 1

    # 按 job 类目统计
    by_job_cat: Dict[str, Dict[str, Any]] = {}
    for c in cases:
        bucket = by_job_cat.setdefault(c.job_category, {
            "n": 0, "passed": 0, "scores": [], "durations": [],
        })
        bucket["n"] += 1
        if c.status == "passed":
            bucket["passed"] += 1
        if c.overall_score is not None:
            bucket["scores"].append(c.overall_score)
        bucket["durations"].append(c.duration_ms)
    for v in by_job_cat.values():
        v["avg_score"] = round(statistics.mean(v["scores"]), 2) if v["scores"] else None
        v["avg_duration_ms"] = round(statistics.mean(v["durations"]), 0) if v["durations"] else None
        v.pop("scores", None)
        v.pop("durations", None)

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "duration_ms": {
            "avg": round(statistics.mean(durations), 0) if durations else None,
            "median": round(statistics.median(durations), 0) if durations else None,
            "p95": percentile(durations, 95),
            "min": min(durations) if durations else None,
            "max": max(durations) if durations else None,
        },
        "overall_score": {
            "avg": round(statistics.mean(scores), 2) if scores else None,
            "median": round(statistics.median(scores), 2) if scores else None,
            "min": min(scores) if scores else None,
            "max": max(scores) if scores else None,
            "p25": percentile(scores, 25),
            "p75": percentile(scores, 75),
        },
        "skill_coverage": {
            "avg": round(statistics.mean(skill_cov), 3) if skill_cov else None,
            "median": round(statistics.median(skill_cov), 3) if skill_cov else None,
        },
        "experience_score": {
            "avg": round(statistics.mean(exp_scores), 3) if exp_scores else None,
        },
        "keyword_coverage": {
            "avg": round(statistics.mean(kw_cov), 3) if kw_cov else None,
        },
        "suggestions_count": {
            "avg": round(statistics.mean(sug_counts), 2) if sug_counts else None,
            "min": min(sug_counts) if sug_counts else None,
            "max": max(sug_counts) if sug_counts else None,
        },
        "same_field_score": {
            "n": len(same_scores),
            "avg": round(statistics.mean(same_scores), 2) if same_scores else None,
            "median": round(statistics.median(same_scores), 2) if same_scores else None,
        },
        "cross_field_score": {
            "n": len(cross_scores),
            "avg": round(statistics.mean(cross_scores), 2) if cross_scores else None,
            "median": round(statistics.median(cross_scores), 2) if cross_scores else None,
        },
        "error_buckets": error_buckets,
        "by_job_category": by_job_cat,
    }


def print_summary(summary: Dict[str, Any]) -> None:
    """打印可读汇总."""
    print()
    print("=" * 80)
    print("批量压测汇总")
    print("=" * 80)
    print(f"  总用例: {summary['total']}")
    print(f"  通过: {summary['passed']}  失败: {summary['failed']}  通过率: {summary['pass_rate']*100:.1f}%")
    print()
    print(f"  时长(ms): avg={summary['duration_ms']['avg']}, "
          f"p95={summary['duration_ms']['p95']}, "
          f"min={summary['duration_ms']['min']}, max={summary['duration_ms']['max']}")
    print()
    print(f"  综合评分: avg={summary['overall_score']['avg']}, "
          f"median={summary['overall_score']['median']}, "
          f"min={summary['overall_score']['min']}, max={summary['overall_score']['max']}")
    print(f"  技能覆盖: avg={summary['skill_coverage']['avg']}")
    print(f"  经验匹配: avg={summary['experience_score']['avg']}")
    print(f"  关键词覆盖: avg={summary['keyword_coverage']['avg']}")
    print(f"  建议数量: avg={summary['suggestions_count']['avg']}, "
          f"min={summary['suggestions_count']['min']}, max={summary['suggestions_count']['max']}")
    print()
    print(f"  同岗位评分: n={summary['same_field_score']['n']}, "
          f"avg={summary['same_field_score']['avg']}, "
          f"median={summary['same_field_score']['median']}")
    print(f"  跨岗位评分: n={summary['cross_field_score']['n']}, "
          f"avg={summary['cross_field_score']['avg']}, "
          f"median={summary['cross_field_score']['median']}")
    print()
    if summary["error_buckets"]:
        print("  错误分布:")
        for k, v in summary["error_buckets"].items():
            print(f"    - {k}: {v}")
    print()
    print("  按 JD 类目:")
    for cat, stats in summary["by_job_category"].items():
        print(f"    - {cat}: n={stats['n']}, 通过={stats['passed']}, "
              f"均分={stats['avg_score']}, 均耗时={stats['avg_duration_ms']}ms")
    print("=" * 80)


def main() -> int:
    parser = argparse.ArgumentParser(description="求职分析全流程批量压测")
    parser.add_argument("--limit", type=int, default=100,
                        help="限制用例数(默认 100;None 表示跑全部组合)")
    parser.add_argument("--concurrency", type=int, default=4,
                        help="并发数(默认 4,避免打爆 LLM 限流)")
    parser.add_argument("--output", default="tests/output",
                        help="报告输出目录")
    parser.add_argument("--limit-all", action="store_true",
                        help="跑全部组合(忽略 --limit)")
    args = parser.parse_args()

    limit = None if args.limit_all else args.limit
    cases = build_cases(limit)
    print(f">> 共构造 {len(cases)} 个用例 (limit={limit}, concurrency={args.concurrency})")

    t0 = time.monotonic()
    asyncio.run(run_batch(cases, concurrency=args.concurrency))
    total_s = time.monotonic() - t0
    print(f"\n>> 总耗时: {total_s:.1f}s")

    write_reports(cases, Path(args.output))

    # 退出码
    failed = sum(1 for c in cases if c.status == "failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())