"""报告装配 —— 章节顺序与表图位置由 ``config/sections.yaml`` 决定。

早期版本把章节骨架硬编码在本文件的 ``OUTLINE`` 里，改章节要改代码。
现在改为配置驱动：增删章节、调整某张表放在哪一节，都只需要改 YAML。

块（table / chart）通过 ``_BLOCKS`` 注册表按名字查找。配置里写了未注册的块名会
直接报错，而不是静默跳过——静默跳过会让人以为表已经生成了。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

from ..compute import valuation
from ..facts import FactsBundle
from ..pipeline import CaseResult
from . import docx_writer as W
from . import tables as T

_SNAPSHOT_LABELS = {
    "932047": "中证REITs全收益指数",
    "932006": "中证REITs（收盘）指数",
    "H00300": "沪深300全收益指数",
    "H00922": "中证红利全收益指数",
    "CBA00201": "中债综合财富指数",
}

REITS_INDEX_CODES = ["932047", "932006"]
CROSS_ASSET_CODES = ["932047", "H00300", "H00922", "CBA00201"]


# --------------------------------------------------------------------- 配置


@dataclass
class Outline:
    chapters: list[dict]
    source_notes: dict[str, str]

    @property
    def section_ids(self) -> list[str]:
        return [c["id"] for c in self.chapters if c.get("level") == "section"]

    @property
    def all_ids(self) -> list[str]:
        return [c["id"] for c in self.chapters]


def load_outline(config_dir: Path | str = Path("config")) -> Outline:
    path = Path(config_dir) / "sections.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    chapters = raw["chapters"]
    for c in chapters:
        if c.get("level") not in ("chapter", "section"):
            raise ValueError(f"未知层级: {c.get('level')} （章节 {c.get('id')}）")
    return Outline(chapters=chapters, source_notes=raw.get("source_notes") or {})


_SECTION_IDS: list[str] = []      # 兼容旧调用，由 build_report 首次运行时填充


def section_ids(config_dir: Path | str = Path("config")) -> list[str]:
    return load_outline(config_dir).section_ids


# --------------------------------------------------------------------- 草稿


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


# --------------------------------------------------------------------- 块


def _index_rows(facts: FactsBundle, codes: list[str]) -> list[tuple[str, str, str, str]]:
    def val(metric: str, code: str) -> str:
        items = [f for f in facts.by_metric(metric) if f.params.get("code") == code]
        return items[0].display if items else "—"

    return [
        (_SNAPSHOT_LABELS.get(code, code), val("index.close", code),
         val("index.wow", code), val("index.ytd", code))
        for code in codes
    ]


@dataclass
class _Ctx:
    doc: object
    result: CaseResult
    charts_dir: Path
    boards_order: list[str]
    source_notes: dict[str, str]

    @property
    def quotes(self) -> pd.DataFrame:
        return self.result.quotes

    @property
    def pending(self) -> pd.DataFrame | None:
        return getattr(self.result, "pending", None)

    @property
    def comparable(self) -> pd.DataFrame:
        return self.quotes[self.quotes["close_prev"].notna()]

    def note(self, block: str) -> None:
        text = self.source_notes.get(block)
        if text:
            W.add_source_note(self.doc, text)


def _b_index_reits(ctx: _Ctx) -> None:
    T.index_table(ctx.doc, _index_rows(ctx.result.facts, REITS_INDEX_CODES))
    ctx.note("index_table_reits")


def _b_chart_reits(ctx: _Ctx) -> None:
    W.add_chart(ctx.doc, ctx.charts_dir / "chart_reits_index.png")
    ctx.note("chart_reits_index")


def _b_index_cross(ctx: _Ctx) -> None:
    T.index_table(ctx.doc, _index_rows(ctx.result.facts, CROSS_ASSET_CODES))
    ctx.note("index_table_cross")


def _b_chart_cross(ctx: _Ctx) -> None:
    W.add_chart(ctx.doc, ctx.charts_dir / "chart_cross_asset.png")
    ctx.note("chart_cross_asset")


def _b_quotes(ctx: _Ctx) -> None:
    T.quotes_table(ctx.doc, ctx.quotes, ctx.boards_order)
    ctx.note("quotes_table")


def _b_chart_turnover(ctx: _Ctx) -> None:
    W.add_chart(ctx.doc, ctx.charts_dir / "chart_board_turnover.png")
    ctx.note("chart_board_turnover")


def _b_chart_turnover_rate(ctx: _Ctx) -> None:
    W.add_chart(ctx.doc, ctx.charts_dir / "chart_board_turnover_rate.png")
    ctx.note("chart_board_turnover_rate")


def _b_pnav(ctx: _Ctx) -> None:
    pv = valuation.pnav_summary(ctx.comparable)
    by_board = valuation.pnav_by_board(ctx.comparable)
    T.pnav_table(
        ctx.doc,
        by_board,
        {
            "median": pv.median,
            "discount_pct": pv.median_discount_pct,
            "weighted": pv.weighted,
            "n_premium": pv.n_premium,
            "n_discount": pv.n_discount,
        },
    )
    ctx.note("pnav_table")


def _b_pending(ctx: _Ctx) -> None:
    if ctx.pending is None or not len(ctx.pending):
        return
    T.pending_table(ctx.doc, ctx.pending)
    ctx.note("pending_table")


_BLOCKS = {
    "index_table_reits": _b_index_reits,
    "chart_reits_index": _b_chart_reits,
    "index_table_cross": _b_index_cross,
    "chart_cross_asset": _b_chart_cross,
    "quotes_table": _b_quotes,
    "chart_board_turnover": _b_chart_turnover,
    "chart_board_turnover_rate": _b_chart_turnover_rate,
    "pnav_table": _b_pnav,
    "pending_table": _b_pending,
}


# --------------------------------------------------------------------- 装配


def build_report(
    result: CaseResult,
    drafts: dict[str, str],
    out_path: Path,
    charts_dir: Path,
    *,
    boards_order: list[str],
    config_dir: Path | str = Path("config"),
) -> Path:
    """按 ``config/sections.yaml`` 装配整份报告。

    草稿缺节时写入占位提示而非抛错，便于分段调试；正式出稿前由
    ``G-STYLE-01`` 检查章节是否齐全。
    """
    outline = load_outline(config_dir)
    doc = W._setup_document()
    label = W.period_label(result.week.start, result.week.end)
    W.setup_footer(doc, label)
    W.add_title(doc, f"公募REITs周报（{label}）")

    ctx = _Ctx(
        doc=doc,
        result=result,
        charts_dir=Path(charts_dir),
        boards_order=boards_order,
        source_notes=outline.source_notes,
    )

    def body_of(sid: str) -> None:
        text = drafts.get(sid, "").strip()
        if not text:
            W.add_body(doc, f"（本节草稿缺失：{sid}）")
            return
        for para in W.split_paragraphs(text):
            W.add_body(doc, para)

    for chapter in outline.chapters:
        if chapter["level"] == "chapter":
            W.add_chapter(doc, chapter["title"])
            continue

        sid = chapter["id"]
        W.add_section_heading(doc, chapter["title"])
        if chapter.get("body", True):
            body_of(sid)

        for block in chapter.get("blocks") or []:
            fn = _BLOCKS.get(block)
            if fn is None:
                raise KeyError(
                    f"sections.yaml 中 {sid} 引用了未注册的块 {block!r}；"
                    f"可用块: {sorted(_BLOCKS)}"
                )
            fn(ctx)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    return out_path
