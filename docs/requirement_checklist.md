# 作业要求逐条对照

对照对象：`final_project.pdf`，《AI Coding in Finance》Fall 2026 Final Project。
每条给出来源原文、本项目对应实现、以及**可在仓库内直接核验的证据路径**。

---

## 第一部分　Specify a substantial, recurring task

| # | 作业要求 | 实现 | 证据 |
|---|---|---|---|
| 1.1 | 选择一项实质性的、可重复的研究或分析活动 | 公募 REITs 周报：每周一期，96 只样本、13 节、5 表 4 图 | `docs/design_note.md` §1.2 |
| 1.2 | 识别预期用户 | 覆盖 REITs 的卖方研究人员 | `design_note.md` §1.1 |
| 1.3 | 描述当前流程 | 六步手工流程，单期 4–6 小时；列出三个真实事故 | `design_note.md` §1.1 |
| 1.4 | 阶段（stages） | 取数→归一化→计算→事实库→图表/草稿→门禁→审批→出稿→质检 | `design_note.md` §1.3；`state.py` 的 `FORWARD_ORDER` |
| 1.5 | 依赖（dependencies） | 单向为主，唯一回边是门禁不过→修订（≤2 轮） | `design_note.md` §1.3；`controller.py` |
| 1.6 | 递归触发（recurring triggers） | 定时（周五 17:30 首跑 / 周六 10:00 复跑）+ 手动 + 新输入到达 | `design_note.md` §2.2；`runbook.md` |
| 1.7 | 输入（inputs） | 行情、成交、分红、指数序列、利率、一级市场、解禁、持有人 | `data_contract.md`；`fixtures/demo-2026-W45/*.csv` |
| 1.8 | 允许来源（permitted sources） | 四个白名单来源 + 明确禁止项 | `design_note.md` §1.4 |
| 1.9 | 信息截止（information cutoffs） | 收盘 15:00 定价；公告截至周日 23:59；由 `info_cutoff` 强制 | `design_note.md` §1.4；`gates.py::point_in_time` |
| 1.10 | 工作产品（work products） | docx 报告 + facts.json + gates.json + state.json | `cases/demo-2026-W45/out/`、`facts/`、`qa/` |
| 1.11 | 验收标准（acceptance criteria） | 八条可判定门禁 + 三项需判断的评审 | `design_note.md` §1.5；`verify/gates.py` |
| 1.12 | 解释为何需要持久工作流而非一次性脚本 | 四条理由：口径跨期一致、可中断续跑、可验证改动、可拦错 | `design_note.md` §1.6 |

---

## 第二部分　Design the architecture

### 2a Roles and handoffs

| # | 作业要求 | 实现 | 证据 |
|---|---|---|---|
| 2a.1 | 带注释的工作流图 | SVG 图，标注五类角色的位置与边界 | `docs/workflow_diagram.svg` |
| 2a.2 | 简短的设计说明 | 约 15KB，覆盖全部子项 | `docs/design_note.md` |
| 2a.3 | 每个 agent 的职责 | 九类角色一览表 | `design_note.md` §2.1 |
| 2a.4 | 工具（tools） | 每角色可用工具与限制 | `design_note.md` §2.1；`config/settings.yaml` |
| 2a.5 | 可复用的 skills 或 instructions | 3 个 skill + 5 份提示词 | `skills/*/SKILL.md`；`prompts/*.md` |
| 2a.6 | 输入/输出产物 | 每角色的 in/out 明确列出 | `design_note.md` §2.1 |
| 2a.7 | 解释为何这样分工 | 计算与写作分离、Critic 与起草者分离、控制器不含 LLM | `design_note.md` §2.1 |
| 2a.8 | 适当处使用确定性代码 | 收益、广度、估值、流动性全部纯函数 | `src/reits_weekly/compute/` |
| 2a.9 | 区分 agent 决策与 harness/controller 执行控制 | 五事归属表：谁能决定什么 | `design_note.md` §2.1 |

### 2b Long-running operation

| # | 作业要求 | 实现 | 证据 |
|---|---|---|---|
| 2b.1 | 持久状态与检查点 | `state.json` 三段式（身份/进度/证据）+ 产物 sha256 | `state.py` |
| 2b.2 | 依赖 | 阶段顺序由 `FORWARD_ORDER` 约束，不可跳阶段 | `state.py::can_enter` |
| 2b.3 | 调度或新输入触发 | 定时 + 手动 + 输入变更 | `design_note.md` §2.2 |
| 2b.4 | 重试规则 | 网络 5s/20s/60s 上限 3 次；schema 漂移不重试 | `design_note.md` §2.2 |
| 2b.5 | 停止或升级规则 | BLOCKED / FAILED / ESCALATED 三态，语义不同 | `state.py`；`controller.py` |
| 2b.6 | 中断后恢复且不重复已完成动作 | 按产物哈希判 SKIP/REDO，**实跑验证** | `docs/verification_evidence/recovery_demo.md`；`tests/integration/test_recovery.py` |
| 2b.7 | 时间、成本、工具权限上限 | 3600s / $3 / 300 calls / 单阶段 600s | `design_note.md` §2.2；`RunConfig` |

### 2c Verification and improvement

