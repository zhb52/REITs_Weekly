"""命令行参数解析测试。

这一组来自一个真实缺陷：``--case`` 原先只挂在主解析器上，导致 README 里写的
``cli run --case X`` 直接报 "unrecognized arguments"——文档里的命令跑不起来。
公共参数现在同时挂在主解析器与各子命令上（子命令用 SUPPRESS 默认值，
避免覆盖主解析器已取到的值），两种写法都支持。
"""

from __future__ import annotations

import pytest

from reits_weekly import cli


def parse(argv: list[str]):
    return cli.build_parser().parse_args(argv)


def test_case_after_subcommand():
    """README 的写法。"""
    a = parse(["run", "--case", "2026-W46", "--force"])
    assert (a.cmd, a.case, a.force) == ("run", "2026-W46", True)


def test_case_before_subcommand():
    """兼容写法。"""
    a = parse(["--case", "2026-W46", "run"])
    assert (a.cmd, a.case) == ("run", "2026-W46")


def test_globals_absent_are_not_set():
    """两个层级都没给时不设值，交由 settings.yaml 兜底。"""
    a = parse(["status"])
    assert not hasattr(a, "case")
    assert not hasattr(a, "week_end")


def test_subcommand_overrides_global():
    a = parse(["--case", "A", "run", "--case", "B"])
    assert a.case == "B"


def test_approve_requires_by():
    with pytest.raises(SystemExit):
        parse(["approve"])


def test_week_override():
    a = parse(["run", "--week-start", "2026-11-09", "--week-end", "2026-11-13"])
    assert a.week_start == "2026-11-09"
    assert a.week_end == "2026-11-13"


def test_subcommands_registered():
    a = parse(["verify"])
    assert a.cmd == "verify"
