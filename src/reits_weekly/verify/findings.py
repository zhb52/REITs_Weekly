"""问题台账（finding ledger）。

要解决的问题
------------
门禁每轮都会重新检查、重新输出一份结果。如果只是覆盖写 ``gates.json``，
就会丢掉一件事：**上一轮发现、这一轮没再出现的问题，是"已修复"还是"这轮没查到"？**

这两种情形完全不同。前者可以关闭，后者必须继续挂在账上——
否则修订循环会变成"每轮只解决当轮被提到的问题"，问题就这么一个个漏过去了。

机制
----
每条问题由 ``gate_id + 内容`` 派生一个稳定 ID。台账跨轮累积：

* 本轮再次出现 → 更新 ``last_seen_round``，状态保持 ``open``
* 本轮未出现 → 标记 ``closed``，记录关闭轮次
* 已关闭的问题若在后续轮次重现 → 重新置为 ``open``，``reopen_count`` 加一

``reopen_count`` 是有意义的信号：一个问题反复开关，说明修订只是在掩盖症状。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path


def _fid(gate_id: str, text: str) -> str:
    return "F-" + hashlib.sha1(f"{gate_id}|{text}".encode("utf-8")).hexdigest()[:8]


@dataclass
class Finding:
    id: str
    gate: str
    text: str
    status: str = "open"          # open | closed
    first_seen_round: int = 1
    last_seen_round: int = 1
    closed_round: int | None = None
    reopen_count: int = 0

    def as_dict(self) -> dict:
        return {
            "id": self.id, "gate": self.gate, "text": self.text,
            "status": self.status, "first_seen_round": self.first_seen_round,
            "last_seen_round": self.last_seen_round,
            "closed_round": self.closed_round, "reopen_count": self.reopen_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Finding":
        return cls(**d)


class FindingLedger:
    def __init__(self, findings: dict[str, Finding] | None = None, round_no: int = 0):
        self._f: dict[str, Finding] = findings or {}
        self.round = round_no

    # ------------------------------------------------------------ 持久化

    @classmethod
    def load(cls, path: Path) -> "FindingLedger":
        path = Path(path)
        if not path.exists():
            return cls()
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            {d["id"]: Finding.from_dict(d) for d in raw.get("findings", [])},
            round_no=int(raw.get("round", 0)),
        )

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "round": self.round,
            "open": len(self.open()),
            "closed": len(self.closed()),
            "findings": sorted((f.as_dict() for f in self._f.values()),
                               key=lambda x: (x["status"] != "open", x["first_seen_round"], x["id"])),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    # ------------------------------------------------------------ 更新

    def begin_round(self) -> int:
        self.round += 1
        return self.round

    def record(self, gate: str, texts: list[str]) -> None:
        """登记本轮出现的问题；未出现但仍是 open 的，标记为关闭。"""
        seen: set[str] = set()
        for text in texts:
            if not text:
                continue
            fid = _fid(gate, text)
            seen.add(fid)
            if fid in self._f:
                f = self._f[fid]
                f.last_seen_round = self.round
                if f.status == "closed":
                    f.status = "open"
                    f.closed_round = None
                    f.reopen_count += 1
            else:
                self._f[fid] = Finding(
                    id=fid, gate=gate, text=text,
                    first_seen_round=self.round, last_seen_round=self.round,
                )

        for fid, f in self._f.items():
            if f.status == "open" and fid not in seen and f.last_seen_round < self.round:
                f.status = "closed"
                f.closed_round = self.round

    # ------------------------------------------------------------ 查询

    def open(self) -> list[Finding]:
        return [f for f in self._f.values() if f.status == "open"]

    def closed(self) -> list[Finding]:
        return [f for f in self._f.values() if f.status == "closed"]

    def reopened(self) -> list[Finding]:
        return [f for f in self._f.values() if f.reopen_count > 0]

    def summary(self) -> dict:
        return {
            "round": self.round,
            "open": len(self.open()),
            "closed": len(self.closed()),
            "reopened": len(self.reopened()),
            "open_texts": [f.text for f in self.open()][:10],
        }
