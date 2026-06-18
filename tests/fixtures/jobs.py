"""模拟岗位 JD 数据集.

覆盖岗位方向:
- 互联网研发:Python 后端 / 前端 / 算法工程师 / 全栈
- 数据/分析:数据分析师 / 商业分析师 / 产品经理
- 传统行业:投行 / 风控 / 咨询顾问 / 品牌经理

每个岗位 1-2 个 JD 变体,合计约 18 个 JD,
配合 27 份简历可产生 100+ 组合,支撑中规模批量测试。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List


@dataclass
class JobFixture:
    """模拟 JD."""

    id: str
    title: str
    category: str
    company: str
    location: str
    salary: str
    text: str


def _python_backend_jd() -> JobFixture:
    text = """岗位职责:
1. 负责后端核心业务系统的设计与开发,使用 Python 技术栈(FastAPI / Flask / Django)
2. 维护和优化微服务架构,涉及 Kafka / RabbitMQ 消息队列、Redis 缓存、PostgreSQL / MySQL 数据库
3. 与前端、数据团队协作完成需求落地,推动服务可观测性建设(Prometheus + Grafana)
4. 参与代码评审、技术方案设计,推动工程效能改进
5. 关注 AI 工程化趋势,有 LLM / LangChain / LangGraph 经验者优先

任职要求:
1. 本科及以上学历,计算机相关专业,3 年以上 Python 后端开发经验
2. 熟练掌握 FastAPI / Flask / Django 至少一种 Web 框架,熟悉异步编程(asyncio)
3. 熟悉关系型数据库(MySQL / PostgreSQL)和 NoSQL(Redis / MongoDB),具备 SQL 调优能力
4. 熟悉 Kafka / RabbitMQ 消息队列,有高并发场景经验
5. 熟悉 Docker / Kubernetes 容器化技术,有 CI/CD 实践经验
6. 有开源项目或技术博客者优先

加分项:
- 熟悉 LLM 应用开发(OpenAI / DeepSeek / 通义千问 等至少一种)
- 有向量数据库(PgVector / Milvus / Qdrant / FAISS)使用经验
- 有 SaaS / 电商 / 金融科技行业经验
"""
    return JobFixture(
        id="jd_python_backend_01",
        title="Python 后端开发工程师",
        category="互联网研发-后端",
        company="某互联网大厂",
        location="北京",
        salary="30-50K · 14薪",
        text=text,
    )


def _python_backend_jd_senior() -> JobFixture:
    text = """【高级 Python 后端工程师 / 技术专家】

岗位职责:
1. 主导核心交易/推荐系统的架构设计和技术演进
2. 负责 LangGraph / LangChain 驱动的 AI Agent 平台后端工程化
3. 推动微服务拆分、可观测性、稳定性治理,支撑业务高可用
4. 制定团队技术规范,培养初中级工程师

岗位要求:
1. 计算机相关专业本科及以上,5 年以上 Python 后端经验
2. 精通 FastAPI / Django,熟悉 Celery / asyncio 异步生态
3. 深入理解 Kafka / Redis / PostgreSQL / 向量检索(FAISS / Milvus)
4. 有 LLM 应用工程化经验,熟悉 RAG / Agent / Prompt Engineering
5. 有 Kubernetes 上千级 Pod 规模的生产实践
6. 良好的系统设计能力,能在复杂场景下做出技术权衡
"""
    return JobFixture(
        id="jd_python_backend_02",
        title="高级 Python 后端工程师(AI 方向)",
        category="互联网研发-后端",
        company="AI 创业公司",
        location="上海",
        salary="40-70K · 15薪",
        text=text,
    )


def _frontend_jd() -> JobFixture:
    text = """【前端开发工程师】

岗位职责:
1. 负责 Web 端产品的前端架构设计与核心开发
2. React / Vue 主流框架开发,TypeScript 工程化
3. 与产品、设计、后端协作,推动高质量需求落地
4. 关注性能、可访问性、工程化最佳实践

岗位要求:
1. 本科及以上学历,计算机相关专业,3 年以上前端经验
2. 精通 React 或 Vue 至少一种,熟练使用 TypeScript
3. 熟悉 Webpack / Vite 等构建工具,有大型项目构建优化经验
4. 熟悉浏览器渲染原理,有性能优化(Lighthouse / Core Web Vitals)实战经验
5. 有 Node.js 全栈经验者优先
6. 有可视化(WebGL / Canvas / D3)经验者优先
"""
    return JobFixture(
        id="jd_frontend_01",
        title="高级前端开发工程师",
        category="互联网研发-前端",
        company="某电商平台",
        location="杭州",
        salary="25-45K · 14薪",
        text=text,
    )


def _algo_jd() -> JobFixture:
    text = """【NLP / 大模型算法工程师】

