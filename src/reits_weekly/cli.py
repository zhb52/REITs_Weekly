"""命令行入口。

    python -m reits_weekly.cli run      --case demo-2026-W45
    python -m reits_weekly.cli status   --case demo-2026-W45
    python -m reits_weekly.cli approve  --case demo-2026-W45 --by 周豪波
    python -m reits_weekly.cli verify   --case demo-2026-W45

设计上刻意让 ``run`` 与 ``approve`` 分离：跑完门禁后流程会停在人工审批节点，
必须显式 approve 才会出稿。这不是麻烦，而是作业要求的"有后果动作前人工审批"
的落点——报告一旦发出，观点就代表作者，不能由流程自动决定。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import controller


def _cfg(args) -> controller.RunConfig:
    """先读 config/settings.yaml 作为默认，再用命令行显式参数覆盖。"""
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[2]
    cfg = controller.RunConfig.from_config(root, case_id=args.case)
    if args.source:
        cfg.source = args.source
    if args.week_start:
        cfg.week_start = args.week_start
    if args.week_end:
        cfg.week_end = args.week_end
    if args.week_prev:
        cfg.week_prev_end = args.week_prev
    if args.cutoff:
        cfg.info_cutoff = args.cutoff
    return cfg


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="reits-weekly", description="公募REITs周报自动化")
    ap.add_argument("--root", help="项目根目录，默认自动推断")
    ap.add_argument("--case", default=None, help="期次标识，默认读 config/settings.yaml")
    ap.add_argument("--source", default=None, help="数据源，默认 fixture")
    ap.add_argument("--week-start", default=None)
    ap.add_argument("--week-end", default=None)
    ap.add_argument("--week-prev", default=None)
    ap.add_argument("--cutoff", default=None,
                    help="信息截止时点，晚于此的公告不得使用；默认读配置")

    sub = ap.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="执行一期")
    p_run.add_argument("--force", action="store_true", help="忽略检查点，全部重跑")

    sub.add_parser("resume", help="从中断处继续（与 run 等价，语义更明确）")
    sub.add_parser("status", help="查看状态")

    p_appr = sub.add_parser("approve", help="记录人工审批")
    p_appr.add_argument("--by", required=True, help="审批人")
    p_appr.add_argument("--comment", default="", help="审批意见")

    p_ver = sub.add_parser("verify", help="只跑门禁，不出稿")
    p_ver.add_argument("--json", action="store_true", help="输出 JSON")

    args = ap.parse_args(argv)
    cfg = _cfg(args)

    if args.cmd in ("run", "resume"):
        force = getattr(args, "force", False)
        state = controller.run(cfg, force=force)
        info = controller.status(cfg)
        print(f"[{info['stage']}] {info['status']}  产物 {info['artifacts']} 项")
        if info["gates"]:
            bad = [k for k, v in info["gates"].items() if not v]
            print("门禁：" + ("全部通过" if not bad else f"未通过 {bad}"))
        if info["blocked_reason"]:
            print(f"原因：{info['blocked_reason']}")
        return 0 if info["status"] in ("DONE", "BLOCKED") else 1

    if args.cmd == "status":
        print(json.dumps(controller.status(cfg), ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "approve":
        state = controller.approve(cfg, by=args.by, comment=args.comment)
        print(f"已记录审批：{args.by}，共 {len(state.approvals)} 条")
        print("现在可以再次运行 run 以生成终稿。")
        return 0

    if args.cmd == "verify":
        case_dir = cfg.case_dir()
        gate_file = case_dir / "qa" / "gates.json"
        if not gate_file.exists():
            print("尚无门禁结果，请先运行 run", file=sys.stderr)
            return 2
        data = json.loads(gate_file.read_text(encoding="utf-8"))
        for r in data:
            mark = "PASS" if r["ok"] else "FAIL"
            print(f"{mark}  {r['id']}  {r['detail']}")
        return 0 if all(r["ok"] for r in data) else 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
