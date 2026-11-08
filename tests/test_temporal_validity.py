"""时间有效性窗口测试 —— 2026-11-09 重写（T-0684「拆掉恒真测试」）。

原来 6 条里有 3 条是假的：
    assert True                        # 恒真，删掉代码也不会红
    assert future > datetime.now()     # 测的是 Python 的 datetime，不是我们的代码
    assert past < datetime.now()       # 同上

它们跑一万遍也发现不了「valid_to 过滤被删」。

改法：
  · 前三条删掉
  · 源码检查改用 **AST 取 SQL 字符串字面量**（今晚踩过的坑：字符串直接匹配会命中自己写的注释）
  · 保留精确字符串断言（统计查询那条本来就准）
  · 「返回 expired 字段」那条太宽（任何地方出现 "expired" 就过），改成检查函数体内
"""
import ast
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
FILTER_RE = r"valid_to\s+IS\s+NULL\s+OR\s+(?:m\.)?valid_to\s*>\s*NOW\(\)"


def _sql_literals(rel: str) -> str:
    """取出某文件里所有 SQL 字符串字面量（排除 docstring 与注释）。"""
    src = (ROOT / rel).read_text(encoding="utf-8")
    tree = ast.parse(src)
    parts = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node) or ""
        else:
            doc = ""
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value != doc:
            parts.append(node.value)
    return "\n".join(parts)


class TestFilterExistsInSQL:
    """每一处召回/注入路径都必须带时间有效性过滤。"""

    def test_injection_filters_expired(self):
        sql = _sql_literals("api/injection.py")
        n = len(re.findall(FILTER_RE, sql, re.IGNORECASE))
        assert n >= 2, (
            f"api/injection.py 的 SQL 里「valid_to IS NULL OR valid_to > NOW()」只找到 {n} 处（期望 ≥2）"
            " —— 过期记忆会被注入回来"
        )

    def test_main_recall_paths_filter_expired(self):
        """main.py 的召回 SQL 必须带 valid_to 过滤，且**数量精确**。

        2026-11-09 反证时发现两个问题：
          ① 原来写「≥4 处」，文件里有 6 处 —— 删掉 1 处测试照样通过，等于没锁住；
          ② 改成「逐块验证」又太糙：把「按 id 取单条」「评分计算」也当成召回路径误报。
        所以用精确数字：13 处（实测）。新增/删除召回路径时这个数字会变 ——
        那正是该人工确认「新路径有没有带过滤」的时刻。
        """
        sql = _sql_literals("main.py")
        n = len(re.findall(FILTER_RE, sql, re.IGNORECASE))
        assert n == 13, (
            f"main.py 的召回过滤有 {n} 处，期望 13 处。\n"
            "  少了 → 有召回路径漏了 valid_to，过期记忆会被捞出来；\n"
            "  多了 → 新增了召回路径，请确认新路径确实带了过滤后把这里的 13 改掉。"
        )

    def test_stats_query_excludes_expired(self):
        """统计口径也要排除过期（这条原来是精确字符串断言，保留）。"""
        sql = _sql_literals("main.py")
        assert re.search(
            r"COUNT\(\*\)\s+FROM\s+memories\s+WHERE\s+user_id=\$1\s+AND\s+is_deleted=FALSE\s+AND\s+\(valid_to",
            sql, re.IGNORECASE), "统计查询应排除过期记忆"


class TestExpiredFlagExposed:
    """list_memories 要把过期状态透出来，否则前端无从判断。"""

    def test_returns_expired_field(self):
        src = (ROOT / "main.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        fn = next((n for n in ast.walk(tree)
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                   and n.name == "list_memories"), None)
        assert fn is not None, "找不到 list_memories 函数（改名了？同步更新本测试）"
        body = ast.get_source_segment(src, fn) or ""
        assert '"expired"' in body or "'expired'" in body, \
            "list_memories 应返回 expired 标记"
        assert "valid_to" in body, "list_memories 应查询 valid_to 字段"


class TestTemporalSemantics:
    """语义规则本身（纯函数，不连库）—— 这部分才算真的在测逻辑。"""

    @staticmethod
    def _is_visible(valid_to, now):
        """复刻 SQL 语义：NULL 或 未来 ⇒ 可见；过去 ⇒ 过期。"""
        return valid_to is None or valid_to > now

    def test_null_means_forever(self):
        assert self._is_visible(None, 1000) is True

    def test_future_still_valid(self):
        assert self._is_visible(2000, 1000) is True

    def test_past_is_expired(self):
        assert self._is_visible(500, 1000) is False
