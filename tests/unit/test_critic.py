"""Critic 评审测试。

评审规则本身也需要被测试：一条只会扣分、从不放行的规则会把流程卡死；
一条什么都放行的规则等于没有。两类都要防。
"""

from __future__ import annotations

import pytest

from reits_weekly.draft import critic
from reits_weekly.facts import FactsBundle


@pytest.fixture
def bundle():
    fb = FactsBundle("t", "h")
    fb.add("pnav.median", 1.055, unit="ratio", decimals=3)
    return fb


def test_good_section_scores_high(bundle):
    text = (
        "本周板块等权收益 {{x}}，按本报告统一口径计算。我们认为这说明分化在加剧，"
        "但单周数据可能不足以支持趋势判断，需要观察后续两周。"
    ).replace("{{x}}", "为 -2.33%")
    r = critic.review({"0.1": text}, bundle, opinions={"judgments": [1]})
    sec = r.sections[0]
    assert sec.mean >= 4.0, sec.issues


def test_missing_number_is_penalised(bundle):
    r = critic.review({"0.1": "本周市场继续分化，我们判断这一趋势会延续，但需观察。"}, bundle)
    assert r.sections[0].logic < 5
    assert any("无任何数据支撑" in i for i in r.sections[0].issues)


def test_absolute_language_is_penalised(bundle):
    text = "本周成交 21.93 亿元，我们判断后续必然上涨，一定会延续。"
    r = critic.review({"0.1": text}, bundle)
    assert r.sections[0].restraint <= 3
    assert any("绝对化" in i for i in r.sections[0].issues)


def test_caliber_required_for_sensitive_metrics(bundle):
    text = "本周 94 只个券中 41 只上涨，P/NAV 中位数为 1.055。"
    r = critic.review({"0.1": text}, bundle)
    assert any("未声明口径" in i for i in r.sections[0].issues)


def test_caliber_satisfied_when_declared(bundle):
    text = "按本报告统一口径（不复权加分红、板块内等权），P/NAV 中位数为 1.055。"
    r = critic.review({"0.1": text}, bundle)
    assert not any("未声明口径" in i for i in r.sections[0].issues)


def test_continuity_only_scored_on_judgment_sections(bundle):
    """描述性章节不该因"没回顾上期观点"被扣分。"""
    text = "本周成交额 21.93 亿元，环比 -9.1%。"
    r = critic.review({"1.4": text}, bundle, opinions={"judgments": [1]})
    assert r.sections[0].continuity == 5


def test_continuity_required_on_judgment_section(bundle):
    text = "我们判断市场仍将横盘，成交额 21.93 亿元。"
    r = critic.review({"2.5": text}, bundle, opinions={"judgments": [1]})
    assert r.sections[0].continuity < 5


def test_table_only_section_is_skipped(bundle):
    r = critic.review({"1.2": ""}, bundle)
    assert r.sections == []


def test_verdict_revise_when_low(bundle):
    r = critic.review({"0.1": "好。"}, bundle)
    assert r.verdict == "revise"


def test_verdict_accept_when_clean(bundle):
    text = (
        "本周 94 只可比样本中 41 只上涨。按统一口径（板块内等权）计算，"
        "产业园区收益为 -2.33%。我们维持上期判断，但若出租率转正则需要修正。"
    )
    turnover = (
        "本周全市场成交额 21.93 亿元，环比 -9.1%；日均成交 4.39 亿元。"
        "按流通市值加权计算的日均换手率为 0.327%。成交缩量与换手率下行同时出现，"
        "说明增量资金入场意愿偏弱，市场延续存量博弈格局。"
    )
    r = critic.review({"0.1": text, "1.4": turnover}, bundle,
                      opinions={"judgments": [1]})
    assert r.verdict == "accept", r.high_issues


def test_load_opinions_missing_file_returns_empty(tmp_path):
    assert critic.load_opinions(tmp_path / "nope.yaml") == {}


def test_load_opinions_reads_yaml(tmp_path):
    p = tmp_path / "opinions.yaml"
    p.write_text("as_of: '2026-11-06'\njudgments:\n  - id: J1\n", encoding="utf-8")
    data = critic.load_opinions(p)
    assert data["judgments"][0]["id"] == "J1"
