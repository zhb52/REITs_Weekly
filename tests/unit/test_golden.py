"""固定基线测试。

作业要求"对固定基线测试每项改动、接受或拒绝"。``tests/golden/baseline_2026-W45.json``
是 2026-W45 期的数值快照。任何改动如果改变了这里的数值，测试会失败——
此时必须显式更新基线并在 CHANGELOG 说明理由，不能默默改掉。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

BASELINE = Path(__file__).resolve().parents[1] / "golden" / "baseline_2026-W45.json"


@pytest.fixture(scope="module")
def baseline():
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def test_baseline_file_exists(baseline):
    assert baseline["case"] == "demo-2026-W45"
    assert baseline["metrics"], "基线为空"


def test_scalar_metrics_match(facts, baseline):
    """标量指标须与基线一致（相对容差 1e-6）。"""
    for metric, expect in baseline["metrics"].items():
        if metric == "board.eq_return":
            continue
        items = [f for f in facts.by_metric(metric) if not f.params]
        assert items, f"事实库缺少 {metric}"
        got = items[0].value
        assert got == pytest.approx(expect["value"], rel=1e-6), (
            f"{metric} 由 {expect['value']} 变为 {got}；"
            f"若为预期改动，请更新 baseline 并在 CHANGELOG 说明"
        )


def test_board_returns_match(facts, baseline):
    got = {f.params["board"]: f.value for f in facts.by_metric("board.eq_return")}
    for board, expect in baseline["metrics"]["board.eq_return"].items():
        assert got[board] == pytest.approx(expect, rel=1e-6), f"{board} 板块收益变化"


def test_display_strings_stable(facts, baseline):
    """display 字符串也要稳定 —— 它是正文里实际出现的文字。"""
    for metric, expect in baseline["metrics"].items():
        if metric == "board.eq_return":
            continue
        items = [f for f in facts.by_metric(metric) if not f.params]
        assert items[0].display == expect["display"], f"{metric} 的显示文本变化"


def test_formula_ids_stable(facts, baseline):
    """formula 标识变化意味着口径变了，必须被记录。"""
    for metric, expect in baseline["metrics"].items():
        if metric == "board.eq_return":
            continue
        items = [f for f in facts.by_metric(metric) if not f.params]
        assert items[0].formula == expect["formula"], f"{metric} 的 formula 变化"
