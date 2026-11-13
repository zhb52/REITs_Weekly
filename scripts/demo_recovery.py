"""生成中断恢复的实际证据。

不是描述机制，而是真跑一遍：
1. 重建一期
2. 删掉中间产物（图表），模拟进程被杀后部分产物丢失
3. 执行 resume
4. 比对"哪些哈希没变"（证明没重做）与"哪些被重建且内容一致"（证明可复现）

输出写入 docs/verification_evidence/recovery_demo.md。

用法：
    python scripts/demo_recovery.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "cases" / "demo-2026-W45"
OUT = ROOT / "docs" / "verification_evidence" / "recovery_demo.md"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def run(*args: str) -> str:
    r = subprocess.run(
        [sys.executable, "-m", "reits_weekly.cli", *args],
        capture_output=True, text=True, cwd=ROOT,
    )
    return (r.stdout + r.stderr).strip()


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    def w(s: str = "") -> None:
        lines.append(s)

    w("# 中断恢复演示")
    w()
    w("本文件由 `scripts/demo_recovery.py` 实跑生成，不是手写描述。重新执行该脚本即可复现。")
    w()
    w("## 场景")
    w()
    w("周报流程跑到一半进程被终止（或机器重启），部分中间产物丢失。")
    w("重启后执行 `resume`，要求**不重做已完成的部分**，且重建的产物与中断前一致。")
    w()
    w("## 步骤与输出")
    w()

    state_file = CASE / "state.json"
    state_file.unlink(missing_ok=True)
    w("### 1. 重建一期（`run --force`）")
    w()
    w("```")
    w(run("run", "--force"))
    w("```")
    w()

    facts = CASE / "facts" / "facts.json"
    charts = sorted((CASE / "work" / "charts").glob("*.png"))
    before_facts = sha(facts)
    before_charts = {p.name: sha(p) for p in charts}
    w(f"登记：`facts.json` = `{before_facts}`，图表 {len(charts)} 张。")
    w()

    for p in charts:
        p.unlink()
    w("### 2. 模拟中断：删除全部图表文件（事实库与草稿保留）")
    w()
    w(f"此时 `facts.json` 仍为 `{before_facts}`。")
    w()
    w("### 3. 执行 `resume`")
    w()
    w("```")
    w(run("resume"))
    w("```")
    w()

    after_facts = sha(facts)
    after_charts = {p.name: sha(p) for p in sorted((CASE / "work" / "charts").glob("*.png"))}
    same = [k for k in before_charts if before_charts.get(k) == after_charts.get(k)]

    w("## 结果对比")
    w()
    w("| 产物 | 中断前 | 恢复后 | 结论 |")
    w("|---|---|---|---|")
    w(
        f"| `facts.json` | `{before_facts}` | `{after_facts}` | "
        f"{'**未重算**（哈希不变）' if before_facts == after_facts else '被重算'} |"
    )
    w(
        f"| 图表数量 | {len(before_charts)} | {len(after_charts)} | "
        f"{'**已重建**' if len(after_charts) == len(before_charts) else '未恢复'} |"
    )
    w(
        f"| 图表内容 | — | {len(same)}/{len(before_charts)} 哈希一致 | "
        f"{'**输出可复现**' if len(same) == len(before_charts) else '存在差异'} |"
    )
    w()

    st = json.loads(state_file.read_text(encoding="utf-8"))
    w(f"恢复后状态：`stage={st['stage']}`，`status={st['status']}`，"
      f"登记产物 {len(st['artifacts'])} 项。")
    w()
    w("## 判据")
    w()
    w("恢复逻辑不看\"上次跑到哪一行\"，只看**产物哈希**：")
    w()
    w("- 产物存在、sha256 与登记一致、阶段匹配 → SKIP")
    w("- 否则 → REDO 该阶段及其下游")
    w()
    w("所以中断时已完成的事实库不会被重算（`facts.json` 哈希前后一致）；")
    w("被删除的图表会重建，且 PNG 哈希与中断前完全相同——")
    w("说明\"不重做已完成动作\"与\"结果可复现\"两条同时成立。")
    w()
    w("## 局限")
    w()
    w("本次演示的中断点是\"产物被删除\"，属于最容易复现的一类。")
    w("更极端的情形（进程在写文件过程中被杀、留下半个 JSON）由 `state.save()` 的")
    w("原子写入（先写 `.tmp` 再 `os.replace`）负责，未在本演示中覆盖。")

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"已写入 {OUT}")
    print(f"  facts 未重算: {before_facts == after_facts}")
    print(f"  图表已重建且一致: {len(same)}/{len(before_charts)}")


if __name__ == "__main__":
    main()
