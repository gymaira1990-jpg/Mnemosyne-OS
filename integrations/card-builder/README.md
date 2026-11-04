# card-builder —— 对话 → 著录卡（参考实现）

> 配套规范：`docs/CARD-SPEC.md`　｜　校验器：`scripts/card_check.py`

一份**纯标准库、零依赖、不调模型**的最小实现，演示「一段对话 → 一张能过规范的卡」。
它不是生产实现 —— 生产侧比它多三层（会话切分策略、标题优选、精修与判重作业），
那层是针对真实语料磨出来的，不进公开仓。这里给你的是**骨架，且能跑通**。

## 快速跑

```bash
# 1. 跑内置自检（不联网、不写库）
python3 integrations/card-builder/build_cards.py --selftest

# 2. 用示例会话产卡
python3 integrations/card-builder/build_cards.py example_session.json

# 3. 逐卡过规范（这才是验收：产出的卡必须能过校验器）
python3 integrations/card-builder/build_cards.py example_session.json > /tmp/cards.txt
#    然后把每张卡喂给 scripts/card_check.py（见 scripts/card_check.py 用法）
```

生成一张卡长这样：

```
[结果卡] 档号：K·GEN·2026-0001
题名：把导出脚本的编码问题修一下，中文全乱码
摘要：已修好。根因是 open() 没写 encoding，在中文 Windows 上按 GBK 解码…
实体：T-0642 · 64624c6 · scripts/export.py
证据：T-0642 · 64624c6 · scripts/export.py
标签：GEN
来源：sid=demo-0001
```

## 它做了什么（四步）

| 步 | 逻辑 | 为什么 |
|---|---|---|
| 1. 切轮 | 以 user 消息为轮起点，收集该轮的全部 assistant 回复 | 一轮的提问 + 回复 = 一次「事情」 |
| 2. 抽证据 | 五级正则（台账 / 提交 / 仓库文件 / URL / 绝对路径）+ `clean_ev()` 三刀 | 没有证据就不出卡 —— 结果卡的最低门槛 |
| 3. 抽实体 | 版本号 / 台账号 / 提交 hash / 路径，纯规则 | 原子事实最有用，且 0 token、不引入幻觉 |
| 4. 组装 | 题名取提问首句、摘要取结论段（40–600 字） | 题名是名词短语便于检索，摘要只写结果 |

## 三个容易踩的坑（都写进代码注释了）

1. **别用 `\S+` / `[\w.\-/]` 抽路径**：Python 的 `\w` 含中文，会一路吞进句子，抓出带句号的长串。
2. **证据必须过滤一次性目录**（`/scratch/`、`/tmp/`）：跑完即删的探针文件等于没有证据。
3. **没有证据的那一轮必须跳过**：宁可少一张卡，不要多一张没法验证的卡。

## 和生产的差异

| | 这里 | 生产 |
|---|---|---|
| 会话切分 | 单纯按 role 切 | 还处理系统通知、中断轮、跨会话续接 |
| 标题 | 取提问首句 | 优先用会话标题 + 提问，超长再截 |
| 证据 | 五级正则 | 同一套 + 按真实语料调过的清洗 |
| 入册 | 打印到 stdout | 走 `POST /api/v1/memories`（`category=session`，落 L0 层避开冲突合并） |

> ⚠️ **入库时务必带 `category=session`**：非 L0 层会跑语义冲突检测，语义相近的旧卡会被标记过期、新卡被合并。
> 卡片是日志，不是知识条目 —— 只增不改。
