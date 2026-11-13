"""收益口径测试。

这些用例锁定的不是"代码能跑"，而是**口径的定义**。任何改动只要破坏了
"不复权 + 分红"这个口径，测试立刻失败。
"""

from __future__ import annotations

import pandas as pd
import pytest

from reits_weekly.compute import returns


def _df(prev, cur, dpu):
    return pd.DataFrame(
        {"close_prev": prev, "close_cur": cur, "dpu_week": dpu}
    )


def test_no_dividend_equals_price_return():
    """无分红时，主口径应退化为纯价格涨跌幅。"""
    df = _df([10.0], [11.0], [0.0])
    assert returns.weekly_total_return(df).iloc[0] == pytest.approx(10.0)
    assert returns.weekly_price_return(df).iloc[0] == pytest.approx(10.0)


def test_dividend_adds_to_return():
    """分红计入总回报：10 元涨到 10.5 元并派 0.2 元，应为 +7%。"""
    df = _df([10.0], [10.5], [0.2])
    assert returns.weekly_total_return(df).iloc[0] == pytest.approx(7.0)
    assert returns.weekly_price_return(df).iloc[0] == pytest.approx(5.0)


def test_dividend_contribution_reconciles():
    """分红贡献 = 主口径 − 价格口径，两者必须闭合到浮点精度。"""
    df = _df([10.0, 3.0], [10.5, 2.7], [0.2, 0.15])
    total = returns.weekly_total_return(df)
    price = returns.weekly_price_return(df)
    contrib = returns.dividend_contribution(df)
    for i in range(len(df)):
        assert total.iloc[i] - price.iloc[i] == pytest.approx(contrib.iloc[i], abs=1e-12)


def test_missing_prev_returns_nan():
    """新上市标的没有上期收盘价，必须返回 NaN，不能当成 0% 涨跌。"""
    df = _df([float("nan")], [10.0], [0.0])
    assert pd.isna(returns.weekly_total_return(df).iloc[0])


def test_zero_prev_guarded():
    """上期价格为 0 时不产生 inf。"""
    df = _df([0.0], [10.0], [0.0])
    assert pd.isna(returns.weekly_total_return(df).iloc[0])


def test_real_fixture_breadth(quotes):
    """真实样本：94 只可比、41 涨 50 跌 3 平。"""
    from reits_weekly.compute.boards import breadth

    b = breadth(quotes)
    assert (b.n, b.up, b.down, b.flat) == (94, 41, 50, 3)
    assert b.mean == pytest.approx(-0.7502, abs=5e-4)
    # 报告写 -0.08%（两位小数）；全精度中位数为 -0.07926，四舍五入后一致
    assert b.median == pytest.approx(-0.0793, abs=1e-3)
    assert f"{b.median:+.2f}%" == "-0.08%"


def test_dividend_cases_in_fixture(quotes):
    """本期 5 只除息标的分红贡献应全部为正。"""
    div = quotes[quotes["dpu_week"] > 0]
    assert len(div) == 5
    assert (div[returns.DIV_CONTRIB_COL] > 0).all()
