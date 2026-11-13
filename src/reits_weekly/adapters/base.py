"""数据适配器契约。

设计要点
--------
1. **适配器只负责"取数 + 附上溯源"**，不做任何口径加工。口径一律在
   ``normalize`` 与 ``compute`` 两层完成，这样换数据源不会改变结果。
2. **能力（Capability）可缺省**。真实数据源往往只覆盖一部分字段，缺什么由
   ``registry`` 记录并在 ``provenance.json`` 中标 ``degraded``，由门禁决定是否阻断，
   而不是让整条链路失败。
3. **溯源到字段级**。每个 ``SourceMeta`` 带 ``raw_hash``（原始响应字节的 sha256），
   它同时是 PIT（point-in-time）校验和回放的凭据。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

import pandas as pd


class Capability(StrEnum):
    """适配器可以提供的数据能力。"""

    CALENDAR = "calendar"
    INDEX_SERIES = "index_series"
    QUOTES_WEEKLY = "quotes_weekly"
    TURNOVER_WEEKLY = "turnover_weekly"
    DIVIDENDS = "dividends"
    YIELDS = "yields"
    PRIMARY_EVENTS = "primary_events"
    PNAV = "pnav"


class CapabilityNotAvailable(NotImplementedError):
    """适配器不支持某项能力。

    显式抛出而不是返回空表，是为了让 ``registry`` 能区分"数据源没有这项能力"
    与"这项能力有数据但本期为空"。前者应降级并记入 provenance，后者是数据缺口。
    """


# --------------------------------------------------------------------------- #
# 规范字段名：所有适配器必须输出这些列，否则 schema 校验失败
# --------------------------------------------------------------------------- #

QUOTES_COLUMNS = [
    "code",              # str  6 位代码，不带交易所后缀
    "name",              # str  基金简称
    "board_raw",         # str  数据源原始板块名，保留以便差异检测
    "asset_class",       # str  产权类 / 特许经营权类
    "close_prev",        # float 基准日收盘（不复权）
    "close_cur",         # float 报告期末收盘（不复权）
    "dpu_week",          # float 本周每份分红，无分红填 0.0
    "mktcap_total",      # float 亿元
    "mktcap_float",      # float 亿元
    "issue_price",       # float 元
    "pnav",              # float 或 NaN
]

TURNOVER_COLUMNS = [
    "code",
    "turnover_week",         # float 亿元，本周合计成交额
    "turnover_week_prev",    # float 亿元
    "weight_float",          # float 亿元，用于加权
]

DIVIDEND_COLUMNS = [
    "code",
    "ex_date",        # date 场内除息日
    "per_unit",       # float 每份分红（元）
    "per_10_units",   # float 每 10 份分红
]

YIELD_COLUMNS = ["code", "trade_date", "value_pct"]


@dataclass(frozen=True)
class SourceMeta:
    """一次取数的溯源信息。"""

    source_id: str            # 例如 "fixture:demo-2026-W45" / "miaoxiang:fund_quote"
    adapter: str              # 适配器类名
    retrieved_at: datetime    # 抓取时刻
    source_asof: date         # 数据本身的最新日期
    license: str              # internal / public / sample-synthetic
    raw_hash: str = ""        # sha256(原始响应字节)

    def as_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "adapter": self.adapter,
            "retrieved_at": self.retrieved_at.isoformat(),
            "source_asof": self.source_asof.isoformat(),
            "license": self.license,
            "raw_hash": self.raw_hash,
        }


@dataclass
class SourceHealth:
    """适配器自检结果，写入 provenance.json 供门禁判断。"""

    capabilities: frozenset[Capability] = frozenset()
    row_counts: dict[str, int] = field(default_factory=dict)
    missing_columns: dict[str, list[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing_columns


@dataclass(frozen=True)
class WeekWindow:
    """一个报告期。日期一律为 date，不做时区换算。"""

    start: date
    end: date
    prev_end: date
    trading_days: tuple[date, ...] = ()

    @property
    def label(self) -> str:
        return f"{self.start:%Y%m%d}-{self.end:%m%d}"

    @property
    def iso_week(self) -> str:
        y, w, _ = self.end.isocalendar()
        return f"{y}-W{w:02d}"

    @property
    def n_trading_days(self) -> int:
        return len(self.trading_days) or 5


@runtime_checkable
class MarketDataAdapter(Protocol):
    """适配器需要实现的接口。未实现的能力可以不提供，由 registry 降级处理。"""

    meta: SourceMeta
    capabilities: frozenset[Capability]

    def quotes_weekly(self, week: WeekWindow) -> pd.DataFrame:
        """个券周度行情，列见 ``QUOTES_COLUMNS``。"""
        ...

    def turnover_weekly(self, week: WeekWindow) -> pd.DataFrame:
        """个券周度成交，列见 ``TURNOVER_COLUMNS``。"""
        ...

    def dividends(self, start: date, end: date) -> pd.DataFrame:
        """区间内除息记录，列见 ``DIVIDEND_COLUMNS``。"""
        ...

    def yields(self, codes: list[str], start: date, end: date) -> pd.DataFrame:
        """利率序列，列见 ``YIELD_COLUMNS``。"""
        ...

    def index_series(
        self, codes: list[str], start: date, end: date
    ) -> pd.DataFrame:
        """指数日收盘序列，列：trade_date, code, close。"""
        ...

    def health(self) -> SourceHealth:
        """自检：覆盖了哪些能力、行数、缺哪些列。"""
        ...
