"""示例数据适配器 —— 从 ``fixtures/`` 的 CSV 读取，无需网络与凭证。

这是默认适配器，也是 CI 与演示路径。它把"取数"这件事变成一个可版本控制的
文件读取，因此任何人拿到仓库都能复现出同一份周报。

数据来源：2026-W45 期的公开市场行情（收盘价、成交额、P/NAV、流通市值）。
不含持仓、客户或内部批注信息，可随作业提交。
"""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from .base import (
    Capability,
    CapabilityNotAvailable,
    MarketDataAdapter,
    SourceHealth,
    SourceMeta,
    WeekWindow,
)


def _hash_dir(path: Path) -> str:
    """对目录内所有 CSV 求联合 sha256，作为 input_hash。"""
    h = hashlib.sha256()
    for f in sorted(path.glob("*.csv")):
        h.update(f.name.encode("utf-8"))
        h.update(f.read_bytes())
    return h.hexdigest()


class FixtureAdapter(MarketDataAdapter):
    """从 fixtures/<case>/ 目录读取一期数据。"""

    def __init__(self, fixture_dir: Path | str, case_id: str) -> None:
        self.dir = Path(fixture_dir)
        if not self.dir.exists():
            raise FileNotFoundError(f"示例数据目录不存在: {self.dir}")
        self.case_id = case_id
        self._quotes = self._read("quotes_weekly.csv")
        self._turnover = self._read("turnover_weekly.csv")
        self._yields = self._read("yields.csv")
        self._index = self._read("index_series.csv")

        self.meta = SourceMeta(
            source_id=f"fixture:{case_id}",
            adapter="FixtureAdapter",
            retrieved_at=pd.Timestamp.now().to_pydatetime(),
            source_asof=self._latest_date(),
            license="public-market-data",
            raw_hash=_hash_dir(self.dir),
        )
        self.capabilities = frozenset(
            {
                Capability.QUOTES_WEEKLY,
                Capability.TURNOVER_WEEKLY,
                Capability.YIELDS,
                Capability.INDEX_SERIES,
            }
        )

    # ------------------------------------------------------------------ 内部

    def _read(self, name: str) -> pd.DataFrame:
        p = self.dir / name
        if not p.exists():
            return pd.DataFrame()
        return pd.read_csv(p, dtype={"code": "string"})

    def _latest_date(self) -> date:
        if not self._index.empty and "date" in self._index.columns:
            return pd.to_datetime(self._index["date"]).max().date()
        return date.today()

    # ------------------------------------------------------------------ 接口

    def quotes_weekly(self, week: WeekWindow) -> pd.DataFrame:
        df = self._quotes.copy()
        for c in ("close_prev", "close_cur", "dpu_week", "mktcap_total",
                  "mktcap_float", "issue_price", "pnav"):
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        df["dpu_week"] = df["dpu_week"].fillna(0.0)
        return df

    def turnover_weekly(self, week: WeekWindow) -> pd.DataFrame:
        if self._turnover.empty:
            raise CapabilityNotAvailable("turnover_weekly")
        df = self._turnover.copy()
        for c in ("turnover_week", "turnover_week_prev"):
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
        return df

    def dividends(self, start: date, end: date) -> pd.DataFrame:
        # 示例数据把本周每份分红直接并入 quotes_weekly 的 dpu_week 列，
        # 因此单独的分红事件表不可用；真实适配器应返回逐笔除息记录。
        raise CapabilityNotAvailable("dividends")

    def yields(self, codes: list[str], start: date, end: date) -> pd.DataFrame:
        if self._yields.empty:
            raise CapabilityNotAvailable("yields")
        df = self._yields.copy()
        if codes:
            df = df[df["code"].isin(codes)]
        return df

    def index_series(self, codes: list[str], start: date, end: date) -> pd.DataFrame:
        if self._index.empty:
            raise CapabilityNotAvailable("index_series")
        df = self._index.copy()
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df = df[(df["date"] >= start) & (df["date"] <= end)]
        if codes:
            df = df[df["series"].isin(codes)]
        return df[["date", "series", "value_rebased"]].rename(
            columns={"date": "trade_date", "series": "code", "value_rebased": "close"}
        )

    def health(self) -> SourceHealth:
        return SourceHealth(
            capabilities=self.capabilities,
            row_counts={
                "quotes_weekly": len(self._quotes),
                "turnover_weekly": len(self._turnover),
                "index_series": len(self._index),
                "yields": len(self._yields),
            },
            warnings=[] if not self._turnover.empty else ["缺少成交表，1.4 将降级"],
        )


def week_from_dates(start: date, end: date, prev_end: date | None = None) -> WeekWindow:
    """构造报告期窗口，默认上一个交易日为上周五。"""
    if prev_end is None:
        prev_end = start - timedelta(days=3)
    days = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return WeekWindow(start=start, end=end, prev_end=prev_end, trading_days=tuple(days))
