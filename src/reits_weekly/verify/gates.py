"""硬门禁 —— 不通过就阻断，不是警告。

与 Critic 的分工：门禁检查**可判定的事实**（数字能否回溯、合计是否勾稽、
是否用了未来信息），Critic 检查**需要判断的东西**（论证是否成立、口径是否说清）。
前者必须有唯一答案，后者允许分歧。

每条门禁返回 ``GateResult``，其中 ``detail`` 要写清"哪个数、哪个位置、差多少"，
因为一条只说"失败"的门禁对修稿没有帮助。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from ..facts import FactsBundle


@dataclass
class GateResult:
    id: str
    ok: bool
    detail: str = ""
    checked: int = 0
    failed: int = 0
    samples: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "ok": self.ok,
            "detail": self.detail,
            "checked": self.checked,
            "failed": self.failed,
            "samples": self.samples[:20],
        }


# --------------------------------------------------------------------- 数字审计

#: 正文里允许出现的非事实数字。每一项都要有理由，不能为了"让门禁通过"而加。
ALLOWED_PATTERNS = [
    (r"\d+年期", "期限名称，如 10年期国债"),
    (r"DR007", "资金利率品种代码"),
    (r"\d{4}[-./年]\d{1,2}[-./月]\d{1,2}", "日期"),
    (r"\d{4}年", "年份"),
    (r"第[一二三四五六七八九十]", "序数，中文数字"),
    (r"沪深\s*300", "指数名称中的数字"),
    (r"中证\s*\d+", "指数名称中的数字"),
    (r"\d+\.\d+\s*节", "章节交叉引用"),
]

_NUM_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")

#: 事实库里 display 可能带的后缀。比对前两侧都要剥掉，
#: 否则 "-6.3bp" 会被拆成 "-6.3" 去和 "6.3" 比，永远对不上。
_UNIT_SUFFIXES = ("亿元", "bp", "只", "%")


def _normalize(token: str) -> str:
    t = token.replace(",", "").strip()
    for suffix in _UNIT_SUFFIXES:
        if t.endswith(suffix):
            t = t[: -len(suffix)]
            break
    try:
        v = float(t)
    except ValueError:
        return token
    if v == 0:
        v = 0.0
    return f"{v:.6f}".rstrip("0").rstrip(".")


def _allowed(token: str, context: str) -> str | None:
    for pattern, why in ALLOWED_PATTERNS:
        if re.search(pattern, context):
            return why
    return None


def numeric_audit(
    sections: dict[str, str], bundle: FactsBundle
) -> GateResult:
    """G-NUM-01：正文每个数字都必须能映射到某条事实的 display。

    这是"数字只能由代码产生"这条约束的执行者。LLM 最容易犯的错是在文中
    自己算一个数（如"相差近六个百分点"写成"相差 5.8 个百分点"），
    这类数字不在事实库里，会被这里拦下。
    """
    known = bundle.displays()
    known_norm = {_normalize(d) for d in known}

    checked = 0
    failed = 0
    samples: list[str] = []

    for sid, text in sections.items():
        for m in _NUM_RE.finditer(text):
            token = m.group(0)
            checked += 1
            if _normalize(token) in known_norm:
                continue
            # 上下文取前后 12 字，用于判断是否命中允许模式
            lo = max(0, m.start() - 12)
            hi = min(len(text), m.end() + 12)
            context = text[lo:hi]
            if _allowed(token, context):
                continue
            failed += 1
            if len(samples) < 10:
                samples.append(f"[{sid}] {token} …{context.strip()}…")

    return GateResult(
        id="G-NUM-01",
        ok=failed == 0,
        detail=f"{failed}/{checked} 个数字无法回溯到事实库",
        checked=checked,
        failed=failed,
        samples=samples,
    )


# --------------------------------------------------------------------- 勾稽


def crossfoot(bundle: FactsBundle) -> GateResult:
    """G-NUM-02：合计类指标必须闭合。"""
    problems: list[str] = []

    def one(metric: str, default=None):
        items = bundle.by_metric(metric)
        return items[0].value if items else default

    n_market = one("breadth.n")
    n_board = sum(f.value for f in bundle.by_metric("board.n"))
    if n_market is not None and n_board != n_market:
        problems.append(f"板块样本数合计 {n_board} ≠ 全市场可比样本 {n_market}")

    up, down, flat = one("breadth.up"), one("breadth.down"), one("breadth.flat")
    if None not in (up, down, flat) and n_market is not None:
        if up + down + flat != n_market:
            problems.append(f"涨{up}+跌{down}+平{flat} ≠ {n_market}")

    total = one("turnover.total")
    parts = sum(f.value for f in bundle.by_metric("turnover.board"))
    if total is not None and abs(parts - total) > 0.02:
        problems.append(f"板块成交合计 {parts:.2f} ≠ 全市场 {total:.2f}")

    n_prem = one("pnav.n_premium")
    n_disc = one("pnav.n_discount")
    n_pnav = sum(f.value for f in bundle.by_metric("pnav.board.n"))
    if None not in (n_prem, n_disc) and n_pnav and n_prem + n_disc != n_pnav:
        problems.append(f"溢价{n_prem}+折价{n_disc} ≠ P/NAV 样本 {n_pnav}")

    return GateResult(
        id="G-NUM-02",
        ok=not problems,
        detail="；".join(problems) or "全部勾稽通过",
        failed=len(problems),
        samples=problems,
    )


# --------------------------------------------------------------------- 一致性


def unit_sanity(bundle: FactsBundle) -> GateResult:
    """G-UNIT-01：数值落在合理区间，防止"百分数存成小数"这类单位错误。"""
    problems: list[str] = []

    for f in bundle.by_metric("market.eq_return"):
        if not (-30 <= f.value <= 30):
            problems.append(f"全市场周收益 {f.value} 超出 [-30,30]，疑似单位错误")

    for f in bundle.by_metric("board.eq_return"):
        if not (-40 <= f.value <= 40):
            problems.append(f"板块 {f.params.get('board')} 等权收益 {f.value} 越界")

    for f in bundle.by_metric("turnover.rate"):
        if not (0 <= f.value <= 50):
            problems.append(f"换手率 {f.value} 越界")

    for f in bundle.by_metric("pnav.median"):
        if not (0.05 <= f.value <= 10):
            problems.append(f"P/NAV 中位数 {f.value} 越界")

    return GateResult(
        id="G-UNIT-01", ok=not problems,
        detail="；".join(problems) or "单位与量级正常",
        failed=len(problems), samples=problems,
    )


def board_consistency(quotes: pd.DataFrame) -> GateResult:
    """G-BOARD-01：同一代码在全篇只能属于一个板块。

    2026-W45 期事故的正面防线：当时第一章按底稿口径、1.5 按终端口径，
    同一只基金被算了两次、且分属不同板块，而两侧样本总数都是 94，
    只查总数根本发现不了。
    """
    dup = quotes.groupby("code")["board"].nunique()
    offenders = dup[dup > 1]
    detail = "每个代码仅一个板块" if offenders.empty else \
        f"{len(offenders)} 个代码对应多个板块: {list(offenders.index)[:5]}"
    return GateResult(
        id="G-BOARD-01", ok=offenders.empty, detail=detail,
        failed=int(len(offenders)),
    )


# --------------------------------------------------------------------- 时效


def point_in_time(bundle: FactsBundle, cutoff: str) -> GateResult:
    """G-PIT-01：所有事实的数据时点不得晚于信息截止时点。"""
    problems = []
    for f in bundle:
        asof = f.source.get("source_asof")
        if asof and asof > cutoff[:10]:
            problems.append(f"{f.metric} 数据时点 {asof} 晚于截止 {cutoff[:10]}")
    return GateResult(
        id="G-PIT-01", ok=not problems,
        detail="；".join(problems) or f"全部事实早于或等于 {cutoff[:10]}",
        failed=len(problems), samples=problems,
    )


# --------------------------------------------------------------------- 凭据


SECRET_PATTERNS = [
    (r"(?i)\b(api[_-]?key|secret|token|passwd|password)\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{12,}", "疑似密钥"),
    (r"gh[pousr]_[A-Za-z0-9]{20,}", "GitHub token"),
    (r"sk-[A-Za-z0-9]{20,}", "API key"),
    (r"(?i)https://[^/\s]+:[^@\s]+@", "URL 内嵌凭证"),
]


def secret_scan(root: Path, max_bytes: int = 2_000_000) -> GateResult:
    """G-SRC-01：仓库内不得含凭证。扫描文本类文件，跳过 .git 与二进制。"""
    skip_dirs = {".git", ".venv", "__pycache__", ".pytest_cache", "node_modules"}
    text_ext = {".py", ".md", ".yaml", ".yml", ".json", ".csv", ".txt", ".ps1", ".sh", ".toml"}
    hits: list[str] = []
    scanned = 0

    for p in Path(root).rglob("*"):
        if any(part in skip_dirs for part in p.parts):
            continue
        if not p.is_file() or p.suffix.lower() not in text_ext:
            continue
        try:
            if p.stat().st_size > max_bytes:
                continue
            content = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        scanned += 1
        for pattern, why in SECRET_PATTERNS:
            if re.search(pattern, content):
                hits.append(f"{p.relative_to(root)}: {why}")

    return GateResult(
        id="G-SRC-01", ok=not hits,
        detail=f"扫描 {scanned} 个文本文件，" + ("发现疑似凭证" if hits else "未发现凭证"),
        checked=scanned, failed=len(hits), samples=hits[:10],
    )


# --------------------------------------------------------------------- 结构


REQUIRED_SECTIONS = ["0.1", "0.2", "0.3", "1.1", "1.2", "1.3",
                     "1.4", "1.5", "2.1", "2.2", "2.3", "2.4", "2.5", "risk"]

DATA_GAP_MARKERS = ("数据缺口", "尚未接入")


def structure_check(sections: dict[str, str]) -> GateResult:
    """G-STYLE-01：章节齐全、风险提示只出现一次、数据缺口已显式标注。"""
    problems = []
    missing = [s for s in REQUIRED_SECTIONS if s not in sections]
    if missing:
        problems.append(f"缺章节: {missing}")

    # 样张在摘要末尾与文末各写了一次风险提示，属于冗余。
    # 本规则要求：正文各节内不得重复出现，风险提示只在文末章节出现一次。
    body_repeats = sum(
        text.count("风险提示") for sid, text in sections.items() if sid != "risk"
    )
    if body_repeats != 0:
        problems.append(f"正文中重复出现'风险提示' {body_repeats} 次，应只在文末出现")

    gaps = [sid for sid, text in sections.items()
            if any(m in text for m in DATA_GAP_MARKERS)]
    detail = "；".join(problems) if problems else f"结构完整；{len(gaps)} 节标注数据缺口"
    return GateResult(
        id="G-STYLE-01", ok=not problems, detail=detail,
        failed=len(problems), samples=problems + [f"数据缺口节: {gaps}"],
    )


def run_all(
    sections: dict[str, str],
    bundle: FactsBundle,
    quotes: pd.DataFrame,
    cutoff: str,
    repo_root: Path,
) -> list[GateResult]:
    """按顺序跑全部硬门禁。任一失败即应阻断推进。"""
    return [
        numeric_audit(sections, bundle),
        crossfoot(bundle),
        unit_sanity(bundle),
        board_consistency(quotes),
        point_in_time(bundle, cutoff),
        structure_check(sections),
        secret_scan(repo_root),
    ]
