# 求职分析智能体 - 测试套件

本目录包含完整的工作流测试套件,覆盖:

| 阶段 | 范围 | LLM 调用 | 速度 |
|---|---|---|---|
| 单元测试 (`unit/`) | 解析器、抽取客户端、匹配器、建议生成、模型、配置、错误码、进度 | 无 | < 1s |
| E2E 测试 (`e2e/`) | 端到端工作流(单条用例) | 真实 LLM | ~1 min/条 |
| 批量压测 (`loadtest/`) | 27 份简历 × 12 个 JD 组合 | 真实 LLM | ~15s/条 (并发 4) |

## 数据集

- `fixtures/resumes.py`: 27 份简历,覆盖 9 个细分类目
  - 互联网研发-后端 / 前端 / 算法 / 全栈(每类 3 份)
  - 数据/分析 / 产品(每类 3 份)
  - 传统行业-金融 / 咨询 / 快消(每类 3 份)
- `fixtures/jobs.py`: 12 个 JD,覆盖同类目

完整笛卡尔积 = 27 × 12 = **324 个组合**。

## 快速使用

### 跑单元测试(秒级)

```bash
D:\miniconda\envs\fastapi\python.exe tests/runner.py --tag unit
```

### 跑 E2E 测试(5-10 分钟,真实 LLM)

```bash
D:\miniconda\envs\fastapi\python.exe tests/runner.py --tag e2e
```

### 跑批量压测(默认 30 用例 × 并发 4)

```bash
D:\miniconda\envs\fastapi\python.exe tests/loadtest/batch_e2e.py --limit 30 --concurrency 4
```

### 一站式:单元 + E2E + 压测

```bash
D:\miniconda\envs\fastapi\python.exe tests/run_all.py --loadtest-limit 50 --concurrency 4
```

## 报告产物

- `output/test_report.json` - 单元测试 JSON 报告
- `output/e2e_report.json` - E2E 测试 JSON 报告
- `output/loadtest/batch_detail.json` - 压测详细 JSON
- `output/loadtest/batch_detail.csv` - 压测 CSV(Excel 可打开)
- `output/loadtest/batch_summary.json` - 压测汇总统计
- `output/full_report.md` - 一站式 Markdown 总报告

## 自定义测试规模

```bash
# 中规模(50 用例,5-10 分钟)
D:\miniconda\envs\fastapi\python.exe tests/run_all.py --loadtest-limit 50 --concurrency 4

# 大规模(全部 324 组合,~80 分钟)
D:\miniconda\envs\fastapi\python.exe tests/run_all.py --loadtest-limit 324 --concurrency 6
```

## 添加新测试

1. 在 `tests/unit/` 或 `tests/e2e/` 下新建 `test_xxx.py`
2. 函数名以 `test_` 开头
3. 用 `@unit` / `@e2e` / `@slow` 装饰器标记
4. 失败时抛 `AssertionError`,框架自动捕获并汇总

示例:

```python
from tests.runner import e2e
from app.services.analyzer import AnalyzerService

@e2e
def test_my_e2e():
    import asyncio
    service = AnalyzerService()
    result = asyncio.run(service.analyze(
        resume_bytes=b"...",
        job_text="...",
    ))
    assert result["match_report"]["overall_score"] > 50
```

## 注意

- 测试默认调用 `DEEPSEEK_API_KEY`,请确保 `.env` 已配置
- 数据库缓存写入失败时会自动降级,不影响测试结果
- LLM 输出偶发 JSON 解析失败,系统自动重试 1 次;若仍失败使用 fallback 建议(建议数 1-3 条)
- 单元测试可在离线/CI 环境无 LLM 情况下跑通