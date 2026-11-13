# 回滚演示

本文件由 `scripts/demo_rollback.py` 在**临时克隆**中实跑生成，主仓库不受影响。

演示的问题：把换手率口径从 `TR-01` 改回报告原来的写法（少除一次交易日数），
看基线测试是否拦得住，以及回滚是否干净。

## 1. 建立基线

```
tag baseline-v0.1.0 -> ffde04a
```

基线提交：`ffde04a`

## 2. 基线测试（改动前）

```
82 passed in 1.12s
```
退出码 0（0 = 通过）

## 3. 提交一处口径改动：TR-01 少除交易日数

改动提交：`1b3dcfe`

## 4. 对基线跑测试

```
E         Expected: 0.327 ± 0.001
tests\unit\test_liquidity.py:46: AssertionError
=========================== short test summary info ===========================
FAILED tests/unit/test_liquidity.py::test_tr01_basic - assert 1.633 == 0.327
FAILED tests/unit/test_liquidity.py::test_real_turnover_matches_report - asse...
2 failed, 80 passed in 1.07s
```
退出码 1（非 0 = 被拦下）

**判定：拒绝该改动**

## 5. 回滚到基线

```
HEAD is now at ffde04a chore: add prompts, skills and evidence scripts
```

回滚后重跑测试：
```
82 passed in 0.99s
```
退出码 0（0 = 已恢复）

## 结论

| 环节 | 结果 |
|---|---|
| 改动被基线拦下 | 是 |
| 回滚后恢复通过 | 是 |
| 主仓库未受影响 | 是（全程在临时克隆 `reits-rollback-ooahrnf8` 中进行） |

## 这个机制保护的是什么

换手率的除数是口径的一部分。少除一次交易日数，数值会变成 1.635% 而不是 0.327%，
相差五倍——但正文读起来毫无异常，"换手率 1.64%" 看起来和 "0.33%" 一样合理。
这正是必须有基线测试的原因：**错误不会以错误的样子出现**。

版本记录在 git tag `baseline-v0.1.0` 上，回滚是 `git reset` 或 `git revert`，
两者都可追溯到具体提交。
