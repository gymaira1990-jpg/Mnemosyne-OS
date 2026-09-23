"""归档质量契约测试 (v7.8.4) — 分级截断 / 证据签名 / 短会话不弃 / 汇报卡入库形态

背景 (2026-09-24 实测):
  用户问「生产服务器上那个几百兆的文件是什么」, 查不到 —— 因为 `archive_session.py` 对每条消息
  一刀切 `content[:2000]`, 而收尾汇报常 >2000 字, 被切掉的恰是**交付物路径/哈希/实测数字**。
  同源毛病与 v7.8.2 的「语义等价 ≠ 可用」一致: **改了措辞/粒度而消费端没跟上, 不报错、只失真**。

本测试锁死三件事:
  ① 截断策略(汇报/用户消息全文, 过程消息压缩) ② 工具证据签名形态 ③ 汇报卡入宫的
  受控 category 与请求形态(不许自造 category —— 服务端会静默归一化为 knowledge)。

不依赖数据库/网络: 临时 sqlite + monkeypatch urlopen。
"""
import importlib.util
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "scripts" / "archive_session.py"
REPORT = ROOT / "scripts" / "report_card.py"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def arch():
    return _load("arch_v784", ARCHIVE)


@pytest.fixture(scope="module")
def rep():
    return _load("rep_v784", REPORT)


# ---------------- 临时库 ----------------

def _mkdb(tmp_path):
    db = tmp_path / "state.db"
    con = sqlite3.connect(db)
    con.executescript("""
        CREATE TABLE sessions(id TEXT PRIMARY KEY, title TEXT, message_count INTEGER, started_at TEXT);
        CREATE TABLE messages(id INTEGER PRIMARY KEY, session_id TEXT, role TEXT,
                              content TEXT, tool_calls TEXT, active INTEGER, timestamp REAL);
    """)
    return str(db), con


def _add(con, sid, title, msgs):
    """msgs: [(role, content, tool_calls_json)]"""
    con.execute("INSERT INTO sessions VALUES (?,?,?,?)",
                (sid, title, len(msgs), "2026-09-24 05:00:00"))
    for i, (role, content, tc) in enumerate(msgs, start=1):
        con.execute("INSERT INTO messages VALUES (?,?,?,?,?,1,?)",
                    (i, sid, role, content, tc, 1758660000 + i))
    con.commit()


TC = json.dumps([{"id": "call_1", "type": "function",
                  "function": {"name": "terminal", "arguments": "{}"}},
                 {"id": "call_2", "type": "function",
                  "function": {"name": "terminal", "arguments": "{}"}},
                 {"id": "call_3", "type": "function",
                  "function": {"name": "read_file", "arguments": "{}"}}])


