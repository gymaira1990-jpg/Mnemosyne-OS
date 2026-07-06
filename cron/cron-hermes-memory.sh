#!/bin/bash
/home/ubuntu/.local/bin/hermes -p mnemosyne -z '检查HERMES Layer1 memory容量。>80%则归档到Mnemosyne。目标保持<60%。加载hermes-memory-system技能。' 2>&1 | tail -3
