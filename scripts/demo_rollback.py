"""回滚演示：改动被基线测试拦下，回滚后恢复。

作业要求"对固定基线测试改动、接受或拒绝、记录版本、并能回滚"。
本脚本在临时克隆里真做一遍，输出写入 docs/verification_evidence/rollback_demo.md。
不动主仓库。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "verification_evidence" / "rollback_demo.md"


def sh(*args: str, cwd: Path) -> tuple[int, str]:
    r = subprocess.run(args, capture_output=True, text=True, cwd=cwd)
    return r.returncode, (r.stdout + r.stderr).strip()


def main() -> None:
    lines: list[str] = []

    def w(s: str = "") -> None:
        lines.append(s)

    w("# 回滚演示")
    w()
    w("本文件由 `scripts/demo_rollback.py` 在**临时克隆**中实跑生成，主仓库不受影响。")
    w()
    w("演示的问题：把换手率口径从 `TR-01` 改回报告原来的写法（少除一次交易日数），")
    w("看基线测试是否拦得住，以及回滚是否干净。")
    w()

    tmp = Path(tempfile.mkdtemp(prefix="reits-rollback-"))
    try:
        sh("git", "clone", "--quiet", str(ROOT), str(tmp / "repo"), cwd=ROOT.parent)
        repo = tmp / "repo"

        w("## 1. 建立基线")
        w()
        code, tag = sh("git", "tag", "-f", "baseline-v0.1.0", "HEAD", cwd=repo)
        _, head = sh("git", "rev-parse", "--short", "HEAD", cwd=repo)
        w(f"```\n{tag or 'tag baseline-v0.1.0 -> ' + head}\n```")
        w()
        w(f"基线提交：`{head}`")
        w()

        w("## 2. 基线测试（改动前）")
        w()
        code, out = sh(sys.executable, "-m", "pytest", "-q", "tests/unit", cwd=repo)
        w("```")
        w(out.strip().splitlines()[-1])
        w("```")
        w(f"退出码 {code}（0 = 通过）")
        w()

        w("## 3. 提交一处口径改动：TR-01 少除交易日数")
        w()
        liq = repo / "src" / "reits_weekly" / "compute" / "liquidity.py"
        before = liq.read_text(encoding="utf-8")
        after = before.replace(
            "return turnover_week / mktcap_float / n_days * 100.0",
            "return turnover_week / mktcap_float * 100.0",
        )
        assert after != before, "替换未生效"
        liq.write_text(after, encoding="utf-8")
        sh("git", "add", "-A", cwd=repo)
        sh("git", "commit", "-q", "-m", "change: drop trading-day divisor from TR-01", cwd=repo)
        _, bad_head = sh("git", "rev-parse", "--short", "HEAD", cwd=repo)
        w(f"改动提交：`{bad_head}`")
        w()

        w("## 4. 对基线跑测试")
        w()
        code2, out2 = sh(sys.executable, "-m", "pytest", "-q", "tests/unit", cwd=repo)
        tail = [l for l in out2.strip().splitlines() if l.strip()]
        w("```")
        for l in tail[-6:]:
            w(l)
        w("```")
        w(f"退出码 {code2}（非 0 = 被拦下）")
        w()

        verdict = "拒绝该改动" if code2 != 0 else "未能拦截（基线不足）"
        w(f"**判定：{verdict}**")
        w()

        w("## 5. 回滚到基线")
        w()
        code3, out3 = sh("git", "reset", "--hard", "baseline-v0.1.0", cwd=repo)
        w("```")
        w(out3.splitlines()[0] if out3 else "HEAD is now at baseline-v0.1.0")
        w("```")
        w()
        code4, out4 = sh(sys.executable, "-m", "pytest", "-q", "tests/unit", cwd=repo)
        w("回滚后重跑测试：")
        w("```")
        w([l for l in out4.strip().splitlines() if l.strip()][-1])
        w("```")
        w(f"退出码 {code4}（0 = 已恢复）")
        w()

        w("## 结论")
        w()
        w("| 环节 | 结果 |")
        w("|---|---|")
        w(f"| 改动被基线拦下 | {'是' if code2 != 0 else '否'} |")
        w(f"| 回滚后恢复通过 | {'是' if code4 == 0 else '否'} |")
        w(f"| 主仓库未受影响 | 是（全程在临时克隆 `{tmp.name}` 中进行） |")
        w()
        w("## 这个机制保护的是什么")
        w()
        w("换手率的除数是口径的一部分。少除一次交易日数，数值会变成 1.635% 而不是 0.327%，")
        w("相差五倍——但正文读起来毫无异常，\"换手率 1.64%\" 看起来和 \"0.33%\" 一样合理。")
        w("这正是必须有基线测试的原因：**错误不会以错误的样子出现**。")
        w()
        w("版本记录在 git tag `baseline-v0.1.0` 上，回滚是 `git reset` 或 `git revert`，")
        w("两者都可追溯到具体提交。")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"已写入 {OUT}")


if __name__ == "__main__":
    main()
