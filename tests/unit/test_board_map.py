"""板块映射测试 —— 防止分类漂移。

2026-W45 期的真实事故：同一只基金（508087）在第一章算在能源、在 1.5 算在水利，
原因是两处分别沿用了不同数据源的原始分类。以下用例把修复方式固定下来。
"""

from __future__ import annotations

import pandas as pd
import pytest

from reits_weekly.normalize.board_map import (
    BoardDictionary,
    UnknownBoardError,
    UnknownFundError,
)


def test_loads_ten_boards(boards):
    assert len(boards.boards) == 10
    assert boards.ordered_names()[0] == "交通基础设施"
    assert boards.ordered_names()[-1] == "商业不动产"


def test_alias_resolution(boards):
    assert boards.canonical("高速公路") == "交通基础设施"
    assert boards.canonical("产业园") == "产业园区"
    assert boards.canonical("保障房") == "保障性租赁住房"
    assert boards.canonical("市政环保") == "生态环保"
    # 规范名本身也应幂等
    assert boards.canonical("产业园区") == "产业园区"


def test_unknown_board_raises(boards):
    with pytest.raises(UnknownBoardError):
        boards.canonical("不存在的板块")


def test_override_is_recorded_and_applied(boards):
    """508087 的归类决定必须显式记录在 overrides 里，并被 board_for_code 采用。

    登记表本身存的是最终归类；override 的作用是让这个决定**在登记表被
    重新生成（例如换一份终端导出）后依然有效**，而不是被数据源悄悄改回去。
    """
    assert boards.overrides["508087"] == "能源基础设施"
    assert boards.board_for_code("508087") == "能源基础设施"
    # override 必须写明理由与决定人，否则无法回溯
    import yaml
    from pathlib import Path
    raw = yaml.safe_load((Path(__file__).resolve().parents[2] / "config" / "boards.yaml")
                         .read_text(encoding="utf-8"))
    ov = [o for o in raw["overrides"] if str(o["code"]) == "508087"][0]
    assert ov["reason"] and ov["decided_by"] and ov["decided_at"]


def test_conflict_detected(boards, quotes):
    """原始分类与最终归类不一致时必须被检出，且只检出这一条。"""
    raw = quotes.rename(columns={"board": "board_resolved"})
    raw["board_raw"] = raw["board_resolved"]
    raw.loc[raw["code"] == "508087", "board_raw"] = "水利设施"
    conflicts = boards.conflicts(raw)
    codes = [c["code"] for c in conflicts]
    assert codes == ["508087"]
    assert conflicts[0]["resolved"] == "能源基础设施"


def test_apply_fills_board_and_asset_class(boards, adapter, week):
    df = adapter.quotes_weekly(week)
    out = boards.apply(df)
    assert out["board"].notna().all()
    assert set(out["board"]) <= set(boards.boards)
    assert (out.loc[out["board"] == "产业园区", "asset_class"] == "产权类").all()
    assert (out.loc[out["board"] == "能源基础设施", "asset_class"] == "特许经营权类").all()


def test_apply_raises_when_neither_code_nor_board_known(boards):
    """代码与板块名都无解时必须报错，不能静默归入"其他"。"""
    df = pd.DataFrame([{"code": "999999", "board_raw": ""}])
    with pytest.raises(UnknownFundError):
        boards.apply(df)


def test_apply_falls_back_to_board_raw(boards):
    """新代码但板块名可识别时，允许按板块名归入（新增标的的常见情形）。"""
    df = pd.DataFrame([{"code": "999999", "board_raw": "产业园区"}])
    out = boards.apply(df)
    assert out["board"].iloc[0] == "产业园区"


def test_board_sample_counts(quotes):
    """可比样本的板块数须与底稿表2 一致（508087 归能源后：能源 12、水利 2）。"""
    comparable = quotes[quotes["close_prev"].notna()]
    counts = comparable["board"].value_counts().to_dict()
    assert counts["产业园区"] == 20
    assert counts["交通基础设施"] == 15
    assert counts["能源基础设施"] == 12
    assert counts["水利设施"] == 2
    assert sum(counts.values()) == 94
