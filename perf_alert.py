#!/usr/bin/env python3
"""
Mnemosyne 性能水位告警 (perf_alert.py)
每30分钟检查: 内存/磁盘/连接数/慢查询; 超阈值写告警日志
阈值: 内存>85% / 磁盘>85% / PG连接>80 / 慢查询>2s
用法: venv/bin/python perf_alert.py
"""
import os, sys, subprocess, json
from datetime import datetime

ALERT_LOG = "/tmp/perf_alert.log"
THRESHOLDS = {"mem_pct": 85, "disk_pct": 85, "pg_conns": 80, "slow_ms": 2000}


def sh(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15).stdout.strip()
    except Exception:
        return ""


def main():
    alerts = []
    # 内存
    try:
        with open("/proc/meminfo") as f:
            d = {}
            for line in f:
                k, v = line.split(":")
                d[k.strip()] = int(v.strip().split()[0])
        total = d["MemTotal"]
        avail = d["MemAvailable"]
        mem_pct = (total - avail) / total * 100
        if mem_pct > THRESHOLDS["mem_pct"]:
            alerts.append(f"[MEM] {mem_pct:.0f}% used")
    except Exception:
        pass
    # 磁盘
    du = sh("df / | tail -1")
    if du:
        pct = int(du.split()[4].rstrip("%"))
        if pct > THRESHOLDS["disk_pct"]:
            alerts.append(f"[DISK] {pct}% used")
    # PG 连接数
    conns = sh("sudo -u postgres psql -t -c \"SELECT count(*) FROM pg_stat_activity;\" 2>/dev/null")
    if conns.strip().isdigit():
        n = int(conns.strip())
        if n > THRESHOLDS["pg_conns"]:
            alerts.append(f"[PG_CONN] {n} connections")
    # 慢查询 (pg_stat_statements)
    slow = sh("sudo -u postgres psql -d mnemosyne -t -c \"SELECT count(*) FROM pg_stat_statements WHERE mean_exec_time > %d;\" 2>/dev/null" % THRESHOLDS["slow_ms"])
    if slow.strip().isdigit() and int(slow.strip()) > 0:
        alerts.append(f"[SLOW] {slow.strip()} queries > {THRESHOLDS['slow_ms']}ms")

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if alerts:
        msg = f"[{ts}] ⚠️ 水位告警: {'; '.join(alerts)}"
        with open(ALERT_LOG, "a") as f:
            f.write(msg + "\n")
        print(msg)
    else:
        # 静默 (健康, 不刷日志 — 每30分钟无告警不打扰)
        pass


if __name__ == "__main__":
    main()
