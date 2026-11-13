"""Critic —— 独立于起草方的评审。

为什么需要它
------------
门禁只能判断"可判定的事实"：数字对不对得上、合计是否勾稽、有没有用未来信息。
但报告的另一半价值在于**论证是否成立**，这没有唯一答案，需要判断。Critic 负责这一半。

规则版 vs 模型版
----------------
当前实现是**规则版**：用可解释的启发式给五个维度打分。它不如模型细腻，但有三个
模型版给不了的优点：可复现（同一稿必得同一分）、可审计（每条扣分都说得清依据）、
零依赖（不需要 API key，CI 里能跑）。

接入模型时只需替换 ``_score_*`` 的实现，接口与产物格式不变。这也是刻意的设计：
评审标准不该随评审者的实现方式而变。

独立性怎么保证
--------------
Critic 只拿到三样东西：成稿文本、事实库、上期观点台账。它看不到起草者的推理过程，
也看不到草稿的中间版本。这与"经理让作者自己校对"是两件事。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

from ..facts import FactsBundle

#: 判定"这句是断言"的标记词
CLAIM_MARKERS = ("我们认为", "判断", "说明", "意味着", "反映", "表明", "指向", "预计")

#: 绝对化措辞。研究报告里出现这类词通常意味着过度自信。
ABSOLUTE_WORDS = ("必然", "一定", "肯定会", "毫无疑问", "必将", "毫无疑问会", "断然")

#: 条件化措辞。有条件的判断比无条件判断更可靠。
CONDITION_WORDS = ("如果", "若", "取决于", "前提是", "在…情况下", "则需要", "有待验证", "需要观察")

#: 口径声明词。涉及板块收益或 P/NAV 时应出现。
CALIBER_WORDS = ("口径", "等权", "市值加权", "不复权", "含分红", "可比样本")

PASS_SCORE = 3.5


@dataclass
class SectionReview:
    sid: str
    logic: int
    evidence: int
    caliber: int
    restraint: int
    continuity: int
    issues: list[str] = field(default_factory=list)

    @property
    def mean(self) -> float:
        vals = [self.logic, self.evidence, self.caliber, self.restraint, self.continuity]
        return round(sum(vals) / len(vals), 2)

    def as_dict(self) -> dict:
        d = asdict(self)
        d["mean"] = self.mean
        return d


@dataclass
class CriticReport:
    sections: list[SectionReview]
    overall: float
    verdict: str
    high_issues: list[str]

    def as_dict(self) -> dict:
        return {
            "overall": self.overall,
            "verdict": self.verdict,
            "high_issues": self.high_issues,
            "sections": [s.as_dict() for s in self.sections],
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2)


def _count(text: str, words: tuple[str, ...]) -> int:
    return sum(text.count(w) for w in words)


def _has_number(text: str) -> bool:
    return bool(re.search(r"\d", text))


def _score_logic(text: str, sid: str) -> tuple[int, list[str]]:
    """逻辑链：有证据（数字）也有结论（判断句）才算完整。"""
    issues: list[str] = []
    score = 5
    if not _has_number(text) and sid != "risk":
        score -= 2
        issues.append("本节无任何数据支撑")
    if _count(text, CLAIM_MARKERS) == 0 and sid not in ("risk", "1.2"):
        score -= 1
        issues.append("缺少明确判断句，偏于资料罗列")
    if len(text) < 80 and sid not in ("risk", "1.2"):
        score -= 1
        issues.append("篇幅过短，论证可能不充分")
    return max(1, score), issues


def _score_evidence(text: str, facts: FactsBundle) -> tuple[int, list[str]]:
    """证据边界：事实与推断是否分清。"""
    issues: list[str] = []
    score = 5
    hedges = ("可能", "或许", "有待", "尚待", "需要观察", "不确定", "未必", "或")
    claims = _count(text, CLAIM_MARKERS)
    if claims >= 2 and _count(text, hedges) == 0:
        score -= 2
        issues.append("多处判断但无任何不确定性表述，事实与推断边界模糊")
    if "属于事后归因" not in text and "归因" in text and "验证" not in text:
        score -= 1
        issues.append("使用归因表述但未说明其局限")
    return max(1, score), issues


def _score_caliber(text: str) -> tuple[int, list[str]]:
    """口径声明：涉及口径敏感的指标时必须写明。"""
    issues: list[str] = []
    score = 5
    # "全收益"不列入：它是具体指数名称的组成部分，自身已说明口径，
    # 把它算作"未声明口径"会产生大量误报，久了就没人看告警了。
    sensitive = ("等权", "P/NAV", "换手率", "溢价", "折价")
    hits = sum(text.count(k) for k in sensitive)
    if hits > 0 and _count(text, CALIBER_WORDS) == 0:
        score -= 2
        issues.append("提及口径敏感指标但未声明口径")
    return max(1, score), issues


def _score_restraint(text: str) -> tuple[int, list[str]]:
    """克制：避免绝对化断言与无条件的预测。"""
    issues: list[str] = []
    score = 5
    absolutes = _count(text, ABSOLUTE_WORDS)
    if absolutes:
        score -= min(3, absolutes * 2)
        issues.append(f"出现 {absolutes} 处绝对化措辞，研究报告宜留有余地")
    if "将" in text and _count(text, CONDITION_WORDS) == 0:
        score -= 1
        issues.append("含预测性表述但未给出条件或验证方式")
    return max(1, score), issues


#: 只有这几节承载"判断"，才需要交代与上期观点（J-*）的关系。
#: 描述性章节（1.1 行情、1.4 成交、2.1 利率）不必逐节回顾上期判断。
JUDGMENT_SECTIONS = {"0.1", "0.2", "0.3", "2.5"}


def _score_continuity(text: str, opinions: dict, sid: str) -> tuple[int, list[str]]:
    """连续性：判断性章节是否交代了与上期观点的关系。"""
    if sid not in JUDGMENT_SECTIONS:
        return 5, []
    if not opinions:
        return 4, ["无上期观点台账，连续性无从比对"]      # 首期，不算错
    markers = ("维持", "延续", "强化", "削弱", "撤销", "不变", "修正")
    if _count(text, markers) == 0:
        return 3, ["未说明与上期判断的关系（维持/强化/削弱/撤销）"]
    return 5, []


def review(
    sections: dict[str, str],
    facts: FactsBundle,
    opinions: dict | None = None,
) -> CriticReport:
    """对全篇逐节评审，返回报告。"""
    opinions = opinions or {}
    reviews: list[SectionReview] = []

    for sid, text in sections.items():
        if sid in ("1.2",):          # 纯表格节，不参与文字评审
            continue
        logic, i1 = _score_logic(text, sid)
        evidence, i2 = _score_evidence(text, facts)
        caliber, i3 = _score_caliber(text)
        restraint, i4 = _score_restraint(text)
        continuity, i5 = _score_continuity(text, opinions, sid)
        reviews.append(
            SectionReview(
                sid=sid, logic=logic, evidence=evidence, caliber=caliber,
                restraint=restraint, continuity=continuity,
                issues=i1 + i2 + i3 + i4 + i5,
            )
        )

    if not reviews:
        return CriticReport([], 0.0, "reject", ["无任何可评审的章节"])

    # 极短章节直接判不通过。分数是各维度均值，一处致命缺陷会被其他维度的
    # 满分稀释掉——"好。"这种只剩一句话的章节，均分仍有 4.0，但它显然不成立。
    too_short = [
        f"[{sid}] 正文仅 {len(text)} 字，不足以构成论证"
        for sid, text in sections.items()
        if sid not in ("risk", "1.2") and len(text.strip()) < 60
    ]

    overall = round(sum(r.mean for r in reviews) / len(reviews), 2)
    high = [f"[{r.sid}] {msg}" for r in reviews if r.mean < 3.0 for msg in r.issues]
    high += too_short
    verdict = "accept" if overall >= PASS_SCORE and not high else "revise"

    return CriticReport(reviews, overall, verdict, high)


def load_opinions(path: Path) -> dict:
    """读取上期观点台账。文件不存在时返回空（首期情形）。"""
    path = Path(path)
    if not path.exists():
        return {}
    try:
        import yaml

        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
