"""事实库 —— 报告里每一个数字的唯一产地。

核心约束
--------
**正文只允许通过占位符 ``{{F:fact_id}}`` 引用数字，不允许直接写阿拉伯数字。**

这样做解决三个问题：

1. 数字一定来自确定性代码，不是模型"记得"或心算的结果；
2. 同一个指标在全篇只有一个 ``display`` 字符串，摘要与正文不会一个写 1.055、
   一个写 1.05；
3. 修订后如果计算口径变了，``fact_id`` 会因参数/输入 hash 变化而改变，
   旧的引用会自动失效，而不是悄悄指向一个过期数值。

``fact_id`` 由 ``metric + params + case_id + input_hash`` 派生。同一期、同一输入、
同一口径下重跑，ID 必须完全一致 —— ``tests/unit/test_facts.py`` 会锁死这一点，
它是"可复跑"的证据。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Any, Iterable

from .formatting import (
    fmt_bp,
    fmt_int,
    fmt_num,
    fmt_pct,
    fmt_ratio,
    fmt_yi,
    is_missing,
)

PLACEHOLDER_PATTERN = r"\{\{F:([A-Za-z0-9\-_]+)\}\}"


def make_fact_id(metric: str, params: dict, case_id: str, input_hash: str) -> str:
    """确定性 fact_id：同输入同口径必然同 ID。"""
    payload = json.dumps(
        {"m": metric, "p": params, "c": case_id, "h": input_hash},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return "F-" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:8]


def format_value(value: Any, unit: str, decimals: int) -> str:
    """按单位选择格式化函数，保证表、文、事实库一致。"""
    if is_missing(value):
        from .formatting import DASH

        return DASH
    if unit == "%":
        return fmt_pct(value, decimals)
    if unit == "bp":
        return fmt_bp(value, decimals)
    if unit == "ratio":
        return fmt_ratio(value, decimals)
    if unit == "亿元":
        return fmt_yi(value, decimals)
    if unit == "只":
        return fmt_int(value)
    if unit == "%no_sign":
        return fmt_pct(value, decimals, sign=False)
    return fmt_num(value, decimals)


@dataclass(frozen=True)
class Fact:
    id: str
    metric: str
    value: Any
    unit: str
    decimals: int
    display: str
    formula: str = ""
    params: dict = field(default_factory=dict)
    source: dict = field(default_factory=dict)
    section_hint: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        d = asdict(self)
        d["section_hint"] = list(self.section_hint)
        return d


class FactsBundle:
    """一期报告的全部事实。只增不改，创建后即冻结。"""

    def __init__(
        self,
        case_id: str,
        input_hash: str,
        facts: Iterable[Fact] | None = None,
    ) -> None:
        self.case_id = case_id
        self.input_hash = input_hash
        self._facts: dict[str, Fact] = {f.id: f for f in (facts or [])}

    # ------------------------------------------------------------ 写入

    def add(
        self,
        metric: str,
        value: Any,
        unit: str = "",
        decimals: int = 2,
        formula: str = "",
        params: dict | None = None,
        source: dict | None = None,
        section_hint: Iterable[str] = (),
    ) -> Fact:
        params = params or {}
        fid = make_fact_id(metric, params, self.case_id, self.input_hash)
        if fid in self._facts:
            existing = self._facts[fid]
            if existing.value != value:
                raise ValueError(
                    f"fact_id 冲突且数值不同: {metric} {existing.value} vs {value}"
                )
            return existing
        fact = Fact(
            id=fid,
            metric=metric,
            value=value,
            unit=unit,
            decimals=decimals,
            display=format_value(value, unit, decimals),
            formula=formula,
            params=params,
            source=source or {},
            section_hint=tuple(section_hint),
        )
        self._facts[fid] = fact
        return fact

    # ------------------------------------------------------------ 读取

    def __len__(self) -> int:
        return len(self._facts)

    def __iter__(self):
        return iter(self._facts.values())

    def get(self, fact_id: str) -> Fact:
        try:
            return self._facts[fact_id]
        except KeyError as exc:
            raise KeyError(
                f"未登记的事实 {fact_id}；正文引用了不存在或已失效的数字"
            ) from exc

    def by_metric(self, metric: str) -> list[Fact]:
        return [f for f in self._facts.values() if f.metric == metric]

    def displays(self) -> set[str]:
        """全部 display 字符串集合，供反查审计使用。"""
        return {f.display for f in self._facts.values()}

    # ------------------------------------------------------------ 序列化

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "input_hash": self.input_hash,
            "count": len(self._facts),
            "facts": sorted(
                (f.as_dict() for f in self._facts.values()), key=lambda x: x["metric"]
            ),
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> "FactsBundle":
        facts = [
            Fact(
                id=f["id"],
                metric=f["metric"],
                value=f["value"],
                unit=f["unit"],
                decimals=f["decimals"],
                display=f["display"],
                formula=f.get("formula", ""),
                params=f.get("params", {}),
                source=f.get("source", {}),
                section_hint=tuple(f.get("section_hint", [])),
            )
            for f in data["facts"]
        ]
        return cls(
            case_id=data["case_id"],
            input_hash=data["input_hash"],
            facts=facts,
        )
