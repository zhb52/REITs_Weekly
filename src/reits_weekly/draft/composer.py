"""草稿占位符的替换。

占位符语法
----------
草稿里不写阿拉伯数字，只写占位符，由本模块替换成事实库的 ``display``：

    {{M:turnover.rate}}                     唯一指标，直接写
    {{M:board.eq_return|board=产业园区}}      带参数的指标，用 | 分隔 k=v
    {{M:pnav.board.median|board=水利设施}}    同上

为什么不用哈希型的 fact_id 直接写
--------------------------------
``fact_id`` 是 ``metric+params+case+input_hash`` 的哈希，人类和模型都无法在
写稿时知道它。若要求作者填哈希，等于强迫他去猜，必然出错。故草稿用**可读指标名**，
由本模块解析成 fact；解析结果同时记录"这一节用了哪些事实"，供审计与回溯。

``fact_id`` 仍然重要——它保证同口径重跑得到同一 ID，是版本比对与回滚的依据。

替换失败即报错
--------------
找不到指标、参数不匹配、或同一指标有多个候选而无法消歧，一律抛
``UnresolvedPlaceholder``，绝不静默留空或填 0。这正是"正文里每个数字都能
回溯到计算结果"这条硬门禁的实现基础。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..facts import FactsBundle

PLACEHOLDER_RE = re.compile(r"\{\{M:([^}]+)\}\}")


class UnresolvedPlaceholder(ValueError):
    """占位符无法解析。"""


@dataclass
class Resolved:
    text: str
    used: list[str]           # 用到的 fact_id
    unresolved: list[str]


def _parse_token(token: str) -> tuple[str, dict]:
    token = token.strip()
    if "|" not in token:
        return token, {}
    metric, _, rest = token.partition("|")
    params = {}
    for part in rest.split("|"):
        if not part.strip():
            continue
        k, _, v = part.partition("=")
        params[k.strip()] = v.strip()
    return metric.strip(), params


def _lookup(bundle: FactsBundle, metric: str, params: dict):
    candidates = [
        f for f in bundle.by_metric(metric)
        if all(str(f.params.get(k)) == str(v) for k, v in params.items())
    ]
    if not candidates:
        raise UnresolvedPlaceholder(
            f"指标不存在: {metric} {params or ''}"
        )
    if len(candidates) > 1:
        raise UnresolvedPlaceholder(
            f"指标有 {len(candidates)} 个候选，请补充参数区分: {metric}"
        )
    return candidates[0]


def resolve(text: str, bundle: FactsBundle) -> Resolved:
    """把所有 ``{{M:...}}`` 替换为事实库的 display 字符串。"""
    used: list[str] = []
    unresolved: list[str] = []

    def _sub(match: re.Match) -> str:
        token = match.group(1)
        metric, params = _parse_token(token)
        try:
            fact = _lookup(bundle, metric, params)
        except UnresolvedPlaceholder:
            unresolved.append(token)
            return match.group(0)
        used.append(fact.id)
        return fact.display

    out = PLACEHOLDER_RE.sub(_sub, text)
    return Resolved(text=out, used=used, unresolved=unresolved)


def validate(text: str, bundle: FactsBundle) -> list[str]:
    """只检查不替换，返回无法解析的占位符列表。"""
    return resolve(text, bundle).unresolved
