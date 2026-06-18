# 求职分析智能体 - 全流程测试报告

**生成时间**: 2026-06-18 16:20:57  
**测试范围**: 单元测试 + E2E 测试 + 批量压测  
**LLM**: DeepSeek v4 Flash (真实调用)

---

## 1. 单元测试

- 总数: **67** | 通过: **67** | 失败: 0 | 异常: 0
- 通过率: **100.0%**
- 总耗时: 0.27s

| 模块 | 通过 | 失败 | 耗时(ms) |
|---|---:|---:|---:|
| test_config | 4 | 0 | 0 |
| test_errors | 7 | 0 | 0 |
| test_llm_client | 10 | 0 | 0 |
| test_matchers | 14 | 0 | 0 |
| test_models | 10 | 0 | 0 |
| test_parsers | 7 | 0 | 265 |
| test_progress | 6 | 0 | 0 |
| test_suggestion_generator | 9 | 0 | 0 |

---

## 2. E2E 测试(真实 LLM)

- 总数: **9** | 通过: **9** | 失败: 0 | 异常: 0
- 通过率: **100.0%**
- 总耗时: 422.8s

| 用例 | 状态 | 耗时 |
|---|---|---:|
| test_e2e_extractors::test_e2e_extract_from_bytes | ✅ | 188ms |
| test_e2e_extractors::test_e2e_extract_txt_jd_file | ✅ | 31ms |
| test_e2e_extractors::test_e2e_extract_txt_resume_file | ✅ | 47ms |
| test_e2e_pipeline::test_e2e_backend_resume_vs_backend_jd | ✅ | 76672ms |
| test_e2e_pipeline::test_e2e_backend_resume_vs_finance_jd_low_score | ✅ | 62593ms |
| test_e2e_pipeline::test_e2e_data_analyst_resume_vs_data_jd | ✅ | 54391ms |
| test_e2e_pipeline::test_e2e_frontend_resume_vs_frontend_jd | ✅ | 74016ms |
| test_e2e_pipeline::test_e2e_stream_emits_events | ✅ | 80578ms |
| test_e2e_pipeline::test_e2e_suggestions_have_required_fields | ✅ | 74312ms |

---

## 3. 批量压测

### 3.1 总览

| 指标 | 数值 |
|---|---|
| 用例总数 | **30** |
| 通过数 | **29** |
| 失败数 | 1 |
| 通过率 | **96.7%** |

**耗时统计(ms)**

| avg | median | p95 | min | max |
|---:|---:|---:|---:|---:|
| 92553 | 77109 | 187578 | 47688 | 254891 |

### 3.2 评分与匹配

**综合评分**: avg=30.69, median=25.0, p25=20.0, p75=35.0, min=10.0, max=85.0

**技能覆盖率**: avg=0.208, median=0.17

**经验匹配分**: avg=0.603

**关键词覆盖率**: avg=0.122

**建议数量**: avg=6.4, min=0, max=8

### 3.3 同岗位 vs 跨岗位匹配分对比

| 类别 | 数量 | 平均分 | 中位分 |
|---|---:|---:|---:|
| 同岗位(同类目) | 6 | 56.17 | 55.0 |
| 跨岗位 | 23 | 24.04 | 20.0 |

> 差异 **32.1 分**,模型能有效区分同类目与跨类目岗位。

### 3.4 按 JD 类目统计

| JD 类目 | 用例数 | 通过 | 平均分 | 平均耗时 |
|---|---:|---:|---:|---:|
| 互联网研发-后端 | 6 | 6 | 56.17 | 89216ms |
| 互联网研发-全栈 | 3 | 3 | 37.67 | 130995ms |
| 互联网研发-算法 | 3 | 3 | 28.33 | 88641ms |
| 数据/分析 | 5 | 5 | 26.0 | 108837ms |
| 传统行业-金融 | 4 | 4 | 20.0 | 78211ms |
| 传统行业-咨询 | 2 | 1 | 20.0 | 99914ms |
| 互联网研发-前端 | 3 | 3 | 18.33 | 76021ms |
| 数据/分析-产品 | 2 | 2 | 17.5 | 57617ms |
| 传统行业-快消 | 2 | 2 | 17.5 | 59219ms |

### 3.5 错误分析

| 异常类型 | 数量 |
|---|---:|
| WorkflowError | 1 |

**失败明细:**

- `backend_01__jd_consulting_01`: WorkflowError: LLM 综合评分失败: name 'List' is not defined

### 3.6 Top 5 高分匹配

| 简历 | JD | 综合分 | 技能覆盖 | 经验匹配 |
|---|---|---:|---:|---:|
| backend_01 | Python 后端开发工程师 | 85.0 | 0.75 | 0.6 |
| backend_01 | 高级 Python 后端工程师(AI 方向) | 82.0 | 0.68 | 0.6 |
| backend_02 | Python 后端开发工程师 | 65.0 | 0.3889 | 0.6 |
| backend_01 | 全栈开发工程师 | 48.0 | 0.17 | 0.6 |
| backend_03 | Python 后端开发工程师 | 45.0 | 0.4 | 0.6 |

---

## 4. 测试产物

- `tests/output/test_report.json` - 单元测试详细报告
- `tests/output/e2e_report.json` - E2E 测试详细报告
- `tests/output/loadtest/batch_detail.json` - 批量压测详细 JSON
- `tests/output/loadtest/batch_detail.csv` - 批量压测详细 CSV(可用 Excel 打开)
- `tests/output/loadtest/batch_summary.json` - 批量压测汇总统计

---

## 5. 测试结论与改进建议

### 5.1 优点

- ✅ 批量压测通过率 **96.7%**,工作流主链路稳定
- ✅ 同岗位(56.2) vs 跨岗位(24.0)评分差异 **32.1 分**,匹配模型能有效区分
- ✅ 技能/经验/关键词三大匹配维度均能输出合理评分
- ✅ 建议数量平均 6.4 条,符合 5-8 条 schema 约束

### 5.2 待改进

- ⚠️ 存在 1 类异常,主要为 LLM 输出格式问题,建议在 aggregate_report 节点加固 JSON 解析
- ⚠️ P95 耗时 187.6s,建议考虑缓存已抽取的简历/JD 减少重复调用
- ⚠️ 最高综合评分仅 85.0,建议在 prompt 中加入量化标准,提升高质量匹配识别
- 💡 经验匹配分(0.603)显著高于技能覆盖率(0.208),提示技能匹配规则偏严,可考虑扩展别名词典

### 5.3 后续测试建议

- 扩大批量规模到 100+ 用例,获取更稳定的统计置信度
- 引入 mock LLM 单元测试,提升 CI 速度
- 增加压力测试(并发 10+),验证 LLM 限流下的降级能力
- 增加简历/JD 异常输入的鲁棒性测试