岗位职责:
1. 负责大语言模型(LLM)在业务场景中的微调与落地
2. Prompt 工程、RAG(检索增强生成)、Agent 设计
3. 模型蒸馏、量化、推理加速(TensorRT / vLLM)
4. 与工程团队合作完成模型服务化部署

岗位要求:
1. 硕士及以上学历,机器学习 / NLP / 计算机科学相关专业,2 年以上算法经验
2. 熟悉 PyTorch / TensorFlow 至少一种深度学习框架
3. 熟悉 Transformer / BERT / GPT 系列模型原理,有 LoRA / RLHF / SFT 实践经验
4. 熟悉 LangChain / LangGraph 等 Agent 框架,有向量检索(PGVector / Milvus / FAISS)经验
5. 熟练使用 Python,熟悉 CUDA / DeepSpeed / Megatron 分布式训练者优先
6. 有顶会论文(NeurIPS / ICML / ACL)者优先
"""
    return JobFixture(
        id="jd_algo_01",
        title="NLP / 大模型算法工程师",
        category="互联网研发-算法",
        company="AI 独角兽",
        location="北京",
        salary="35-65K · 15薪",
        text=text,
    )


def _fullstack_jd() -> JobFixture:
    text = """【全栈开发工程师】

岗位职责:
1. 负责 SaaS 产品全栈开发,前端 React/Vue + 后端 Node.js/Go
2. PostgreSQL/MySQL 数据库设计与优化
3. GraphQL API 设计与开发
4. DevOps:Docker / Kubernetes 部署,CI/CD 流水线

岗位要求:
1. 本科及以上学历,3 年以上全栈开发经验
2. 精通 JavaScript / TypeScript,熟悉 React 或 Vue
3. 熟悉 Node.js / Express / NestJS 或 Go / Gin
4. 熟悉关系型数据库和 ORM(Prisma / TypeORM / Sequelize)
5. 有 Serverless / 微前端经验者优先
"""
    return JobFixture(
        id="jd_fullstack_01",
        title="全栈开发工程师",
        category="互联网研发-全栈",
        company="SaaS 公司",
        location="深圳",
        salary="25-45K · 14薪",
        text=text,
    )


def _data_analyst_jd() -> JobFixture:
    text = """【高级数据分析师】

岗位职责:
1. 负责业务数据分析,支持产品、运营、战略决策
2. 搭建指标体系,设计 A/B 实验,解读业务表现
3. SQL + Python 处理海量数据(Hive / Spark / Presto)
4. Tableau / Power BI 可视化报表

岗位要求:
1. 本科及以上学历,统计 / 数学 / 经济学 / 计算机相关专业,3 年以上经验
2. 精通 SQL,熟练使用 Python(Pandas / NumPy / Scikit-learn)
3. 熟悉 A/B 实验设计、因果推断方法
4. 熟悉 Hive / Spark / Presto 等大数据工具
5. 有 Tableau / Power BI / FineBI 等 BI 工具使用经验
6. 良好的业务理解和沟通能力
"""
    return JobFixture(
        id="jd_data_analyst_01",
        title="高级数据分析师",
        category="数据/分析",
        company="互联网大厂",
        location="北京",
        salary="25-40K · 14薪",
        text=text,
    )


def _biz_analyst_jd() -> JobFixture:
    text = """【商业分析师 / 经营分析】

岗位职责:
1. 业务指标拆解与监控,识别业务机会和风险
2. 用户分群与精细化运营分析
3. 行业研究与竞品分析,产出策略建议
4. 跨部门协作推动分析结论落地

岗位要求:
1. 本科及以上,统计 / 金融 / 经济 / 管理类相关专业,2 年以上商业分析经验
2. 精通 SQL 和 Excel,熟练使用 Python 或 R
3. 熟悉 Power BI / Tableau 等 BI 工具
4. 良好的逻辑思维和商业敏感度
5. 咨询公司 / 互联网大厂经营分析经验者优先
"""
    return JobFixture(
        id="jd_biz_analyst_01",
        title="商业分析师",
        category="数据/分析",
        company="O2O 平台",
        location="上海",
        salary="20-35K · 14薪",
        text=text,
    )


def _product_jd() -> JobFixture:
    text = """【高级产品经理】

岗位职责:
1. 负责核心业务线产品规划与设计
2. 用户调研、需求分析、PRD 撰写
3. 推动需求开发上线,跟踪数据表现并迭代优化
4. 与研发、设计、运营、数据团队紧密协作

岗位要求:
1. 本科及以上学历,3 年以上互联网产品经理经验
2. 熟练使用 Axure / Figma 等原型工具
3. 具备 SQL 数据分析能力,熟悉 A/B 测试方法
4. 良好的跨部门沟通与项目推动能力
5. 有 0-1 产品孵化经验者优先
"""
    return JobFixture(
        id="jd_product_01",
        title="高级产品经理",
        category="数据/分析-产品",
        company="内容社区",
        location="北京",
        salary="25-45K · 14薪",
        text=text,
    )


def _ibd_jd() -> JobFixture:
    text = """【投资银行部 - 项目经理】