class TestTieredTruncation:
    """① 收尾汇报与用户消息全文保留, 只有过程消息被压缩。"""

    def test_final_report_survives_intact(self, arch, tmp_path):
        long_report = ("交付清单如下: C:\\Users\\<user>\\Desktop\\交付箱\\99_归档\\报告.md " * 200)
        assert len(long_report) > 2000, "构造的汇报必须超过旧版 2000 字一刀切阈值"
        db, con = _mkdb(tmp_path)
        _add(con, "s1", "测试会话", [
            ("user", "帮我搬文件", None),
            ("assistant", "中间分析" * 500, TC),
            ("assistant", long_report + "\n\n汇报完毕请指示", None),
        ])
        s = arch.get_session(db, "s1")
        assert "汇报完毕请指示" in s["content"], "收尾汇报被截断 → 交付要素丢失"
        assert s["stats"]["final_report_chars"] > 2000, "汇报未被识别为最终汇报"
        # 只有过程消息那一条被压缩
        assert s["content"].count("...(截断") == 1, "截断次数不对: 不应动到汇报"

    def test_user_message_kept(self, arch, tmp_path):
        long_user = "需求原文" * 900          # 3600 字 < LIMIT_USER
        db, con = _mkdb(tmp_path)
        _add(con, "s2", "t", [("user", long_user, None), ("assistant", "收到", None)])
        s = arch.get_session(db, "s2")
        assert long_user in s["content"]

    def test_process_message_compressed(self, arch, tmp_path):
        db, con = _mkdb(tmp_path)
        _add(con, "s3", "t", [("user", "q", None),
                              ("assistant", "过程" * 2000, TC),
                              ("assistant", "终稿", None)])
        s = arch.get_session(db, "s3")
        assert "...(截断" in s["content"]
        assert s["stats"]["truncated_process"] >= 1

    def test_total_budget_never_eats_report(self, arch, tmp_path):
        """总预算超限时只能压缩过程消息, 汇报依然完整。"""
        big = "过程消息长文" * 4000           # ~24000 字
        report = "收尾汇报" + "X" * 300 + "汇报完毕请指示"
        db, con = _mkdb(tmp_path)
        _add(con, "s4", "t", [("user", "q", None),
                              ("assistant", big, TC),
                              ("assistant", big, TC),
                              ("assistant", big, TC),
                              ("assistant", report, None)])
        s = arch.get_session(db, "s4")
        assert len(s["content"]) <= arch.MAX_TOTAL + 2000
        assert "汇报完毕请指示" in s["content"]


    def test_budget_trimmed_counts_messages_not_iterations(self, arch, tmp_path, monkeypatch):
        """让位计数语义 = 消息条数(旧版是循环迭代次数, 实测跑出 4227 这种无意义数字)。"""
        monkeypatch.setattr(arch, "MAX_TOTAL", 3000)     # 压低预算才触发让位路径
        big = "过程长文" * 600                            # 每条 2400 字 → 先被 1200 阈值压
        db, con = _mkdb(tmp_path)
        _add(con, "s13", "t", [("user", "q", None), ("assistant", big, None),
                               ("assistant", big, None), ("assistant", big, None),
                               ("assistant", "终稿 汇报完毕请指示", None)])
        s = arch.get_session(db, "s13")
        n_proc = 3
        assert 0 < s["stats"]["budget_trimmed"] <= n_proc, \
            f"让位计数应是消息条数(<= {n_proc}), 实得 {s['stats']['budget_trimmed']}"
        assert "汇报完毕请指示" in s["content"], "让位不许吃掉收尾汇报"


class TestEvidenceSignature:
    """② 工具证据签名: 让语义层看得见"这轮干了什么"。"""

    def test_signature_counts(self, arch):
        sig = arch.tool_signature(TC)
        assert "terminal×2" in sig and "read_file" in sig
        assert sig.startswith(" ⟪工具:") and sig.endswith("⟫")

    def test_signature_tolerates_garbage(self, arch):
        assert arch.tool_signature("") == ""
        assert arch.tool_signature("not-json") == ""
        assert arch.tool_signature(None) == ""
        assert arch.tool_signature('[{"type":"function"}]') == ""

    def test_signature_appears_in_content(self, arch, tmp_path):
        db, con = _mkdb(tmp_path)
        _add(con, "s5", "t", [("user", "q", None), ("assistant", "跑完了", TC)])
        s = arch.get_session(db, "s5")
        assert "⟪工具: terminal×2, read_file⟫" in s["content"]

    def test_last_report_id_picks_final_ai(self, arch, tmp_path):
        db, con = _mkdb(tmp_path)
        _add(con, "s6", "t", [("user", "q", None), ("assistant", "a", None),
                              ("user", "再问", None), ("assistant", "最终答复", None)])
        s = arch.get_session(db, "s6")
        assert s["stats"]["final_report_chars"] == len("最终答复")


