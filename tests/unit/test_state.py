"""状态机测试 —— 续跑与回滚的基础语义。

这些用例回答一个问题：**中断之后再跑，凭什么可以不重做已完成的部分？**
答案是产物哈希：只要文件没变、且登记的阶段匹配，就跳过；变了就重做。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reits_weekly.state import CaseState, Stage, Status, sha256_file


def test_new_state_defaults(tmp_path):
    st = CaseState.load_or_new(tmp_path, "c1")
    assert st.stage == Stage.INIT.value
    assert st.status == Status.PENDING.value


def test_atomic_save_and_load(tmp_path):
    st = CaseState(case_id="c1")
    st.advance(Stage.INGEST.value)
    st.save(tmp_path)
    loaded = CaseState.load(tmp_path)
    assert loaded.stage == Stage.INGEST.value
    # 不应残留临时文件
    assert not (tmp_path / "state.json.tmp").exists()


def test_forward_only(tmp_path):
    st = CaseState(case_id="c1")
    st.advance(Stage.INGEST.value)
    assert st.can_enter(Stage.NORMALIZE.value)
    assert not st.can_enter(Stage.CHART.value)   # 不能跳阶段
    assert not st.can_enter(Stage.INIT.value)    # 不能回退


def test_revise_is_a_back_edge(tmp_path):
    st = CaseState(case_id="c1")
    st.advance(Stage.FACTS.value)
    st.advance(Stage.CHART.value)
    st.advance(Stage.TABLES.value)
    st.advance(Stage.DRAFT.value)
    st.advance(Stage.MERGE.value)
    st.advance(Stage.CRITIC.value)
    assert st.can_enter(Stage.REVISE.value)
    st.advance(Stage.REVISE.value)
    assert st.can_enter(Stage.DRAFT.value)       # 修订后回到起草


def test_artifact_freshness(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("v1", encoding="utf-8")
    st = CaseState(case_id="c1")
    st.record_artifact(f, Stage.FACTS.value, tmp_path)
    assert st.is_fresh(f, Stage.FACTS.value, tmp_path)

    f.write_text("v2", encoding="utf-8")
    assert not st.is_fresh(f, Stage.FACTS.value, tmp_path)


def test_artifact_stage_mismatch_is_not_fresh(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("v1", encoding="utf-8")
    st = CaseState(case_id="c1")
    st.record_artifact(f, Stage.CHART.value, tmp_path)
    assert not st.is_fresh(f, Stage.FACTS.value, tmp_path)


def test_missing_artifact_is_not_fresh(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("v1", encoding="utf-8")
    st = CaseState(case_id="c1")
    st.record_artifact(f, Stage.FACTS.value, tmp_path)
    f.unlink()
    assert not st.is_fresh(f, Stage.FACTS.value, tmp_path)


def test_blocked_and_resume_hint(tmp_path):
    st = CaseState(case_id="c1")
    st.block("缺数据", "补数据后 resume")
    assert st.status == Status.BLOCKED.value
    assert "补数据" in st.resume_hint


def test_escalate_is_distinct_from_blocked(tmp_path):
    st = CaseState(case_id="c1")
    st.escalate("额度用尽")
    assert st.status == Status.ESCALATED.value


def test_approval_binds_hash(tmp_path):
    st = CaseState(case_id="c1")
    st.add_approval("HUMAN_REVIEW", by="张三", decision="approve",
                    artifact_sha256="abc123")
    assert st.has_approval("HUMAN_REVIEW", "abc123")
    # 哈希不符 = 批的不是这一版，视为未批
    assert not st.has_approval("HUMAN_REVIEW", "different")


def test_approval_requires_approve_decision(tmp_path):
    st = CaseState(case_id="c1")
    st.add_approval("HUMAN_REVIEW", by="张三", decision="reject")
    assert not st.has_approval("HUMAN_REVIEW")


def test_history_records_transitions(tmp_path):
    st = CaseState(case_id="c1")
    st.advance(Stage.INGEST.value, "开始")
    st.advance(Stage.COMPUTE.value, "计算")
    assert len(st.history) == 2
    assert st.history[0]["to"] == Stage.INGEST.value
    assert st.history[1]["reason"] == "计算"


def test_round_trip_json(tmp_path):
    st = CaseState(case_id="c1")
    st.advance(Stage.FACTS.value)
    st.gates = {"G-NUM-01": {"ok": True}}
    st.save(tmp_path)
    raw = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert raw["case_id"] == "c1"
    assert raw["gates"]["G-NUM-01"]["ok"] is True
