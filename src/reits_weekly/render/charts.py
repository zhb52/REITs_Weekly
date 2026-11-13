"""图表生成 —— 复现样张的四张图。

设计取舍
--------
样张的四张图是 **Word 原生图表**（``word/charts/chartN.xml``）。原生图表的优点是
在 Word 里仍可编辑数据，缺点是数据点变化时必须同步修改 ``c:ptCount``、``c:f``
引用范围以及内嵌的 ``Microsoft_Excel_Worksheet*.xlsx``，任何一处漏改都会让
Word 打开时报"图表数据错误"。

周报每周重画、点数固定（1234 个交易日 + 10 个板块），但样本会随新上市增加。
权衡后默认输出 **300dpi PNG**：版式与配色可精确控制，且不会因点数变化而损坏文档。
``--charts native`` 分支留给需要继续编辑图表的场景。

样式来源（从样张 XML 读出，不是估的）
* 主题色：Office 2007 强调色 ``#4F81BD / #C0504D / #9BBB59 / #8064A2``
* 线宽：22225 EMU ≈ 1.75pt
* 字体：宋体；标注字号 9pt
* 图宽：16.63cm（5976620 EMU），高度 6.54 / 7.14 / 6.97 / 6.54 cm
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # 无界面后端，CI 与服务器可用

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib import font_manager

# 样张主题色（Office 2007）
ACCENT = ["#4F81BD", "#C0504D", "#9BBB59", "#8064A2"]
GRID = "#D9D9D9"
LABEL = "#595959"

# 样张图宽（cm）
FIG_WIDTH_CM = 16.63
DPI = 300

_CM = 1 / 2.54


def _pick_font() -> str:
    """优先宋体（样张所用），缺失则降级雅黑，再缺则用 matplotlib 默认。"""
    for name in ("SimSun", "Microsoft YaHei", "SimHei"):
        try:
            font_manager.findfont(name, fallback_to_default=False)
            return name
        except Exception:
            continue
    return "DejaVu Sans"


def apply_style() -> list[str]:
    """设置全局样式，返回生效的字体提示（供 QA 记录降级情况）。"""
    font = _pick_font()
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": [font, "DejaVu Sans"],
            "axes.unicode_minus": False,
            "font.size": 9,
            "axes.edgecolor": GRID,
            "axes.linewidth": 0.8,
            "xtick.color": LABEL,
            "ytick.color": LABEL,
            "figure.dpi": DPI,
        }
    )
    return [font]


@dataclass(frozen=True)
class ChartSpec:
    """图表的数据契约，便于测试比对而不必比像素。"""

    name: str
    series: tuple[tuple[str, tuple], ...]
    height_cm: float

    @property
    def n_points(self) -> tuple[int, ...]:
        return tuple(len(v) for _, v in self.series)


def _save(fig, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out_path


# --------------------------------------------------------------------- 折线图


def line_chart(
    df: pd.DataFrame,
    series_order: list[str],
    labels: dict[str, str],
    out_path: Path,
    height_cm: float,
    ylabel: str = "",
    ylim_floor: float | None = None,
) -> ChartSpec:
    """多序列折线图。``df`` 列为 date / series / value。"""
    fig, ax = plt.subplots(figsize=(FIG_WIDTH_CM * _CM, height_cm * _CM))
    specs = []
    for i, code in enumerate(series_order):
        sub = df[df["series"] == code].sort_values("date")
        if sub.empty:
            continue
        x = pd.to_datetime(sub["date"])
        y = sub["value"].astype(float)
        ax.plot(x, y, color=ACCENT[i % len(ACCENT)], linewidth=1.75,
                label=labels.get(code, code))
        specs.append((labels.get(code, code), tuple(y.tolist())))

    ax.set_ylabel(ylabel)
    if ylim_floor is not None:
        ax.set_ylim(bottom=ylim_floor)
    ax.grid(axis="y", color=GRID, linewidth=0.6, alpha=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.legend(loc="lower center", ncol=min(len(specs), 4), frameon=False, fontsize=9)
    fig.tight_layout()
    _save(fig, out_path)
    return ChartSpec(name=out_path.stem, series=tuple(specs), height_cm=height_cm)


# --------------------------------------------------------------------- 柱状图


def grouped_bar_chart(
    df: pd.DataFrame,
    board_order: list[str],
    cur_col: str,
    prev_col: str,
    cur_label: str,
    prev_label: str,
    out_path: Path,
    height_cm: float,
    ylabel: str = "",
    annotate: bool = True,
) -> ChartSpec:
    """分板块双系列柱状图（本周 / 上周）。

    ``df`` 需含 ``board`` 与两个数值列，按 ``board_order`` 排序。
    """
    data = df.set_index("board").reindex(board_order)
    x = range(len(data))
    width = 0.38

    fig, ax = plt.subplots(figsize=(FIG_WIDTH_CM * _CM, height_cm * _CM))
    cur = data[cur_col].astype(float).fillna(0.0)
    prev = data[prev_col].astype(float).fillna(0.0)

    b1 = ax.bar([i - width / 2 for i in x], cur, width, label=cur_label, color=ACCENT[0])
    b2 = ax.bar([i + width / 2 for i in x], prev, width, label=prev_label, color=ACCENT[1])

    if annotate:
        for bars in (b1, b2):
            for rect in bars:
                h = rect.get_height()
                if h == 0:
                    continue
                ax.annotate(
                    f"{h:.2f}",
                    xy=(rect.get_x() + rect.get_width() / 2, h),
                    xytext=(0, 2),
                    textcoords="offset points",
                    ha="center",
                    va="bottom",
                    fontsize=7,
                    color=LABEL,
                )

    ax.set_xticks(list(x))
    ax.set_xticklabels(list(data.index), rotation=0, fontsize=8)
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", color=GRID, linewidth=0.6, alpha=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.legend(frameon=False, fontsize=9, loc="upper right")
    fig.tight_layout()
    _save(fig, out_path)
    return ChartSpec(
        name=out_path.stem,
        series=((cur_label, tuple(cur.tolist())), (prev_label, tuple(prev.tolist()))),
        height_cm=height_cm,
    )


# --------------------------------------------------------------------- 组装


INDEX_LABELS = {
    "932047.CSI": "中证 REITs 全收益",
    "932006.CSI": "中证 REITs（收盘）",
    "H00300.CSI": "沪深 300 全收益",
    "H00922.CSI": "中证红利全收益",
    "CBA00201.CS": "中债综合财富",
}

CHART_HEIGHTS = {"chart_reits_index": 6.54, "chart_cross_asset": 7.14,
                 "chart_board_turnover": 6.97, "chart_board_turnover_rate": 6.54}


def build_all(
    index_df: pd.DataFrame,
    board_turnover: pd.DataFrame,
    out_dir: Path,
) -> list[ChartSpec]:
    """生成四张图，返回各自的 ChartSpec。

    Parameters
    ----------
    index_df : 列 date / series / value，value 已按 2021-09-30 = 1000 定基。
    board_turnover : 列 board / turnover / turnover_prev / rate / rate_prev。
    """
    apply_style()
    out_dir = Path(out_dir)
    specs: list[ChartSpec] = []

    specs.append(
        line_chart(
            index_df,
            ["932047.CSI", "932006.CSI"],
            INDEX_LABELS,
            out_dir / "chart_reits_index.png",
            CHART_HEIGHTS["chart_reits_index"],
            ylabel="指数点位（2021-09-30=1000）",
            ylim_floor=600,
        )
    )
    specs.append(
        line_chart(
            index_df,
            ["932047.CSI", "H00300.CSI", "H00922.CSI", "CBA00201.CS"],
            INDEX_LABELS,
            out_dir / "chart_cross_asset.png",
            CHART_HEIGHTS["chart_cross_asset"],
            ylabel="指数点位（2021-09-30=1000）",
        )
    )
    specs.append(
        grouped_bar_chart(
            board_turnover,
            list(board_turnover["board"]),
            "turnover",
            "turnover_prev",
            "本周日均成交额（亿元）",
            "上周日均成交额（亿元）",
            out_dir / "chart_board_turnover.png",
            CHART_HEIGHTS["chart_board_turnover"],
            ylabel="亿元",
        )
    )
    specs.append(
        grouped_bar_chart(
            board_turnover,
            list(board_turnover["board"]),
            "turnover_rate",
            "turnover_rate_prev",
            "本周日均换手率（%）",
            "上周日均换手率（%）",
            out_dir / "chart_board_turnover_rate.png",
            CHART_HEIGHTS["chart_board_turnover_rate"],
            ylabel="%",
        )
    )
    return specs
