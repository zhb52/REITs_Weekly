"""生成验证汇总。

汇总里的每个数字都来自实际执行结果，不是手写的：
测试数取自 pytest 输出、门禁结果取自 qa/gates.json、Critic 取自 qa/critic.json、
凭证扫描现跑一遍、仓库统计取自 git。

用法：
    python scripts/gen_verification_summary.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "cases" / "demo-2026-W45"
OUT = ROOT / "docs" / "verification_evidence" / "verification_summary.md"

GATE_NAMES = {
    "G-NUM-01": "正文数字可回溯",
    "G-NUM-02": "合计勾稽",
    "G-UNIT-01": "数值量级",
    "G-BOARD-01": "板块归属唯一",
    "G-PIT-01": "信息时效",
    "G-STYLE-01": "结构完整",
    "G-SRC-01": "凭证扫描",
    "G-SRC-02": "数据源白名单",
}


def sh(*args: str) -> str:
    r = subprocess.run(args, capture_output=True, text=True, cwd=ROOT)
    return (r.stdout + r.stderr).strip()


def main() -> None:
    L: list[str] = []

    def w(s: str = "") -> None:
        L.append(s)

    w("# 验证汇总")
    w()
    w("本文件由 `scripts/gen_verification_summary.py` 实跑生成，数字均为实际执行结果。")
    w("重新执行该脚本即可刷新。")
    w()

    # ---------------------------------------------------------- 测试
    r = subprocess.run([sys.executable, "-m", "pytest", "-q"],
                       capture_output=True, text=True, cwd=ROOT)
    summary = [x for x in r.stdout.strip().splitlines() if x.strip()][-1]
    w("## 1. 测试")
    w()
    w("```")
    w("$ pytest -q")
    w(summary)
    w("```")
    w(f"退出码 {r.returncode}（0 = 全部通过）")
    w()

    # ---------------------------------------------------------- 门禁
    gate_file = CASE / "qa" / "gates.json"
    w("## 2. 硬门禁")
    w()
    if gate_file.exists():
        gl = json.loads(gate_file.read_text(encoding="utf-8"))
        w("| 门禁 | 检查内容 | 结果 |")
        w("|---|---|---|")
        for g in gl:
            mark = "通过" if g["ok"] else "**未通过**"
            w(f"| `{g['id']}` | {GATE_NAMES.get(g['id'], '')} | {mark} |")
        passed = sum(1 for g in gl if g["ok"])
        num = next((g for g in gl if g["id"] == "G-NUM-01"), None)
        w()
        w(f"{passed}/{len(gl)} 通过。")
        if num:
            w(f"数字审计共检查 {num['checked']} 个数字，{num['failed']} 个无法回溯。")
        w()
    else:
        w("（未运行）")
        w()

    # ---------------------------------------------------------- Critic
    critic_file = CASE / "qa" / "critic.json"
    w("## 3. Critic 评审")
    w()
    if critic_file.exists():
        c = json.loads(critic_file.read_text(encoding="utf-8"))
        w(f"全篇均分 **{c['overall']}**，结论 `{c['verdict']}`，"
          f"高优问题 {len(c['high_issues'])} 条。")
        w()
        w("| 章节 | 逻辑 | 证据 | 口径 | 克制 | 连续 | 均分 |")
        w("|---|---|---|---|---|---|---|")
        for s in c["sections"]:
            w(f"| {s['sid']} | {s['logic']} | {s['evidence']} | {s['caliber']} "
              f"| {s['restraint']} | {s['continuity']} | {s['mean']} |")
        w()
    else:
        w("（未运行）")
        w()

    # ---------------------------------------------------------- 凭证
    sys.path.insert(0, str(ROOT / "src"))
    from reits_weekly.verify import gates as gmod

    sc = gmod.secret_scan(ROOT, config_dir=str(ROOT / "config"))
    w("## 4. 凭证检查")
    w()
    w(f"工作区文本文件扫描：{sc.detail}。")
    w()
    hist = sh("git", "log", "-p", "--all")
    pat = re.compile(
        r"(api[_-]?key|token|password|secret)[ \t]*[=:][ \t]*['\"]?[A-Za-z0-9_-]{12,}"
        r"|sk-[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,}"
        r"|https://[^/ ]+:[^@ ]+@",
        re.I,
    )
    hits = pat.findall(hist)
    w(f"完整提交历史扫描（`git log -p --all`）：{'未发现凭证' if not hits else f'发现 {len(hits)} 处'}。")
    w()

    # ---------------------------------------------------------- 仓库
    cnt = sh("git", "rev-list", "--count", "HEAD")
    files = sh("git", "ls-files").splitlines()
    fsck = sh("git", "fsck", "--no-progress")
    shallow = sh("git", "rev-parse", "--is-shallow-repository")
    w("## 5. 仓库")
    w()
    w("| 项 | 值 |")
    w("|---|---|")
    w(f"| 提交数 | {cnt} |")
    w(f"| 跟踪文件 | {len(files)} |")
    w(f"| 完整性 | {'`git fsck` 无输出（无损坏）' if not fsck else '**存在问题**'} |")
    w(f"| 浅克隆 | {'是（不合格）' if shallow == 'true' else '否'} |")
    w()

    # ---------------------------------------------------------- 结论
    w("## 结论")
    w()
    parts = [f"测试 `{summary}`"]
    if gate_file.exists():
        parts.append(f"门禁 {sum(1 for g in gl if g['ok'])}/{len(gl)} 通过")
    if critic_file.exists():
        parts.append(f"Critic 均分 {c['overall']}")
    parts.append("工作区与完整历史均未发现凭证" if not hits else "历史中发现疑似凭证")
    w("；".join(parts) + "。")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"已写入 {OUT}")


if __name__ == "__main__":
    main()
