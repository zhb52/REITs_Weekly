# 运行手册

## 首次准备

```bash
# 1. 建虚拟环境（依赖全部装在项目内，不污染系统）
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.in
./.venv/Scripts/python.exe -m pip install -e .

# 2. 验证
./.venv/Scripts/python.exe -m pytest -q
```

Windows PowerShell 用户可用 `scripts\bootstrap_venv.ps1` 一步完成。

## 每周常规流程

```bash
# 1. 跑一期（数据取到 → 计算 → 图表 → 草稿 → 门禁）
./.venv/Scripts/python.exe -m reits_weekly.cli run --case 2026-W46 \
    --week-start 2026-11-09 --week-end 2026-11-13 --week-prev 2026-11-06 \
    --cutoff 2026-11-15T23:59:59+08:00

# 2. 看状态与门禁
./.venv/Scripts/python.exe -m reits_weekly.cli status --case 2026-W46
./.venv/Scripts/python.exe -m reits_weekly.cli verify --case 2026-W46

# 3. 人工审阅草稿与门禁结果后签字
./.venv/Scripts/python.exe -m reits_weekly.cli approve --case 2026-W46 \
    --by 周豪波 --comment "数字已核，口径无异议"

# 4. 再次运行，出稿
./.venv/Scripts/python.exe -m reits_weekly.cli run --case 2026-W46
```

产物位置：

```
cases/<case>/
├─ facts/facts.json          本期全部数字及其来源、公式、适用章节
├─ drafts/drafts.md          草稿源文件（含占位符，可直接改）
├─ drafts/composed.json      占位符替换后的成稿文本
├─ qa/gates.json             八条门禁的检查结果与失败样本
├─ work/quotes_normalized.csv  归一化后的个券表
├─ work/provenance.json      数据溯源与板块差异
├─ work/charts/*.png         四张图
├─ out/*.docx                成品
└─ state.json                状态机（含流转历史与审批记录）
```

## 常见中断与处理

| 现象 | 状态 | 含义 | 处理 |
|---|---|---|---|
| `run` 后停在 `[HUMAN_REVIEW] BLOCKED` | BLOCKED | 门禁全过，等人签字 | `approve` 后再 `run` |
| `run` 后落到 `[REVISE]` | RUNNING | 门禁未过，已进入修订 | 看 `qa/gates.json` 的 `samples`，改草稿后 `run` |
| 连续两轮门禁不过 | ESCALATED | 触发升级 | 看是否阈值不合理，或数据本身有问题；记录理由后再放宽 |
| 提示"草稿中存在无法解析的事实占位符" | BLOCKED | 引用了不存在的指标 | 按提示补事实或改指标名 |
| 数据源字段缺失 | BLOCKED | schema 漂移 | 核对新字段含义，更新适配器；**不要自动跳过** |

`resume` 与 `run` 等价，语义更明确：从 `state.stage` 继续。

## 门禁读法

`G-NUM-01` 的 `samples` 会给出"哪个数字、在哪一节、上下文是什么"。例如：

```
[1.3] 5.8 …本周首尾相差 5.8 个百分点…
```

意思是正文写了 5.8，但事实库里没有这个数——通常是在文中自己算了一个数。
正确的做法是给它建一条事实（`aggregate.py` 里加 `bundle.add`），而不是把 5.8 删掉换成含糊表述。

## 口径变更怎么做

1. 改 `config/boards.yaml` 或 `compute/` 下的公式
2. 同步更新 `docs/metrics.md` 与 `CHANGELOG.md`
3. 重跑并对比基线 `tests/golden/baseline_2026-W45.json`：`pytest -q`。若关键数值变化是预期的，
   更新基线文件并在 `CHANGELOG.md` 写明理由与影响范围
4. 历史 `cases/` 不受影响——每期产物独立，不做回溯重算

## 换数据源

适配器在 `src/reits_weekly/adapters/`，实现 `MarketDataAdapter` 协议即可。
必须提供 `SourceMeta.raw_hash` 与 `source_asof`，否则 PIT 门禁无法工作。

妙想 MCP 适配器（`miaoxiang.py`）尚未接入。接入时需要：

1. 取得 MCP 的启动配置（命令或 URL）
2. 在 `get_adapter()` 里注册
3. 用录制回放模式先跑通（避免每次调试都打真实接口）
