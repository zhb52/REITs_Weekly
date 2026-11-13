"""状态机与检查点。

设计要点
--------
1. **状态即文件**。``state.json`` 是唯一权威，对话记录、终端输出都不算数。
   这与"对话的最后一句不能证明任务完成"是同一条原则。
2. **原子写入**。先写 ``.tmp`` 再 ``os.replace``，避免断电/中断留下半个 JSON
   ——半个状态文件比没有状态文件更危险，它会让续跑基于错误的前提。
3. **产物带哈希**。每个阶段的产出记 ``sha256``，续跑时用它判断"这份产物还是不是
   当初那份"。哈希不符说明输入变了，必须重做，而不是接着往下走。
4. **三态终止**。``BLOCKED``（等外部条件，不自动重试）、``FAILED``（代码错）、
   ``ESCALATED``（额度用尽）。区分它们是因为处理方式完全不同：
   BLOCKED 该等人，FAILED 该改代码，ESCALATED 该由人决定是否放宽限制。
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any


class Stage(StrEnum):
    INIT = "INIT"
    INGEST = "INGEST"
    NORMALIZE = "NORMALIZE"
    COMPUTE = "COMPUTE"
    FACTS = "FACTS"
    CHART = "CHART"
    TABLES = "TABLES"
    DRAFT = "DRAFT"
    MERGE = "MERGE"
    CRITIC = "CRITIC"
    REVISE = "REVISE"
    HARD_GATES = "HARD_GATES"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    RENDER = "RENDER"
    QA = "QA"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class Status(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"
    DONE = "DONE"


#: 正常推进的顺序。REVISE 是回边，不在线性序列里。
FORWARD_ORDER = [
    Stage.INIT, Stage.INGEST, Stage.NORMALIZE, Stage.COMPUTE, Stage.FACTS,
    Stage.CHART, Stage.TABLES, Stage.DRAFT, Stage.MERGE, Stage.CRITIC,
    Stage.HARD_GATES, Stage.HUMAN_REVIEW, Stage.RENDER, Stage.QA,
    Stage.PUBLISHED, Stage.ARCHIVED,
]

TERMINAL_STATUS = {Status.DONE, Status.BLOCKED, Status.FAILED, Status.ESCALATED}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


@dataclass
class Artifact:
    path: str
    stage: str
    sha256: str
    bytes: int
    produced_at: str = field(default_factory=_now)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class CaseState:
    case_id: str
    pipeline_version: str = "0.1.0"
    stage: str = Stage.INIT.value
    status: str = Status.PENDING.value
    info_cutoff: str = ""
    input_hash: str = ""
    input_hashes: dict[str, str] = field(default_factory=dict)
    attempts: dict[str, int] = field(default_factory=dict)
    artifacts: list[dict] = field(default_factory=list)
    gates: dict[str, dict] = field(default_factory=dict)
    budget: dict[str, Any] = field(default_factory=dict)
    approvals: list[dict] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)
    blocked_reason: str = ""
    resume_hint: str = ""

    # ---------------------------------------------------------------- 持久化

    @staticmethod
    def path_for(case_dir: Path) -> Path:
        return Path(case_dir) / "state.json"

    @classmethod
    def load(cls, case_dir: Path) -> "CaseState":
        p = cls.path_for(case_dir)
        if not p.exists():
            raise FileNotFoundError(f"没有状态文件: {p}")
        return cls(**json.loads(p.read_text(encoding="utf-8")))

    @classmethod
    def load_or_new(cls, case_dir: Path, case_id: str) -> "CaseState":
        try:
            return cls.load(case_dir)
        except FileNotFoundError:
            return cls(case_id=case_id)

    def save(self, case_dir: Path) -> Path:
        """原子写入：先写临时文件再替换，避免留下半个 JSON。"""
        target = self.path_for(case_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(tmp, target)
        return target

    # ---------------------------------------------------------------- 推进

    def can_enter(self, stage: str) -> bool:
        """只允许按 FORWARD_ORDER 前进，或回退到 REVISE。"""
        if stage == Stage.REVISE:
            return self.stage in (Stage.CRITIC.value, Stage.REVISE.value)
        if self.stage == Stage.REVISE and stage == Stage.DRAFT:
            return True
        try:
            cur = FORWARD_ORDER.index(Stage(self.stage))
            nxt = FORWARD_ORDER.index(Stage(stage))
        except ValueError:
            return False
        return nxt == cur + 1

    def advance(self, stage: str, reason: str = "") -> None:
        self.history.append(
            {"at": _now(), "from": self.stage, "to": stage, "reason": reason}
        )
        self.stage = stage
        self.status = Status.RUNNING.value

    def bump_attempt(self, key: str) -> int:
        self.attempts[key] = self.attempts.get(key, 0) + 1
        return self.attempts[key]

    def block(self, reason: str, hint: str = "") -> None:
        self.status = Status.BLOCKED.value
        self.blocked_reason = reason
        self.resume_hint = hint
        self.history.append({"at": _now(), "event": "BLOCKED", "reason": reason})

    def fail(self, reason: str) -> None:
        self.status = Status.FAILED.value
        self.blocked_reason = reason
        self.history.append({"at": _now(), "event": "FAILED", "reason": reason})

    def escalate(self, reason: str) -> None:
        self.status = Status.ESCALATED.value
        self.blocked_reason = reason
        self.history.append({"at": _now(), "event": "ESCALATED", "reason": reason})

    # ---------------------------------------------------------------- 产物

    def record_artifact(self, path: Path, stage: str, case_dir: Path) -> dict:
        """登记产物并返回其清单项。路径存相对路径，便于整个目录搬迁。"""
        path = Path(path)
        rel = str(path.relative_to(case_dir)).replace("\\", "/")
        item = Artifact(
            path=rel,
            stage=stage,
            sha256=sha256_file(path),
            bytes=path.stat().st_size,
        ).as_dict()
        self.artifacts = [a for a in self.artifacts if a["path"] != rel] + [item]
        return item

    def find_artifact(self, rel_path: str) -> dict | None:
        for a in self.artifacts:
            if a["path"] == rel_path:
                return a
        return None

    def is_fresh(self, path: Path, stage: str, case_dir: Path) -> bool:
        """产物是否仍与登记时一致 —— 续跑时据此决定 SKIP 还是 REDO。"""
        path = Path(path)
        if not path.exists():
            return False
        rel = str(path.relative_to(case_dir)).replace("\\", "/")
        item = self.find_artifact(rel)
        if item is None or item["stage"] != stage:
            return False
        return item["sha256"] == sha256_file(path)

    # ---------------------------------------------------------------- 审批

    def add_approval(self, gate: str, by: str, decision: str,
                     artifact_sha256: str = "", comment: str = "") -> None:
        """记录审批。绑定被批准对象的哈希，防止批完再改。"""
        self.approvals.append(
            {
                "gate": gate,
                "by": by,
                "decision": decision,
                "artifact_sha256": artifact_sha256,
                "comment": comment,
                "at": _now(),
            }
        )

    def has_approval(self, gate: str, artifact_sha256: str | None = None) -> bool:
        for a in self.approvals:
            if a["gate"] != gate or a["decision"] != "approve":
                continue
            if artifact_sha256 is None or a["artifact_sha256"] == artifact_sha256:
                return True
        return False
