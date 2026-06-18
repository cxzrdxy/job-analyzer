"""轻量级测试运行器(无 pytest 依赖).

设计目标:
- 用 stdlib + dataclass 实现 unittest.TestCase 的简化版
- 自动发现 tests/unit/ 和 tests/e2e/ 下以 test_ 开头的 .py 文件
- 输出汇总报告 + 每个用例的执行结果
- 支持标签过滤(@unit / @e2e / @slow)
- 输出 JSON 报告供后续分析
"""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import inspect
import json
import sys
import time
import traceback
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

TESTS_ROOT = Path(__file__).resolve().parent


# ---- 装饰器 / 标签 ----

def unit(func: Callable) -> Callable:
    """标记为单元测试(快速,无 LLM 调用)."""
    func.__test_tag__ = "unit"
    return func


def e2e(func: Callable) -> Callable:
    """标记为端到端测试(调用 LLM,较慢)."""
    func.__test_tag__ = "e2e"
    return func


def slow(func: Callable) -> Callable:
    """标记为慢测试(批量压测,默认跳过)."""
    func.__test_tag__ = "slow"
    func.__test_tag__ = getattr(func, "__test_tag__", "") + " slow"
    return func


# ---- 测试结果 ----

@dataclass
class TestResult:
    name: str
    module: str
    tag: str
    status: str  # passed / failed / error / skipped
    duration_ms: float
    message: str = ""
    traceback: str = ""


@dataclass
class SuiteReport:
    started_at: str
    duration_s: float
    total: int = 0
    passed: int = 0
    failed: int = 0
    error: int = 0
    skipped: int = 0
    results: List[TestResult] = field(default_factory=list)

    def passed_ratio(self) -> float:
        return self.passed / self.total if self.total else 0.0


# ---- 用例收集 ----

def collect_tests(tags: List[str]) -> List[Dict[str, Any]]:
    """发现并加载所有测试用例."""
    found: List[Dict[str, Any]] = []

    # 把项目根目录加入 sys.path,确保 tests.* 可被 import
    project_root = TESTS_ROOT.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    search_dirs = [
        TESTS_ROOT / "unit",
        TESTS_ROOT / "e2e",
    ]
    for d in search_dirs:
        if not d.exists():
            continue
        for py in sorted(d.glob("test_*.py")):
            mod_name = f"tests.{d.name}.{py.stem}"
            try:
                spec = importlib.util.spec_from_file_location(mod_name, py)
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                sys.modules[mod_name] = module
                spec.loader.exec_module(module)
            except Exception as exc:  # noqa: BLE001
                print(f"[!] 模块加载失败 {py}: {exc}")
                continue

            for name, obj in inspect.getmembers(module, inspect.isfunction):
                if not name.startswith("test_"):
                    continue
                if not callable(obj):
                    continue
                # 只保留从该模块定义的函数,排除导入项
                if getattr(obj, "__module__", None) != mod_name:
                    continue
                tag = getattr(obj, "__test_tag__", "")
                if tags and not any(t in tag for t in tags):
                    continue
                found.append({
                    "module": mod_name,
                    "name": name,
                    "func": obj,
                    "tag": tag or "unit",
                    "file": str(py.relative_to(project_root)),
                })

    return found


# ---- 运行 ----

def run_tests(tags: List[str], verbose: bool = True) -> SuiteReport:
    """执行全部匹配用例."""
    from datetime import datetime

    cases = collect_tests(tags)
    started = datetime.now().isoformat()
    t0 = time.monotonic()
    report = SuiteReport(started_at=started, duration_s=0.0)

    print(f"\n>> 发现 {len(cases)} 个测试用例 (tags={tags or 'ALL'})\n")
    print("=" * 80)

    for case in cases:
        report.total += 1
        name = f"{case['module'].split('.')[-1]}::{case['name']}"
        if verbose:
            print(f"[{report.total:03d}] {name}", end=" ... ", flush=True)

        tc0 = time.monotonic()
        status = "passed"
        message = ""
        tb_text = ""
        try:
            case["func"]()
        except AssertionError as exc:
            status = "failed"
            message = str(exc) or "断言失败"
            tb_text = traceback.format_exc()
        except Exception as exc:  # noqa: BLE001
            status = "error"
            message = f"{type(exc).__name__}: {exc}"
            tb_text = traceback.format_exc()

        elapsed_ms = (time.monotonic() - tc0) * 1000
        if status == "passed":
            report.passed += 1
            if verbose:
                print(f"OK ({elapsed_ms:.0f}ms)")
        elif status == "failed":
            report.failed += 1
            if verbose:
                print(f"FAIL ({elapsed_ms:.0f}ms)")
                print(f"     {message}")
        else:
            report.error += 1
            if verbose:
                print(f"ERROR ({elapsed_ms:.0f}ms)")
                print(f"     {message}")

        report.results.append(TestResult(
            name=case["name"],
            module=case["module"],
            tag=case["tag"],
            status=status,
            duration_ms=elapsed_ms,
            message=message,
            traceback=tb_text,
        ))

    report.duration_s = round(time.monotonic() - t0, 3)
    return report


# ---- 报告输出 ----

def print_summary(report: SuiteReport) -> None:
    """打印汇总."""
    print("\n" + "=" * 80)
    print(f"汇总: 总数={report.total}, 通过={report.passed}, 失败={report.failed}, "
          f"异常={report.error}, 通过率={report.passed_ratio()*100:.1f}%, "
          f"总耗时={report.duration_s:.1f}s")
    print("=" * 80)


def write_json_report(report: SuiteReport, path: Path) -> None:
    """落盘 JSON 报告."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(report)
    # 去除过长的 traceback 摘要
    for r in data["results"]:
        if r.get("traceback"):
            r["traceback"] = r["traceback"][:1500]
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f">> JSON 报告: {path}")


# ---- CLI ----

def main() -> int:
    parser = argparse.ArgumentParser(description="轻量测试运行器")
    parser.add_argument(
        "--tag",
        action="append",
        default=[],
        help="按标签过滤,例如 --tag unit / --tag e2e / --tag slow",
    )
    parser.add_argument("--report", default="tests/output/test_report.json")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    report = run_tests(args.tag, verbose=not args.quiet)
    print_summary(report)

    if args.report:
        write_json_report(report, Path(args.report))

    return 0 if report.failed == 0 and report.error == 0 else 1


if __name__ == "__main__":
    sys.exit(main())