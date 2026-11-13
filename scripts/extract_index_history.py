"""从样张 docx 的原生图表中提取指数历史序列。

背景
----
2026-W45 期报告的两张折线图是 Word 原生图表（``word/charts/chart1.xml``、
``chart2.xml``），Office 会把绘图数据以缓存形式（``c:numCache``）内嵌在 XML 里。
这意味着**历史日序列本来就躺在文档里**，不必再去爬中证指数官网，也不必让使用者
从终端重新导一遍。

提取出的序列已按 2021-09-30 = 1000 重新定基（原图即如此），仅用于绘图，
不参与 1.1 的点位计算 —— 后者用 ``02_市场指数与跨资产`` 的当期收盘值。

用法
----
    python scripts/extract_index_history.py --docx REITs周报.docx --out fixtures/demo-2026-W45
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import re
import zipfile
from pathlib import Path

EXCEL_EPOCH = dt.date(1899, 12, 30)

SER_RE = re.compile(r"<c:ser>(.*?)</c:ser>", re.S)
TX_RE = re.compile(r"<c:tx>.*?<c:v>([^<]*)</c:v>.*?</c:tx>", re.S)
CAT_RE = re.compile(r"<c:cat>(.*?)</c:cat>", re.S)
VAL_RE = re.compile(r"<c:val>(.*?)</c:val>", re.S)
PT_RE = re.compile(r'<c:pt idx="(\d+)"[^>]*>\s*<c:v>([^<]*)</c:v>', re.S)


def _points(block: str) -> dict[int, str]:
    return {int(i): v for i, v in PT_RE.findall(block)}


def _to_date(token: str) -> dt.date | None:
    token = token.strip()
    if re.fullmatch(r"\d+(\.\d+)?", token):
        return EXCEL_EPOCH + dt.timedelta(days=int(float(token)))
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(token, fmt).date()
        except ValueError:
            continue
    return None


def extract(docx: Path) -> list[dict]:
    rows: list[dict] = []
    with zipfile.ZipFile(docx) as z:
        chart_names = sorted(
            n for n in z.namelist() if re.fullmatch(r"word/charts/chart\d+\.xml", n)
        )
        for name in chart_names:
            xml = z.read(name).decode("utf-8")
            for ser in SER_RE.findall(xml):
                tx = TX_RE.search(ser)
                label = tx.group(1).strip() if tx else ""
                cat_block = CAT_RE.search(ser)
                val_block = VAL_RE.search(ser)
                if not (cat_block and val_block):
                    continue
                cats = _points(cat_block.group(1))
                vals = _points(val_block.group(1))
                if not cats or not vals:
                    continue
                for idx, raw_val in vals.items():
                    d = _to_date(cats.get(idx, ""))
                    if d is None:
                        continue
                    try:
                        v = float(raw_val)
                    except ValueError:
                        continue
                    rows.append(
                        {
                            "date": d.isoformat(),
                            "series": label,
                            "chart": Path(name).stem,
                            "value_rebased": v,
                        }
                    )
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--docx", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    rows = extract(args.docx)
    if not rows:
        raise SystemExit("未在文档中找到内嵌图表数据")

    args.out.mkdir(parents=True, exist_ok=True)
    target = args.out / "index_series.csv"
    with target.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "series", "chart", "value_rebased"])
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["chart"], r["series"], r["date"])))

    series = sorted({(r["chart"], r["series"]) for r in rows})
    print(f"写入 {target}  共 {len(rows)} 个数据点")
    for chart, label in series:
        n = sum(1 for r in rows if r["chart"] == chart and r["series"] == label)
        pts = sorted(r["date"] for r in rows if r["chart"] == chart and r["series"] == label)
        print(f"  {chart}  {label:<22} {n:>5} 点  {pts[0]} → {pts[-1]}")


if __name__ == "__main__":
    main()
