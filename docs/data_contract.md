# 数据契约

任何适配器（妙想 MCP、交易所抓取、本地 CSV）只要输出下列列名与类型，就能接入本工作流。
列名不符会在 `normalize/schema.py` 阶段失败，不做模糊匹配。

## quotes_weekly（个券周度行情，一期主表）

| 列 | 类型 | 说明 |
|---|---|---|
| `code` | str | 6 位代码，不带交易所后缀，主键 |
| `name` | str | 基金简称 |
| `board_raw` | str | **数据源原始板块名**，保留以便检测分类差异 |
| `asset_class` | str | `产权类` / `特许经营权类` |
| `listing_date` | date | 上市日期 |
| `close_prev` | float | 基准日收盘（**不复权**） |
| `close_cur` | float | 报告期末收盘（不复权） |
| `dpu_week` | float | 本周每份分红，无分红填 `0.0`（不是空） |
| `mktcap_total` | float | 总市值（亿元） |
| `mktcap_float` | float | 流通市值（亿元） |
| `issue_price` | float | 发行价（元） |
| `pnav` | float | P/NAV，缺失留空（`NaN`），**不得填 1.0** |

强制校验：

- `code` 唯一
- `mktcap_float ≤ mktcap_total × 1.02`（留 2% 容差，应对数据源口径差异）
- `dpu_week ≥ 0`
- 百分比字段统一为**百分点**（`0.95` 表示 0.95%），不得混用小数

## turnover_weekly（个券周度成交）

| 列 | 类型 | 说明 |
|---|---|---|
| `code` | str | 外键 |
| `turnover_week` | float | 本周成交额（亿元） |
| `turnover_week_prev` | float | 上周成交额（亿元） |

换手率不在此表，由 `compute/liquidity.py` 按 TR-01 从成交额与流通市值算出——
避免数据源给一个口径不明的换手率字段。

## index_snapshot（指数当期点位）

`code` / `label` / `close` / `wow_pct` / `ytd_pct`。
用于 1.1 的两张表。与下面的历史序列分开存放，因为前者是"当期值"、后者是"绘图序列"。

## index_series（指数日序列）

`date` / `series` / `value_rebased`。已按 2021-09-30 = 1000 定基，仅用于绘图。
来源是样张 docx 原生图表的内嵌缓存（`word/charts/chart*.xml` 的 `c:numCache`）。

## yields（利率）

`code` / `prev` / `cur`。`code` 取 `T10Y`、`T30Y`、`DR007`。单位为 %。

## 溯源要求

每个适配器必须提供 `SourceMeta`：

| 字段 | 用途 |
|---|---|
| `source_id` | 如 `fixture:demo-2026-W45`、`miaoxiang:fund_quote` |
| `adapter` | 适配器类名 |
| `retrieved_at` | 抓取时刻 |
| `source_asof` | **数据本身的最新日期**，PIT 门禁据此判断 |
| `license` | `public-market-data` / `internal` / `sample-synthetic` |
| `raw_hash` | 原始响应字节的 sha256，用于回放与"输入是否变过"的判断 |

`raw_hash` 同时参与 `fact_id` 的派生：输入一变，所有 fact_id 随之改变，
旧草稿里的引用会自动失效，而不是悄悄指向一个过期数值。
