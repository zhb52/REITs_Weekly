"""编排层 —— 把适配器、归一化、计算、图表串成一次可重复的构建。

这一层只做"按顺序调用 + 落盘"，不含业务判断。真正的流程控制
（阶段推进、门禁、重试、续跑）在 ``controller.py`` 里，二者刻意分开：
本模块可以单独用于回放与调试，不需要状态机在跑。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

from .adapters.base import MarketDataAdapter, WeekWindow
from .adapters.fixture import FixtureAdapter
from .compute import returns
from .compute.aggregate import build_facts
from .compute import liquidity
from .facts import FactsBundle
from .normalize.board_map import BoardDictionary


# 指数折线的起点：样张以 2021-09-30 为基期（=1000）
INDEX_HISTORY_START = date(2021, 9, 30)


@dataclass
class CasePaths:
    root: Path
    case_id: str

    @property
    def dir(self) -> Path:
        return self.root / "cases" / self.case_id

    @property
    def work(self) -> Path:
        return self.dir / "work"

    @property
    def facts(self) -> Path:
        return self.dir / "facts"

    @property
    def charts(self) -> Path:
        return self.work / "charts"

    @property
    def out(self) -> Path:
        return self.dir / "out"

    def ensure(self) -> "CasePaths":
        for p in (self.work, self.facts, self.charts, self.out):
            p.mkdir(parents=True, exist_ok=True)
        return self


@dataclass
class CaseResult:
    case_id: str
    week: WeekWindow
    quotes: pd.DataFrame
    turnover: pd.DataFrame
    board_turnover: pd.DataFrame
    index_series: pd.DataFrame
    facts: FactsBundle
    board_conflicts: list[dict] = field(default_factory=list)
    source_meta: dict = field(default_factory=dict)


def get_adapter(
    source: str, fixture_dir: Path, case_id: str
) -> MarketDataAdapter:
    """按名称装配适配器。真实数据源的适配器接入点在这里。"""
    if source in ("fixture", "demo"):
        return FixtureAdapter(fixture_dir, case_id)
    raise ValueError(
        f"未知数据源 {source!r}。当前可用：fixture。"
        f"妙想 MCP 适配器见 adapters/miaoxiang.py（待接入）。"
    )


def prepare(
    adapter: MarketDataAdapter,
    week: WeekWindow,
    boards: BoardDictionary,
    case_id: str,
) -> CaseResult:
    """执行 INGEST → NORMALIZE → COMPUTE → FACTS，全部在内存中完成。"""
    raw_quotes = adapter.quotes_weekly(week)
    conflicts = boards.conflicts(raw_quotes)

    quotes = returns.attach_returns(boards.apply(raw_quotes))

    try:
        turnover = adapter.turnover_weekly(week)
    except Exception:
        turnover = pd.DataFrame()

    if len(turnover):
        tv = turnover.merge(
            quotes[["code", "board", "mktcap_float"]].rename(
                columns={"mktcap_float": "weight_float"}
            ),
            on="code",
            how="left",
        )
        bt = liquidity.board_turnover(tv, n_days=week.n_trading_days)
    else:
        bt = pd.DataFrame()

    try:
        # 折线图要的是完整历史（样张起点 2021-09-30，定基 1000），
        # 不是报告期那 5 个交易日，故这里显式回溯。
        index_df = adapter.index_series([], INDEX_HISTORY_START, week.end)
    except Exception:
        index_df = pd.DataFrame()

    facts = build_facts(
        quotes, turnover, week, case_id,
        adapter.meta.raw_hash, boards, adapter.meta.as_dict(),
    )

    return CaseResult(
        case_id=case_id,
        week=week,
        quotes=quotes,
        turnover=turnover,
        board_turnover=bt,
        index_series=index_df,
        facts=facts,
        board_conflicts=conflicts,
        source_meta=adapter.meta.as_dict(),
    )


def write_artifacts(result: CaseResult, paths: CasePaths) -> dict[str, Path]:
    """把事实库、中间表与溯源写入 case 目录。"""
    paths.ensure()
    written: dict[str, Path] = {}

    fpath = paths.facts / "facts.json"
    fpath.write_text(result.facts.to_json(), encoding="utf-8")
    written["facts"] = fpath

    qpath = paths.work / "quotes_normalized.csv"
    result.quotes.to_csv(qpath, index=False, encoding="utf-8")
    written["quotes"] = qpath

    prov = {
        "source": result.source_meta,
        "board_conflicts": result.board_conflicts,
        "n_total": int(len(result.quotes)),
        "n_comparable": int(result.quotes["close_prev"].notna().sum()),
        "n_facts": len(result.facts),
    }
    ppath = paths.work / "provenance.json"
    ppath.write_text(json.dumps(prov, ensure_ascii=False, indent=2), encoding="utf-8")
    written["provenance"] = ppath

    return written


def render_charts(result: CaseResult, paths: CasePaths) -> list:
    """生成四张图。指数序列不足时跳过对应图并记录，而不是报错中断。"""
    from .render import charts

    if result.index_series.empty:
        raise RuntimeError("缺少指数序列，无法生成折线图")

    index_df = result.index_series.rename(
        columns={"trade_date": "date", "code": "series", "close": "value"}
    )
    # 样张的 chart1 与 chart2 都含 932047（全收益），提取时会各出现一次，
    # 需按 (日期, 代码) 去重，否则同一条线会被画两遍、点数翻倍。
    index_df = index_df.drop_duplicates(subset=["date", "series"], keep="first")
    return charts.build_all(index_df, result.board_turnover, paths.charts)
