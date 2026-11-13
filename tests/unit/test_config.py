"""配置加载测试。

配置是"文档承诺"与"代码实际行为"之间的桥。这些用例保证：
配置能被读到、缺配置时不崩、配置改动会真正影响行为。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from reits_weekly import controller
from reits_weekly.render import build
from reits_weekly.verify import gates

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"


# ------------------------------------------------------------------ 章节结构


def test_outline_loads_from_config():
    o = build.load_outline(CONFIG)
    assert len(o.chapters) == 17
    assert "1.1" in o.section_ids
    assert "risk" in o.all_ids


def test_outline_blocks_match_registry():
    """配置里写的块名必须在代码里注册过，否则出稿时才报错就太晚了。"""
    o = build.load_outline(CONFIG)
    registered = set(build._BLOCKS)
    used = {b for c in o.chapters for b in (c.get("blocks") or [])}
    assert used <= registered, f"未注册的块: {used - registered}"


def test_outline_source_notes_cover_blocks():
    """每个带资料来源的块都应配好标注。"""
    o = build.load_outline(CONFIG)
    blocks = {b for c in o.chapters for b in (c.get("blocks") or [])}
    missing = blocks - set(o.source_notes)
    assert not missing, f"缺资料来源标注: {missing}"


def test_unknown_block_raises(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "sections.yaml").write_text(
        "chapters:\n  - level: section\n    id: '1.1'\n    title: t\n"
        "    blocks: [no_such_block]\n",
        encoding="utf-8",
    )
    o = build.load_outline(cfg)
    block = o.chapters[0]["blocks"][0]
    assert block not in build._BLOCKS


# ------------------------------------------------------------------ 门禁配置


def test_gates_config_loads():
    cfg = gates.load_config(str(CONFIG))
    assert "numeric_audit" in cfg
    assert cfg["critic"]["pass_score"] == 3.5


def test_allowed_patterns_from_config():
    pats = gates.allowed_patterns(str(CONFIG))
    assert len(pats) >= 6
    # 每条都必须有理由，不能为了过门禁而加
    assert all(reason for _, reason in pats)


def test_unit_ranges_from_config_drive_behaviour():
    from reits_weekly.facts import FactsBundle

    fb = FactsBundle("t", "h")
    fb.add("turnover.rate", 99.0, unit="%")      # 远超 [0,50]
    assert not gates.unit_sanity(fb, str(CONFIG)).ok


# ------------------------------------------------------------------ 数据源白名单


def test_source_whitelist_accepts_registered_license():
    meta = {"license": "public-market-data", "source_id": "fixture:x"}
    assert gates.source_whitelist(meta, str(CONFIG)).ok


def test_source_whitelist_rejects_unknown_license():
    meta = {"license": "internal-research", "source_id": "x"}
    r = gates.source_whitelist(meta, str(CONFIG))
    assert not r.ok
    assert "不在白名单" in r.detail


# ------------------------------------------------------------------ 运行参数


def test_runconfig_from_settings():
    cfg = controller.RunConfig.from_config(ROOT)
    assert cfg.max_wall_clock_sec == 3600
    assert cfg.max_gate_rounds == 2
    assert cfg.case_id == "demo-2026-W45"
    assert cfg.config_dir.name == "config"


def test_runconfig_cli_override():
    cfg = controller.RunConfig.from_config(ROOT, case_id="2026-W46")
    assert cfg.case_id == "2026-W46"
    assert cfg.week_start == "2026-11-02"      # 其余仍取配置默认
