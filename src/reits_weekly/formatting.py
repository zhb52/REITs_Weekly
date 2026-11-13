"""数字格式化 —— 表、文、事实库三方共用的唯一入口。

为什么要单独一个模块：报告里最容易出的一类错，是同一个数在表格里写 1.055、
在正文里写成 1.05 或 1.06。只要三处都走同一套函数，这类不一致就不可能发生。

格式化约定（沿用 2026-W45 期样张）
* 涨跌幅：两位小数、带正负号，``+0.01%`` / ``-0.14%``
* 指数点位：两位小数、无符号，``945.73``
* P/NAV：三位小数，``1.055``
* 折溢价：一位小数、带符号，``-28.6%``
* 利率变动：一位小数、带 bp，``-6.3bp``
* 缺失：统一 ``—``，绝不填 0
"""

from __future__ import annotations

import math

DASH = "—"


def is_missing(x: object) -> bool:
    if x is None:
        return True
    if isinstance(x, float) and math.isnan(x):
        return True
    try:
        return bool(x != x)  # numpy nan / pandas NA 的通用判断
    except Exception:
        return False


def fmt_num(x: float, dp: int = 2, thousands: bool = False) -> str:
    """普通数值。

    >>> fmt_num(945.734, 2)
    '945.73'
    >>> fmt_num(4000, 0, thousands=True)
    '4,000'
    """
    if is_missing(x):
        return DASH
    s = f"{x:,.{dp}f}" if thousands else f"{x:.{dp}f}"
    # 避免出现 "-0.00"
    if s.startswith("-") and float(s.replace(",", "")) == 0:
        s = s[1:]
    return s


def fmt_pct(x: float, dp: int = 2, sign: bool = True) -> str:
    """百分比（输入已是百分点，如 0.95 表示 0.95%）。"""
    if is_missing(x):
        return DASH
    s = f"{x:+.{dp}f}%" if sign else f"{x:.{dp}f}%"
    if s.startswith("-") and float(s.rstrip("%")) == 0:
        s = ("+" if sign else "") + f"{0:.{dp}f}%"
    return s


def fmt_bp(x: float, dp: int = 1, sign: bool = True) -> str:
    """基点。输入为 bp 数值（-6.3 表示下行 6.3bp）。"""
    if is_missing(x):
        return DASH
    s = f"{x:+.{dp}f}bp" if sign else f"{x:.{dp}f}bp"
    if s.startswith("-") and float(s.rstrip("bp")) == 0:
        s = ("+" if sign else "") + f"{0:.{dp}f}bp"
    return s


def fmt_ratio(x: float, dp: int = 3) -> str:
    """倍数类指标（P/NAV 等）。"""
    if is_missing(x):
        return DASH
    return f"{x:.{dp}f}"


def fmt_yi(x: float, dp: int = 2) -> str:
    """亿元金额。"""
    return fmt_num(x, dp)


def fmt_int(x: float) -> str:
    """整数（家数、只数）。"""
    if is_missing(x):
        return DASH
    return f"{int(round(x)):,}"