class TestTitlePrefixes:
    """项目前缀(回库) + 短会话标记。"""

    def test_project_prefix_from_keywords(self, arch, tmp_path, monkeypatch):
        monkeypatch.setattr(arch, "PROJECT_KEYWORDS", {"relife": ["relife", "首对外"]})
        db, con = _mkdb(tmp_path)
        # 6 条消息 → 不算短会话; 正文同时命中 2 个关键词(阈值)才算项目
        _add(con, "s7", "搬文件", [("user", "relife 首对外 项目", None)]
             + [("assistant", f"第{i}步", None) for i in range(5)])
        s = arch.get_session(db, "s7")
        assert s["title"] == "[relife] 搬文件", s["title"]

    def test_short_and_project_single_tag(self, arch, tmp_path, monkeypatch):
        """短会话 + 项目 → 单个标签 [短·relife], 不是 [短] [relife]。"""
        monkeypatch.setattr(arch, "PROJECT_KEYWORDS", {"relife": ["relife", "首对外"]})
        db, con = _mkdb(tmp_path)
        _add(con, "s7b", "改个名", [("user", "relife 首对外 项目", None), ("assistant", "好了", None)])
        s = arch.get_session(db, "s7b")
        assert s["title"] == "[短·relife] 改个名", s["title"]

    def test_title_prefix_is_idempotent(self, arch, tmp_path, monkeypatch):
        """已带标签的标题再处理不许叠加。"""
        monkeypatch.setattr(arch, "PROJECT_KEYWORDS", {"relife": ["relife", "首对外"]})
        db, con = _mkdb(tmp_path)
        _add(con, "s7c", "[relife] 搬文件", [("user", "relife 首对外", None)]
             + [("assistant", "ok", None)] * 5)
        assert arch.get_session(db, "s7c")["title"] == "[relife] 搬文件"

    def test_short_session_flagged_not_dropped(self, arch, tmp_path):
        db, con = _mkdb(tmp_path)
        _add(con, "s8", "小任务", [("user", "改个名", None), ("assistant", "改好了", None)])
        s = arch.get_session(db, "s8")
        assert s["title"].startswith("[短]")
        assert s["content"]


class TestAutoModeShortSessions:
    """③ 短会话不再被静默跳过 (旧版 `message_count < 5: continue`)。"""

    @pytest.fixture
    def stub(self, arch, tmp_path, monkeypatch):
        seen = {"archived": [], "saved": None}
        monkeypatch.setattr(arch, "load_archived", lambda: set())
        monkeypatch.setattr(arch, "list_sessions",
                            lambda db, limit=20: [{"id": "short-1", "title": "小任务",
                                                   "message_count": 2, "started_at": "x"}])
        monkeypatch.setattr(arch, "get_session",
                            lambda db, sid=None: {"session_id": "short-1", "title": "[短] 小任务",
                                                  "content": "内容", "message_count": 2, "stats": {}})
        monkeypatch.setattr(arch, "archive_to_mnemosyne",
                            lambda s, dry_run=False: seen["archived"].append(s["session_id"]) or {"archived": True, "memory_id": 1})
        monkeypatch.setattr(arch, "save_archived", lambda a: seen.update(saved=set(a)))
        return seen

    def test_short_session_archived_by_default(self, arch, stub):
        arch.auto_mode(include_short=True)
        assert stub["archived"] == ["short-1"], "短会话被跳过了 → 小任务无痕"

    def test_skip_short_flag_restores_old_behaviour(self, arch, stub):
        arch.auto_mode(include_short=False)
        assert stub["archived"] == [], "--skip-short 应还原旧行为"


