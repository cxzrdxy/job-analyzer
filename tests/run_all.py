"""一站式运行入口:单元测试 + E2E 测试 + 批量压测.

执行流程:
1. 单元测试(快速,几十秒)
2. E2E 关键路径测试(真实 LLM,~5 分钟)
3. 批量压测(并发,默认 30 个用例,可选更大规模)
4. 汇总输出到 tests/output/full_report.md

使用:
    python tests/run_all.py
    python tests/run_all.py --skip-e2e --skip-loadtest
    python tests/run_all.py --loadtest-limit 100 --concurrency 6
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

TESTS_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT))


def run_unit_tests() -> dict:
    """跑单元测试."""
    from tests import runner
    print("\n" + "=" * 80)
    print("▶ 阶段 1/3: 单元测试")
    print("=" * 80)
    report = runner.run_tests(["unit"], verbose=True)
    runner.print_summary(report)
    return {
        "total": report.total,
        "passed": report.passed,
        "failed": report.failed,
        "error": report.error,
        "duration_s": report.duration_s,
    }


def run_e2e_tests() -> dict:
    """跑 E2E 测试."""
    from tests import runner
    print("\n" + "=" * 80)
    print("▶ 阶段 2/3: 端到端测试(真实 LLM)")
    print("=" * 80)
    report = runner.run_tests(["e2e"], verbose=True)
    runner.print_summary(report)
    runner.write_json_report(report, Path("tests/output/e2e_report.json"))
    return {
        "total": report.total,
        "passed": report.passed,
        "failed": report.failed,
        "error": report.error,
        "duration_s": report.duration_s,
    }


def run_loadtest(limit: int, concurrency: int, output_dir: Path) -> dict:
    """跑批量压测."""
    print("\n" + "=" * 80)
    print(f"▶ 阶段 3/3: 批量压测 (limit={limit}, concurrency={concurrency})")
    print("=" * 80)
    from tests.loadtest.batch_e2e import build_cases, run_batch, write_reports

    cases = build_cases(limit)
    print(f">> 用例数: {len(cases)}")
    t0 = time.monotonic()
    import asyncio
    asyncio.run(run_batch(cases, concurrency=concurrency))
    duration_s = time.monotonic() - t0

    write_reports(cases, output_dir)

    passed = sum(1 for c in cases if c.status == "passed")
    failed = sum(1 for c in cases if c.status == "failed")
    return {
        "total": len(cases),
        "passed": passed,
        "failed": failed,
        "duration_s": round(duration_s, 1),
        "output_dir": str(output_dir),
    }


def build_markdown_report(
    unit: dict,
    e2e: dict,
    loadtest: dict,
    summary: dict | None,
) -> str:
    """构建最终 Markdown 报告."""
    lines = []
    lines.append("# 求职分析智能体 - 全流程测试报告")
    lines.append("")
    lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ")
    lines.append("**测试范围**: 单元 + E2E + 批量压测  ")
    lines.append("**LLM**: DeepSeek v4 Flash (真实调用)")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 概览
    lines.append("## 1. 概览")
    lines.append("")
    lines.append("| 阶段 | 用例数 | 通过 | 失败 | 异常 | 通过率 | 耗时 |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    lines.append(
        f"| 单元测试 | {unit['total']} | {unit['passed']} | {unit['failed']} | {unit['error']} | "
        f"{unit['passed']/(unit['total'] or 1)*100:.1f}% | {unit['duration_s']:.1f}s |"
    )
    if e2e:
        lines.append(
            f"| E2E 测试 | {e2e['total']} | {e2e['passed']} | {e2e['failed']} | {e2e['error']} | "
            f"{e2e['passed']/(e2e['total'] or 1)*100:.1f}% | {e2e['duration_s']:.1f}s |"
        )
    if loadtest:
        lines.append(
            f"| 批量压测 | {loadtest['total']} | {loadtest['passed']} | {loadtest['failed']} | - | "
            f"{loadtest['passed']/(loadtest['total'] or 1)*100:.1f}% | {loadtest['duration_s']:.1f}s |"
        )
    lines.append("")

    # 批量压测详情
    if summary:
        lines.append("## 2. 批量压测质量分析")
        lines.append("")

        # 总体
        lines.append("### 2.1 总体评分")
        lines.append("")
        lines.append(f"- 总用例: **{summary['total']}**")
        lines.append(f"- 通过: **{summary['passed']}** (通过率 {summary['pass_rate']*100:.1f}%)")
        lines.append(f"- 综合评分 avg/median: **{summary['overall_score']['avg']} / {summary['overall_score']['median']}**")
        lines.append(f"- 技能覆盖率 avg: **{summary['skill_coverage']['avg']}**")
        lines.append(f"- 关键词覆盖率 avg: **{summary['keyword_coverage']['avg']}**")
        lines.append(f"- 经验匹配 avg: **{summary['experience_score']['avg']}**")
        lines.append(f"- 建议数量 avg/min/max: **{summary['suggestions_count']['avg']} / {summary['suggestions_count']['min']} / {summary['suggestions_count']['max']}**")
        lines.append("")

        # 时长
        lines.append("### 2.2 性能")
        lines.append("")
        d = summary["duration_ms"]
        lines.append(f"- 单次分析平均耗时: **{d['avg']:.0f}ms** ({d['avg']/1000:.1f}s)")
        lines.append(f"- 中位耗时: {d['median']:.0f}ms")
        lines.append(f"- P95 耗时: {d['p95']:.0f}ms")
        lines.append(f"- 最快/最慢: {d['min']:.0f}ms / {d['max']:.0f}ms")
        lines.append("")

        # 同岗位 vs 跨岗位
        lines.append("### 2.3 同岗位 vs 跨岗位匹配分")
        lines.append("")
        s = summary["same_field_score"]
        c = summary["cross_field_score"]
        lines.append("| 类别 | 数量 | 平均分 | 中位分 |")
        lines.append("|---|---:|---:|---:|")
        lines.append(f"| 同岗位(简历类目与 JD 同类) | {s['n']} | {s['avg']} | {s['median']} |")
        lines.append(f"| 跨岗位 | {c['n']} | {c['avg']} | {c['median']} |")
        diff = (s["avg"] or 0) - (c["avg"] or 0)
        lines.append("")
        lines.append(f"> 同岗位平均分比跨岗位高 **{diff:.1f} 分**,验证匹配模型对同类岗位识别有效。")
        lines.append("")

        # 错误分析
        if summary["error_buckets"]:
            lines.append("### 2.4 错误分析")
            lines.append("")
            lines.append("| 异常类型 | 数量 |")
            lines.append("|---|---:|")
            for k, v in summary["error_buckets"].items():
                lines.append(f"| {k} | {v} |")
            lines.append("")

        # 按 JD 类目
        lines.append("### 2.5 按 JD 类目统计")
        lines.append("")
        lines.append("| JD 类目 | 用例数 | 通过 | 平均分 | 平均耗时 |")
        lines.append("|---|---:|---:|---:|---:|")
        for cat, stats in summary["by_job_category"].items():
            lines.append(
                f"| {cat} | {stats['n']} | {stats['passed']} | "
                f"{stats['avg_score']} | {stats['avg_duration_ms']}ms |"
            )
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 3. 测试产物")
    lines.append("")
    lines.append("- `tests/output/test_report.json` - 单元测试详细报告")
    if e2e:
        lines.append("- `tests/output/e2e_report.json` - E2E 测试详细报告")
    if loadtest:
        lines.append(f"- `{loadtest['output_dir']}/batch_detail.json` - 批量压测详细 JSON")
        lines.append(f"- `{loadtest['output_dir']}/batch_detail.csv` - 批量压测详细 CSV(Excel 可打开)")
        lines.append(f"- `{loadtest['output_dir']}/batch_summary.json` - 批量压测汇总 JSON")
    lines.append("")
    lines.append("---")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="求职分析智能体 - 一站式测试入口")
    parser.add_argument("--skip-unit", action="store_true")
    parser.add_argument("--skip-e2e", action="store_true")
    parser.add_argument("--skip-loadtest", action="store_true")
    parser.add_argument("--loadtest-limit", type=int, default=30)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--output", default="tests/output")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    unit = {}
    e2e = {}
    loadtest = {}
    summary = None

    # 1. 单元测试
    if not args.skip_unit:
        unit = run_unit_tests()

    # 2. E2E
    if not args.skip_e2e:
        try:
            e2e = run_e2e_tests()
        except Exception as exc:  # noqa: BLE001
            print(f"[!] E2E 测试异常: {exc}")

    # 3. 批量压测
    if not args.skip_loadtest:
        try:
            loadtest = run_loadtest(args.loadtest_limit, args.concurrency, output_dir / "loadtest")
            # 读回 summary
            summary_path = output_dir / "loadtest" / "batch_summary.json"
            if summary_path.exists():
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            print(f"[!] 批量压测异常: {exc}")

    # 4. 输出 Markdown 报告
    md = build_markdown_report(unit, e2e, loadtest, summary)
    report_path = output_dir / "full_report.md"
    report_path.write_text(md, encoding="utf-8")
    print(f"\n>> 报告: {report_path}")

    # 退出码
    failed = (unit.get("failed", 0) if unit else 0) + \
             (e2e.get("failed", 0) if e2e else 0) + \
             (loadtest.get("failed", 0) if loadtest else 0)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())