"""估值与事实库测试。

事实库这一组用例的核心命题：**同一个输入，重跑必须得到同一个 fact_id 和同一个
display**。这是"可复跑"的最小证据，也是后面版本对比、回滚的前提。
"""

from __future__ import annotations

import pytest

from reits_weekly.facts import FactsBundle, format_value, make_fact_id
from reits_weekly.formatting import DASH


# --------------------------------------------------------------------- 格式化


def test_format_pct_signs():
    assert format_value(0.01, "%", 2) == "+0.01%"
    assert format_value(-0.14, "%", 2) == "-0.14%"
    assert format_value(0.0, "%", 2) == "+0.00%"


def test_format_ratio_three_dp():
    assert format_value(1.0546, "ratio", 3) == "1.055"


def test_format_missing_is_dash():
    assert format_value(float("nan"), "%", 2) == DASH
    assert format_value(None, "亿円", 2) == DASH


def test_format_bp():
    assert format_value(-6.3, "bp", 1) == "-6.3bp"


# --------------------------------------------------------------------- fact_id


def test_fact_id_deterministic():
    a = make_fact_id("turnover.rate", {"n_days": 5}, "2026-W45", "abc")
    b = make_fact_id("turnover.rate", {"n_days": 5}, "2026-W45", "abc")
    assert a == b
    assert a.startswith("F-") and len(a) == 10


def test_fact_id_changes_with_input():
    a = make_fact_id("turnover.rate", {"n_days": 5}, "2026-W45", "abc")
    b = make_fact_id("turnover.rate", {"n_days": 5}, "2026-W45", "abd")
    assert a != b


def test_fact_id_changes_with_params():
    a = make_fact_id("board.eq_return", {"board": "产业园区"}, "2026-W45", "abc")
    b = make_fact_id("board.eq_return", {"board": "商业不动产"}, "2026-W45", "abc")
    assert a != b


def test_bundle_rejects_conflicting_value():
    fb = FactsBundle("c", "h")
    fb.add("x", 1.0)
    with pytest.raises(ValueError):
        fb.add("x", 2.0)


def test_bundle_is_idempotent():
    fb1 = FactsBundle("c", "h")
    fb1.add("x", 1.0, unit="%")
    fb2 = FactsBundle("c", "h")
    fb2.add("x", 1.0, unit="%")
    assert fb1.to_json() == fb2.to_json()


# --------------------------------------------------------------------- 真实样本


def test_pnav_matches_report(facts):
    """P/NAV 分布须与报告 1.5 一致：94 只、中位 1.055、加权 1.091、56/38。"""
    def one(metric):
        return facts.by_metric(metric)[0].value

    assert one("pnav.median") == pytest.approx(1.055, abs=1e-3)
    assert one("pnav.weighted") == pytest.approx(1.091, abs=1e-3)
    assert one("pnav.n_premium") == 56
    assert one("pnav.n_discount") == 38
    assert one("pnav.n_premium") + one("pnav.n_discount") == 94


def test_pnav_excludes_new_listings(facts):
    """P/NAV 样本数应为 94，而不是 96 —— 新上市标的会把中位数拉向 1。"""
    n = facts.by_metric("pnav.board.n")
    assert sum(f.value for f in n) == 94


def test_board_return_match(facts):
    """板块等权收益与底稿表2 一致。"""
    got = {f.params["board"]: f.value for f in facts.by_metric("board.eq_return")}
    assert got["数据中心"] == pytest.approx(1.69, abs=5e-3)
    assert got["产业园区"] == pytest.approx(-2.3295, abs=5e-3)
    assert got["商业不动产"] == pytest.approx(-3.3617, abs=5e-3)
    assert got["水利设施"] == pytest.approx(0.80, abs=5e-3)


def test_water_board_now_two_funds(facts):
    """508087 归能源后，水利只剩 2 只，P/NAV 中位数为 1.284 而非 1.430。"""
    med = {f.params["board"]: f.value for f in facts.by_metric("pnav.board.median")}
    assert med["水利设施"] == pytest.approx(1.284, abs=2e-3)
    assert med["能源基础设施"] == pytest.approx(1.101, abs=2e-3)


def test_element_count_reconciles(facts):
    """勾稽：板块样本数之和 = 全市场可比样本数。"""
    n_board = sum(f.value for f in facts.by_metric("board.n"))
    n_market = facts.by_metric("breadth.n")[0].value
    assert n_board == n_market


def test_every_fact_has_source(facts):
    """每条事实都必须能追溯到数据来源，否则无法审计。"""
    missing = [f.metric for f in facts if not f.source.get("source_id")]
    assert missing == []
