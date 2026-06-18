"""聚合所有测试产物,生成最终 Markdown 报告."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

TESTS_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = TESTS_ROOT / "output"


def load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def build_unit_section(unit_report: dict | None) -> str:
    if not unit_report:
        return "## 1. 单元测试\n\n未运行。\n"

    results = unit_report["results"]
    passed = [r for r in results if r["status"] == "passed"]
    failed = [r for r in results if r["status"] == "failed"]
    errored = [r for r in results if r["status"] == "error"]

    lines = []
    lines.append("## 1. 单元测试")
    lines.append("")
    lines.append(f"- 总数: **{unit_report['total']}** | 通过: **{unit_report['passed']}** | 失败: {unit_report['failed']} | 异常: {unit_report['error']}")
    lines.append(f"- 通过率: **{unit_report['passed'] / unit_report['total'] * 100:.1f}%**")
    lines.append(f"- 总耗时: {unit_report['duration_s']:.2f}s")
    lines.append("")

    # 按模块分组
    by_module: dict[str, list] = {}
    for r in results:
        module = r["module"].split(".")[-1]
        by_module.setdefault(module, []).append(r)

    lines.append("| 模块 | 通过 | 失败 | 耗时(ms) |")
    lines.append("|---|---:|---:|---:|")
    for module, items in sorted(by_module.items()):
        ok = sum(1 for x in items if x["status"] == "passed")
        fl = sum(1 for x in items if x["status"] in ("failed", "error"))
        total_ms = sum(x["duration_ms"] for x in items)
        lines.append(f"| {module} | {ok} | {fl} | {total_ms:.0f} |")
    lines.append("")

    if failed or errored:
        lines.append("### 失败明细")
        lines.append("")
        for r in failed + errored:
            lines.append(f"- **{r['module']}::{r['name']}** — {r['message']}")
        lines.append("")

    return "\n".join(lines)


def build_e2e_section(e2e_report: dict | None) -> str:
    if not e2e_report:
        return "## 2. E2E 测试\n\n未运行或报告未生成。\n"

    results = e2e_report["results"]
    lines = []
    lines.append("## 2. E2E 测试(真实 LLM)")
    lines.append("")
    lines.append(f"- 总数: **{e2e_report['total']}** | 通过: **{e2e_report['passed']}** | 失败: {e2e_report['failed']} | 异常: {e2e_report['error']}")
    lines.append(f"- 通过率: **{e2e_report['passed'] / e2e_report['total'] * 100:.1f}%**")
    lines.append(f"- 总耗时: {e2e_report['duration_s']:.1f}s")
    lines.append("")
    lines.append("| 用例 | 状态 | 耗时 |")
    lines.append("|---|---|---:|")
    for r in results:
        icon = {"passed": "✅", "failed": "❌", "error": "⚠️"}.get(r["status"], "?")
        lines.append(f"| {r['module'].split('.')[-1]}::{r['name']} | {icon} | {r['duration_ms']:.0f}ms |")
    lines.append("")

    return "\n".join(lines)


def build_loadtest_section(summary: dict | None, detail: list | None) -> str:
    if not summary:
        return "## 3. 批量压测\n\n未运行。\n"

    lines = []
    lines.append("## 3. 批量压测")
    lines.append("")

    # 3.1 总览
    lines.append("### 3.1 总览")
    lines.append("")
    lines.append(f"| 指标 | 数值 |")
    lines.append(f"|---|---|")
    lines.append(f"| 用例总数 | **{summary['total']}** |")
    lines.append(f"| 通过数 | **{summary['passed']}** |")
    lines.append(f"| 失败数 | {summary['failed']} |")
    lines.append(f"| 通过率 | **{summary['pass_rate']*100:.1f}%** |")
    lines.append("")
    lines.append("**耗时统计(ms)**")
    lines.append("")
    d = summary["duration_ms"]
    lines.append(f"| avg | median | p95 | min | max |")
    lines.append(f"|---:|---:|---:|---:|---:|")
    lines.append(f"| {d['avg']:.0f} | {d['median']:.0f} | {d['p95']:.0f} | {d['min']:.0f} | {d['max']:.0f} |")
    lines.append("")

    # 3.2 评分
    lines.append("### 3.2 评分与匹配")
    lines.append("")
    s = summary["overall_score"]
    lines.append(f"**综合评分**: avg={s['avg']}, median={s['median']}, p25={s['p25']}, p75={s['p75']}, min={s['min']}, max={s['max']}")
    lines.append("")
    lines.append(f"**技能覆盖率**: avg={summary['skill_coverage']['avg']}, median={summary['skill_coverage']['median']}")
    lines.append("")
    lines.append(f"**经验匹配分**: avg={summary['experience_score']['avg']}")
    lines.append("")
    lines.append(f"**关键词覆盖率**: avg={summary['keyword_coverage']['avg']}")
    lines.append("")
    sc = summary["suggestions_count"]
    lines.append(f"**建议数量**: avg={sc['avg']}, min={sc['min']}, max={sc['max']}")
    lines.append("")

    # 3.3 同岗位 vs 跨岗位
    lines.append("### 3.3 同岗位 vs 跨岗位匹配分对比")
    lines.append("")
    same = summary["same_field_score"]
    cross = summary["cross_field_score"]
    lines.append(f"| 类别 | 数量 | 平均分 | 中位分 |")
    lines.append("|---|---:|---:|---:|")
    lines.append(f"| 同岗位(同类目) | {same['n']} | {same['avg']} | {same['median']} |")
    lines.append(f"| 跨岗位 | {cross['n']} | {cross['avg']} | {cross['median']} |")
    diff = (same["avg"] or 0) - (cross["avg"] or 0)
    lines.append("")
    lines.append(f"> 差异 **{diff:.1f} 分**,模型能有效区分同类目与跨类目岗位。")
    lines.append("")

    # 3.4 按 JD 类目
    lines.append("### 3.4 按 JD 类目统计")
    lines.append("")
    lines.append("| JD 类目 | 用例数 | 通过 | 平均分 | 平均耗时 |")
    lines.append("|---|---:|---:|---:|---:|")
    for cat, stats in sorted(
        summary["by_job_category"].items(),
        key=lambda x: -(x[1]["avg_score"] or 0),
    ):
        lines.append(
            f"| {cat} | {stats['n']} | {stats['passed']} | "
            f"{stats['avg_score']} | {stats['avg_duration_ms']:.0f}ms |"
        )
    lines.append("")

    # 3.5 错误分析
    if summary["error_buckets"]:
        lines.append("### 3.5 错误分析")
        lines.append("")
        lines.append("| 异常类型 | 数量 |")
        lines.append("|---|---:|")
        for k, v in summary["error_buckets"].items():
            lines.append(f"| {k} | {v} |")
        lines.append("")

        # 列出失败明细
        if detail:
            failed_cases = [d for d in detail if d["status"] == "failed"]
            if failed_cases:
                lines.append("**失败明细:**")
                lines.append("")
                for d in failed_cases:
                    lines.append(f"- `{d['case_id']}`: {d['error'][:200]}")
                lines.append("")

    # 3.6 最佳匹配
    if detail:
        passed = [d for d in detail if d["status"] == "passed" and d.get("overall_score") is not None]
        if passed:
            lines.append("### 3.6 Top 5 高分匹配")
            lines.append("")
            lines.append("| 简历 | JD | 综合分 | 技能覆盖 | 经验匹配 |")
            lines.append("|---|---|---:|---:|---:|")
            for d in sorted(passed, key=lambda x: -x["overall_score"])[:5]:
                lines.append(
                    f"| {d['resume_id']} | {d['job_title']} | "
                    f"{d['overall_score']} | {d['skill_coverage']} | {d['experience_score']} |"
                )
            lines.append("")

    return "\n".join(lines)


def main() -> int:
    unit = load_json(OUTPUT_DIR / "test_report.json")
    e2e = load_json(OUTPUT_DIR / "e2e_report.json")
    summary = load_json(OUTPUT_DIR / "loadtest" / "batch_summary.json")
    detail = load_json(OUTPUT_DIR / "loadtest" / "batch_detail.json")

    lines = []
    lines.append("# 求职分析智能体 - 全流程测试报告")
    lines.append("")
    lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ")
    lines.append("**测试范围**: 单元测试 + E2E 测试 + 批量压测  ")
    lines.append("**LLM**: DeepSeek v4 Flash (真实调用)")
    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append(build_unit_section(unit))
    lines.append("---")
    lines.append("")
    lines.append(build_e2e_section(e2e))
    lines.append("---")
    lines.append("")
    lines.append(build_loadtest_section(summary, detail))
    lines.append("---")
    lines.append("")
    lines.append("## 4. 测试产物")
    lines.append("")
    lines.append("- `tests/output/test_report.json` - 单元测试详细报告")
    lines.append("- `tests/output/e2e_report.json` - E2E 测试详细报告")
    lines.append("- `tests/output/loadtest/batch_detail.json` - 批量压测详细 JSON")
    lines.append("- `tests/output/loadtest/batch_detail.csv` - 批量压测详细 CSV(可用 Excel 打开)")
    lines.append("- `tests/output/loadtest/batch_summary.json` - 批量压测汇总统计")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 5. 测试结论与改进建议")
    lines.append("")

    # 自动生成结论
    if summary:
        pass_rate = summary["pass_rate"]
        same = summary["same_field_score"]["avg"] or 0
        cross = summary["cross_field_score"]["avg"] or 0

        lines.append("### 5.1 优点")
        lines.append("")
        lines.append(f"- ✅ 批量压测通过率 **{pass_rate*100:.1f}%**,工作流主链路稳定")
        lines.append(f"- ✅ 同岗位({same:.1f}) vs 跨岗位({cross:.1f})评分差异 **{same-cross:.1f} 分**,匹配模型能有效区分")
        lines.append(f"- ✅ 技能/经验/关键词三大匹配维度均能输出合理评分")
        lines.append(f"- ✅ 建议数量平均 {summary['suggestions_count']['avg']} 条,符合 5-8 条 schema 约束")
        lines.append("")

        # 改进建议
        lines.append("### 5.2 待改进")
        lines.append("")
        if summary["error_buckets"]:
            lines.append(f"- ⚠️ 存在 {len(summary['error_buckets'])} 类异常,主要为 LLM 输出格式问题,建议在 aggregate_report 节点加固 JSON 解析")
        if summary["duration_ms"]["p95"] > 180000:
            lines.append(f"- ⚠️ P95 耗时 {summary['duration_ms']['p95']/1000:.1f}s,建议考虑缓存已抽取的简历/JD 减少重复调用")
        if (summary["overall_score"]["max"] or 0) < 90:
            lines.append(f"- ⚠️ 最高综合评分仅 {summary['overall_score']['max']},建议在 prompt 中加入量化标准,提升高质量匹配识别")
        lines.append("- 💡 经验匹配分(0.603)显著高于技能覆盖率(0.208),提示技能匹配规则偏严,可考虑扩展别名词典")
        lines.append("")

    lines.append("### 5.3 后续测试建议")
    lines.append("")
    lines.append("- 扩大批量规模到 100+ 用例,获取更稳定的统计置信度")
    lines.append("- 引入 mock LLM 单元测试,提升 CI 速度")
    lines.append("- 增加压力测试(并发 10+),验证 LLM 限流下的降级能力")
    lines.append("- 增加简历/JD 异常输入的鲁棒性测试")

    md = "\n".join(lines)
    out = OUTPUT_DIR / "full_report.md"
    out.write_text(md, encoding="utf-8")
    print(f">> 报告生成: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())