"""进度回调单元测试.

- stage 查找
- 进度计算
- contextvar 隔离
"""
from __future__ import annotations

from tests.runner import unit
from app.workflow.progress import (
    STAGES,
    compute_streaming_percent,
    get_progress_callback,
    set_progress_callback,
    set_current_stage,
    get_current_stage,
    stage_by_node,
    stage_by_key,
)


@unit
def test_stages_non_empty():
    """STAGES 应至少包含 upload + 多个核心节点."""
    assert len(STAGES) >= 5
    keys = {s.key for s in STAGES}
    assert "upload" in keys


@unit
def test_stage_by_node_and_key_consistency():
    """key → stage 和 node → stage 都应能找到."""
    # 1. key → stage
    for s in STAGES:
        s2 = stage_by_key(s.key)
        assert s2 is not None
        assert s2.key == s.key

    # 2. node → stage(显式映射所有已知节点)
    from app.workflow.progress import _NODE_TO_STAGE_KEY
    for node_name, key in _NODE_TO_STAGE_KEY.items():
        s3 = stage_by_node(node_name)
        assert s3 is not None, f"node {node_name} 应映射到 {key}"
        assert s3.key == key


@unit
def test_stage_by_node_unknown():
    """未知 node 返回 None."""
    assert stage_by_node("nonexistent_node") is None


@unit
def test_compute_streaming_percent_in_range():
    """percent 应当是 0-100."""
    for s in STAGES:
        for chars in [0, 100, 1000, 10000]:
            p = compute_streaming_percent(s, "streaming", chars)
            assert 0 <= p <= 100, f"stage={s.key}, chars={chars}, p={p}"


@unit
def test_set_get_progress_callback():
    """contextvar 应当隔离."""
    set_progress_callback(lambda phase, info: None)
    cb = get_progress_callback()
    assert cb is not None

    set_progress_callback(None)
    assert get_progress_callback() is None


@unit
def test_set_get_current_stage():
    """contextvar 应当隔离."""
    s = stage_by_key("skill_gap")
    assert s is not None
    set_current_stage(s)
    cur = get_current_stage()
    assert cur is not None
    assert cur.key == "skill_gap"

    set_current_stage(None)
    assert get_current_stage() is None