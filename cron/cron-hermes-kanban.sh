#!/bin/bash
/home/ubuntu/.local/bin/hermes -p mnemosyne -z '列出所有kanban boards，归档7天前的done任务，列出blocked超24h任务，生成健康报告。' 2>&1 | tail -5
