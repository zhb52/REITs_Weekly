# Task Packet 模板

控制器为每一节生成一个 task packet，交给 Writer。packet 是这一节写作的**全部输入**，
不含其他章节的内容——这是刻意的：让每节独立起草，避免后写的章节去迎合前面已经写下的判断。

## packet 结构

```json
{
  "case_id": "2026-W45",
  "section_id": "1.3",
  "title": "1.3 个券表现与异常识别",
  "chapter_boundary": "描述事实、识别异常，不承担完整的基本面解释",
  "facts": [
    {"ref": "breadth.up", "display": "41", "meaning": "上涨家数"},
    {"ref": "mover.top_name", "display": "中金杭州安居宁巢REIT", "meaning": "涨幅第一"},
    {"ref": "mover.top_value", "display": "+2.46%", "meaning": "涨幅第一的幅度"},
    {"ref": "fund.ret|code=508087", "display": "-4.85%", "meaning": "国泰海通济南能源供热本周涨跌"}
  ],
  "previous_view": {
    "J-2026W44-02": "产业园区折价反映运营压力，拐点前不宜博弈修复"
  },
  "constraints": [
    "数字一律用 {{M:...}} 引用，禁止裸写",
    "归因必须声明是事后归因",
    "涉及 P/NAV 时声明口径"
  ],
  "negative_examples": [
    "✗ 本周市场分化明显，部分标的回调较大。（无数字、无判断，属资料罗列）",
    "✗ 本周首尾相差 5.8 个百分点。（5.8 未在事实库中，会被 G-NUM-01 拦下）"
  ],
  "word_range": [150, 400]
}
```

## 事实切片怎么选

不按"这一节可能用到什么"来猜，而是按事实的 `section_hint` 字段取：
`aggregate.py` 在登记每条事实时已声明它服务于哪几节。这样 packet 的构成是可审计的，
不依赖调度者的临场判断。

## 回执要求

Writer 返回的草稿必须满足：

1. 所有数字都是 `{{M:...}}` 形式
2. 至少一句判断、至少一处局限声明
3. 字数落在 `word_range` 内
4. 不含 Markdown 标题（标题由渲染器加）

不满足则由控制器退回重写，不进入下一步。
