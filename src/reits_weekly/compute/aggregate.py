"""把归一化后的数据聚合成事实库。

这一层是"数字的唯一产地"：报告里出现的每个指标都在这里算一次、登记一次，
之后正文只引用事实 ID。函数本身不做 IO，输入输出都是内存对象，便于单测与回放。
"""

from __future__ import annotations

import pandas as pd

from ..adapters.base import WeekWindow
from ..facts import FactsBundle
from ..normalize.board_map import BoardDictionary
from . import boards as _boards
from . import liquidity as _liquidity
from . import returns as _returns
from . import valuation as _valuation


def build_facts(
    quotes: pd.DataFrame,
    turnover: pd.DataFrame | None,
    week: WeekWindow,
    case_id: str,
    input_hash: str,
    boards: BoardDictionary,
    source_meta: dict | None = None,
) -> FactsBundle:
    """计算并登记全部事实。

    Parameters
    ----------
    quotes : 已归一化并挂上 ``board`` / ``ret_total`` 的个券表。
    turnover : 个券成交表；缺失时跳过成交类事实并记录缺口。
    week : 报告期窗口，用于交易日数等参数。
    case_id, input_hash : 决定 fact_id 的两个要素。
    boards : 板块字典，用于排序与属性查表。
    """
    src = source_meta or {}
    bundle = FactsBundle(case_id=case_id, input_hash=input_hash)

    q = quotes.copy()
    if _returns.RETURN_COL not in q.columns:
        q = _returns.attach_returns(q)

    # ---------------------------------------------------------- 市场广度
    b = _boards.breadth(q)
    bundle.add("breadth.n", b.n, unit="只", formula="count(non-null ret_total)",
               source=src, section_hint=["0.1", "1.3"])
    bundle.add("breadth.up", b.up, unit="只", formula="ret_total > 1e-9",
               source=src, section_hint=["0.1", "1.3"])
    bundle.add("breadth.down", b.down, unit="只", formula="ret_total < -1e-9",
               source=src, section_hint=["0.1", "1.3"])
    bundle.add("breadth.flat", b.flat, unit="只", formula="n - up - down",
               source=src, section_hint=["0.1", "1.3"])
    bundle.add("market.eq_return", b.mean, unit="%", formula="mean(ret_total)",
               source=src, section_hint=["0.1", "1.3"])
    bundle.add("market.median_return", b.median, unit="%", formula="median(ret_total)",
               source=src, section_hint=["0.1", "1.3"])

    # ---------------------------------------------------------- 板块收益
    agg = _boards.board_aggregate(q, weight_col="mktcap_float")
    for _, row in agg.iterrows():
        board = row["board"]
        bundle.add(
            "board.eq_return", float(row["eq_return"]), unit="%",
            formula="mean(ret_total) within board",
            params={"board": board}, source=src,
            section_hint=["0.1", "1.2", "1.3"],
        )
        bundle.add(
            "board.n", int(row["n"]), unit="只",
            formula="count within board",
            params={"board": board}, source=src, section_hint=["1.2"],
        )
        if row.get("w_return") == row.get("w_return"):
            bundle.add(
                "board.w_return", float(row["w_return"]), unit="%",
                formula="sum(ret*w)/sum(w) within board",
                params={"board": board}, source=src, section_hint=["1.2"],
            )

    # ---------------------------------------------------------- 估值
    # P/NAV 统计只用"可比样本"：本期新上市的标的没有完整比较期，
    # 其 P/NAV 恒接近 1.00，若计入会把中位数整体拉向 1，
    # 2026-W45 期正是 96 只算得 1.039、94 只算得 1.055。
    comparable = q[q["close_prev"].notna()].copy()
    pv = _valuation.pnav_summary(comparable)
    if pv.n:
        bundle.add("pnav.median", pv.median, unit="ratio", decimals=3,
                   formula="median(pnav)", source=src, section_hint=["0.2", "1.5"])
        bundle.add("pnav.mean", pv.mean, unit="ratio", decimals=3,
                   formula="mean(pnav)", source=src, section_hint=["1.5"])
        bundle.add("pnav.weighted", pv.weighted, unit="ratio", decimals=3,
                   formula="sum(pnav*mktcap_total)/sum(mktcap_total)",
                   source=src, section_hint=["0.2", "1.5"])
        bundle.add("pnav.n_premium", pv.n_premium, unit="只",
                   formula="pnav >= 1", source=src, section_hint=["0.2", "1.5"])
        bundle.add("pnav.n_discount", pv.n_discount, unit="只",
                   formula="pnav < 1", source=src, section_hint=["0.2", "1.5"])
        bundle.add("pnav.median_discount", pv.median_discount_pct, unit="%",
                   decimals=1, formula="(median(pnav)-1)*100",
                   source=src, section_hint=["1.5"])
        bundle.add("pnav.min", pv.pmin, unit="ratio", decimals=3,
                   formula="min(pnav)", source=src, section_hint=["1.5"])
        bundle.add("pnav.max", pv.pmax, unit="ratio", decimals=3,
                   formula="max(pnav)", source=src, section_hint=["1.5"])
        bundle.add("pnav.q25", pv.q25, unit="ratio", decimals=3,
                   formula="quantile(pnav,0.25)", source=src, section_hint=["1.5"])
        bundle.add("pnav.q75", pv.q75, unit="ratio", decimals=3,
                   formula="quantile(pnav,0.75)", source=src, section_hint=["1.5"])

        by_board = _valuation.pnav_by_board(comparable)
        for _, row in by_board.iterrows():
            board = row["board"]
            bundle.add("pnav.board.median", float(row["median"]), unit="ratio",
                       decimals=3, formula="median(pnav) within board",
                       params={"board": board}, source=src, section_hint=["1.5"])
            bundle.add("pnav.board.median_discount", float(row["median_discount_pct"]),
                       unit="%", decimals=1,
                       formula="(median(pnav within board)-1)*100",
                       params={"board": board}, source=src, section_hint=["1.5"])
            bundle.add("pnav.board.n", int(row["n"]), unit="只",
                       formula="count within board",
                       params={"board": board}, source=src, section_hint=["1.5"])
            bundle.add("pnav.board.n_premium", int(row["n_premium"]), unit="只",
                       formula="pnav >= 1 within board",
                       params={"board": board}, source=src, section_hint=["1.5"])
            bundle.add("pnav.board.n_discount", int(row["n_discount"]), unit="只",
                       formula="pnav < 1 within board",
                       params={"board": board}, source=src, section_hint=["1.5"])

    # ---------------------------------------------------------- 成交
    if turnover is not None and len(turnover):
        # 成交表本身不含板块与权重，必须从个券表挂过来，否则分板块成交无法归集。
        tv = turnover.merge(
            q[["code", "board", "mktcap_float"]].rename(columns={"mktcap_float": "weight_float"}),
            on="code",
            how="left",
        )
        total = _liquidity.total_turnover(tv)
        mktcap_float = float(q["mktcap_float"].sum())
        n_days = week.n_trading_days
        rate = _liquidity.aggregate_turnover_rate(total, mktcap_float, n_days)

        bundle.add("turnover.total", total, unit="亿元",
                   formula="sum(turnover_week)", source=src, section_hint=["0.1", "1.4"])
        bundle.add("turnover.avg_daily", _liquidity.avg_daily_turnover(total, n_days),
                   unit="亿元", formula="sum(turnover_week)/n_days",
                   source=src, section_hint=["0.1", "1.4"])
        bundle.add("turnover.rate", rate, unit="%", decimals=3,
                   formula=_liquidity.TURNOVER_FORMULA_ID,
                   params={"n_days": n_days}, source=src, section_hint=["0.1", "1.4"])

        prev = float(pd.to_numeric(tv.get("turnover_week_prev"), errors="coerce").fillna(0).sum())
        if prev > 0:
            bundle.add("turnover.mom", _liquidity.turnover_mom(total, prev), unit="%",
                       decimals=1, formula="(cur-prev)/prev*100",
                       source=src, section_hint=["0.1", "1.4"])

        bt = _liquidity.board_turnover(tv, n_days=n_days)
        for board, row in bt.iterrows():
            bundle.add("turnover.board", float(row["turnover"]), unit="亿元",
                       formula="sum(turnover_week) within board",
                       params={"board": board}, source=src, section_hint=["1.4"])
            bundle.add("turnover.board_rate", float(row["turnover_rate"]), unit="%",
                       decimals=2, formula=_liquidity.TURNOVER_FORMULA_ID,
                       params={"board": board, "n_days": n_days}, source=src,
                       section_hint=["1.4"])

    return bundle
