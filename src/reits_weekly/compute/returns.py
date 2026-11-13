"""收益计算 —— 纯函数，输入输出都是 DataFrame / Series。

口径（2026-W45 期经作者确认，后续各期沿用）
----------------------------------------
主口径为 **不复权价格 + 当期分红**：

    周涨跌幅 = (本周收盘价 − 上周收盘价 + 本周每份分红) ÷ 上周收盘价 × 100

为什么不用前复权：前复权序列会在每次分红后整体重算历史价格，导致"上周收盘价"
随本期分红变化，跨期不可比。用"不复权 + 分红"可以把价格变动与分红收益分开呈现，
这正是报告 1.1 里"价格指数与全收益指数差 15bp 来自 5 只集中除息"那句话的算法基础。

与交易所/终端的差别：终端"涨跌幅"字段默认是前复权口径，且部分导出把百分数存成小数
（0.0094637 表示 0.95%），必须在 ``normalize`` 层显式乘 100，不在此处处理。
"""

from __future__ import annotations

import pandas as pd

RETURN_COL = "ret_total"
RETURN_PRICE_COL = "ret_price"
DIV_CONTRIB_COL = "div_contrib"


def weekly_total_return(df: pd.DataFrame) -> pd.Series:
    """主口径周涨跌幅（%）。

    Parameters
    ----------
    df : 需含 ``close_prev`` / ``close_cur`` / ``dpu_week`` 三列。

    Returns
    -------
    Series，单位百分点（0.95 表示 0.95%）。无有效基准价者返回 NaN。
    """
    prev = pd.to_numeric(df["close_prev"], errors="coerce")
    cur = pd.to_numeric(df["close_cur"], errors="coerce")
    dpu = pd.to_numeric(df["dpu_week"], errors="coerce").fillna(0.0)

    valid = prev.notna() & cur.notna() & (prev > 0)
    out = pd.Series(float("nan"), index=df.index, dtype="float64")
    out[valid] = (cur[valid] - prev[valid] + dpu[valid]) / prev[valid] * 100.0
    return out


def weekly_price_return(df: pd.DataFrame) -> pd.Series:
    """仅价格口径周涨跌幅（%），用于解释分红贡献。"""
    prev = pd.to_numeric(df["close_prev"], errors="coerce")
    cur = pd.to_numeric(df["close_cur"], errors="coerce")
    valid = prev.notna() & cur.notna() & (prev > 0)
    out = pd.Series(float("nan"), index=df.index, dtype="float64")
    out[valid] = (cur[valid] - prev[valid]) / prev[valid] * 100.0
    return out


def dividend_contribution(df: pd.DataFrame) -> pd.Series:
    """分红对周涨跌幅的贡献（百分点）。

    等于主口径减价格口径，也等于 ``dpu / close_prev * 100``。
    两者应当一致，``verify/crosscheck.py`` 会断言差值为 0。
    """
    prev = pd.to_numeric(df["close_prev"], errors="coerce")
    dpu = pd.to_numeric(df["dpu_week"], errors="coerce").fillna(0.0)
    valid = prev.notna() & (prev > 0)
    out = pd.Series(0.0, index=df.index, dtype="float64")
    out[valid] = dpu[valid] / prev[valid] * 100.0
    return out


def attach_returns(df: pd.DataFrame) -> pd.DataFrame:
    """把三种收益口径一次性挂到表上并返回副本。"""
    out = df.copy()
    out[RETURN_COL] = weekly_total_return(out)
    out[RETURN_PRICE_COL] = weekly_price_return(out)
    out[DIV_CONTRIB_COL] = dividend_contribution(out)
    return out
