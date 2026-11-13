"""门禁自身的测试。

门禁是"拦错的机制"，它自己必须是对的：既不能漏放（假阴性），
也不能把正确内容误判为错误（假阳性，会让人逐渐忽略告警）。
以下用例两者都覆盖。
"""

from __future__ import annotations

import pandas as pd
import pytest

from reits_weekly.facts import FactsBundle
from reits_weekly.verify import gates


@pytest.fixture
def bundle():
    fb = FactsBundle("t", "h")
    fb.add("turnover.total", 21.93, unit="亿元")
    fb.add("turnover.rate", 0.327, unit="%", decimals=3)
    fb.add("breadth.n", 94, unit="只")
    fb.add("breadth.up", 41, unit="只")
    fb.add("breadth.down", 50, unit="只")
    fb.add("breadth.flat", 3, unit="只")
    for b in ("产业园区", "水利设施"):
        fb.add("board.n", 20 if b == "产业园区" else 74, unit="只", params={"board": b})
        fb.add("turnover.board", 3.0 if b == "产业园区" else 18.93,
                unit="亿元", params={"board": b})
    fb.add("pnav.n_premium", 56, unit="只")
    fb.add("pnav.n_discount", 38, unit="只")
    fb.add("pnav.board.n", 94, unit="只", params={"board": "全部"})
    fb.add("market.eq_return", -0.75, unit="%")
    fb.add("board.eq_return", -2.33, unit="%", params={"board": "产业园区"})
    fb.add("pnav.median", 1.055, unit="ratio", decimals=3)
    return fb


# ------------------------------------------------------------------ 数字审计


def test_audit_passes_on_known_numbers(bundle):
    sections = {"0.1": "成交额 21.93 亿元，换手率 0.327%，样本 94 只。"}
    r = gates.numeric_audit(sections, bundle)
    assert r.ok, r.samples


def test_audit_catches_fabricated_number(bundle):
    """模型自己算出来的数字必须被拦下。"""
    sections = {"1.3": "本周首尾相差 5.8 个百分点。"}
    r = gates.numeric_audit(sections, bundle)
    assert not r.ok
    assert r.failed == 1
    assert "5.8" in r.samples[0]


def test_audit_allows_term_names(bundle):
    """期限名称、指数名、章节号不属于待审计数字。"""
    sections = {"2.1": "10年期国债与沪深 300 同步走弱，详见 1.3 节。"}
    r = gates.numeric_audit(sections, bundle)
    assert r.ok, r.samples


def test_audit_normalizes_units(bundle):
    """事实库里存 21.93，正文写 '21.93 亿元' 应视为一致。"""
    r = gates.numeric_audit({"x": "全市场 21.93 亿元"}, bundle)
    assert r.ok


# ------------------------------------------------------------------ 勾稽


def test_crossfoot_passes(bundle):
    assert gates.crossfoot(bundle).ok


def test_crossfoot_catches_imbalance():
    fb = FactsBundle("t", "h")
    fb.add("breadth.n", 94, unit="只")
    fb.add("breadth.up", 41, unit="只")
    fb.add("breadth.down", 50, unit="只")
    fb.add("breadth.flat", 1, unit="只")   # 41+50+1=92 ≠ 94
    r = gates.crossfoot(fb)
    assert not r.ok
    assert "≠" in r.detail


def test_crossfoot_catches_board_sum():
    fb = FactsBundle("t", "h")
    fb.add("breadth.n", 94, unit="只")
    fb.add("board.n", 90, unit="只", params={"board": "A"})
    r = gates.crossfoot(fb)
    assert not r.ok


# ------------------------------------------------------------------ 一致性


def test_board_consistency_detects_duplicate_assignment():
    """同一代码出现两个板块 —— 2026-W45 期事故的复现。"""
    df = pd.DataFrame(
        [
            {"code": "508087", "board": "能源基础设施"},
            {"code": "508087", "board": "水利设施"},
            {"code": "180101", "board": "产业园区"},
        ]
    )
    r = gates.board_consistency(df)
    assert not r.ok
    assert "508087" in r.detail


def test_board_consistency_passes_on_clean_data():
    df = pd.DataFrame([{"code": "000001", "board": "A"}, {"code": "000002", "board": "B"}])
    assert gates.board_consistency(df).ok


# ------------------------------------------------------------------ 时效


def test_pit_flags_future_data():
    fb = FactsBundle("t", "h")
    fb.add("x", 1.0, source={"source_asof": "2026-11-20"})
    r = gates.point_in_time(fb, "2026-11-08T23:59:59+08:00")
    assert not r.ok


def test_pit_passes_when_within_cutoff():
    fb = FactsBundle("t", "h")
    fb.add("x", 1.0, source={"source_asof": "2026-11-06"})
    assert gates.point_in_time(fb, "2026-11-08T23:59:59+08:00").ok


# ------------------------------------------------------------------ 凭据


def test_secret_scan_catches_token(tmp_path):
    (tmp_path / "cfg.py").write_text('api_key = "sk-abcdefghijklmnopqrstuvwxyz123456"',
                                     encoding="utf-8")
    r = gates.secret_scan(tmp_path)
    assert not r.ok


def test_secret_scan_ignores_clean_files(tmp_path):
    (tmp_path / "ok.py").write_text("value = 1\n", encoding="utf-8")
    assert gates.secret_scan(tmp_path).ok


def test_secret_scan_skips_venv(tmp_path):
    venv = tmp_path / ".venv" / "lib"
    venv.mkdir(parents=True)
    (venv / "leak.py").write_text('api_key = "sk-abcdefghijklmnopqrstuvwxyz123456"',
                                  encoding="utf-8")
    assert gates.secret_scan(tmp_path).ok


# ------------------------------------------------------------------ 结构


def test_structure_detects_missing_section():
    sections = {s: "内容" for s in gates.REQUIRED_SECTIONS if s != "2.4"}
    r = gates.structure_check(sections)
    assert not r.ok
    assert "2.4" in r.detail


def test_structure_detects_repeated_risk_notice():
    sections = {s: "内容" for s in gates.REQUIRED_SECTIONS}
    sections["0.3"] = "风险提示：以下为风险。"
    sections["risk"] = "风险提示：底层资产风险。"
    r = gates.structure_check(sections)
    assert not r.ok
