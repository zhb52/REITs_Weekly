"""成交与流动性指标。

换手率口径（TR-01）—— 全项目唯一实现
----------------------------------
    全周日均换手率(%) = Σ本周成交额 ÷ Σ流通市值 ÷ 交易日数 × 100

这个公式是 2026-11-14 经作者确认的对外口径。之所以要专门写一段说明，是因为
2026-W45 期的报告里同一指标出现过三个数：

* 底稿 ``02_市场指数与跨资产`` 记 **0.36%**
* 报告正文（摘要与 1.4）写 **0.31%**
* 按上式复算得 **0.327%**（21.93 ÷ 1343.05 ÷ 5 × 100）

三者互不相符，其中 0.31% 用当时的数据无论如何算不出来。为了避免这类"合法地生成
一个错数字"，本模块把公式固定为 ``TR-01`` 并写入 facts 的 ``formula_id``，
``verify/crosscheck.py`` 会断言正文引用的换手率必须来自本函数。

TR-01 的优点是**可被外部复现**：任何人拿公开的成交额与流通市值都能算出同一个数。
"个券换手率等权平均"等替代口径会给出更低的数值，但依赖样本选择，不可复现，
故仅作敏感性参考，不进入正文。
"""

from __future__ import annotations

import pandas as pd

TURNOVER_FORMULA_ID = "TR-01"


def aggregate_turnover_rate(
    turnover_week: float, mktcap_float: float, n_days: int
) -> float:
    """TR-01：全周日均换手率（%）。

    Parameters
    ----------
    turnover_week : 全市场本周成交额合计（亿元）
    mktcap_float : 全市场流通市值合计（亿元）
    n_days : 本周交易日数
    """
    if mktcap_float <= 0 or n_days <= 0:
        return float("nan")
    return turnover_week / mktcap_float / n_days * 100.0


def total_turnover(df: pd.DataFrame, col: str = "turnover_week") -> float:
    """全市场本周成交额（亿元）。"""
    return float(pd.to_numeric(df[col], errors="coerce").fillna(0.0).sum())


def avg_daily_turnover(turnover_week: float, n_days: int) -> float:
    """日均成交额（亿元）。"""
    if n_days <= 0:
        return float("nan")
    return turnover_week / n_days


def turnover_mom(current: float, previous: float) -> float:
    """成交额环比变化（%）。上期为 0 时返回 NaN，不返回 inf。"""
    if previous is None or previous == 0 or previous != previous:
        return float("nan")
    return (current - previous) / previous * 100.0


def board_turnover(
    df: pd.DataFrame,
    board_col: str = "board",
    turnover_col: str = "turnover_week",
    prev_col: str = "turnover_week_prev",
    weight_col: str = "weight_float",
    n_days: int = 5,
) -> pd.DataFrame:
    """分板块成交额与换手率，列与报告图 3、图 4 对应。

    Returns
    -------
    DataFrame，列：``board`` / ``turnover`` / ``turnover_prev`` /
        ``turnover_rate`` / ``turnover_rate_prev`` / ``share_pct``。

    Note
    ----
    上周换手率用**本期流通市值**作分母重算，是与本周同口径的可比值，
    不等于终端公布的"上周日均换手率"（那用的是上周市值）。报告 1.4 的
    环比表述因此要写成"较上周同口径回落 X 个百分点"，不能直接照抄终端值。
    """
    work = df.copy()
    for c in (turnover_col, prev_col, weight_col):
        if c in work.columns:
            work[c] = pd.to_numeric(work[c], errors="coerce").fillna(0.0)

    grouped = work.groupby(board_col, sort=False)
    out = pd.DataFrame(
        {
            "turnover": grouped[turnover_col].sum(),
            "turnover_prev": grouped[prev_col].sum() if prev_col in work.columns else 0.0,
            "weight": grouped[weight_col].sum() if weight_col in work.columns else 0.0,
        }
    )
    out["turnover_rate"] = out.apply(
        lambda r: r["turnover"] / r["weight"] / n_days * 100.0 if r["weight"] > 0 else float("nan"),
        axis=1,
    )
    out["turnover_rate_prev"] = out.apply(
        lambda r: r["turnover_prev"] / r["weight"] / n_days * 100.0 if r["weight"] > 0 else float("nan"),
        axis=1,
    )
    total = out["turnover"].sum()
    out["share_pct"] = out["turnover"] / total * 100.0 if total > 0 else float("nan")
    return out.reset_index().rename(columns={board_col: "board"}).sort_values(
        "turnover", ascending=False
    ).reset_index(drop=True)


def concentration(df: pd.DataFrame, top_n: int = 4, col: str = "turnover_week") -> dict:
    """成交集中度：前 N 大板块合计占比（%），对应 1.4 的"合计占全市场 59.1%"。

    Returns
    -------
    dict，含 ``share_pct`` / ``boards`` / ``amount``。
    """
    bt = df.groupby("board", sort=False)[col].apply(
        lambda s: pd.to_numeric(s, errors="coerce").fillna(0.0).sum()
    )
    bt = bt.sort_values(ascending=False)
    total = float(bt.sum())
    top = bt.head(top_n)
    return {
        "share_pct": float(top.sum() / total * 100.0) if total > 0 else float("nan"),
        "boards": list(top.index),
        "amount": float(top.sum()),
    }
