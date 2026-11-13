"""问题台账测试。

核心命题：**本轮没提到的问题，不等于已经解决。**
如果台账只是每轮覆盖，修订循环就会退化成"只修当轮被点名的问题"。
"""

from __future__ import annotations

from reits_weekly.verify.findings import FindingLedger


def test_new_finding_is_open():
    lg = FindingLedger()
    lg.begin_round()
    lg.record("G-NUM-01", ["[1.3] 5.8 无法回溯"])
    assert len(lg.open()) == 1
    assert lg.open()[0].gate == "G-NUM-01"


def test_finding_id_is_stable_across_rounds():
    lg = FindingLedger()
    lg.begin_round()
    lg.record("G-NUM-01", ["问题A"])
    fid = lg.open()[0].id
    lg.begin_round()
    lg.record("G-NUM-01", ["问题A"])
    assert lg.open()[0].id == fid
    assert lg.open()[0].last_seen_round == 2


def test_disappeared_finding_is_closed():
    lg = FindingLedger()
    lg.begin_round()
    lg.record("G-NUM-01", ["问题A"])
    lg.begin_round()
    lg.record("G-NUM-01", [])          # 本轮未出现
    assert len(lg.open()) == 0
    assert len(lg.closed()) == 1
    assert lg.closed()[0].closed_round == 2


def test_partial_fix_keeps_others_open():
    """修掉一个、留下一个时，留下的必须仍然 open。"""
    lg = FindingLedger()
    lg.begin_round()
    lg.record("G-NUM-01", ["问题A", "问题B"])
    lg.begin_round()
    lg.record("G-NUM-01", ["问题B"])
    texts = [f.text for f in lg.open()]
    assert texts == ["问题B"]


def test_reopened_finding_is_flagged():
    """修好又复现，说明上次的修订只是掩盖症状。"""
    lg = FindingLedger()
    lg.begin_round()
    lg.record("G-STYLE-01", ["问题X"])
    lg.begin_round()
    lg.record("G-STYLE-01", [])
    lg.begin_round()
    lg.record("G-STYLE-01", ["问题X"])
    assert len(lg.reopened()) == 1
    assert lg.reopened()[0].reopen_count == 1


def test_persist_and_reload(tmp_path):
    p = tmp_path / "findings.json"
    lg = FindingLedger()
    lg.begin_round()
    lg.record("G-PIT-01", ["未来数据"])
    lg.save(p)

    back = FindingLedger.load(p)
    assert back.round == 1
    assert [f.text for f in back.open()] == ["未来数据"]


def test_missing_file_gives_empty_ledger(tmp_path):
    lg = FindingLedger.load(tmp_path / "nope.json")
    assert lg.round == 0
    assert lg.open() == []


def test_summary_shape():
    lg = FindingLedger()
    lg.begin_round()
    lg.record("G-NUM-01", ["A"])
    s = lg.summary()
    assert s["round"] == 1
    assert s["open"] == 1
    assert "A" in s["open_texts"]
