"""把底稿的事件表与待上市清单做成可分享的 fixture。

数据来源：
* ``REITs周报数据底稿_20261102-1106.xlsx`` 的 ``07_一级市场与事件`` 表
* ``待上市REITs储备清单_20261106.xlsx``

两者都是对上交所/深交所公示信息的整理，属公开披露信息。
输出时剔除"来源编号"这类内部标注，保留事件本身的日期、类型、内容与影响。

用法：
    python scripts/build_events_fixture.py \
        --ledger 数据底稿.xlsx --pending 待上市清单.xlsx --out fixtures/demo-2026-W45
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

EVENT_COLS = ["date", "type", "event", "impact"]
PENDING_COLS = ["seq", "category", "name", "exchange", "status", "updated"]


def build(ledger: Path, pending: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------- 本周事件
    raw = pd.read_excel(ledger, sheet_name="07_一级市场与事件", header=1)
    ev = raw.iloc[:, :5].copy()
    ev.columns = ["date", "type", "event", "impact", "source"]
    ev = ev.dropna(subset=["event"])
    ev = ev[ev["event"].astype(str).str.strip() != ""]
    ev["date"] = ev["date"].astype(str)
    ev = ev[EVENT_COLS]
    ev.to_csv(out_dir / "events_weekly.csv", index=False, encoding="utf-8")
    print(f"events_weekly.csv    {len(ev)} 条")

    # ---------------------------------------------------------- 待上市清单
    raw2 = pd.read_excel(pending, sheet_name=0, header=0)
    pp = raw2.iloc[:, :6].copy()
    pp.columns = PENDING_COLS
    pp = pp[pd.to_numeric(pp["seq"], errors="coerce").notna()].copy()
    pp["seq"] = pp["seq"].astype(int)
    pp["updated"] = pp["updated"].astype(str).str[:10]
    pp.to_csv(out_dir / "primary_pipeline.csv", index=False, encoding="utf-8")
    print(f"primary_pipeline.csv {len(pp)} 条")

    # ---------------------------------------------------------- 自检
    print("\n审核状态分布：")
    for k, v in pp["status"].value_counts().items():
        print(f"  {k:<8} {v}")
    print("\n类别分布：")
    for k, v in pp["category"].value_counts().items():
        print(f"  {k:<8} {v}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ledger", required=True, type=Path)
    ap.add_argument("--pending", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    build(args.ledger, args.pending, args.out)


if __name__ == "__main__":
    main()
