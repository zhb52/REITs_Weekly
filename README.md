# 公募 REITs 周报 · 自动化生产工作流

> 复旦大学国际金融学院《AI Coding in Finance》期末项目（个人作业）
> 作者：周豪波　学号：25210660117　2026 年秋季

把"每周出一份公募 REITs 周报"从纯手工流程改造成**可长跑、可校验、可恢复、可迭代**的 agent 工作流。

**仓库地址**：https://github.com/zhb52/REITs_Weekly（完整开发历史同时包含在本目录的 `.git/` 中，无需访问远程即可审阅）

---

## 它解决什么问题

周报每期约 4–6 小时，绝大部分不是写作，而是数据整理与口径核对。真正的痛点有三个，
都来自 2026-W45 期的真实事故：

| 问题 | 表现 |
|---|---|
| **板块归属漂移** | 国泰海通济南能源供热 REIT（508087）在第一章按"能源"算、在 1.5 的 P/NAV 表按"水利"算。同一只基金在同一份报告里属于两个板块 |
| **换手率三个数** | 底稿 0.36%、正文 0.31%、按公式复算 0.327%，互不相符 |
| **单位陷阱** | 终端导出的"涨跌幅（%）"实为小数（`0.0094637` = 0.95%），直接入表会缩小 100 倍 |

这三类错误的共同点是**单看任何一张表都发现不了**，必须跨表勾稽。人眼做不到每周查，代码可以。

本项目的做法：数字全部由确定性代码产生，正文只允许用占位符引用；写完再由独立门禁
反向扫描每个数字能否回溯；跨章一致性、样本勾稽、信息时效各有一条硬门禁。

---

## 文件导览

| 路径 | 内容 |
|---|---|
| **`docs/design_note.md`** | **设计说明（作业第一部分与第二部分）—— 先看这个** |
| `docs/workflow_diagram.svg` | 带注释的工作流图 |
| `docs/metrics.md` | 九类指标的定义、公式与口径陷阱 |
| `docs/data_contract.md` | 适配器必须满足的字段契约与溯源要求 |
| `docs/runbook.md` | 每周操作流程、中断处理、口径变更步骤 |
| `docs/requirement_checklist.md` | **作业要求逐条对照（含证据路径）** |
| `docs/verification_evidence/` | 验证汇总、中断恢复实录、回滚实录 |
| `config/boards.yaml` | 板块字典（10 个板块、别名、显式覆盖、冲突记录） |
| `config/fund_registry.csv` | 96 只基金的板块与属性登记表 |
| `src/reits_weekly/` | 主程序，见下方模块说明 |
| `cases/demo-2026-W45/` | 一期完整产物：事实库、草稿、门禁结果、成品 docx、状态机 |
| `fixtures/demo-2026-W45/` | 可分享的示例输入（公开行情）与期望输出 |
| `tests/` | 119 项测试，含门禁、问题台账、Critic、状态机、中断恢复与固定基线 |
| `scripts/` | 环境引导、示例数据生成、指数序列提取、提交打包 |

### 源码结构

```
src/reits_weekly/
├─ adapters/     数据源适配器（fixture 已实现，妙想 MCP 待接入）
├─ normalize/    板块映射（唯一事实源）与字段校验
├─ compute/      收益 / 广度 / 估值 / 流动性 —— 纯函数，数字只在这里产生
├─ facts.py      事实库：fact_id 派生、display 定型
├─ draft/        占位符解析（{{M:metric|param}}）
├─ render/       图表、五张表、docx 装配
├─ verify/       八条硬门禁 + 问题台账 + 问题台账
├─ state.py      状态机、检查点、审批记录
├─ controller.py 阶段推进、重试、阻断、升级
└─ cli.py        命令行入口
```

---

## 环境与运行

依赖**全部装在项目内**的 `.venv`，不影响系统环境。

```bash
# 一条命令完成：建 venv、装依赖、可编辑安装、跑测试
powershell -ExecutionPolicy Bypass -File scripts/bootstrap_venv.ps1
```

或手动：

```bash
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.in
./.venv/Scripts/python.exe -m pip install -e .
./.venv/Scripts/python.exe -m pytest -q      # 119 passed
```

### 跑一期

```bash
# 1. 跑完数据 → 计算 → 图表 → 草稿 → 门禁（会停在人工审批）
./.venv/Scripts/python.exe -m reits_weekly.cli run --case demo-2026-W45

# 2. 查看状态
./.venv/Scripts/python.exe -m reits_weekly.cli status --case demo-2026-W45

# 3. 审阅后签字
./.venv/Scripts/python.exe -m reits_weekly.cli approve --case demo-2026-W45 \
    --by 周豪波 --comment "数字已核，口径无异议"

# 4. 再次运行出稿
./.venv/Scripts/python.exe -m reits_weekly.cli run --case demo-2026-W45
```

第一条命令会返回 `[HUMAN_REVIEW] BLOCKED`，这是**设计如此**——门禁全过后流程必然停下等人签字。
成品在 `cases/demo-2026-W45/out/`。

依赖：Python ≥ 3.11、Git ≥ 2.40；Python 包见 `requirements.in`（python-docx、matplotlib、
pandas、numpy、PyYAML、openpyxl、lxml、requests、pytest）。中文字体优先宋体，缺失时降级雅黑并在质检中记录。

---

## 数据来源与合规

- `fixtures/` 中只保留**公开市场行情**（收盘价、成交额、P/NAV、流通市值），
  已剔除内部批注与来源编号，可公开分享
- 不含任何持仓、客户或内部研报数据
- 所有输出为研究流程演示，**不构成投资建议**
- 凭证一律走 `.env`（已 gitignore），仓库与提交历史中不含任何密钥；
  `G-SRC-01` 每次运行都会扫描

---

## 本人贡献

本项目的研究判断、口径决策与验收由本人完成，具体包括：

1. **确定任务与验收标准**：选定周报为对象，梳理现有流程，定义 13 个章节结构与各自的交付要求
2. **做出两处关键口径决策**（这两处直接改变了输出数值）：
   - 换手率统一为 `TR-01`（Σ成交额 ÷ Σ流通市值 ÷ 交易日数），放弃原报告的 0.31%，
     理由是原值用现有数据无法复现，而 TR-01 任何人都能验算
   - 508087 的板块归属统一为"能源基础设施"，修正原报告"第一章算能源、1.5 算水利"的不一致
3. **主持数字核对**：将程序输出与原报告逐项比对（94 只 / 41涨50跌3平 / P-NAV 1.055 与 1.091 /
   56溢价38折价 / 成交 21.93 亿），确认口径可复现
4. **审阅与定稿**：对每期草稿做人工审批，签字记录在 `state.json` 的 `approvals[]`
5. **代码实现**：在 AI 编码助手协作下完成数据层、计算层、门禁、状态机与文档装配的编写与调试

> 说明：本项目按课程要求使用 AI 工具完成，代码由 AI 编码助手在本人指导下编写；
> 研究口径、数据核对与最终判断由本人负责。

---

## 已知边界

- Critic 是规则版而非模型版：可复现、可审计、零依赖，但判断不了论证的实质成立与否
- 一级市场关键数值靠公告转录（`formula=announcement_transcription`），不是自动抓取
- 原生 Word 图表未启用，默认 300dpi PNG（换取版式稳定）

详见 `docs/design_note.md` 第 2.4 节。

---

## 许可证

课程作业，仅用于教学与评估。
