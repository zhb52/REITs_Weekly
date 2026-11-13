"""测试共用的 fixture 与路径。"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

CONFIG_DIR = ROOT / "config"
FIXTURE_DIR = ROOT / "fixtures" / "demo-2026-W45"
CASE_ID = "demo-2026-W45"

WEEK_START = dt.date(2026, 11, 2)
WEEK_END = dt.date(2026, 11, 6)
WEEK_PREV_END = dt.date(2026, 10, 30)


@pytest.fixture(scope="session")
def boards():
    from reits_weekly.normalize.board_map import BoardDictionary

    return BoardDictionary.load(CONFIG_DIR)


@pytest.fixture(scope="session")
def week():
    from reits_weekly.adapters.fixture import week_from_dates

    return week_from_dates(WEEK_START, WEEK_END, WEEK_PREV_END)


@pytest.fixture(scope="session")
def adapter():
    from reits_weekly.adapters.fixture import FixtureAdapter

    return FixtureAdapter(FIXTURE_DIR, CASE_ID)


@pytest.fixture(scope="session")
def quotes(adapter, boards, week):
    """已归一化并挂上收益列的个券表（96 行）。"""
    from reits_weekly.compute import returns

    raw = adapter.quotes_weekly(week)
    return returns.attach_returns(boards.apply(raw))


@pytest.fixture(scope="session")
def facts(adapter, boards, week, quotes):
    """2026-W45 期的完整事实库。"""
    from reits_weekly.compute.aggregate import build_facts

    return build_facts(
        quotes,
        adapter.turnover_weekly(week),
        week,
        CASE_ID,
        adapter.meta.raw_hash,
        boards,
        adapter.meta.as_dict(),
    )
