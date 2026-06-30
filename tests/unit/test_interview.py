"""面试题预测模块单元测试.

覆盖:
- 风险点提取与分层(_extract_risk_points)
- Prompt 构造(_build_user_prompt)
- 后处理校验(_validate_questions)
- 修正提示构造(_build_correction_prompt)
- 数据模型(InterviewQuestion 新字段)
- 面试专用阶段定义(INTERVIEW_STAGES)
"""
from __future__ import annotations

from tests.runner import unit
from app.models.interview import (
    InterviewQuestion,
    InterviewPredictionOutput,
    QuestionCategory,
    QuestionPriority,
    Difficulty,
    PROMPT_VERSION,
    STRATEGY_VERSION,
)
from app.services.interview_service import (
    RiskPoint,
    RiskProfile,
    _extract_risk_points,
    _build_user_prompt,
    _validate_questions,
    _build_correction_prompt,
    ValidationResult,
)
from app.workflow.progress import (
    INTERVIEW_STAGES,
    interview_stage_by_key,
    compute_streaming_percent,
)


# ---- 测试数据工厂 ----


def _make_cached_data(
    *,
    missing_skills: list | None = None,
    partial_skills: list | None = None,
    matched_skills: list | None = None,
    weaknesses: list | None = None,
    hard_requirements_gaps: list | None = None,
    experience_notes: list | None = None,
    keywords_missing: list | None = None,
    strengths: list | None = None,
) -> dict:
    """构造模拟缓存数据."""
    return {
        "resume_data": {
            "name": "张三",
            "summary": "3年后端开发经验",
            "projects": [
                {
                    "name": "订单系统",
                    "role": "后端开发",
                    "technologies": ["Python", "Django", "PostgreSQL"],
                    "highlights": ["QPS提升3倍"],
                },
            ],
            "work_experience": [
                {"company": "ABC科技", "position": "后端工程师"},
            ],
        },
        "job_requirement": {
            "title": "高级后端工程师",
            "hard_skills": [{"description": "Kubernetes"}],
            "soft_skills": [{"description": "团队协作"}],
            "responsibilities": ["设计高并发系统"],
        },
        "match_report": {
            "overall_score": 65.0,
            "weaknesses": weaknesses or [],
            "strengths": strengths or [],
            "hard_requirements_gaps": hard_requirements_gaps or [],
            "skill_gap": {
                "matched": matched_skills or [],
                "missing": missing_skills or [],
                "partial": partial_skills or [],
                "coverage": 0.5,
            },
            "experience": {
                "score": 0.6,
                "notes": experience_notes or [],
            },
            "keywords": {
                "matched": ["Python"],
                "missing": keywords_missing or [],
                "coverage": 0.6,
            },
        },
    }


def _make_question(
    *,
    category: str = "technical",
    difficulty: str = "hard",
    related_skill: str = "",
    priority: str = "high",
    question: str = "请解释 Kubernetes 的 Pod 调度策略",
) -> InterviewQuestion:
    """构造单道面试题."""
    return InterviewQuestion(
        category=QuestionCategory(category),
        difficulty=Difficulty(difficulty),
        question=question,
        intent="测试核心能力",
        suggested_answer_direction="1. 要点一 2. 要点二 3. 要点三",
        related_skill=related_skill or None,
        priority=QuestionPriority(priority),
        reason="缺失该技能",
        confidence=0.8,
    )


# ---- 风险点提取 ----


@unit
def test_extract_risk_points_missing_skills_as_high():
    """缺失技能应被提取为一级风险(high)."""
    data = _make_cached_data(missing_skills=[
        {"skill": "Kubernetes", "matched": False, "confidence": 1.0, "evidence": ""},
    ])
    profile = _extract_risk_points(data)
    assert len(profile.high) >= 1
    assert any("Kubernetes" in rp.description for rp in profile.high)


@unit
def test_extract_risk_points_weaknesses_as_high():
    """weaknesses 应被提取为一级风险."""
    data = _make_cached_data(weaknesses=["缺少微服务经验"])
    profile = _extract_risk_points(data)
    assert any("缺少微服务经验" in rp.description for rp in profile.high)


@unit
def test_extract_risk_points_hard_req_gaps_as_high():
    """hard_requirements_gaps 应被提取为一级风险."""
    data = _make_cached_data(hard_requirements_gaps=["需要3年以上K8s经验"])
    profile = _extract_risk_points(data)
    assert any("需要3年以上K8s经验" in rp.description for rp in profile.high)


@unit
def test_extract_risk_points_partial_as_medium():
    """部分匹配技能应被提取为二级风险(medium)."""
    data = _make_cached_data(partial_skills=[
        {"skill": "Docker", "matched": False, "confidence": 0.5, "evidence": "使用过docker run"},
    ])
    profile = _extract_risk_points(data)
    assert any("Docker" in rp.description for rp in profile.medium)


@unit
def test_extract_risk_points_experience_notes_as_medium():
    """experience.notes 应被提取为二级风险."""
    data = _make_cached_data(experience_notes=["年限不足"])
    profile = _extract_risk_points(data)
    assert any("年限不足" in rp.description for rp in profile.medium)


