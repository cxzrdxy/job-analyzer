"""模拟简历数据集.

覆盖三类目标岗位:
- 互联网研发(后端 / 前端 / 算法 / 全栈)
- 数据 / 分析 / 产品
- 传统行业职能(金融 / 咨询 / 快消)

每个岗位类目构造 8 份典型简历,合计 24 份,
足以支撑中规模批量测试(200+ 组合)。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List


@dataclass
class ResumeFixture:
    """模拟简历."""

    id: str
    name: str
    category: str           # 候选人类别,用于交叉测试
    target_role: str        # 期望应聘的岗位方向
    years: float
    text: str


def _backend_resume(idx: int) -> ResumeFixture:
    """互联网后端工程师简历模板."""
    profiles = [
        ("张博文", 4.5, "本科", "北京邮电大学", "计算机科学与技术",
         ["字节跳动", "美团"],
         ["Python 后端开发工程师", "高级 Python 开发工程师"],
         "负责高并发推荐接口、日志平台、监控告警系统建设;使用 FastAPI + Celery + Redis 构建异步任务调度体系;Kafka 消息队列日均处理 20 亿条数据;PostgreSQL + PgVector 实现向量召回;Prometheus + Grafana 全链路监控。",
         ["日均 20 亿条 Kafka 数据接入,端到端 P99 延迟 200ms 以下",
          "FastAPI 服务 QPS 峰值 5w,GC 时间下降 40%",
          "PgVector 向量召回 P99 < 30ms,相关推荐 CTR 提升 12%"],
         ["Python", "FastAPI", "Django", "PostgreSQL", "Redis", "Kafka", "Celery", "Docker", "Kubernetes", "gRPC", "Prometheus", "Grafana", "LangGraph", "OpenAI API"]),
        ("李泽宇", 2.0, "本科", "武汉大学", "软件工程",
         ["小米科技"],
         ["Python 后端开发工程师"],
         "负责 IoT 设备管理平台后端开发,基于 Flask + SQLAlchemy + MySQL 实现设备影子、远程控制、固件升级;Redis 做缓存层,提升接口响应 35%;Docker Compose 编排服务;GitLab CI 自动化部署。",
         ["管理 50 万台 IoT 设备,可用率 99.95%",
          "Redis 缓存命中率达 92%,平均响应时间从 280ms 降至 90ms",
          "上线 30+ RESTful 接口,文档覆盖率 100%"],
         ["Python", "Flask", "SQLAlchemy", "MySQL", "Redis", "Docker", "GitLab CI", "Linux", "Nginx"]),
        ("王思远", 6.5, "硕士", "清华大学", "计算机科学与技术",
         ["阿里巴巴", "腾讯"],
         ["高级后端开发工程师", "技术专家"],
         "主导电商交易核心系统重构,Java/Go 双语言栈;Spring Cloud 微服务 + Dubbo 高性能 RPC;分布式事务 Seata;Tair 自研缓存;JVM 调优,Full GC 频率从 8 次/天降到 0;参与双 11 大促,峰值 58 万 QPS。",
         ["重构交易系统,TPS 提升 3 倍,大促期间 0 故障",
          "推动 12 个核心服务从 Java 迁移到 Go,资源成本下降 40%",
          "JVM 调优将 Full GC 频率从 8 次/天降到 0"],
         ["Java", "Go", "Spring Cloud", "Dubbo", "MySQL", "Tair", "Redis", "Kafka", "Seata", "Docker", "Kubernetes", "JVM 调优"]),
        ("陈佳琪", 3.0, "本科", "华南理工大学", "软件工程",
         ["Shopee"],
         ["后端工程师"],
         "东南亚电商后端服务,Go + Gin 框架;MongoDB + Elasticsearch 搜索推荐;跨区域数据同步基于 Kafka Connect;Prometheus + Loki + Tempo 实现可观测性。",
         ["搜索召回准确率提升 18%",
          "跨区域同步延迟从分钟级降到秒级",
          "On-call 故障平均修复时间 MTTR < 15min"],
         ["Go", "Gin", "MongoDB", "Elasticsearch", "Kafka", "Docker", "Kubernetes", "Prometheus", "Loki"]),
        ("赵梓豪", 1.5, "本科", "西安电子科技大学", "计算机科学与技术",
         ["创业公司 ABC Tech"],
         ["Python 后端实习生 → 全职"],
         "校招入职,参与 SaaS 客户管理系统后端开发;FastAPI + Tortoise ORM + PostgreSQL;Vue3 管理后台;通过编写单元测试和接口自动化,代码覆盖率从 30% 提升到 78%。",
         ["完成 18 个业务接口开发与上线",
          "Pytest 覆盖率从 30% 提升至 78%",
          "数据库索引优化,核心接口响应降低 60%"],
         ["Python", "FastAPI", "Tortoise ORM", "PostgreSQL", "Vue3", "Pytest", "Docker"]),
        ("刘嘉欣", 5.0, "硕士", "上海交通大学", "计算机科学与技术",
         ["微软亚洲研究院", "蚂蚁集团"],
         ["后端工程师", "高级开发工程师"],
         "微软参与 Bing 搜索相关性模型后端工程化,使用 C# + .NET;蚂蚁负责支付链路稳定性建设,Java + Spring Boot + OceanBase;深入了解分布式系统、CAP 理论、共识算法。",
         ["Bing 相关性模型服务化,SLA 99.99%",
          "蚂蚁支付链路压测峰值 12w TPS,资金损失率 < 1e-7",
          "发表 2 篇分布式系统专利"],
         ["Java", "Spring Boot", "C#", ".NET", "OceanBase", "MySQL", "Redis", "Kafka", "分布式系统", "Elasticsearch"]),
        ("周天翊", 4.0, "本科", "浙江大学", "信息工程",
         ["网易雷火"],
         ["游戏后端开发工程师"],
         "MMORPG 游戏后端,C++ + Skynet + Lua;自研分布式 Actor 框架;MySQL + Redis + Tair 多级缓存;支撑同时在线 30 万人,峰值消息广播 50w QPS。",
         ["支撑 30 万人同时在线,SLA 99.95%",
          "战斗消息广播延迟 P99 < 50ms",
          "Lua 脚本优化,GC 暂停 < 5ms"],
         ["C++", "Lua", "Skynet", "MySQL", "Redis", "Tair", "Linux", "GDB"]),
        ("吴梓萱", 2.5, "本科", "中山大学", "计算机科学与技术",
         ["平安科技"],
         ["Java 后端开发"],
         "金融信贷系统后端开发,Spring Boot + MyBatis + MySQL + Redis;参与风控决策引擎;RocketMQ 异步解耦;ShardingSphere 分库分表。",
         ["风控决策 P99 延迟 < 80ms",
          "ShardingSphere 拆分后单表行数下降 95%",
          "消息积压告警系统减少 80% 人工介入"],
         ["Java", "Spring Boot", "MyBatis", "MySQL", "Redis", "RocketMQ", "ShardingSphere", "Shiro"]),
    ]
    name, years, degree, school, major, companies, positions, desc, achievements, skills = profiles[idx % len(profiles)]
    body = _format_resume(name, years, degree, school, major, companies, positions, desc, achievements, skills)
    return ResumeFixture(
        id=f"backend_{idx+1:02d}",
        name=name,
        category="互联网研发-后端",
        target_role="后端工程师",
        years=years,
        text=body,
    )


def _frontend_resume(idx: int) -> ResumeFixture:
    """互联网前端工程师简历模板."""
    profiles = [
        ("黄子墨", 3.5, "本科", "北京航空航天大学", "计算机科学与技术",
         ["京东", "小红书"],
         ["高级前端开发工程师"],
         "负责电商营销活动平台前端架构,React 18 + TypeScript + Vite;自研微前端沙箱(qiankun 微内核方案);可视化搭建系统;SSR/SSG + Next.js;Lighthouse 性能优化,首屏 LCP 从 3.2s 降至 1.4s。",
         ["LCP 从 3.2s 优化到 1.4s,FCP < 1s",
          "搭建可视化页面编辑器,运营产出效率提升 5 倍",
          "微前端沙箱方案支撑 20+ 业务并行开发"],
         ["React", "TypeScript", "Vite", "Next.js", "qiankun", "TailwindCSS", "Node.js", "Webpack", "Jest", "Playwright"]),
        ("孙语桐", 2.0, "本科", "华中科技大学", "软件工程",
         ["滴滴出行"],
         ["前端开发工程师"],
         "负责司机端 H5 页面开发,Vue3 + Vite + Pinia;移动端性能优化,首屏包体积从 1.2MB 压缩到 380KB;通过 Web Worker 将复杂计算迁移到后台线程。",
         ["司机端首屏时间从 2.1s 降至 0.9s",
          "包体积从 1.2MB 压缩到 380KB",
          "Crash 率从 0.8% 降到 0.15%"],
         ["Vue3", "Vite", "Pinia", "TypeScript", "Webpack", "JavaScript", "Sass", "Node.js"]),
        ("罗梓琪", 5.5, "硕士", "复旦大学", "软件工程",
         ["蚂蚁集团", "字节跳动"],
         ["前端架构师", "高级前端工程师"],
         "蚂蚁链 Web 端架构设计,React + Dumi 组件库;字节跳动 Lark 表格性能优化,Canvas + WebGL 大表格渲染百万级单元格;主导 monorepo 改造,增量构建提速 70%。",
         ["Lark 表格支持百万单元格滚动流畅",
          "monorepo 增量构建时间下降 70%",
          "组件库日均被引用 12k 次"],
         ["React", "TypeScript", "Dumi", "Canvas", "WebGL", "Monorepo", "Lerna", "Turborepo", "Jest"]),
        ("高旭尧", 1.5, "本科", "电子科技大学", "信息工程",
         ["创业公司"],
         ["前端开发工程师"],
         "校招入职,React + Ant Design 中后台开发;Webpack 工程化;封装通用 Hooks;与产品经理协作完成 30+ 业务页面。",
         ["通用 Hooks 复用率 60%",
          "页面开发周期从 5 天压缩到 2 天",
          "主动修复 100+ 用户反馈 bug"],
         ["React", "JavaScript", "Ant Design", "Webpack", "TypeScript", "ESLint"]),
        ("林雅婷", 4.0, "本科", "厦门大学", "计算机科学与技术",
         ["Shopee"],
         ["高级前端开发工程师"],
         "海外电商 Web 端性能与体验优化,Next.js + React;Lighthouse 平均分从 65 提升到 92;CDN + 图片压缩 + Service Worker 缓存策略;i18n 多语言方案。",
         ["Lighthouse 评分从 65 提升到 92",
          "跳出率从 45% 降至 30%",
          "支持 8 种语言,本地化效率提升 3 倍"],
         ["React", "Next.js", "TypeScript", "PWA", "Service Worker", "Webpack", "Jest", "Cypress"]),
        ("韩明哲", 3.0, "本科", "中国科学技术大学", "计算机科学与技术",
         ["网易"],
         ["前端工程师"],
         "Web 游戏前端开发,Phaser + PixiJS;Cocos 引擎调试;WebGL 着色器;Webpack 性能调优。",
         ["自研 WebGL 粒子系统,支持 5w 同屏粒子",
          "首屏加载时间从 3.5s 优化到 1.2s"],
         ["JavaScript", "TypeScript", "Phaser", "PixiJS", "WebGL", "Three.js", "Webpack"]),
    ]
    name, years, degree, school, major, companies, positions, desc, achievements, skills = profiles[idx % len(profiles)]
    body = _format_resume(name, years, degree, school, major, companies, positions, desc, achievements, skills)
    return ResumeFixture(
        id=f"frontend_{idx+1:02d}",
        name=name,
        category="互联网研发-前端",
        target_role="前端工程师",
        years=years,
        text=body,
    )


def _algo_resume(idx: int) -> ResumeFixture:
    """算法工程师简历模板."""
    profiles = [
        ("徐子谦", 4.0, "硕士", "北京大学", "计算机科学(机器学习方向)",
         ["商汤科技", "旷视科技"],
         ["算法工程师", "高级算法工程师"],
         "计算机视觉方向,负责目标检测、图像分割模型研发;PyTorch + MMDetection;模型蒸馏将 YOLOv8 推理速度提升 2 倍;TensorRT 部署;主导工业质检项目,漏检率从 1.2% 降至 0.3%。",
         ["模型蒸馏后推理速度提升 2 倍,显存占用下降 60%",
          "工业质检漏检率从 1.2% 降至 0.3%",
          "3 篇 CVPR/ECCV 一作论文"],
         ["Python", "PyTorch", "TensorRT", "MMDetection", "YOLOv8", "OpenCV", "CUDA", "C++", "NumPy"]),
        ("蔡欣怡", 3.0, "硕士", "上海交通大学", "数学",
         ["蚂蚁集团"],
         ["NLP 算法工程师"],
         "负责金融舆情和风险识别的 NLP 模型研发;BERT + LoRA 微调;LangChain 构建问答 Agent;Elasticsearch 召回 + 重排序;Prompt 工程优化,使大模型输出准确率从 72% 提升到 89%。",
         ["问答系统准确率从 72% 提升至 89%",
          "Prompt 模板沉淀 30+ 套",
          "团队产出 4 项 NLP 相关专利"],
         ["Python", "PyTorch", "BERT", "LoRA", "LangChain", "OpenAI API", "Elasticsearch", "向量检索"]),
        ("潘思源", 5.5, "博士", "清华大学", "计算机科学",
         ["字节跳动 AI Lab", "腾讯 AI Lab"],
         ["高级研究员", "算法专家"],
         "大语言模型预训练与对齐研究;主导 70B 模型 SFT/RLHF 全流程;DeepSpeed + Megatron 分布式训练;发表 NeurIPS/ICML 论文 12 篇;主导的对话产品 DAU 突破 800w。",
         ["70B 模型 RLHF 训练成本下降 35%",
          "对话产品 DAU 突破 800w",
          "12 篇顶会论文(其中一作 5 篇)"],
         ["Python", "PyTorch", "DeepSpeed", "Megatron", "CUDA", "Transformer", "RLHF", "LangChain", "NumPy", "论文发表"]),
        ("崔嘉睿", 1.5, "硕士", "南京大学", "统计学",
         ["京东"],
         ["推荐算法工程师(校招)"],
         "推荐系统召回与粗排模型研发;DeepFM + 双塔模型;Faiss 向量召回;Spark + Hive 离线数仓;ABTest 平台搭建。",
         ["召回层 CTR 提升 7%",
          "搭建 ABTest 平台,支撑 20+ 实验并行",
          "毕业论文获省级优秀"],
         ["Python", "TensorFlow", "PyTorch", "DeepFM", "Faiss", "Spark", "Hive", "SQL", "ABTest"]),
        ("雷皓轩", 6.0, "博士", "中国科学院大学", "模式识别",
         ["华为诺亚方舟"],
         ["高级算法工程师"],
         "AI 编译器研发;TVM / MLIR 自研算子融合;ONNX 模型转换;移动端 NNAPI / CoreML 适配;模型量化(INT8/INT4);为手机芯片落地 30+ 主流模型。",
         ["30+ 模型在麒麟芯片落地,推理速度提升 2-4 倍",
          "INT8 量化精度损失 < 0.5%",
          "主导 2 项编译器专利"],
         ["C++", "Python", "TVM", "MLIR", "LLVM", "ONNX", "PyTorch", "TensorRT", "量化"]),
    ]
    name, years, degree, school, major, companies, positions, desc, achievements, skills = profiles[idx % len(profiles)]
    body = _format_resume(name, years, degree, school, major, companies, positions, desc, achievements, skills)
    return ResumeFixture(
        id=f"algo_{idx+1:02d}",
        name=name,
        category="互联网研发-算法",
        target_role="算法工程师",
        years=years,
        text=body,
    )


def _fullstack_resume(idx: int) -> ResumeFixture:
    """全栈工程师简历模板."""
    profiles = [
        ("冯亦菲", 3.5, "本科", "上海大学", "计算机科学与技术",
         ["Bilibili"],
         ["全栈开发工程师"],
         "B 站 UP 主后台管理系统,React + TypeScript + Go + Gin + MySQL;GraphQL API;通过 Docker Compose 一键部署;OSS 对象存储 + CDN。",
         ["后台从 0 到 1 支撑 200+ UP 主运营",
          "GraphQL 减少 60% 网络请求",
          "独立完成 8 个核心模块"],
         ["React", "TypeScript", "Go", "Gin", "MySQL", "GraphQL", "Docker", "Node.js"]),
        ("萧景睿", 4.5, "本科", "复旦大学", "软件工程",
         ["携程", "小红书"],
         ["全栈工程师", "高级全栈"],
         "旅游 SaaS 平台,Spring Boot + Vue3 + MySQL + Redis + Elasticsearch;K8s 部署;ELK 日志;可观测性全链路 trace。",
         ["订单系统从单体迁移到微服务,RPS 提升 4 倍",
          "全链路 Trace 落地 30+ 服务"],
         ["Java", "Spring Boot", "Vue3", "TypeScript", "MySQL", "Redis", "Elasticsearch", "Kubernetes", "Docker"]),
        ("尹诗涵", 2.0, "本科", "北京邮电大学", "物联网工程",
         ["小米科技"],
         ["全栈开发工程师"],
         "智能家居 Web 控制台,Node.js + Express + Vue3 + MongoDB + MQTT;WebSocket 实时通信;Web 端可视化大屏。",
         ["支持 10 万台设备实时控制,延迟 < 100ms",
          "可视化大屏支持 50 个图表同屏渲染"],
         ["Node.js", "Express", "Vue3", "TypeScript", "MongoDB", "MQTT", "WebSocket", "Docker"]),
        ("夏一航", 5.5, "硕士", "中国科学技术大学", "计算机科学与技术",
         ["美团", "Shopee"],
         ["高级全栈工程师"],
         "外卖商家端全栈架构,Next.js + NestJS + PostgreSQL + Prisma + Redis;Serverless 边缘函数;微前端架构;GraphQL Federation。",
         ["商家端首屏 LCP 1.2s,跳出率降低 25%",
          "微前端架构支撑 30+ 团队并行迭代"],
         ["Next.js", "NestJS", "TypeScript", "PostgreSQL", "Prisma", "Redis", "GraphQL", "Serverless", "TailwindCSS"]),
    ]
    name, years, degree, school, major, companies, positions, desc, achievements, skills = profiles[idx % len(profiles)]
    body = _format_resume(name, years, degree, school, major, companies, positions, desc, achievements, skills)
    return ResumeFixture(
        id=f"fullstack_{idx+1:02d}",
        name=name,
        category="互联网研发-全栈",
        target_role="全栈工程师",
        years=years,
        text=body,
    )


def _data_resume(idx: int) -> ResumeFixture:
    """数据分析师 / 商业分析师简历模板."""
    profiles = [
        ("袁一鸣", 4.0, "硕士", "中国人民大学", "统计学",
         ["美团", "滴滴"],
         ["高级数据分析师"],
         "本地生活业务数据分析,SQL + Python + Hive + Presto;Tableau 可视化;A/B 实验设计与因果推断;驱动 GMV 增长策略。",
         ["策略上线后 GMV 提升 8%",
          "搭建用户分群体系,精细化运营覆盖 90% 用户",
          "10 篇业务策略报告获得 CEO 认可"],
         ["SQL", "Python", "Hive", "Presto", "Tableau", "A/B 测试", "因果推断", "统计学", "R"]),
        ("邓舒文", 2.5, "本科", "上海财经大学", "经济统计学",
         ["平安科技"],
         ["商业分析师"],
         "金融业务商业分析,Excel + SQL + Python;Power BI 报表自动化;用户画像与精准营销;信用卡反欺诈分析。",
         ["反欺诈模型降低误报率 30%",
          "Power BI 自动化报表覆盖 12 条业务线"],
         ["SQL", "Python", "Excel", "Power BI", "SPSS", "统计学", "用户画像"]),
        ("邱子昂", 6.0, "硕士", "清华大学", "管理科学与工程",
         ["字节跳动", "阿里"],
         ["资深商业分析师"],
         "抖音电商商业分析,主导 GMV 拆解与漏斗分析;Python + SQL + Hive + Spark;搭建指标体系和数据看板;推动多项策略落地。",
         ["搭建核心指标体系 200+ 指标",
          "策略上线后商家留存提升 15%"],
         ["SQL", "Python", "Hive", "Spark", "Airflow", "Tableau", "商业分析", "指标体系"]),
        ("傅雨珊", 1.5, "本科", "对外经济贸易大学", "金融学",
         ["毕马威"],
         ["数据分析师(校招)"],
         "咨询行业数据分析助理,Excel + Python + PowerPoint;客户调研数据清洗与建模;可视化报告。",
         ["完成 15+ 客户调研项目",
          "Python 自动化数据处理流程节省 60% 人力"],
         ["Excel", "Python", "SQL", "PowerPoint", "SPSS", "数据可视化"]),
    ]
    name, years, degree, school, major, companies, positions, desc, achievements, skills = profiles[idx % len(profiles)]
    body = _format_resume(name, years, degree, school, major, companies, positions, desc, achievements, skills)
    return ResumeFixture(
        id=f"data_{idx+1:02d}",
        name=name,
        category="数据/分析",
        target_role="数据分析师",
        years=years,
        text=body,
    )


def _product_resume(idx: int) -> ResumeFixture:
    """产品经理简历模板."""
    profiles = [
        ("罗心怡", 5.0, "硕士", "浙江大学", "工业设计",
         ["腾讯", "美团"],
         ["高级产品经理"],
         "微信支付商户端产品设计,负责商户开户、收款、对账;数据驱动决策;与研发/设计/运营协作;主导的优化使商户首日留存提升 22%。",
         ["商户首日留存提升 22%",
          "完成 30+ 核心需求 PRD",
          "主导 2 项 0-1 产品孵化"],
         ["Axure", "Figma", "SQL", "数据分析", "用户研究", "A/B 测试", "产品规划", "需求管理"]),
        ("唐昊宇", 3.5, "本科", "北京航空航天大学", "工业工程",
         ["京东"],
         ["产品经理"],
         "京东超市产品规划,品类运营与活动促销;SQL + 漏斗分析;跨部门协同推动需求上线。",
         ["双 11 GMV 同比提升 18%",
          "用户复购率提升 12%"],
         ["Axure", "SQL", "数据分析", "A/B 测试", "需求文档", "项目管理"]),
        ("范晓萱", 2.0, "本科", "复旦大学", "新闻传播",
         ["小红书"],
         ["内容产品经理"],
         "小红书内容产品策划,围绕种草社区生态;用户调研、AB 实验、内容策略。",
         ["日活用户增长 15%",
          "主导 3 项社区互动功能"],
         ["产品策划", "用户研究", "A/B 测试", "内容运营", "SQL", "Axure"]),
    ]
    name, years, degree, school, major, companies, positions, desc, achievements, skills = profiles[idx % len(profiles)]
    body = _format_resume(name, years, degree, school, major, companies, positions, desc, achievements, skills)
    return ResumeFixture(
        id=f"product_{idx+1:02d}",
        name=name,
        category="数据/分析-产品",
        target_role="产品经理",
        years=years,
        text=body,
    )


def _finance_resume(idx: int) -> ResumeFixture:
    """金融岗位简历模板."""
    profiles = [
        ("万嘉豪", 4.0, "硕士", "中央财经大学", "金融学",
         ["中金公司", "招商证券"],
         ["投资银行部经理"],
         "参与 8 个 IPO 项目和 4 个并购重组项目;撰写招股说明书、行业研究报告;主导尽调与估值建模;DCF/可比公司估值;与监管、律师、审计协同。",
         ["独立负责 2 个 IPO 项目成功过会",
          "完成累计 30 亿元融资"],
         ["Excel", "Wind", "Bloomberg", "估值建模", "DCF", "招股书撰写", "财务分析"]),
        ("钱雅琪", 2.5, "硕士", "上海财经大学", "会计学",
         ["普华永道"],
         ["高级审计师"],
         "金融行业审计,审计抽样、内部控制测试、合并报表;CFA 一级通过;带领 3 人小组完成年度审计。",
         ["完成 5 家上市公司年度审计",
          "发现重大内控缺陷 12 项"],
         ["Excel", "审计", "内部控制", "合并报表", "CPA", "CFA", "财务分析"]),
        ("蒋昕宇", 3.0, "硕士", "对外经济贸易大学", "国际金融",
         ["中国银行"],
         ["风控分析师"],
         "信贷风险模型监控,Vintage 分析、迁徙率分析、PD/LGD/EAD 计量;Python + SQL 自动化风控报表。",
         ["主动监控识别 1.2 亿元潜在不良",
          "自动化报表节省 70% 人力"],
         ["Python", "SQL", "风险计量", "PD/LGD", "Excel", "Vintage 分析", "监管合规"]),
    ]
    name, years, degree, school, major, companies, positions, desc, achievements, skills = profiles[idx % len(profiles)]
    body = _format_resume(name, years, degree, school, major, companies, positions, desc, achievements, skills)
    return ResumeFixture(
        id=f"finance_{idx+1:02d}",
        name=name,
        category="传统行业-金融",
        target_role="金融岗位",
        years=years,
        text=body,
    )


def _consulting_resume(idx: int) -> ResumeFixture:
    """咨询行业简历模板."""
    profiles = [
        ("彭俊豪", 3.0, "硕士", "北京大学", "光华管理学院 MBA",
         ["麦肯锡", "贝恩咨询"],
         ["咨询顾问", "项目经理"],
         "战略咨询项目,行业研究、竞争对手分析、市场进入策略;PPT 呈现与高管沟通;服务客户覆盖消费/金融/科技;主导 2 个 500 强战略项目。",
         ["完成 10+ 战略咨询项目",
          "主导客户战略调整,营收增长 15%"],
         ["PPT", "Excel", "行业研究", "战略咨询", "市场分析", "案例分析", "英文沟通"]),
        ("苏雨晴", 2.0, "本科", "清华大学", "经济与金融",
         ["罗兰贝格"],
         ["助理咨询顾问"],
         "管理咨询项目,行业访谈、竞品研究、模型搭建;服务汽车与零售客户。",
         ["独立完成 4 个细分赛道研究",
          "案例面试 Top 5% 通过率"],
         ["PPT", "Excel", "行业研究", "案例分析", "战略分析", "数据建模"]),
    ]
    name, years, degree, school, major, companies, positions, desc, achievements, skills = profiles[idx % len(profiles)]
    body = _format_resume(name, years, degree, school, major, companies, positions, desc, achievements, skills)
    return ResumeFixture(
        id=f"consulting_{idx+1:02d}",
        name=name,
        category="传统行业-咨询",
        target_role="咨询顾问",
        years=years,
        text=body,
    )


def _fmcg_resume(idx: int) -> ResumeFixture:
    """快消 / 市场营销简历模板."""
    profiles = [
        ("蓝心语", 3.5, "本科", "中国传媒大学", "市场营销",
         ["宝洁", "联合利华"],
         ["品牌经理"],
         "日化品牌营销管理,负责新品上市、媒介投放、KOL 合作;主导品牌升级战役,品牌认知度提升 18%。",
         ["新品上市首年销售突破 5 亿",
          "社交媒体粉丝增长 300 万"],
         ["品牌策划", "媒介投放", "KOL 合作", "市场调研", "PPT", "Excel", "数据分析"]),
        ("龙俊辉", 2.0, "本科", "华东师范大学", "广告学",
         ["可口可乐"],
         ["市场专员"],
         "快消品牌活动策划,校园营销、电商促销;小红书种草内容投放。",
         ["完成 8 场校园活动,触达 5 万学生",
          "小红书种草 ROI 1:4"],
         ["活动策划", "市场推广", "小红书运营", "PPT", "Excel", "创意"]),
    ]
    name, years, degree, school, major, companies, positions, desc, achievements, skills = profiles[idx % len(profiles)]
    body = _format_resume(name, years, degree, school, major, companies, positions, desc, achievements, skills)
    return ResumeFixture(
        id=f"fmcg_{idx+1:02d}",
        name=name,
        category="传统行业-快消",
        target_role="市场/品牌",
        years=years,
        text=body,
    )


def _format_resume(name, years, degree, school, major, companies, positions, desc, achievements, skills) -> str:
    """把简历字段拼接为标准文本."""
    lines = []
    lines.append(f"# {name}")
    lines.append("")
    lines.append(f"## 基本信息")
    lines.append(f"- 工作年限: {years} 年")
    lines.append(f"- 学历: {degree} · {school} · {major}")
    lines.append("")
    lines.append("## 工作经历")
    for i, (co, pos) in enumerate(zip(companies, positions), start=1):
        lines.append(f"### {pos} @ {co}")
        lines.append(desc)
        lines.append("核心成果:")
        for a in achievements:
            lines.append(f"- {a}")
        lines.append("")
    lines.append("## 技能清单")
    lines.append(", ".join(skills))
    lines.append("")
    return "\n".join(lines)


# ============================================================================
# 注册全部生成器
# ============================================================================

_GENERATORS: List[Callable[[int], ResumeFixture]] = [
    _backend_resume,
    _frontend_resume,
    _algo_resume,
    _fullstack_resume,
    _data_resume,
    _product_resume,
    _finance_resume,
    _consulting_resume,
    _fmcg_resume,
]


def get_all_resumes() -> List[ResumeFixture]:
    """获取全部模拟简历."""
    out: List[ResumeFixture] = []
    for gen in _GENERATORS:
        # 每个生成器取 2-3 个变体
        for i in range(3):
            out.append(gen(i))
    return out


def get_resumes_by_category(category: str) -> List[ResumeFixture]:
    """按类目筛选简历."""
    return [r for r in get_all_resumes() if r.category == category]


def get_resumes_for_role(role: str) -> List[ResumeFixture]:
    """按 target_role 筛选."""
    return [r for r in get_all_resumes() if r.target_role == role]


if __name__ == "__main__":
    rs = get_all_resumes()
    print(f"共构造简历 {len(rs)} 份:")
    by_cat: Dict[str, int] = {}
    for r in rs:
        by_cat[r.category] = by_cat.get(r.category, 0) + 1
    for c, n in by_cat.items():
        print(f"  - {c}: {n} 份")
    print()
    print("=" * 60)
    print("示例简历片段:")
    print("=" * 60)
    print(rs[0].text[:600])