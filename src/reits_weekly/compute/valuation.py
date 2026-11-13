"""估值指标 —— P/NAV 及其分布。

口径说明
--------
* P/NAV = 收盘价 ÷ 单位净值。数据源直接给 ``pnav`` 字段时直接使用，不做二次估算；
  缺 NAV 桥接时本模块**不猜**，返回 NaN 并由门禁记录为数据缺口。
* 溢价/折价判定：``pnav >= 1`` 记溢价，``pnav < 1`` 记折价。恰好等于 1 计入溢价，
  与报告"56 只高于 1 倍、38 只低于 1 倍"的表述保持一致（合计须等于样本数）。
* 市值加权 P/NAV 用**总市值**加权（与报告 1.5 的 1.091 口径一致），
  用流通市值加权会系统性偏低，不可混用。
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import pandas as pd


@dataclass(frozen=True)
class PnavSummary:
    n: int
    median: float
    mean: float
    weighted: float
    n_premium: int
    n_discount: int
    pmin: float
    pmax: float
    q25: float
    q75: float

    @property
    def median_discount_pct(self) -> float:
        """中位折溢价（%），=(中位数−1)×100。"""
        return (self.median - 1.0) * 100.0 if self.median == self.median else float("nan")

    def as_dict(self) -> dict:
        d = asdict(self)
        d["median_discount_pct"] = self.median_discount_pct
        return d


def _clean_pnav(df: pd.DataFrame, col: str = "pnav") -> pd.DataFrame:
    work = df.copy()
    work[col] = pd.to_numeric(work[col], errors="coerce")
    return work.dropna(subset=[col])


def pnav_summary(
    df: pd.DataFrame, weight_col: str = "mktcap_total", col: str = "pnav"
) -> PnavSummary:
    """全市场 P/NAV 分布摘要。"""
    work = _clean_pnav(df, col)
    if work.empty:
        nan = float("nan")
        return PnavSummary(0, nan, nan, nan, 0, 0, nan, nan, nan, nan)

    p = work[col].astype("float64")
    if weight_col and weight_col in work.columns:
        w = work[weight_col].astype("float64")
        total = w.sum()
        weighted = float((p * w).sum() / total) if total > 0 else float("nan")
    else:
        weighted = float("nan")

    return PnavSummary(
        n=int(len(p)),
        median=float(p.median()),
        mean=float(p.mean()),
        weighted=weighted,
        n_premium=int((p >= 1.0).sum()),
        n_discount=int((p < 1.0).sum()),
        pmin=float(p.min()),
        pmax=float(p.max()),
        q25=float(p.quantile(0.25)),
        q75=float(p.quantile(0.75)),
    )


def pnav_by_board(
    df: pd.DataFrame,
    board_col: str = "board",
    weight_col: str = "mktcap_total",
    col: str = "pnav",
) -> pd.DataFrame:
    """分板块 P/NAV 表，列与报告 1.5 表一致。

    Returns
    -------
    DataFrame，列：``board`` / ``n`` / ``median`` / ``median_discount_pct`` /
        ``weighted`` / ``n_premium`` / ``n_discount``，按 ``median`` 升序。
    """
    work = _clean_pnav(df, col)
    rows = []
    for board, g in work.groupby(board_col, sort=False):
        p = g[col].astype("float64")
        w = g[weight_col].astype("float64") if weight_col in g.columns else None
        weighted = float((p * w).sum() / w.sum()) if w is not None and w.sum() > 0 else float("nan")
        rows.append(
            {
                "board": board,
                "n": int(len(p)),
                "median": float(p.median()),
                "median_discount_pct": float((p.median() - 1.0) * 100.0),
                "weighted": weighted,
                "n_premium": int((p >= 1.0).sum()),
                "n_discount": int((p < 1.0).sum()),
            }
        )
    out = pd.DataFrame(rows)
    return out.sort_values("median", ascending=True).reset_index(drop=True)
