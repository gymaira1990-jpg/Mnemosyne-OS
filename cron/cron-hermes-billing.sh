#!/bin/bash
/home/ubuntu/.local/bin/hermes -p mnemosyne -z '加载api-billing-check技能，查DeepSeek+火山引擎API余额，存Mnemosyne(category=fact,importance=0.7)并报告。' 2>&1 | tail -3
