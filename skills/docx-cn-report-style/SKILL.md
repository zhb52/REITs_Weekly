---
name: docx-cn-report-style
description: 生成与既有样本版式一致的中文研究报告 docx（标题层级、正文缩进、表格样式、页脚页码）。适用于需要严格复刻某份既有报告排版的场景。
---

# 中文研报 docx 版式复刻

## 核心教训

如果样本 docx **没有使用命名样式**（`pStyle` 全为空），就不要试图用"应用 Heading 1"来复现。
那种文档的所有格式都是直接格式化，只能靠代码把常量固化下来。

先检查：解压 docx，看 `word/document.xml` 里有没有 `<w:pStyle w:val="...">`。
没有就说明是直接格式化，走本 skill 的常量路线。

## 从样本提取常量

```python
from docx import Document
d = Document("sample.docx")
n = d.styles["Normal"]
print(n.font.name, n.font.size.pt, n.element.xml)
```

需要提取的六项：

| 项 | 取法 | 示例值 |
|---|---|---|
| 正文字号 | `styles["Normal"].font.size` | 11pt |
| 中文字体 | `rPr/rFonts` 的 `w:eastAsia` | 宋体 |
| 行距 | `paragraph_format.line_spacing` | 1.15 |
| 段后间距 | `paragraph_format.space_after` | 200 twips |
| 首行缩进 | `paragraph_format.first_line_indent` | 420 twips（2 字符） |
| 标题色 | 各标题 run 的 `font.color.rgb` | `1F3864` |

## 三级标题的惯用参数

| 级别 | 字号 | 颜色 | 段前 | 对齐 |
|---|---|---|---|---|
| 主标题 | 18pt 加粗 | `1F3864` | 0 | 居中 |
| 章标题 | 14pt 加粗 | `1F3864` | 10pt | 左 |
| 节标题 | 11.5pt 加粗 | `262626` | 7pt | 左 |

## 表格的坑

**列宽**：`cell.width = None` 会抛 `TypeError`。要逐格写 `tcW`，
百分比单位是 1/50 个百分点（100% = 5000）：

```python
tcW = OxmlElement("w:tcW")
tcW.set(qn("w:w"), str(int(pct * 5000)))
tcW.set(qn("w:type"), "pct")
```

只设 `tblW` 在固定布局下不生效。

**跨页重复表头**：长表必须加 `w:tblHeader`，否则跨页后表头消失、读者不知道列是什么。

```python
trPr = row._tr.get_or_add_trPr()
trPr.append(OxmlElement("w:tblHeader"))
```

**合并首列**：按分组连续合并，而不是每行都写一次组名。

## 页脚页码

python-docx 不支持域，需手写 `fldChar`：

```python
run._r.append(OxmlElement("w:fldChar"))   # begin
instr = OxmlElement("w:instrText"); instr.text = " PAGE "
run._r.append(instr)
run._r.append(OxmlElement("w:fldChar"))   # end
```

## 图表

优先输出 300dpi PNG 插入，而不是生成 Word 原生图表。原生图表在数据点数变化时
需同步修改 `c:ptCount`、`c:f` 与内嵌 xlsx，任何一处漏改都会让 Word 报"图表数据错误"。
除非接收方明确要求"图表可在 Word 里继续编辑"，否则不值得这个代价。

中文字体要先探测，缺失时降级并记录：

```python
matplotlib.rcParams["font.sans-serif"] = ["SimSun", "Microsoft YaHei"]
matplotlib.rcParams["axes.unicode_minus"] = False   # 否则负号显示为方块
```
