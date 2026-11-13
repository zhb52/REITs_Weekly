"""板块映射 —— 把数据源里的各种叫法收敛到唯一规范名。

三层优先级（高到低）：
1. ``boards.yaml`` 的 ``overrides``（按基金代码显式指定，附理由与决定人）
2. ``fund_registry.csv`` 的登记值（按代码查表）
3. ``boards.yaml`` 的 ``aliases``（按数据源给出的板块名匹配）

任何一层都匹配不上时抛 ``UnknownBoardError``，而不是静默归入"其他"。
静默兜底是分类漂移最常见的来源 —— 2026-W45 期同一只基金在第一章与 1.5 被归入
不同板块，正是因为两处各自沿用了不同数据源的原始分类，且都没有报错。
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml


class UnknownBoardError(ValueError):
    """数据源给出的板块名无法映射到规范板块。"""


class UnknownFundError(KeyError):
    """基金代码不在登记表中。"""


@dataclass(frozen=True)
class Board:
    name: str
    key: str
    asset_class: str
    order: int


@dataclass
class BoardDictionary:
    boards: dict[str, Board]
    aliases: dict[str, str]
    overrides: dict[str, str]
    registry: dict[str, dict]

    # ---------------------------------------------------------------- 载入

    @classmethod
    def load(cls, config_dir: Path | str) -> "BoardDictionary":
        config_dir = Path(config_dir)
        raw = yaml.safe_load((config_dir / "boards.yaml").read_text(encoding="utf-8"))

        boards = {
            b["name"]: Board(
                name=b["name"],
                key=b["key"],
                asset_class=b["asset_class"],
                order=int(b["order"]),
            )
            for b in raw["boards"]
        }
        aliases = {str(k): str(v) for k, v in (raw.get("aliases") or {}).items()}

        overrides: dict[str, str] = {}
        for o in raw.get("overrides") or []:
            code = str(o["code"]).zfill(6)
            target = o["board"]
            if target not in boards:
                raise UnknownBoardError(f"override 指向未知板块: {target}")
            overrides[code] = target

        registry: dict[str, dict] = {}
        reg_path = config_dir / "fund_registry.csv"
        if reg_path.exists():
            with reg_path.open(encoding="utf-8", newline="") as fh:
                for row in csv.DictReader(fh):
                    code = str(row["code"]).zfill(6)
                    registry[code] = row

        return cls(boards=boards, aliases=aliases, overrides=overrides, registry=registry)

    # ---------------------------------------------------------------- 查询

    def canonical(self, raw_board: str) -> str:
        """把数据源板块名映射为规范名。"""
        if raw_board in self.boards:
            return raw_board
        alias = self.aliases.get(raw_board)
        if alias is None:
            raise UnknownBoardError(
                f"未登记的板块名: {raw_board!r}；"
                f"请在 config/boards.yaml 的 aliases 中补充映射"
            )
        return alias

    def board_for_code(self, code: str) -> str | None:
        """按代码查规范板块，优先级 override > registry。"""
        code = str(code).zfill(6)
        if code in self.overrides:
            return self.overrides[code]
        row = self.registry.get(code)
        if row:
            return self.canonical(row["board"])
        return None

    def ordered_names(self) -> list[str]:
        """按 1.2 表展示顺序返回板块名。"""
        return [b.name for b in sorted(self.boards.values(), key=lambda b: b.order)]

    def asset_class_of(self, board_name: str) -> str:
        return self.boards[board_name].asset_class

    # ---------------------------------------------------------------- 应用

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        """给 DataFrame 补上规范 ``board`` 列与 ``asset_class``（若缺失）。

        解析顺序：先按代码查登记表，再退回按 ``board_raw`` 做别名映射。
        两者都失败则抛错，便于第一时间发现新增标的。
        """
        out = df.copy()
        resolved: list[str] = []
        unmatched: list[str] = []

        for _, row in out.iterrows():
            code = str(row.get("code", "")).zfill(6)
            board = self.board_for_code(code)
            if board is None and row.get("board_raw"):
                board = self.canonical(str(row["board_raw"]))
            if board is None:
                unmatched.append(code)
                board = ""
            resolved.append(board)

        if unmatched:
            raise UnknownFundError(
                f"以下代码既不在 fund_registry.csv 中，也无可用的 board_raw: {unmatched}"
            )

        out["board"] = resolved
        if "asset_class" not in out.columns or out["asset_class"].isna().any():
            out["asset_class"] = out["board"].map(self.asset_class_of)
        return out

    def conflicts(self, df: pd.DataFrame) -> list[dict]:
        """检测数据源分类与登记表不一致的情况，供 QA 记录（不阻断）。

        这类差异不一定是错误（数据源分类体系本就不同），但必须显式记录，
        否则跨章口径漂移会悄无声息地发生。
        """
        found = []
        for _, row in df.iterrows():
            code = str(row.get("code", "")).zfill(6)
            raw_board = row.get("board_raw")
            if not raw_board:
                continue
            try:
                raw_canonical = self.canonical(str(raw_board))
            except UnknownBoardError:
                found.append({"code": code, "raw": raw_board, "resolved": None, "reason": "unknown_board"})
                continue
            resolved = self.board_for_code(code) or raw_canonical
            if raw_canonical != resolved:
                found.append(
                    {
                        "code": code,
                        "name": row.get("name", ""),
                        "raw": raw_board,
                        "raw_canonical": raw_canonical,
                        "resolved": resolved,
                        "reason": "override_or_registry",
                    }
                )
        return found
