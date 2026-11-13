"""草稿输入变更必须使审批失效。

这条用例来自一个真实缺陷：检查点只看输出 composed.json 是否变化，
不看它的输入 drafts.md。结果是改了草稿却毫无反应，用户会以为程序坏了，
更危险的是——改完的稿子会带着旧的审批被当成"已批准"发出去。
"""

from __future__ import annotations

from pathlib import Path

from reits_weekly.state import CaseState, Stage


def test_draft_input_hash_is_tracked(tmp_path):
    drafts = tmp_path / "drafts.md"
    drafts.write_text("## 1.1\n初版", encoding="utf-8")

    st = CaseState(case_id="c1")
    digest = str(hash(drafts.read_text(encoding="utf-8")))
    st.input_hashes["drafts.md"] = digest
    st.save(tmp_path)

    reloaded = CaseState.load(tmp_path)
    assert reloaded.input_hashes["drafts.md"] == digest


def test_changed_input_is_detected(tmp_path):
    drafts = tmp_path / "drafts.md"
    drafts.write_text("## 1.1\n初版", encoding="utf-8")

    st = CaseState(case_id="c1")
    st.input_hashes["drafts.md"] = "old-digest"

    from reits_weekly.state import sha256_file

    assert st.input_hashes["drafts.md"] != sha256_file(drafts)


def test_approval_binds_to_specific_digest():
    """审批必须绑到具体一版，换一版就不算已批。"""
    st = CaseState(case_id="c1")
    st.add_approval("HUMAN_REVIEW", by="张三", decision="approve",
                    artifact_sha256="digest-A")
    assert st.has_approval("HUMAN_REVIEW", "digest-A")
    assert not st.has_approval("HUMAN_REVIEW", "digest-B")
