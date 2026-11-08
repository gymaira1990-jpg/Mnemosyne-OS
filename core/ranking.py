"""检索排序权重（单一真源）

为什么不留在 main.py 的 SQL 拼接里：
  权重以前是散在一条长 SQL 里的字面量，测试只能「断言字符串里有 0.15」——
  那等于断言自己刚写下的话，改实现它照样绿。抽出来之后：
    1. 权重表可被代码与测试同时引用；
    2. 时近性表达式有名字，能被真库测试直接执行（灌三条不同年龄的记忆，看排序）。
"""

# 五维权重：语义 / 关键词 / 时近 / 可信度 / 热度，合计 1.0
WEIGHTS = {
    "semantic": 0.50,
    "bm25": 0.15,
    "temporal": 0.15,
    "reliability": 0.10,
    "heat": 0.10,
}

# 时近性：**归一系数**，最终由 WEIGHTS["temporal"] 加权。
# 🔴 2026-11-08 修（DSH 审计 P0-3，已核实成立）：
#   原来这里直接写绝对值 0.15/0.08，而 build_order_sql 外层又乘了一次 WEIGHTS["temporal"]
#   ⇒ 7 天内的实际贡献是 0.15 × 0.15 = 0.0225，只剩 15% 的效果，五维有效和也只有 0.8725。
#   「新记忆优先」这个设计实际上一直是失效的。现在改成 1.0 / 0.533 / 0（保持原来 0.15:0.08 的比例）。
TEMPORAL_WEIGHT_SQL = (
    "CASE WHEN m.created_at > NOW() - INTERVAL '7 days' THEN 1.0 "
    "WHEN m.created_at > NOW() - INTERVAL '30 days' THEN 0.533 ELSE 0.0 END"
)

# 语义相似度用余弦距离换算：1 - (embedding <=> query)
SEMANTIC_SQL = "(1.0 - (m.embedding <=> $2::vector))"


def build_order_sql(bm25_sql: str) -> str:
    """拼 ORDER BY 的评分表达式。bm25_sql 由调用方按有没有分词决定（没有就是 "0"）。"""
    return (
        f"{WEIGHTS['semantic']} * {SEMANTIC_SQL} "
        f"+ {WEIGHTS['bm25']} * ({bm25_sql}) "
        f"+ {WEIGHTS['temporal']} * ({TEMPORAL_WEIGHT_SQL}) "
        f"+ {WEIGHTS['reliability']} * m.reliability "
        f"+ {WEIGHTS['heat']} * GREATEST(0.0, m.heat_score)"
    )
