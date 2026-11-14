"""产物可复现性测试。

"同一输入重跑必然得到同一结果"是这个项目最重要的性质之一——没有它，
基线比对、版本回滚、问题台账都失去意义。

容易踩的坑：抓取时刻（retrieved_at）如果写进 facts.json，文件就会每次都变，
数值没变但哈希变了，于是"可复现"只能靠嘴说。这里把它锁住。
"""

from __future__ import annotations

import hashlib
import time

import pytest

from reits_weekly import pipeline


def _digest(fb) -> str:
    return hashlib.sha256(fb.to_json().encode("utf-8")).hexdigest()


def test_facts_json_identical_across_runs(adapter, boards, week):
    """连跑两次，事实库文件的 sha256 必须相同。"""
    a = pipeline.prepare(adapter, week, boards, "demo-2026-W45").facts
    time.sleep(0.01)                      # 确保两次的 retrieved_at 必然不同
    b = pipeline.prepare(adapter, week, boards, "demo-2026-W45").facts
    assert _digest(a) == _digest(b)


def test_retrieved_at_not_embedded_in_facts(adapter, boards, week):
    """抓取时刻属于运行过程，不应出现在 facts.json 里。"""
    fb = pipeline.prepare(adapter, week, boards, "demo-2026-W45").facts
    text = fb.to_json()
    assert "retrieved_at" not in text
    assert "raw_hash" in text             # 溯源凭证仍保留


def test_fact_ids_stable(adapter, boards, week):
    a = pipeline.prepare(adapter, week, boards, "demo-2026-W45").facts
    b = pipeline.prepare(adapter, week, boards, "demo-2026-W45").facts
    assert [f.id for f in a] == [f.id for f in b]


def test_provenance_still_records_timing(tmp_path, adapter, boards, week):
    """时间戳移到 provenance.json —— 仍可追溯，只是不污染事实库。"""
    from reits_weekly.pipeline import CasePaths

    res = pipeline.prepare(adapter, week, boards, "demo-2026-W45")
    written = pipeline.write_artifacts(res, CasePaths(tmp_path, "demo-2026-W45"))
    prov = written["provenance"].read_text(encoding="utf-8")
    assert "retrieved_at" in prov
    assert "raw_hash" in prov