@unit
def test_extract_risk_points_keywords_missing_as_medium():
    """keywords.missing 应被提取为二级风险."""
    data = _make_cached_data(keywords_missing=["CI/CD"])
    profile = _extract_risk_points(data)
    assert any("CI/CD" in rp.description for rp in profile.medium)


@unit
def test_extract_risk_points_matched_as_low():
    """已匹配技能应被提取为三级风险(low)."""
    data = _make_cached_data(matched_skills=[
        {"skill": "Python", "matched": True, "confidence": 1.0, "evidence": "3年经验"},
    ])
    profile = _extract_risk_points(data)
    assert any("Python" in rp.description for rp in profile.low)


@unit
def test_extract_risk_points_empty_data():
    """空数据不应产生风险点."""
    data = _make_cached_data()
    profile = _extract_risk_points(data)
    assert len(profile.high) == 0
    assert len(profile.medium) == 0
    assert len(profile.low) == 0


# ---- Prompt 构造 ----


@unit
def test_build_user_prompt_contains_risk_sections():
    """prompt 应包含风险点分层段落."""
    data = _make_cached_data(
        missing_skills=[{"skill": "K8s", "matched": False, "confidence": 1.0}],
        partial_skills=[{"skill": "Docker", "matched": False, "confidence": 0.5}],
    )
    profile = _extract_risk_points(data)
    prompt = _build_user_prompt(data, profile)
    assert "一级风险" in prompt
    assert "二级风险" in prompt
    assert "三级风险" in prompt
    assert "K8s" in prompt


@unit
def test_build_user_prompt_contains_weaknesses():
    """prompt 应包含 weaknesses 信息."""
    data = _make_cached_data(weaknesses=["缺少分布式经验"])
    profile = _extract_risk_points(data)
    prompt = _build_user_prompt(data, profile)
    assert "缺少分布式经验" in prompt


@unit
def test_build_user_prompt_contains_keywords_missing():
    """prompt 应包含缺失关键词."""
    data = _make_cached_data(keywords_missing=["CI/CD"])
    profile = _extract_risk_points(data)
    prompt = _build_user_prompt(data, profile)
    assert "CI/CD" in prompt


@unit
def test_build_user_prompt_contains_experience_notes():
    """prompt 应包含经验差距说明."""
    data = _make_cached_data(experience_notes=["年限不达标"])
    profile = _extract_risk_points(data)
    prompt = _build_user_prompt(data, profile)
    assert "年限不达标" in prompt


@unit
def test_build_user_prompt_new_fields_in_rules():
    """prompt 的生成规则应要求 reason/priority/confidence 等新字段."""
    data = _make_cached_data()
    profile = _extract_risk_points(data)
    prompt = _build_user_prompt(data, profile)
    assert "reason" in prompt
    assert "priority" in prompt
    assert "confidence" in prompt
    assert "evidence_from_resume" in prompt
    assert "evidence_from_jd" in prompt


# ---- 后处理校验 ----


@unit
def test_validate_good_output():
    """符合规则的输出应通过校验."""
    questions = [
        _make_question(category="technical", related_skill="K8s", priority="high"),
        _make_question(category="technical", related_skill="Docker", priority="medium", difficulty="medium"),
        _make_question(category="technical", related_skill="Redis", priority="high"),
        _make_question(category="technical", related_skill="MQ", priority="medium", difficulty="medium"),
        _make_question(category="behavioral", priority="medium", difficulty="medium", question="描述一次团队冲突解决经历"),
        _make_question(category="behavioral", priority="low", difficulty="easy", question="如何推动跨部门协作"),
        _make_question(category="project", priority="medium", difficulty="medium", question="订单系统中如何保证数据一致性"),
        _make_question(category="project", priority="low", difficulty="easy", question="项目中的技术选型考虑"),
    ]
    output = InterviewPredictionOutput(questions=questions, summary="优先准备K8s和Docker相关题目。")
    result = _validate_questions(output)
    assert result.passed, f"应通过校验,但发现问题: {result.issues}"


@unit
def test_validate_too_few_questions():
    """题量不足 8 道应校验失败."""
    questions = [_make_question() for _ in range(5)]
    output = InterviewPredictionOutput(questions=questions, summary="不足")
    result = _validate_questions(output)
    assert not result.passed
    assert any("8-12" in i for i in result.issues)


@unit
def test_validate_too_many_questions():
    """题量超过 12 道应校验失败."""
    questions = [_make_question() for _ in range(13)]
    output = InterviewPredictionOutput(questions=questions, summary="过多")
    result = _validate_questions(output)
    assert not result.passed
    assert any("8-12" in i for i in result.issues)


@unit
def test_validate_generic_question():
    """通用题应被检测."""
    questions = [
        _make_question(question="请自我介绍一下", difficulty="easy", priority="low"),
        *[_make_question() for _ in range(7)],
    ]
    output = InterviewPredictionOutput(questions=questions, summary="有通用题")
    result = _validate_questions(output)
    assert any("通用题" in i for i in result.issues)


