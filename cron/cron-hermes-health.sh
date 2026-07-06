#!/bin/bash
# 每日健康巡检 — 通过 Hermes 执行
/home/ubuntu/.local/bin/hermes -p mnemosyne -z '加载system-housekeeping技能，检查GZ服务器磁盘/内存/Mnemosyne API(:8010/echo)/TMT树状态。正常则存一条低重要度健康记录到Mnemosyne。' 2>&1 | tail -3
