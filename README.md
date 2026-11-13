# 公募 REITs 周报 · 自动化生产工作流

> 复旦《AI Coding in Finance》期末项目 — 个人作业
> 作者：周豪波（学号 25210660117）

一个把「每周出一份公募 REITs 周报」从手工流程改造成**可长跑、可校验、可恢复、可迭代**的 agent 工作流的项目。

---

## 这个项目解决什么问题

公募 REITs 周报每周都要出，结构固定但数据链路很长：终端导出行情 → 手工整理口径 → 算板块等权、P/NAV、成交换手 → 画图 → 写分析 → 排版。重复劳动多，且最容易出错的地方不是写作，而是**数字口径**——同一只基金被归进两个板块、换手率三个数打架、终端导出的涨跌幅其实是小数，这类问题靠人眼很难发现。

本项目把这条链路拆成明确阶段，用确定性代码算数字、用 agent 写分析、用独立 Critic 校验、用硬门禁拦截口径错误，并保留完整状态以支持中断续跑和版本回滚。

详细设计见 [`docs/design_note.md`](docs/design_note.md)，工作流图见 [`docs/workflow_diagram.png`](docs/workflow_diagram.png)。

---

## 文件导览

| 路径 | 内容 |
|---|---|
| `docs/` | 设计说明、工作流图、数据契约、指标定义、运行手册、验证证据 |
| `config/` | 板块字典、章节注册表、门禁阈值、数据源配置、运行参数 |
| `src/reits_weekly/` | 主程序：适配器 / 归一化 / 计算 / 事实库 / 起草 / 渲染 / 校验 / 状态机 |
| `prompts/` | 各角色提示词（分章写作、评审、修订） |
| `skills/` | 可复用的 skill 包（跨项目可搬） |
| `cases/<周期>/` | 每期运行的完整产物：输入快照、事实库、草稿、质检、成品 |
| `fixtures/` | 脱敏的示例输入与期望输出（可公开分享） |
| `tests/` | 单元测试、黄金基线、集成测试（含中断续跑演练） |
| `scripts/` | 环境引导、基线抽取、提交打包 |

---

## 环境要求

- Windows 10/11（本项目在 Windows + Git Bash 下开发）
- Python 3.13+
- Git 2.40+

依赖装在项目内的 `.venv`，不污染系统环境：

```bash
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.in
```

或直接运行引导脚本：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap_venv.ps1
```

---

## 运行方式

```bash
# 用脱敏示例数据跑完整一期（无需任何凭证）
./.venv/Scripts/python.exe -m reits_weekly.cli run --case demo-2026-W45

# 查看当前状态
./.venv/Scripts/python.exe -m reits_weekly.cli status --case demo-2026-W45

# 中断后恢复（不会重跑已完成阶段）
./.venv/Scripts/python.exe -m reits_weekly.cli resume --case demo-2026-W45

# 运行测试
./.venv/Scripts/python.exe -m pytest -q
```

完整操作手册见 [`docs/runbook.md`](docs/runbook.md)。

---

## 数据来源说明

- **示例数据（`fixtures/`）**：脱敏后的合成数据，仅用于演示与测试，不含任何真实持仓或客户信息。
- **真实数据**：通过东方财富妙想 MCP 获取公开市场行情；不包含任何私有数据。

本项目所有输出均为研究流程演示，**不构成投资建议**。

---

## 本人贡献

（此节由作者本人撰写，说明在项目设计与实现中承担的具体工作。）

---

## 许可证

本项目为课程作业，仅用于教学与评估目的。
