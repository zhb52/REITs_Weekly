"""五张数据表的构造器。

版式参数从样张 docx 的 XML 里读出（字号、行高、边框、底纹），不是估的：

* 个券表：11 列固定布局、表头行高 500 twips / 宋体 7.5pt 加粗、
  数据行高 260 twips，首列按板块 ``vMerge`` 合并
* P/NAV 表：表头底纹 ``F7F7F7``、单元格边距 120/180 twips、末行"全市场"加粗
* 指数表与跨资产表：``Table Grid``、宽度 5000 pct、涨跌幅带正负号

样张的个券表缺 ``w:tblHeader``，96 行跨页后表头不重复，阅读体验很差。
本模块生成时补上该标记 —— 这是对样张的修正，不是照抄。
"""

from __future__ import annotations

import pandas as pd
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

from ..formatting import fmt_num, fmt_pct, fmt_ratio

FONT_CN = "宋体"


# --------------------------------------------------------------------- 底层


def _set_cell_shading(cell, hex_fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    tc_pr.append(shd)


def _set_repeat_header(row) -> None:
    """标记表头行跨页重复。"""
    tr_pr = row._tr.get_or_add_trPr()
    header = OxmlElement("w:tblHeader")
    header.set(qn("w:val"), "true")
    tr_pr.append(header)


def _set_row_height(row, twips: int) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    height = OxmlElement("w:trHeight")
    height.set(qn("w:val"), str(twips))
    height.set(qn("w:hRule"), "atLeast")
    tr_pr.append(height)


def _set_cell_margins(cell, top: int = 15, bottom: int = 15, left: int = 15, right: int = 15) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    mar = OxmlElement("w:tcMar")
    for tag, val in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        node = OxmlElement(f"w:{tag}")
        node.set(qn("w:w"), str(val))
        node.set(qn("w:type"), "dxa")
        mar.append(node)
    tc_pr.append(mar)


def _fixed_layout(table) -> None:
    tbl_pr = table._tbl.tblPr
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tbl_pr.append(layout)


def _write_cell(cell, text: str, *, bold: bool = False, size_pt: float = 9.0,
                align=WD_ALIGN_PARAGRAPH.CENTER, font: str = FONT_CN) -> None:
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = align
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 1.0
    run = p.add_run(text)
    run.bold = bold
    run.font.size = Pt(size_pt)
    run.font.name = font
    run._element.rPr.rFonts.set(qn("w:eastAsia"), font)


def _set_col_widths(table, pcts: list[float]) -> None:
    """按百分比设置列宽。

    Word 的百分比宽度单位是 1/50 个百分点：100% = 5000。
    必须逐格写 ``tcW``，只设 ``tblW`` 在固定布局下不会生效。
    """
    tbl_pr = table._tbl.tblPr
    for el in tbl_pr.findall(qn("w:tblW")):
        tbl_pr.remove(el)
    tbl_w = OxmlElement("w:tblW")
    tbl_w.set(qn("w:w"), "5000")
    tbl_w.set(qn("w:type"), "pct")
    tbl_pr.append(tbl_w)

    for row in table.rows:
        for idx, pct in enumerate(pcts):
            if idx >= len(row.cells):
                continue
            cell = row.cells[idx]
            tc_pr = cell._tc.get_or_add_tcPr()
            for el in tc_pr.findall(qn("w:tcW")):
                tc_pr.remove(el)
            tc_w = OxmlElement("w:tcW")
            tc_w.set(qn("w:w"), str(int(round(pct * 5000))))
            tc_w.set(qn("w:type"), "pct")
            tc_pr.append(tc_w)


# --------------------------------------------------------------------- 表1/2


def index_table(doc, rows: list[tuple[str, str, str, str]]) -> None:
    """指数/跨资产表现表：4 列，首列表头留空（与样张一致）。"""
    table = doc.add_table(rows=len(rows) + 1, cols=4)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_col_widths(table, [0.34, 0.22, 0.22, 0.22])

    headers = ["", "收盘价", "较上周涨跌幅（%）", "较年初涨跌幅（%）"]
    for j, h in enumerate(headers):
        _write_cell(table.rows[0].cells[j], h, bold=True, size_pt=9.0)
    _set_repeat_header(table.rows[0])

    for i, row in enumerate(rows, start=1):
        for j, val in enumerate(row):
            align = WD_ALIGN_PARAGRAPH.LEFT if j == 0 else WD_ALIGN_PARAGRAPH.CENTER
            _write_cell(table.rows[i].cells[j], val, size_pt=9.0, align=align)


# --------------------------------------------------------------------- 表3


QUOTE_HEADERS = [
    "项目类型", "证券代码", "证券名称", "上市日期", "总市值\n（亿元）",
    "流通市值\n(亿元)", "发行价\n（元）", "上周收盘价\n（元）",
    "本周收盘价\n（元）", "本周涨跌幅\n（%）", "p/nav",
]

QUOTE_WIDTHS = [0.075, 0.085, 0.145, 0.095, 0.085, 0.085, 0.085, 0.085, 0.085, 0.09, 0.085]


def quotes_table(doc, df: pd.DataFrame, board_order: list[str]) -> None:
    """全市场个券行情表（96 行）。首列按板块纵向合并。"""
    data = df.copy()
    data["_bord"] = pd.Categorical(data["board"], categories=board_order, ordered=True)
    data = data.sort_values(["_bord", "code"]).reset_index(drop=True)

    table = doc.add_table(rows=len(data) + 1, cols=len(QUOTE_HEADERS))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _fixed_layout(table)
    _set_col_widths(table, QUOTE_WIDTHS)

    for j, h in enumerate(QUOTE_HEADERS):
        _write_cell(table.rows[0].cells[j], h, bold=True, size_pt=7.5)
    _set_row_height(table.rows[0], 500)
    _set_repeat_header(table.rows[0])

    for i, row in data.iterrows():
        cells = table.rows[i + 1].cells
        _set_row_height(table.rows[i + 1], 260)
        listing = pd.to_datetime(row["listing_date"], errors="coerce")
        values = [
            row["board"],
            str(row["code"]),
            str(row["name"]),
            listing.strftime("%Y-%m-%d") if pd.notna(listing) else "—",
            fmt_num(row["mktcap_total"], 2),
            fmt_num(row["mktcap_float"], 2),
            fmt_num(row["issue_price"], 2),
            fmt_num(row["close_prev"], 3),
            fmt_num(row["close_cur"], 3),
            fmt_pct(row.get("ret_total"), 2),
            fmt_ratio(row["pnav"], 3),
        ]
        for j, val in enumerate(values):
            align = WD_ALIGN_PARAGRAPH.LEFT if j in (0, 2) else WD_ALIGN_PARAGRAPH.CENTER
            _write_cell(cells[j], val, size_pt=7.5, align=align)

    # 首列按板块合并：连续相同板块合并为一个跨行单元格
    start = 1
    boards = list(data["board"])
    for idx in range(1, len(boards) + 1):
        if idx == len(boards) or boards[idx] != boards[start - 1]:
            if idx - start > 1:
                top = table.cell(start, 0)
                bottom = table.cell(idx, 0)
                merged = top.merge(bottom)
                _write_cell(merged, boards[start - 1], size_pt=7.5,
                            align=WD_ALIGN_PARAGRAPH.CENTER)
            start = idx + 1


# --------------------------------------------------------------------- 表4


def pnav_table(doc, by_board: pd.DataFrame, overall: dict) -> None:
    """分板块 P/NAV 表，按中位数升序，末行"全市场"。"""
    rows = len(by_board) + 2
    table = doc.add_table(rows=rows, cols=5)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_col_widths(table, [0.26, 0.18, 0.18, 0.2, 0.18])

    headers = ["板块", "P/NAV中位数", "中位折溢价", "市值加权P/NAV", "溢价/折价数量"]
    for j, h in enumerate(headers):
        cell = table.rows[0].cells[j]
        _write_cell(cell, h, bold=True, size_pt=9.0)
        _set_cell_shading(cell, "F7F7F7")
        _set_cell_margins(cell, 120, 120, 180, 180)
    _set_repeat_header(table.rows[0])

    def _row(r, board, median, disc, weighted, prem, disc_n, bold=False):
        vals = [
            board,
            fmt_ratio(median, 3),
            fmt_pct(disc, 1),
            fmt_ratio(weighted, 3),
            f"{prem} / {disc_n}",
        ]
        for j, v in enumerate(vals):
            _write_cell(r.cells[j], v, size_pt=9.0, bold=bold)

    for i, (_, row) in enumerate(by_board.iterrows(), start=1):
        _row(table.rows[i], row["board"], row["median"], row["median_discount_pct"],
             row["weighted"], int(row["n_premium"]), int(row["n_discount"]))

    _row(table.rows[rows - 1], "全市场", overall["median"], overall["discount_pct"],
         overall["weighted"], overall["n_premium"], overall["n_discount"], bold=True)


# --------------------------------------------------------------------- 表5


PENDING_HEADERS = ["序号", "类别", "项目简称", "审核状态", "最近更新"]


def pending_table(doc, pending: pd.DataFrame) -> None:
    """待上市储备清单。列与样张一致（不含交易所与基金全称）。

    类别列按类别分组留空，只在首行写一次 —— 与样张的处理一致，
    避免 47 行里重复 47 次"商业不动产"。
    """
    data = pending.sort_values(["category", "seq"]).reset_index(drop=True)
    table = doc.add_table(rows=len(data) + 1, cols=len(PENDING_HEADERS))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_col_widths(table, [0.10, 0.26, 0.34, 0.16, 0.14])

    for j, h in enumerate(PENDING_HEADERS):
        _write_cell(table.rows[0].cells[j], h, bold=True, size_pt=8.0)
    _set_repeat_header(table.rows[0])

    prev_cat = None
    for i, row in data.iterrows():
        cat = str(row["category"])
        show_cat = cat if cat != prev_cat else ""
        prev_cat = cat
        values = [
            str(int(row["seq"])),
            show_cat,
            str(row["name"]),
            str(row["status"]),
            str(row["updated"]),
        ]
        for j, v in enumerate(values):
            align = WD_ALIGN_PARAGRAPH.LEFT if j == 2 else WD_ALIGN_PARAGRAPH.CENTER
            _write_cell(table.rows[i + 1].cells[j], v, size_pt=8.0, align=align)
        _set_row_height(table.rows[i + 1], 260)
