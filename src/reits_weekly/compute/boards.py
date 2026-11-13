"""市场广度与板块聚合。

板块收益一律采用**板块内等权**（不含本期新上市标的），这是报告 0.1 与 1.2 的口径：
"按本报告统一口径（不复权加分红、板块内等权）"。

注意与官方指数的区别：中证 REITs 指数是市值加权、含分红再投资，两者不能混用。
报告里凡出现"板块等权"与"指数"并列的地方，必须分别命名，这是章节口径边界的一部分。
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .returns import RETURN_COL


@dataclass(frozen=True)
class Breadth:
    """涨跌家数统计。"""

    n: int
    up: int
    down: int
    flat: int
    mean: float
    median: float

    def as_dict(self) -> dict:
        return {
            "n": self.n,
            "up": self.up,
            "down": self.down,
            "flat": self.flat,
            "mean": self.mean,
            "median": self.median,
        }


def breadth(df: pd.DataFrame, ret_col: str = RETURN_COL) -> Breadth:
    """统计涨/跌/平家数与均值、中位数。

    阈值取 1e-9 而非 0：浮点减法会产生 1e-16 量级的噪声，
    若用 ``> 0`` 判断，价格完全持平的个券会被误计为上涨。
    """
    s = pd.to_numeric(df[ret_col], errors="coerce").dropna()
    if s.empty:
        return Breadth(0, 0, 0, 0, float("nan"), float("nan"))
    up = int((s > 1e-9).sum())
    down = int((s < -1e-9).sum())
    flat = int(len(s) - up - down)
    return Breadth(
        n=int(len(s)),
        up=up,
        down=down,
        flat=flat,
        mean=float(s.mean()),
        median=float(s.median()),
    )


def board_aggregate(
    df: pd.DataFrame,
    board_col: str = "board",
    ret_col: str = RETURN_COL,
    weight_col: str | None = None,
) -> pd.DataFrame:
    """按板块聚合：样本数、等权收益、可选市值加权收益。

    Parameters
    ----------
    weight_col : 若给定（如 ``mktcap_float``），额外输出市值加权收益。
        加权收益用于与官方指数比对，**不作为正文主口径**。

    Returns
    -------
    DataFrame，列：``board`` / ``n`` / ``eq_return`` / ``w_return``（可选）。
        按 ``eq_return`` 降序排列。
    """
    work = df[[board_col, ret_col] + ([weight_col] if weight_col else [])].copy()
    work[ret_col] = pd.to_numeric(work[ret_col], errors="coerce")
    work = work.dropna(subset=[ret_col])

    grouped = work.groupby(board_col, sort=False)
    out = pd.DataFrame(
        {
            "n": grouped[ret_col].size(),
            "eq_return": grouped[ret_col].mean(),
        }
    )
    if weight_col:
        w = work[weight_col].astype("float64")

        def _wavg(g: pd.DataFrame) -> float:
            ww = g[weight_col].astype("float64")
            total = ww.sum()
            if total <= 0:
                return float("nan")
            return float((g[ret_col] * ww).sum() / total)

        out["w_return"] = grouped.apply(_wavg, include_groups=False)
    out = out.reset_index().rename(columns={board_col: "board"})
    return out.sort_values("eq_return", ascending=False).reset_index(drop=True)


def market_equal_weight(df: pd.DataFrame, ret_col: str = RETURN_COL) -> float:
    """全市场等权收益（%）。应与 ``breadth().mean`` 完全相同，用于勾稽。"""
    s = pd.to_numeric(df[ret_col], errors="coerce").dropna()
    return float(s.mean()) if len(s) else float("nan")