| # | 作业要求 | 实现 | 证据 |
|---|---|---|---|
| 2c.1 | 独立于产出方的检查 | Critic 只看成稿、事实库、上期观点，看不到推理过程 | `draft/critic.py`；`prompts/critic.md` |
| 2c.2 | 有后果动作前的人工审批 | 门禁通过后**必然停下**，签字绑定草稿 sha256 | `controller.py`；`state.add_approval` |
| 2c.3 | 有界修订循环 | ≤2 轮，超出转 ESCALATED；耗尽不等于通过 | `design_note.md` §2.3 |
| 2c.4 | 对固定基线测试改动 | `tests/golden/baseline_2026-W45.json` + `test_golden.py`；改动被拦的实例 | `docs/verification_evidence/rollback_demo.md` |
| 2c.5 | 接受或拒绝 | 基线测试退出码非 0 即拒绝该改动 | 同上 |
| 2c.6 | 记录版本 | `pipeline_version` + git tag `baseline-v0.1.0` + `CHANGELOG.md` | `CHANGELOG.md`；`git tag` |
| 2c.7 | 回滚 | 临时克隆中实跑 `git reset --hard` 并验证恢复 | `docs/verification_evidence/rollback_demo.md` |
| 2c.8 | 时效性任务防未来信息泄漏 | `G-PIT-01` 按 `info_cutoff` 比较（不与系统时钟比较） | `gates.py::point_in_time`；`tests/unit/test_gates.py` |

---

## 第三部分　Submit one ZIP with complete Git history

| # | 作业要求 | 实现 | 证据 |
|---|---|---|---|
| 3.1 | 设计说明与图 | 均在 `docs/` | `docs/design_note.md`、`workflow_diagram.svg` |
| 3.2 | 提示词（prompts） | 5 份：总纲、packet 模板、critic、修订、分节 | `prompts/` |
| 3.3 | 技能或可复用指令（skills） | 3 个 SKILL.md | `skills/` |
| 3.4 | 配置（configuration） | 板块字典、基金登记表、配置项、环境模板 | `config/`、`.env.example` |
| 3.5 | 已实现的代码 | 74 个跟踪文件，33 个源文件 | `src/reits_weekly/` |
| 3.6 | 可分享的示例输入与输出 | 公开行情 fixtures + 期望输出（docx/facts/critic） | `fixtures/demo-2026-W45/` |
| 3.7 | 验证证据 | 门禁结果、Critic 报告、测试结果 | `cases/demo-2026-W45/qa/`；`docs/verification_evidence/verification_summary.md` |
| 3.8 | 恢复证据 | 实跑的中断恢复记录 | `docs/verification_evidence/recovery_demo.md` |
| 3.9 | 根目录 README 写明身份 | 姓名、学号、学院、学期 | `README.md` 顶部 |
| 3.10 | README 任务简介 | 三段：问题、做法、结果 | `README.md` |
| 3.11 | README 仓库 URL | 已填实际地址 | `README.md` |
| 3.12 | README 文件导览 | 12 行表格 + 源码结构树 | `README.md` |
| 3.13 | README 依赖 | Python 版本、包清单、字体说明 | `README.md`；`requirements.in` |
| 3.14 | README 安装运行步骤 | 一条命令 + 四步流程 | `README.md`；`scripts/bootstrap_venv.ps1` |
| 3.15 | README 简述本人贡献 | 五条具体工作 + 说明 | `README.md` |
| 3.16 | 开发全程有意义的提交 | 逐层提交，每条 message 写"为什么" | `git log --oneline`（见 3.22） |
| 3.17 | 压缩前提交最终改动 | 打包脚本强制检查工作区干净 | `scripts/package_submission.ps1` 预检 |
| 3.18 | 压缩现有本地项目文件夹，含隐藏目录 | 用 .NET ZipFile，非 Compress-Archive | 同上 |
| 3.19 | 命名 `studentID-final-project.zip` | `25210660117-final-project.zip` | 打包脚本输出 |
| 3.20 | 完整历史，非浅克隆 | 打包时检查 `is-shallow-repository` 并拒绝 | 同上 |
| 3.21 | 不用 Download ZIP / git archive | 两者均不含 `.git/`，本项目未使用 | 打包脚本注释说明原因 |
| 3.22 | 无需访问远程即可审阅 | 解压后 `git log` 可读、`git fsck` 无损坏 | `docs/verification_evidence/verification_summary.md` |
| 3.23 | 凭证/私有数据不入库、不入历史 | 全历史正则扫描无命中；`.env` 已 gitignore；`G-SRC-01` 每次运行扫描 | `verification_summary.md` 第 4 节 |

---

## 已知不满足项

诚实列出，避免"看起来完美"：

| 项 | 状况 | 影响 |
|---|---|---|
| Critic 为规则版 | 五个维度用启发式打分，判断不了论证的实质成立与否 | 不能替代真人评审，故保留人工审批为必经环节 |
| 一级市场数值靠转录 | 发行规模、解禁比例等从公告原文摘录，`formula=announcement_transcription` | 换期时需要人工补录，尚未做到无人值守 |
| 原生 Word 图表未启用 | 输出 300dpi PNG | 图表不能在 Word 里继续编辑；换取版式稳定 |

以上三项在 `docs/design_note.md` §2.4 中均有说明，属于**知情取舍**，不是遗漏。
