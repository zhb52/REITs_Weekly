"""控制器 —— 决定"下一步做什么"，以及"能不能往下走"。

它与 agent 的分工是本项目的核心设计：

* **agent（起草者）** 只产出草稿文本，不决定流程，不改状态，不写数字。
* **控制器（本模块）** 决定推进、重试、阻断、升级；只有它能写 ``state.json``。

之所以要分开，是因为如果让产出方自己判断"我做好了"，验收标准就会随产出方的
意愿漂移。控制器只认产物哈希与门禁结果，不认"我觉得可以了"。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import pipeline
from .adapters.fixture import week_from_dates
from .draft import composer
from .normalize.board_map import BoardDictionary
from .render import build
from .state import CaseState, Stage, Status
from .verify import gates


@dataclass
class RunConfig:
    repo_root: Path
    case_id: str = "demo-2026-W45"
    source: str = "fixture"
    fixture_dir: Path | None = None
    week_start: str = "2026-11-02"
    week_end: str = "2026-11-06"
    week_prev_end: str = "2026-10-30"
    info_cutoff: str = "2026-11-08T23:59:59+08:00"
    max_wall_clock_sec: int = 3600
    max_gate_rounds: int = 2

    def case_dir(self) -> Path:
        return self.repo_root / "cases" / self.case_id

    def fixture(self) -> Path:
        return self.fixture_dir or (self.repo_root / "fixtures" / self.case_id)


def _d(s: str):
    from datetime import date

    y, m, d = (int(x) for x in s.split("-"))
    return date(y, m, d)


def _log(state: CaseState, msg: str) -> None:
    state.history.append({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "event": "LOG", "msg": msg})


def run(cfg: RunConfig, state: CaseState | None = None, force: bool = False) -> CaseState:
    """跑完一期的全部阶段。已完成且产物未变的阶段会被跳过。"""
    case_dir = cfg.case_dir()
    case_dir.mkdir(parents=True, exist_ok=True)
    state = state or CaseState.load_or_new(case_dir, cfg.case_id)
    if not state.info_cutoff:
        state.info_cutoff = cfg.info_cutoff

    t0 = time.time()

    def budget_left() -> bool:
        return (time.time() - t0) < cfg.max_wall_clock_sec

    paths = pipeline.CasePaths(cfg.repo_root, cfg.case_id)
    boards = BoardDictionary.load(cfg.repo_root / "config")
    week = week_from_dates(_d(cfg.week_start), _d(cfg.week_end), _d(cfg.week_prev_end))

    # ---------------------------------------------------------- 1. 取数与计算
    facts_path = case_dir / "facts" / "facts.json"
    need_prep = force or not state.is_fresh(facts_path, Stage.FACTS.value, case_dir)
    if need_prep:
        state.advance(Stage.INGEST.value, "开始取数")
        state.advance(Stage.COMPUTE.value, "归一化与计算")
        adapter = pipeline.get_adapter(cfg.source, cfg.fixture(), cfg.case_id)
        result = pipeline.prepare(adapter, week, boards, cfg.case_id)
        written = pipeline.write_artifacts(result, paths)
        for key, p in written.items():
            state.record_artifact(p, Stage.FACTS.value, case_dir)
        state.input_hash = adapter.meta.raw_hash
        state.advance(Stage.FACTS.value, f"登记 {len(result.facts)} 条事实")
        _log(state, f"事实库 {len(result.facts)} 条，板块差异 {len(result.board_conflicts)} 条")
    else:
        _log(state, "事实库未变，跳过取数与计算")
        from .facts import FactsBundle

        adapter = pipeline.get_adapter(cfg.source, cfg.fixture(), cfg.case_id)
        result = pipeline.prepare(adapter, week, boards, cfg.case_id)

    if state.status in (Status.FAILED.value, Status.BLOCKED.value):
        state.save(case_dir)
        return state

    # ---------------------------------------------------------- 2. 图表
    chart_marker = case_dir / "work" / "charts" / "chart_cross_asset.png"
    if force or not state.is_fresh(chart_marker, Stage.CHART.value, case_dir):
        pipeline.render_charts(result, paths)
        for png in sorted(paths.charts.glob("*.png")):
            state.record_artifact(png, Stage.CHART.value, case_dir)
        state.advance(Stage.CHART.value, "四张图完成")
    else:
        _log(state, "图表未变，跳过")

    # ---------------------------------------------------------- 3. 草稿装配
    drafts_path = case_dir / "drafts" / "drafts.md"
    composed_path = case_dir / "drafts" / "composed.json"
    sections: dict[str, str] = {}
    if force or not state.is_fresh(composed_path, Stage.DRAFT.value, case_dir):
        raw = build.load_drafts(drafts_path)
        problems: list[str] = []
        for sid, text in raw.items():
            r = composer.resolve(text, result.facts)
            sections[sid] = r.text
            if r.unresolved:
                problems.append(f"{sid}: {r.unresolved}")
        if problems:
            state.block(
                "草稿中存在无法解析的事实占位符",
                "；".join(problems[:5]) + " —— 补充对应事实或修正指标名后 resume",
            )
            state.save(case_dir)
            return state
        composed_path.write_text(
            json.dumps(sections, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        state.record_artifact(composed_path, Stage.DRAFT.value, case_dir)
        state.advance(Stage.DRAFT.value, f"装配 {len(sections)} 节")
        state.advance(Stage.MERGE.value, "草稿合并")
    else:
        sections = json.loads(composed_path.read_text(encoding="utf-8"))
        _log(state, "草稿未变，跳过")

    # ---------------------------------------------------------- 4. 硬门禁
    results = gates.run_all(
        sections, result.facts, result.quotes, cfg.info_cutoff, cfg.repo_root
    )
    state.gates = {r.id: r.as_dict() for r in results}
    gate_path = case_dir / "qa" / "gates.json"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(
        json.dumps([r.as_dict() for r in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    state.record_artifact(gate_path, Stage.HARD_GATES.value, case_dir)

    failed = [r for r in results if not r.ok]
    if failed:
        n = state.bump_attempt("HARD_GATES")
        if n >= cfg.max_gate_rounds:
            state.escalate(
                f"门禁连续 {n} 轮未通过: {[r.id for r in failed]} —— 需人工决定是否放宽标准"
            )
        else:
            state.advance(Stage.CRITIC.value, "进入修订（门禁未过）")
            state.advance(Stage.REVISE.value, "；".join(r.id for r in failed))
        state.save(case_dir)
        return state

    state.advance(Stage.HARD_GATES.value, "七条门禁全部通过")

    # ---------------------------------------------------------- 5. 人工审批
    if not state.has_approval("HUMAN_REVIEW"):
        state.status = Status.BLOCKED.value
        state.blocked_reason = "等待人工审批"
        state.resume_hint = "审阅 cases/<case>/out 下的草稿与 gate 结果，然后执行 approve"
        state.stage = Stage.HUMAN_REVIEW.value
        state.save(case_dir)
        _log(state, "已到人工审批节点，暂停")
        return state

    # ---------------------------------------------------------- 6. 出稿
    if not budget_left():
        state.escalate("超出墙钟预算")
        state.save(case_dir)
        return state

    out_path = case_dir / "out" / f"REITs周报_{cfg.case_id}.docx"
    build.build_report(
        result, sections, out_path, paths.charts,
        boards_order=boards.ordered_names(),
    )
    state.record_artifact(out_path, Stage.RENDER.value, case_dir)
    state.advance(Stage.RENDER.value, "docx 生成完成")
    state.advance(Stage.QA.value, "质检完成")
    state.status = Status.DONE.value
    state.blocked_reason = ""
    state.resume_hint = ""
    state.save(case_dir)
    return state


def approve(cfg: RunConfig, by: str, comment: str = "") -> CaseState:
    """记录人工审批。绑定当前草稿哈希，审批后改动会被识别为无效审批。"""
    case_dir = cfg.case_dir()
    state = CaseState.load(case_dir)
    composed = case_dir / "drafts" / "composed.json"
    digest = ""
    if composed.exists():
        from .state import sha256_file

        digest = sha256_file(composed)
    state.add_approval("HUMAN_REVIEW", by=by, decision="approve",
                       artifact_sha256=digest, comment=comment)
    state.status = Status.PENDING.value
    state.save(case_dir)
    return state


def status(cfg: RunConfig) -> dict:
    case_dir = cfg.case_dir()
    state = CaseState.load(case_dir)
    return {
        "case": state.case_id,
        "stage": state.stage,
        "status": state.status,
        "attempts": state.attempts,
        "gates": {k: v["ok"] for k, v in state.gates.items()},
        "artifacts": len(state.artifacts),
        "approvals": len(state.approvals),
        "blocked_reason": state.blocked_reason,
    }