@unit
def test_validate_duplicate_questions():
    """同一 related_skill + category 重复出现应被检测."""
    questions = [
        _make_question(related_skill="K8s", category="technical"),
        _make_question(related_skill="K8s", category="technical", question="K8s中Pod如何管理", difficulty="hard"),
        *[_make_question(related_skill=f"skill_{i}", category="technical") for i in range(6)],
    ]
    # 需要至少 8 道题
    while len(questions) < 8:
        questions.append(_make_question(related_skill=f"extra_{len(questions)}", category="behavioral", difficulty="medium", priority="medium", question="行为题"))
    output = InterviewPredictionOutput(questions=questions, summary="有重复")
    result = _validate_questions(output)
    assert any("重复题" in i for i in result.issues)


@unit
def test_validate_priority_difficulty_mismatch():
    """priority=high 但 difficulty=easy 应被检测."""
    questions = [
        _make_question(priority="high", difficulty="easy", related_skill="K8s"),
        *[_make_question() for _ in range(7)],
    ]
    output = InterviewPredictionOutput(questions=questions, summary="不匹配")
    result = _validate_questions(output)
    assert any("优先级/难度不匹配" in i for i in result.issues)


# ---- 修正提示构造 ----


@unit
def test_build_correction_prompt():
    """修正提示应包含具体问题."""
    prompt = _build_correction_prompt(["技术题数量不足", "存在通用题"])
    assert "技术题数量不足" in prompt
    assert "存在通用题" in prompt
    assert "修正" in prompt


# ---- 数据模型 ----


@unit
def test_interview_question_new_fields():
    """新字段应有合理默认值."""
    q = InterviewQuestion(
        category=QuestionCategory.TECHNICAL,
        difficulty=Difficulty.HARD,
        question="测试题",
        intent="测试",
        suggested_answer_direction="1. 要点",
    )
    assert q.reason == ""
    assert q.priority == QuestionPriority.MEDIUM
    assert q.confidence == 0.0
    assert q.evidence_from_resume is None
    assert q.evidence_from_jd is None


@unit
def test_interview_question_with_all_fields():
    """所有字段都应能正确赋值."""
    q = InterviewQuestion(
        category=QuestionCategory.TECHNICAL,
        difficulty=Difficulty.HARD,
        question="请解释 K8s 的调度策略",
        intent="测试 K8s 理解",
        suggested_answer_direction="1. NodeSelector 2. Affinity 3. Taint/Toleration",
        related_skill="Kubernetes",
        related_jd_requirement="需要 K8s 经验",
        reason="候选人缺失 K8s 技能,JD 明确要求",
        priority=QuestionPriority.HIGH,
        confidence=0.9,
        evidence_from_resume="简历未提及 K8s",
        evidence_from_jd="JD: 需要3年K8s经验",
    )
    assert q.priority == QuestionPriority.HIGH
    assert q.confidence == 0.9
    assert q.reason == "候选人缺失 K8s 技能,JD 明确要求"
    assert q.evidence_from_resume == "简历未提及 K8s"


@unit
def test_question_priority_enum():
    """QuestionPriority 枚举值应正确."""
    assert QuestionPriority.HIGH.value == "high"
    assert QuestionPriority.MEDIUM.value == "medium"
    assert QuestionPriority.LOW.value == "low"


@unit
def test_prompt_version_defined():
    """版本号应已定义."""
    assert PROMPT_VERSION == "v2"
    assert STRATEGY_VERSION == "risk_stratified"


@unit
def test_interview_prediction_output_model_dump():
    """InterviewPredictionOutput 应能正确序列化."""
    questions = [_make_question()]
    output = InterviewPredictionOutput(questions=questions, summary="测试摘要")
    dumped = output.model_dump()
    assert "questions" in dumped
    assert "summary" in dumped
    assert dumped["questions"][0]["priority"] == "high"


# ---- 面试专用阶段 ----


@unit
def test_interview_stages_defined():
    """面试专用阶段应包含 4 个阶段."""
    assert len(INTERVIEW_STAGES) == 4
    keys = [s.key for s in INTERVIEW_STAGES]
    assert "load_cache" in keys
    assert "build_prompt" in keys
    assert "predict" in keys
    assert "validate" in keys


@unit
def test_interview_stage_by_key():
    """应能按 key 查找面试阶段."""
    s = interview_stage_by_key("predict")
    assert s is not None
    assert s.key == "predict"
    assert s.is_llm is True


@unit
def test_interview_stage_by_key_unknown():
    """不存在的 key 应返回 None."""
    assert interview_stage_by_key("nonexistent") is None


@unit
def test_interview_stages_percent_ranges():
    """面试各阶段百分比区间应递增且不重叠."""
    for i in range(len(INTERVIEW_STAGES) - 1):
        assert INTERVIEW_STAGES[i].percent_end == INTERVIEW_STAGES[i + 1].percent_start


@unit
def test_compute_streaming_percent_interview_stage():
    """面试阶段的进度计算应在区间内."""
    predict_stage = interview_stage_by_key("predict")
    assert predict_stage is not None
    pct = compute_streaming_percent(predict_stage, "streaming", 500)
    assert predict_stage.percent_start <= pct <= predict_stage.percent_end