岗位职责:
1. 参与 IPO / 再融资 / 并购重组项目执行
2. 撰写招股说明书、行业研究报告、反馈意见回复
3. 财务建模、估值分析(DCF / 可比公司 / 相对估值)
4. 协调律师、审计、监管等各方关系

任职要求:
1. 硕士及以上学历,金融 / 经济 / 会计相关专业
2. 3 年以上投行 / 会计师事务所相关经验
3. 具备 CFA / CPA / FRM 证书者优先
4. 熟练使用 Excel / Wind / Bloomberg
5. 良好的中英文写作和沟通能力
6. 抗压能力强,适应高强度出差
"""
    return JobFixture(
        id="jd_ibd_01",
        title="投资银行部项目经理",
        category="传统行业-金融",
        company="头部券商",
        location="北京/上海",
        salary="面议",
        text=text,
    )


def _risk_jd() -> JobFixture:
    text = """【风险建模分析师】

岗位职责:
1. 零售信贷 / 信用卡风险模型监控与迭代
2. Vintage / 迁徙率 / PD / LGD / EAD 计量分析
3. 风险策略制定与回测,推动模型上线
4. 监管报表自动化,协助合规报送

岗位要求:
1. 硕士及以上学历,统计 / 数学 / 金融工程相关专业,2 年以上风控经验
2. 熟练使用 Python + SQL,熟悉 SAS / R
3. 熟悉巴塞尔协议、IFRS9 减值模型者优先
4. 有银行 / 消金 / 互金风控建模经验者优先
"""
    return JobFixture(
        id="jd_risk_01",
        title="风险建模分析师",
        category="传统行业-金融",
        company="股份制商业银行",
        location="上海",
        salary="25-40K",
        text=text,
    )


def _consulting_jd() -> JobFixture:
    text = """【咨询顾问 / 高级咨询顾问】

岗位职责:
1. 战略咨询项目交付,行业研究、案例分析、市场进入策略
2. 数据建模与统计分析,产出 Insight
3. 撰写咨询报告与高质量 PPT 演示
4. 与客户高层沟通,管理项目预期

岗位要求:
1. 国内外顶尖高校本科及以上, MBA 优先
2. 2 年以上战略咨询经验,有 MBB / Big4 项目经验者优先
3. 优秀的逻辑思维与结构化表达能力
4. 熟练使用 PPT / Excel
5. 良好的英语沟通能力
"""
    return JobFixture(
        id="jd_consulting_01",
        title="高级咨询顾问",
        category="传统行业-咨询",
        company="MBB 咨询公司",
        location="上海",
        salary="面议",
        text=text,
    )


def _brand_jd() -> JobFixture:
    text = """【品牌经理】

岗位职责:
1. 负责品牌策略制定、新品上市、营销战役规划
2. 媒介投放管理、KOL 合作、社交媒体运营
3. 消费者洞察与市场调研
4. 跨部门协作推动品牌增长

岗位要求:
1. 本科及以上学历,市场营销 / 广告 / 传播学相关专业
2. 3 年以上快消 / 互联网品牌营销经验
3. 有大型品牌战役操盘经验
4. 优秀的中英文沟通和创意能力
5. 熟练使用 PPT / Excel / 数据分析工具
"""
    return JobFixture(
        id="jd_brand_01",
        title="品牌经理",
        category="传统行业-快消",
        company="全球快消巨头",
        location="上海",
        salary="25-45K · 14薪",
        text=text,
    )


# ============================================================================
# 注册全部 JD
# ============================================================================

_JD_GENERATORS: List[Callable[[], JobFixture]] = [
    _python_backend_jd,
    _python_backend_jd_senior,
    _frontend_jd,
    _algo_jd,
    _fullstack_jd,
    _data_analyst_jd,
    _biz_analyst_jd,
    _product_jd,
    _ibd_jd,
    _risk_jd,
    _consulting_jd,
    _brand_jd,
]


def get_all_jobs() -> List[JobFixture]:
    """获取全部模拟 JD."""
    return [gen() for gen in _JD_GENERATORS]


def get_jobs_by_category(category: str) -> List[JobFixture]:
    """按类目筛选 JD."""
    return [j for j in get_all_jobs() if j.category == category]


if __name__ == "__main__":
    jobs = get_all_jobs()
    print(f"共构造 JD {len(jobs)} 个:")
    by_cat: Dict[str, int] = {}
    for j in jobs:
        by_cat[j.category] = by_cat.get(j.category, 0) + 1
    for c, n in by_cat.items():
        print(f"  - {c}: {n} 个")
    print()
    print("=" * 60)
    print("示例 JD 片段(后端):")
    print("=" * 60)
    print(jobs[0].text[:600])