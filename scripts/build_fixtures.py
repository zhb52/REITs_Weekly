"""从终端导出与数据底稿生成可分享的示例数据（fixtures）。

用途
----
`fixtures/` 里放的是**公开市场行情**（收盘价、成交额、单位净值、流通市值），
不含任何持仓、客户或内部批注信息。数据底稿里的"来源编号""备注"等内部字段
在这里被剔除，因此可以直接随作业提交、供他人复现。

这不是玩具数据：它就是 2026-W45 期的真实公开行情，所以
`tests/golden/` 里的期望值能直接对应到那一期报告的数字。

用法
----
    python scripts/build_fixtures.py \
        --ledger "REITs周报数据底稿_20261102-1106.xlsx" \
        --market "沪深REITs.xlsx" \
        --out fixtures/demo-2026-W45
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

# 底稿 04 的列位置（表头在第 2 行）
LEDGER_COLS = {
    1: "code",
    2: "name",
    3: "board_raw",
    4: "asset_class",
    5: "close_prev",
    6: "close_cur",
    7: "dpu_week",
}

# 终端 周度行情 的列位置（表头在第 1 行）
MARKET_COLS = {
    0: "board_terminal",
    1: "code_full",
    2: "name",
    3: "listing_date",
    4: "mktcap_total",
    5: "mktcap_float",
    6: "issue_price",
    7: "close_prev_fq",
    8: "close_cur",
    9: "ret_pct_decimal",
    10: "pnav",
}

TURNOVER_COLS = {
    0: "board_terminal",
    1: "code_full",
    2: "name",
    3: "turnover_week",
    4: "turnover_avg",
    5: "rate_pct",
    6: "turnover_week_prev",
    7: "turnover_avg_prev",
    8: "rate_pct_prev",
}


def _by_position(df: pd.DataFrame, mapping: dict[int, str]) -> pd.DataFrame:
    cols = {}
    for idx, name in mapping.items():
        if idx < len(df.columns):
            cols[df.columns[idx]] = name
    out = df.rename(columns=cols)
    keep = [c for c in mapping.values() if c in out.columns]
    return out[keep].copy()


def _norm_code(series: pd.Series) -> pd.Series:
    return (
        series.astype("string")
        .str.strip()
        .str.split(".")
        .str[0]
        .str.replace(r"\D", "", regex=True)
        .str.zfill(6)
    )


# 终端导出的证券代码形如 508001.SH / 180201.SZ。
# 工作表底部常有"分板块小计"与"合计"块，其首位是数字的板块汇总值，
# 若只按"是否 6 位数字"过滤会被误当成个券，故必须要求带交易所后缀。
_SEC_CODE = r"^\d{6}\.(SH|SZ|BJ)$"


def _is_security(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().str.match(_SEC_CODE).fillna(False)


def build(ledger: Path, market: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------- 底稿个券表
    raw = pd.read_excel(ledger, sheet_name="04_个券行情", header=1)
    led = _by_position(raw, LEDGER_COLS)
    led["code"] = _norm_code(led["code"])
    led["board_raw"] = led["board_raw"].ffill()
    leading = led[led["code"].str.len() == 6].copy()
    for c in ("close_prev", "close_cur", "dpu_week"):
        leading[c] = pd.to_numeric(leading[c], errors="coerce")

    # ---------------------------------------------------------- 终端行情
    mkt = pd.read_excel(market, sheet_name="周度行情", header=0)
    mkt = _by_position(mkt, MARKET_COLS)
    mkt = mkt[_is_security(mkt["code_full"])].copy()
    mkt["code"] = _norm_code(mkt["code_full"])
    # 终端导出的板块列是合并单元格，只有每组首行有值，必须向下填充，
    # 否则组内其余标的会带着空板块进入合并，最终混用两套叫法。
    mkt["board_terminal"] = mkt["board_terminal"].ffill()
    for c in ("mktcap_total", "mktcap_float", "issue_price", "pnav",
              "close_prev_fq", "close_cur"):
        mkt[c] = pd.to_numeric(mkt[c], errors="coerce")

    # ---------------------------------------------------------- 合并
    quotes = leading.merge(
        mkt[["code", "board_terminal", "mktcap_total", "mktcap_float",
             "issue_price", "pnav", "listing_date"]],
        on="code",
        how="left",
        suffixes=("", "_mkt"),
    )
    # 板块以终端口径作为"数据源原始值"，用来检验别名词典与 override 是否生效
    quotes["board_raw"] = quotes["board_terminal"].fillna(quotes["board_raw"])
    quotes["close_cur"] = quotes["close_cur"].fillna(quotes["close_cur_mkt"]) \
        if "close_cur_mkt" in quotes.columns else quotes["close_cur"]
    quotes["dpu_week"] = quotes["dpu_week"].fillna(0.0)

    quotes = quotes[[
        "code", "name", "board_raw", "asset_class",
        "close_prev", "close_cur", "dpu_week",
        "mktcap_total", "mktcap_float", "issue_price", "pnav",
    ]].sort_values("code")
    quotes.to_csv(out_dir / "quotes_weekly.csv", index=False, encoding="utf-8")
    print(f"quotes_weekly.csv  {len(quotes)} 行")

    # ---------------------------------------------------------- 成交
    tv = pd.read_excel(market, sheet_name="成交与流动性", header=0)
    tv = _by_position(tv, TURNOVER_COLS)
    tv = tv[_is_security(tv["code_full"])].copy()
    tv["code"] = _norm_code(tv["code_full"])
    for c in ("turnover_week", "turnover_week_prev"):
        tv[c] = pd.to_numeric(tv[c], errors="coerce")
    tv = tv.dropna(subset=["turnover_week"])[
        ["code", "turnover_week", "turnover_week_prev"]
    ].sort_values("code")
    tv.to_csv(out_dir / "turnover_weekly.csv", index=False, encoding="utf-8")
    print(f"turnover_weekly.csv  {len(tv)} 行")

    # ---------------------------------------------------------- 利率
    rates = pd.DataFrame(
        [
            {"code": "T10Y", "prev": 1.650, "cur": 1.587},
            {"code": "T30Y", "prev": 2.083, "cur": 2.028},
            {"code": "DR007", "prev": 1.390, "cur": 1.345},
        ]
    )
    rates.to_csv(out_dir / "yields.csv", index=False, encoding="utf-8")
    print(f"yields.csv  {len(rates)} 行")

    # ---------------------------------------------------------- 自检
    n_total = len(quotes)
    n_cmp = int(quotes["close_prev"].notna().sum())
    print(f"\n合计 {n_total} 只，其中可比 {n_cmp} 只，"
          f"新上市 {n_total - n_cmp} 只")
    if n_total != 96 or n_cmp != 94:
        print("⚠ 与 2026-W45 期的规模（96/94）不一致，请核对源文件", file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ledger", required=True, type=Path, help="数据底稿 xlsx")
    ap.add_argument("--market", required=True, type=Path, help="终端导出 xlsx")
    ap.add_argument("--out", required=True, type=Path, help="输出目录")
    args = ap.parse_args()
    build(args.ledger, args.market, args.out)


if __name__ == "__main__":
    main()
