"""报告装配 —— 决定"哪一节后面接哪张表、哪张图"。

章节顺序与块的位置写在这里而不是散落在各处，是因为它同时是
``verify/lint.py`` 检查结构完整性的依据（章节是否齐全、顺序是否对）。
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
from docx import Document

from ..compute import valuation
from ..facts import FactsBundle
from ..formatting import fmt_pct, fmt_ratio
from ..pipeline import CaseResult
from . import docx_writer as W
from . import tables as T

# 章节骨架：(级别, 标识, 标题)
OUTLINE = [
    ("chapter", "abs", "摘要：本周判断与配置关注"),
    ("section", "0.1", "0.1 市场核心判断"),
    ("section", "0.2", "0.2 基本面与定价判断"),
    ("section", "0.3", "0.3 配置关注与观点变化"),
    ("chapter", "ch1", "第一章 市场表现——整体收益、板块分化与交易变化"),
    ("section", "1.1", "1.1 整体收益与跨资产表现"),
    ("section", "1.2", "1.2 板块表现与市场全景"),
    ("section", "1.3", "1.3 个券表现与异常识别"),
    ("section", "1.4", "1.4 成交活跃度与流动性"),
    ("section", "1.5", "1.5 折溢价变化"),
    ("chapter", "ch2", "第二章 定价环境——利率变化与近期供需安排"),
    ("section", "2.1", "2.1 利率与资金价格"),
    ("section", "2.2", "2.2 首发与扩募供给安排"),
    ("section", "2.3", "2.3 解禁与份额变化"),
    ("section", "2.4", "2.4 已披露的持有人行为"),
    ("section", "2.5", "2.5 外部条件的综合判断"),
    ("chapter", "risk", "风险提示"),
]

SECTION_IDS = [sid for lvl, sid, _ in OUTLINE if lvl == "section"] + ["risk"]


def load_drafts(path: Path) -> dict[str, str]:
    """草稿文件用 ``## <sid>`` 分节。

    单文件而非每节一个文件，是为了让"同一期的叙述"能被一次性读完 ——
    分章起草容易写出彼此重复、口径不一的段落，审稿时需要看到全文。
    """
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    parts = re.split(r"^##\s+(\S+)\s*$", text, flags=re.M)
    drafts: dict[str, str] = {}
    for i in range(1, len(parts) - 1, 2):
        drafts[parts[i].strip()] = parts[i + 1].strip()
    return drafts


_SNAPSHOT_LABELS = {
    "932047": "中证REITs全收益指数",
    "932006": "中证REITs（收盘）指数",
    "H00300": "沪深300全收益指数",
    "H00922": "中证红利全收益指数",
    "CBA00201": "中债综合财富指数",
}

REITS_INDEX_CODES = ["932047", "932006"]
CROSS_ASSET_CODES = ["932047", "H00300", "H00922", "CBA00201"]


def _index_rows(facts: FactsBundle, codes: list[str]) -> list[tuple[str, str, str, str]]:
    """按代码取当期点位、周涨跌、年初至今，拼成表格行。"""
    def val(metric: str, code: str) -> str:
        items = [f for f in facts.by_metric(metric) if f.params.get("code") == code]
        return items[0].display if items else "—"

    return [
        (_SNAPSHOT_LABELS.get(code, code), val("index.close", code),
         val("index.wow", code), val("index.ytd", code))
        for code in codes
    ]


def build_report(
    result: CaseResult,
    drafts: dict[str, str],
    out_path: Path,
    charts_dir: Path,
    *,
    boards_order: list[str],
    source_label: str = "Choice",
) -> Path:
    """按 OUTLINE 装配整份报告。草稿缺节时写入占位提示，不抛错 —— 便于分段调试。"""
    doc = W._setup_document()
    label = W.period_label(result.week.start, result.week.end)
    W.setup_footer(doc, label)
    W.add_title(doc, f"公募REITs周报（{label}）")

    quotes = result.quotes
    comparable = quotes[quotes["close_prev"].notna()]
    pv = valuation.pnav_summary(comparable)
    by_board = valuation.pnav_by_board(comparable)

    def body_of(sid: str) -> None:
        text = drafts.get(sid, "").strip()
        if not text:
            W.add_body(doc, f"（本节草稿缺失：{sid}）")
            return
        for para in W.split_paragraphs(text):
            W.add_body(doc, para)

    for level, sid, title in OUTLINE:
        if level == "chapter":
            W.add_chapter(doc, title)
            continue

        W.add_section_heading(doc, title)
        body_of(sid)

        # ---- 各节的表与图 ----
        if sid == "1.1":
            T.index_table(doc, _index_rows(result.facts, REITS_INDEX_CODES))
            W.add_source_note(doc, source_label)
            W.add_chart(doc, Path(charts_dir) / "chart_reits_index.png")
            T.index_table(doc, _index_rows(result.facts, CROSS_ASSET_CODES))
            W.add_source_note(doc, source_label)
            W.add_chart(doc, Path(charts_dir) / "chart_cross_asset.png")
        elif sid == "1.2":
            T.quotes_table(doc, quotes, boards_order)
            W.add_source_note(doc, f"{source_label}；收盘价为前复权价格口径")
        elif sid == "1.3":
            pass
        elif sid == "1.4":
            W.add_chart(doc, Path(charts_dir) / "chart_board_turnover.png")
            W.add_chart(doc, Path(charts_dir) / "chart_board_turnover_rate.png")
            W.add_source_note(doc, source_label)
        elif sid == "1.5":
            T.pnav_table(
                doc,
                by_board,
                {
                    "median": pv.median,
                    "discount_pct": pv.median_discount_pct,
                    "weighted": pv.weighted,
                    "n_premium": pv.n_premium,
                    "n_discount": pv.n_discount,
                },
            )
            W.add_source_note(doc, source_label)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    return out_path
