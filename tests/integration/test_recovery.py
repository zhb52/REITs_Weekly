"""中断恢复的集成测试。

这条用例锁的是作业要求里最容易被"写个说明"糊弄过去的一点：
**中断后再跑，不能重做已完成的部分，且重建的产物要与原来一致。**

它来自一个真实缺陷：控制器在 BLOCKED 状态下直接返回，
导致补完外部条件后 resume 变成空操作——用户会以为程序坏了。
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

from reits_weekly import controller
from reits_weekly.state import CaseState

ROOT = Path(__file__).resolve().parents[2]
CASE = "demo-2026-W45"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.fixture
def sandbox(tmp_path):
    """把 config 与 fixtures 复制到临时目录，构造一个独立的仓库根。"""
    for name in ("config", "fixtures"):
        shutil.copytree(ROOT / name, tmp_path / name)
    (tmp_path / "cases" / CASE).mkdir(parents=True)
    (tmp_path / "memory").mkdir()
    shutil.copy(ROOT / "memory" / "opinions.yaml", tmp_path / "memory" / "opinions.yaml")
    (tmp_path / "cases" / CASE / "drafts").mkdir()
    shutil.copy(
        ROOT / "cases" / CASE / "drafts" / "drafts.md",
        tmp_path / "cases" / CASE / "drafts" / "drafts.md",
    )
    return tmp_path


def _cfg(root: Path) -> controller.RunConfig:
    return controller.RunConfig(repo_root=root, case_id=CASE, source="fixture")


def test_first_run_stops_at_human_review(sandbox):
    """门禁通过后必须停下等签字，不能自动出稿。"""
    st = controller.run(_cfg(sandbox))
    assert st.status == "BLOCKED"
    assert st.stage == "HUMAN_REVIEW"
    assert st.blocked_reason == "等待人工审批"
    # 未签字前不应产出 docx
    assert not (sandbox / "cases" / CASE / "out").exists() or \
        not list((sandbox / "cases" / CASE / "out").glob("*.docx"))


def test_blocked_state_does_not_short_circuit(sandbox):
    """BLOCKED 之后再次 run 不能直接返回——必须重新评估条件。

    这是修复前的缺陷：控制器见 BLOCKED 就 return，
    外部条件改善（删掉的产物补回来、草稿改好）后 resume 毫无反应。
    """
    cfg = _cfg(sandbox)
    st1 = controller.run(cfg)
    assert st1.status == "BLOCKED"

    charts = sorted((sandbox / "cases" / CASE / "work" / "charts").glob("*.png"))
    assert len(charts) == 4
    for p in charts:
        p.unlink()

    # 不签字，只是再跑一次：因为还停在审批节点，状态仍是 BLOCKED，
    # 但被删除的图表必须已经重建 —— 证明没有提前返回
    controller.run(cfg)
    rebuilt = sorted((sandbox / "cases" / CASE / "work" / "charts").glob("*.png"))
    assert len(rebuilt) == 4


def test_resume_does_not_recompute_facts(sandbox):
    """恢复时已完成的事实库不能被重算。"""
    cfg = _cfg(sandbox)
    controller.run(cfg)
    facts = sandbox / "cases" / CASE / "facts" / "facts.json"
    before = _sha(facts)

    for p in (sandbox / "cases" / CASE / "work" / "charts").glob("*.png"):
        p.unlink()
    controller.run(cfg)

    assert _sha(facts) == before


def test_rebuilt_charts_are_identical(sandbox):
    """重建的图表要与中断前逐字节一致——证明输出可复现。"""
    cfg = _cfg(sandbox)
    controller.run(cfg)
    charts = {p.name: _sha(p) for p in (sandbox / "cases" / CASE / "work" / "charts").glob("*.png")}

    for p in (sandbox / "cases" / CASE / "work" / "charts").glob("*.png"):
        p.unlink()
    controller.run(cfg)
    after = {p.name: _sha(p) for p in (sandbox / "cases" / CASE / "work" / "charts").glob("*.png")}

    assert charts.keys() == after.keys()
    assert charts == after


def test_approval_releases_the_gate(sandbox):
    """签字后才出稿。"""
    cfg = _cfg(sandbox)
    controller.run(cfg)
    controller.approve(cfg, by="测试", comment="")
    st = controller.run(cfg)
    assert st.status == "DONE"
    assert list((sandbox / "cases" / CASE / "out").glob("*.docx"))


def test_editing_draft_invalidates_approval(sandbox):
    """改稿后原审批失效，必须重新签字。"""
    cfg = _cfg(sandbox)
    controller.run(cfg)
    controller.approve(cfg, by="测试")
    assert controller.run(cfg).status == "DONE"

    drafts = sandbox / "cases" / CASE / "drafts" / "drafts.md"
    drafts.write_text(
        drafts.read_text(encoding="utf-8").replace("本周", "本周（修订）", 1),
        encoding="utf-8",
    )
    st = controller.run(cfg)
    assert st.status == "BLOCKED"
    assert st.stage == "HUMAN_REVIEW"
