"""v7.4 WIKI 知识图谱 — 纯函数逻辑测试 (不依赖 DB)

覆盖: 幂等判定 (同hash→exists / 异hash→updated) + 指纹计算 + 抽取结果解析。
生产逻辑同源复制 (见 main.py create_wiki_page / scripts/md_ingest.py file_hash)。
"""
import hashlib
import json


def file_hash(path: str) -> str:
    """与 scripts/md_ingest.py 同源"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def decide_status(existing_hash: str, new_hash: str) -> str:
    """幂等判定 (同源同hash→exists / 异hash→updated / 无存量→created)"""
    if not existing_hash:
        return "created"
    if existing_hash == new_hash:
        return "exists"
    return "updated"


def parse_extract_output(raw) -> dict:
    """解析 LLM 抽取输出 (兼容 str/dict)"""
    if isinstance(raw, str):
        data = json.loads(raw)
    elif isinstance(raw, dict):
        data = raw
    else:
        return {"entities": [], "relations": []}
    return {
        "entities": data.get("entities", []) or [],
        "relations": data.get("relations", []) or [],
    }


class TestWikiIdempotency:
    def test_created_no_existing(self):
        assert decide_status("", "abc") == "created"

    def test_exists_same_hash(self):
        assert decide_status("abc", "abc") == "exists"

    def test_updated_diff_hash(self):
        assert decide_status("abc", "def") == "updated"

    def test_hash_stable(self, tmp_path):
        p = tmp_path / "doc.md"
        p.write_text("内容内容内容", encoding="utf-8")
        h1 = file_hash(str(p))
        h2 = file_hash(str(p))
        assert h1 == h2
        assert len(h1) == 64  # sha256

    def test_hash_changes_on_edit(self, tmp_path):
        p = tmp_path / "doc.md"
        p.write_text("v1 内容", encoding="utf-8")
        h1 = file_hash(str(p))
        p.write_text("v2 内容修改", encoding="utf-8")
        h2 = file_hash(str(p))
        assert h1 != h2


class TestExtractParsing:
    def test_parse_str_json(self):
        raw = '{"entities":[{"name":"A","type":"concept"}],"relations":[{"from":"A","relation":"建于","to":"B"}]}'
        d = parse_extract_output(raw)
        assert len(d["entities"]) == 1
        assert d["entities"][0]["name"] == "A"
        assert len(d["relations"]) == 1

    def test_parse_dict(self):
        raw = {"entities": [], "relations": []}
        d = parse_extract_output(raw)
        assert d["entities"] == []

    def test_parse_garbage(self):
        d = parse_extract_output(None)
        assert d == {"entities": [], "relations": []}

    def test_parse_bad_json_fallback(self):
        import pytest
        with pytest.raises(json.JSONDecodeError):
            parse_extract_output("{not-json")
