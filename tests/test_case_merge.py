"""用例合并与去重（2026-11-07）

人裁决导出的题会进评测基线（`make eval-live`）。这里锁两件事：
1. **同 query 只能算一次分** —— 不去重就是同一道题计两遍，分数虚高；
2. **后者覆盖前者** —— 人的判断会变，新裁决比手写旧题更可信。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.eval_recall import load_cases  # noqa: E402


def _write(tmp_path, name, rows):
    p = tmp_path / name
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    return str(p)


def test_merges_two_files(tmp_path):
    a = _write(tmp_path, "a.jsonl", [{"q": "q1", "expect": ["A"]}])
    b = _write(tmp_path, "b.jsonl", [{"q": "q2", "forbid": ["X"]}])
    cases, per_file = load_cases([a, b])
    assert len(cases) == 2
    assert per_file[a] == 1 and per_file[b] == 1


def test_duplicate_query_kept_once_later_wins(tmp_path):
    a = _write(tmp_path, "a.jsonl", [{"q": "周报怎么写", "expect": ["旧答案"]}])
    b = _write(tmp_path, "b.jsonl", [{"q": "周报怎么写", "expect": ["K·DEMO·2026-0029"]}])
    cases, _ = load_cases([a, b])
    assert len(cases) == 1, "同一句问法不能算两次分"
    assert cases[0]["expect"] == ["K·DEMO·2026-0029"], "后出现的（人工裁决）应覆盖手写题"


def test_missing_file_reported_not_crash(tmp_path):
    a = _write(tmp_path, "a.jsonl", [{"q": "q1", "expect": ["A"]}])
    cases, per_file = load_cases([a, str(tmp_path / "nope.jsonl")])
    assert len(cases) == 1
    assert per_file[str(tmp_path / "nope.jsonl")] == -1, "缺失文件用 -1 标记，由调用方决定报错"


def test_empty_file_is_zero_not_error(tmp_path):
    a = _write(tmp_path, "empty.jsonl", [])
    cases, per_file = load_cases([a])
    assert cases == []
    assert per_file[a] == 0
