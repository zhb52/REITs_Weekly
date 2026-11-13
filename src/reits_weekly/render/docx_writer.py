"""docx 装配 —— 把事实、表格、图表和草稿组装成一份周报。

为什么要"从样张抽样式"而不是"套一个通用模板"
------------------------------------------------
样张 docx 没有任何命名样式（``pStyle`` 全为空），所有格式都是直接格式化：
正文 11pt、首行缩进 420 twips、行距 1.15、段后 200twips、
章标题 14pt 加粗色 ``1F3864``、节标题 11.5pt 加粗色 ``262626``。
因此无法靠"应用 Heading 1"复现，只能在代码里把这些常量固化下来。

本模块只负责**排版**：它读入已填充占位符的草稿文本，不做任何业务判断、
不产生任何数字。数字来自 ``facts.json``，由 ``draft/composer.py`` 在更早一步完成替换。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor, Twips

FONT_CN = "宋体"
COLOR_TITLE = RGBColor(0x1F, 0x38, 0x64)
COLOR_SECTION = RGBColor(0x26, 0x26, 0x26)
BODY_SIZE = Pt(11)
LINE_SPACING = 1.15
SPACE_AFTER = Twips(200)
FIRST_LINE_INDENT = Twips(420)
CHART_WIDTH = Cm(16.63)


# --------------------------------------------------------------------- 基础


def _setup_document() -> Document:
    doc = Document()
    sec = doc.sections[0]
    sec.page_width = Cm(21.0)
    sec.page_height = Cm(29.7)
    sec.top_margin = Twips(1304)
    sec.bottom_margin = Twips(1304)
    sec.left_margin = Twips(1247)
    sec.right_margin = Twips(1247)

    normal = doc.styles["Normal"]
    normal.font.name = FONT_CN
    normal.font.size = BODY_SIZE
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CN)
    pf = normal.paragraph_format
    pf.line_spacing = LINE_SPACING
    pf.space_after = SPACE_AFTER
    return doc


def _add_page_field(paragraph) -> None:
    """在页脚插入 PAGE 域。"""
    run = paragraph.add_run()
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    run._r.append(fld_begin)
    run._r.append(instr)
    run._r.append(fld_end)


def setup_footer(doc: Document, period_label: str) -> None:
    footer = doc.sections[0].footer
    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(f"公募REITs周报｜{period_label}｜第 ")
    run.font.size = Pt(9)
    run.font.name = FONT_CN
    _add_page_field(p)
    tail = p.add_run(" 页")
    tail.font.size = Pt(9)
    tail.font.name = FONT_CN


# --------------------------------------------------------------------- 文本块


def add_title(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(12)
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(18)
    run.font.color.rgb = COLOR_TITLE
    run.font.name = FONT_CN
    run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CN)


def add_chapter(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(6)
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(14)
    run.font.color.rgb = COLOR_TITLE
    run.font.name = FONT_CN
    run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CN)


def add_section_heading(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(7)
    p.paragraph_format.space_after = Pt(3)
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(11.5)
    run.font.color.rgb = COLOR_SECTION
    run.font.name = FONT_CN
    run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CN)


def add_body(doc: Document, text: str) -> None:
    """正文段落：首行缩进两个字符、两端对齐。"""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.first_line_indent = FIRST_LINE_INDENT
    run = p.add_run(text.strip())
    run.font.size = BODY_SIZE
    run.font.name = FONT_CN
    run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CN)


def add_source_note(doc: Document, text: str) -> None:
    """表格/图下方的"资料来源"注，字号略小、无段后间距。"""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    run = p.add_run(f"资料来源：{text}")
    run.font.size = Pt(9)
    run.font.name = FONT_CN
    run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CN)


def add_chart(doc: Document, png_path: Path, caption: str = "") -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(2)
    p.add_run().add_picture(str(png_path), width=CHART_WIDTH)


# --------------------------------------------------------------------- 工具


def period_label(start: date, end: date) -> str:
    """样张格式：2026.11.02—11.06"""
    return f"{start:%Y.%m.%d}—{end:%m.%d}"


def split_paragraphs(text: str) -> list[str]:
    """草稿以空行分段；单换行视为同一段内的折行。"""
    blocks = [b.strip().replace("\n", "") for b in text.split("\n\n")]
    return [b for b in blocks if b]