class TestReportCardContract:
    """④ 汇报卡: 抽取 + 受控 category + 请求形态。"""

    SAMPLE = (
        "## 交付完成\n"
        "成品: C:\\Users\\<user>\\Desktop\\交付箱\\99_归档\\物料归档_20260924\\\n"
        "清单: /home/<user>/.hermes/reports/cards.jsonl\n"
        "线上: https://example.com/posts/123\n"
        "sha256: 7b63ac4e77268b5d313706912ff841b7\n"
        "体积 507MB / 1.3GB, 耗时 85 秒\n"
        "哈希全部比对一致 ✓\n"
        "汇报完毕请指示"
    )

    def test_extract_signals(self, rep):
        sig = rep.extract_signals(self.SAMPLE)
        for k in ("路径", "URL", "哈希", "实测数字", "收尾语"):
            assert k in sig, f"缺信号: {k}"
        assert any(p.startswith("C:\\") for p in sig["路径"])

    def test_is_report_card(self, rep):
        assert rep.is_report_card(self.SAMPLE)
        assert not rep.is_report_card("好, 收到")
        assert not rep.is_report_card("今天天气不错, 随便聊聊")

    def test_card_is_stable_and_structured(self, rep):
        sig = rep.extract_signals(self.SAMPLE)
        card = rep.build_card({"id": 42, "session_id": "sess-1", "timestamp": 1758660000,
                               "content": self.SAMPLE}, sig)
        assert card["msg_id"] == 42
        assert any("<user>" in p for p in card["paths"])
        assert "https://example.com/posts/123" in card["urls"]
        assert card["hashes"] and card["measures"]
        assert rep.card_digest(card) == rep.card_digest(dict(card)), "指纹必须稳定"
        txt = rep.card_text(card)
        assert "[汇报卡]" in txt and "507MB" in txt and "<user>" in txt

    def test_category_must_be_controlled(self, rep):
        """自造 category 会被服务端静默归一化 —— 只许取 capabilities 词表内的值。"""
        expected = {"knowledge", "pitfall", "reference", "project", "ops",
                    "deploy", "preference", "session", "worklog", "temp"}
        assert rep.CONTROLLED_CATEGORIES == expected
        assert rep.CATEGORY in rep.CONTROLLED_CATEGORIES

    def test_push_payload_shape(self, rep, monkeypatch):
        captured = {}

        class FakeResp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return json.dumps({"stored": True, "memory_id": 7}).encode()

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data.decode())
            captured["method"] = req.get_method()
            return FakeResp()

        monkeypatch.setattr(rep.urllib.request, "urlopen", fake_urlopen)
        sig = rep.extract_signals(self.SAMPLE)
        card = rep.build_card({"id": 1, "session_id": "s", "timestamp": 0,
                               "content": self.SAMPLE}, sig)
        out = rep.push_card(card)
        assert out.get("stored") is True
        assert captured["method"] == "POST"
        assert captured["url"].endswith("/api/v1/memories")
        body = captured["body"]
        assert set(body) == {"user_id", "content", "category"}, "字段必须显式, 不靠服务端默认"
        assert body["category"] == rep.CATEGORY
        assert body["content"].startswith("[汇报卡]")

    def test_run_is_idempotent(self, rep, tmp_path, monkeypatch):
        db, con = _mkdb(tmp_path)
        _add(con, "s9", "交付", [("user", "干活", None),
                                 ("assistant", self.SAMPLE, None)])
        monkeypatch.setattr(rep, "REPORTS_DIR", str(tmp_path))
        monkeypatch.setattr(rep, "CARDS_FILE", str(tmp_path / "cards.jsonl"))
        monkeypatch.setattr(rep, "INDEX_FILE", str(tmp_path / ".index.json"))
        first = rep.run(db, "s9", 1)
        assert first["cards_found"] == 1 and first["new_cards"] == 1
        second = rep.run(db, "s9", 1)
        assert second["new_cards"] == 0 and second["duplicates"] == 1, "重复抽卡 → 记忆污染"

    def test_final_mode_one_card_per_session(self, rep, tmp_path):
        """默认 final: 每场会话只取收尾汇报 —— 否则一场技术会话会被刷成几十张卡(实测 66 张)。"""
        db, con = _mkdb(tmp_path)
        _add(con, "s11", "大活", [("user", "干活", None),
                                  ("assistant", self.SAMPLE, None),
                                  ("assistant", "中间过程 C:\\tmp\\a.txt 507MB", None),
                                  ("assistant", "最终交付 C:\\Users\\<user>\\out.md 1.3GB "
                                                "sha256 7b63ac4e77268b5d", None)])
        msgs = rep.fetch_report_messages(db, "s11", 1, "final")
        assert len(msgs) == 1, f"final 模式每会话只该出一张卡, 实得 {len(msgs)}"
        assert "最终交付" in msgs[0][0]["content"]

    def test_final_mode_looks_back_past_short_closer(self, rep, tmp_path):
        """会话常以一句简短收尾结束 → 汇报卡要能回看到前一条真汇报。"""
        db, con = _mkdb(tmp_path)
        _add(con, "s11b", "大活", [("user", "干活", None),
                                   ("assistant", self.SAMPLE, None),
                                   ("assistant", "好的，就这样吧", None)])
        msgs = rep.fetch_report_messages(db, "s11b", 1, "final")
        assert len(msgs) == 1 and "[汇报卡]" not in msgs[0][0]["content"]
        assert "成品:" in msgs[0][0]["content"], "应回看到真汇报那条"

    def test_final_mode_no_card_when_nothing_delivered(self, rep, tmp_path):
        db, con = _mkdb(tmp_path)
        _add(con, "s11c", "闲聊", [("user", "聊聊", None), ("assistant", "好的，就这样吧", None)])
        assert rep.fetch_report_messages(db, "s11c", 1, "final") == [], "无交付要素就不该造卡"

    def test_tool_role_messages_never_become_cards(self, rep, tmp_path):
        """role='tool' 是工具回显 —— 把它的 diff/日志当交付汇报过一次(实测), 必须排除。"""
        db, con = _mkdb(tmp_path)
        _add(con, "s14", "干活", [("user", "q", None),
                                  ("tool", "C:\\tmp\\x.txt 507MB sha256 7b63ac4e77268b5d", None),
                                  ("assistant", "好的，就这样吧", None)])
        assert rep.fetch_report_messages(db, "s14", 1, "final") == []

    def test_path_signal_drops_diff_noise(self, rep):
        """工具输出的 `\\n` 转义与 diff 的 `+++` 曾被当路径(实测), 必须清掉。"""
        noisy = r"/home/u/proj/a.py\n+++ b/a.py\n--- /home/u/proj/b.py 507MB 1.3GB"
        sig = rep.extract_signals(noisy)
        joined = " ".join(sig.get("路径", []))
        assert "+++" not in joined, f"diff 噪声未清理: {joined}"
        assert "\\n" not in joined, f"转义残留: {joined}"
        assert all(len(p) <= rep.MAX_SIG_LEN for p in sig.get("路径", []))

    def test_scan_mode_is_stricter_than_all(self, rep):
        weak = "顺手看了下 C:\\tmp\\x.txt, 有 3MB 数据"      # 2 类信号
        assert rep.is_report_card(weak, None, "all")
        assert not rep.is_report_card(weak, None, "scan"), "scan 不抬门槛 → 污染记忆"
        assert rep.is_report_card(self.SAMPLE, None, "scan")
        assert rep.is_report_card(self.SAMPLE, None, "final")

    def test_scan_mode_caps_cards_per_session(self, rep, tmp_path):
        db, con = _mkdb(tmp_path)
        _add(con, "s12", "多轮交付", [("user", "q", None)] + [("assistant", self.SAMPLE, None)] * 6)
        assert len(rep.fetch_report_messages(db, "s12", 1, "scan")) == 3

    def test_dry_run_writes_nothing(self, rep, tmp_path, monkeypatch):
        db, con = _mkdb(tmp_path)
        _add(con, "s10", "交付", [("assistant", self.SAMPLE, None)])
        monkeypatch.setattr(rep, "REPORTS_DIR", str(tmp_path / "rep"))
        monkeypatch.setattr(rep, "CARDS_FILE", str(tmp_path / "rep" / "cards.jsonl"))
        monkeypatch.setattr(rep, "INDEX_FILE", str(tmp_path / "rep" / ".index.json"))
        out = rep.run(db, "s10", 1, dry_run=True)
        assert out["dry_run"] and out["new_cards"] == 1
        assert not (tmp_path / "rep" / "cards.jsonl").exists()


class TestArchivePushContractRegression:
    """回归: 会话归档的推送形态不变 (POST /sessions/archive, json body, 四字段)。"""

    def test_session_archive_payload(self, arch, monkeypatch):
        captured = {}

        class FakeResp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return json.dumps({"archived": True, "memory_id": 9}).encode()

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data.decode())
            captured["content_type"] = req.headers.get("Content-type")
            return FakeResp()

        monkeypatch.setattr(arch.urllib.request, "urlopen", fake_urlopen)
        out = arch.archive_to_mnemosyne({"session_id": "s", "title": "[项目] t", "content": "正文"})
        assert out.get("archived") is True
        assert captured["url"].endswith("/api/v1/sessions/archive")
        assert set(captured["body"]) == {"user_id", "session_id", "title", "content"}
        assert captured["body"]["user_id"] == "default"
        assert captured["content_type"] == "application/json"

    def test_dry_run_reports_stats(self, arch):
        out = arch.archive_to_mnemosyne({"session_id": "s", "title": "t", "content": "x" * 10,
                                         "stats": {"messages": 1}}, dry_run=True)
        assert out["dry_run"] and out["would_send"] == 10
        assert "stats" in out
