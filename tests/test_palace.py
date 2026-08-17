"""v7.0 魔法记忆宫殿 — palace.py 单元测试 (无需 DB)

覆盖: 分类树 / 档号生成 / 生命周期规则 / SQL 生成
"""
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import palace


class TestClassify:
    def test_proxy_keyword(self):
        r = palace.classify("在GZ部署xray代理 2081端口", "ops")
        assert r["room"] == "proxy"

    def test_deploy_keyword(self):
        r = palace.classify("rsync部署到GZ服务器", "worklog")
        assert r["room"] == "deploy"

    def test_secret_keyword(self):
        r = palace.classify("密钥在保险柜KEY.txt line3", "ops")
        assert r["room"] == "secret"

    def test_user_preference(self):
        r = palace.classify("用户喜欢红果短剧风格AI美女图", "preference")
        assert r["room"] == "user"

    def test_security_priority(self):
        r = palace.classify("服务器安全审计 漏洞扫描", "ops")
        assert r["room"] == "security"

    def test_model_room(self):
        r = palace.classify("DeepSeek v4-flash 模型配置", "knowledge")
        assert r["room"] == "model"

    def test_billing_room(self):
        r = palace.classify("豆包余额查询 充值", "ops")
        assert r["room"] == "billing"

    def test_content_room(self):
        r = palace.classify("公众号文章排版 小红书", "knowledge")
        assert r["room"] == "content"

    def test_unknown_falls_to_wing(self):
        r = palace.classify("完全无关的内容xyz", "knowledge")
        assert r["wing"] in palace.WINGS

    def test_wing_mapping(self):
        assert palace.classify("xray部署", "ops")["wing"] == "O"
        assert palace.classify("用户偏好", "preference")["wing"] == "P"


class TestArchiveNo:
    def test_format(self):
        no = palace.gen_archive_no("K", "PROXY", "", 2026, 7)
        assert no == "K·PROXY·2026-0007"

    def test_default_year(self):
        from datetime import datetime
        no = palace.gen_archive_no("K", "MEMORY", "", 0, 1)
        assert no.endswith(f"-0001")
        assert str(datetime.now().year) in no


class TestRetention:
    def test_permanent_no_decay(self):
        assert palace.RETENTION_RULES["permanent"]["decay"] == 0.0
        assert palace.RETENTION_RULES["permanent"]["keep_days"] is None

    def test_short_90_days(self):
        assert palace.RETENTION_RULES["short"]["keep_days"] == 90

    def test_long_slow_decay(self):
        assert palace.RETENTION_RULES["long"]["decay"] == 0.999


class TestSchemaSQL:
    def test_taxonomy_sql(self):
        sql = palace.build_taxonomy_table_sql()
        assert "archive_taxonomy" in sql
        assert "UNIQUE(wing, room, shelf)" in sql

    def test_tome_cards_sql(self):
        sql = palace.build_tome_cards_sql()
        assert "tome_cards" in sql
        assert "memory_id BIGINT PRIMARY KEY" in sql
        assert "tags TEXT[]" in sql


class TestRefinePrompt:
    def test_prompt_has_json_fields(self):
        p = palace.refine_prompt("测试内容")
        assert "title" in p
        assert "summary" in p
        assert "tags" in p
