"""流动性测试 —— 锁定 TR-01 口径。

TR-01 是全项目唯一实现的换手率公式。2026-W45 期报告里同一指标出现过
0.36% / 0.31% / 0.327% 三个值，本测试存在的意义就是让第四个值不可能再出现。
"""

from __future__ import annotations

import pytest

from reits_weekly.compute import liquidity


def test_tr01_basic():
    """21.93 亿成交、1343.05 亿流通市值、5 个交易日 → 0.327%。"""
    rate = liquidity.aggregate_turnover_rate(21.93, 1343.05, 5)
    assert round(rate, 3) == 0.327


def test_tr01_guards():
    assert liquidity.aggregate_turnover_rate(21.93, 0, 5) != \
        liquidity.aggregate_turnover_rate(21.93, 0, 5)  # NaN
    assert liquidity.aggregate_turnover_rate(21.93, 1000, 0) != \
        liquidity.aggregate_turnover_rate(21.93, 1000, 0)


def test_turnover_mom():
    assert liquidity.turnover_mom(21.93, 24.14) == pytest.approx(-9.155, abs=1e-3)
    # 上期为 0 时应返回 NaN 而不是 inf
    assert liquidity.turnover_mom(10.0, 0.0) != liquidity.turnover_mom(10.0, 0.0)


def test_avg_daily():
    assert liquidity.avg_daily_turnover(21.93, 5) == pytest.approx(4.386)


def test_real_turnover_matches_report(facts):
    """真实样本的成交类事实须与报告一致。"""
    def one(metric):
        items = facts.by_metric(metric)
        assert len(items) == 1, metric
        return items[0]

    assert one("turnover.total").value == pytest.approx(21.93, abs=0.01)
    assert one("turnover.avg_daily").value == pytest.approx(4.39, abs=0.01)
    assert one("turnover.rate").value == pytest.approx(0.327, abs=1e-3)
    assert one("turnover.mom").value == pytest.approx(-9.1, abs=0.1)


def test_tr01_recorded_in_facts(facts):
    """换手率事实必须带 formula_id，否则无法说明它来自哪个公式。"""
    rate = facts.by_metric("turnover.rate")[0]
    assert rate.formula == liquidity.TURNOVER_FORMULA_ID


def test_board_turnover_sums_to_total(facts):
    """分板块成交额之和应等于全市场成交额（勾稽）。"""
    total = facts.by_metric("turnover.total")[0].value
    parts = sum(f.value for f in facts.by_metric("turnover.board"))
    assert parts == pytest.approx(total, abs=0.01)
