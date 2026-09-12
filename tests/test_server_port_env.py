"""v7.8.3 — 服务监听端口/地址由环境变量决定 (修复 main.py 入口硬编码)

两层契约:
  ① `config.PORT` / `config.HOST` 读 `MNEMOSYNE_PORT` / `MNEMOSYNE_HOST`(子进程验证, 不污染本进程)
  ② 服务入口 `main._run_server()` **必须使用** 这两个值 —— 这一条才是本次真正的修复点:
     入口曾经写死 `host="127.0.0.1", port=8010`, 环境变量被静默忽略(不报错、只是没效果)。
     ② 用例在旧代码下会红(写死时 captured["port"] == 8010 != 9123), 反证过。
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _config_value(expr: str, env_override: dict) -> str:
    env = dict(os.environ)
    for k in ("MNEMOSYNE_PORT", "MNEMOSYNE_HOST"):
        env.pop(k, None)
    env.update(env_override)
    out = subprocess.run(
        [sys.executable, "-c", f"import config; print({expr})"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=60,
    )
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


class TestConfigReadsEnv:
    def test_default_port_and_host(self):
        assert _config_value("config.PORT", {}) == "8010"
        assert _config_value("config.HOST", {}) == "127.0.0.1"

    def test_env_override_is_honored(self):
        assert _config_value("config.PORT", {"MNEMOSYNE_PORT": "9123"}) == "9123"
        assert _config_value("config.HOST", {"MNEMOSYNE_HOST": "0.0.0.0"}) == "0.0.0.0"


class TestServerEntryUsesConfig:
    """入口接线契约 —— 写死端口时本用例必红(反证过)。"""

    def test_run_server_passes_config_host_and_port(self, monkeypatch):
        import uvicorn
        import main

        captured = {}
        monkeypatch.setattr(uvicorn, "run", lambda *a, **kw: captured.update(kw))
        monkeypatch.setattr(main, "PORT", 9123, raising=False)
        monkeypatch.setattr(main, "HOST", "0.0.0.0", raising=False)

        main._run_server()

        assert captured.get("port") == 9123, f"入口未使用 config.PORT: {captured}"
        assert captured.get("host") == "0.0.0.0", f"入口未使用 config.HOST: {captured}"
        assert captured.get("app") == "main:app" or captured.get("app") is None
