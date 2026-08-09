#!/usr/bin/env python3
"""
Mnemosyne v7.1 抽屉周报 (drawer_report.py)
每周生成双抽屉健康报告: 分布/遗忘候选top/合并统计/建议
用法: venv/bin/python drawer_report.py
输出: /tmp/drawer_report_YYYYMMDD.json + 打印摘要
"""
import asyncio
import json
import sys
from datetime import datetime

sys.path.insert(0, "/opt/mnemosyne")
from tmt.distill import load_env, get_pool


async def main():
    load_env()
    pool = await get_pool()
    try:
        temp = await pool.fetch("""
            SELECT temp_drawer, COUNT(*) AS cnt FROM memories
            WHERE user_id='default' AND is_deleted=FALSE GROUP BY 1 ORDER BY 1
        """)
        time_d = await pool.fetch("""
            SELECT time_drawer, COUNT(*) AS cnt FROM memories
            WHERE user_id='default' AND is_deleted=FALSE GROUP BY 1 ORDER BY 1
        """)
        forget = await pool.fetch("""
            SELECT id, LEFT(content, 80) AS preview, category, heat_score
            FROM memories
            WHERE user_id='default' AND is_deleted=FALSE
              AND COALESCE(metadata->>'forget_candidate','false')='true'
            ORDER BY heat_score ASC LIMIT 10
        """)
        merged = await pool.fetchval("""
            SELECT COUNT(*) FROM memories
            WHERE user_id='default' AND is_deleted=TRUE
              AND metadata->>'merged_into' IS NOT NULL
        """)
        denoised = await pool.fetchval("""
            SELECT COUNT(*) FROM memories
            WHERE user_id='default' AND is_deleted=FALSE
              AND COALESCE(metadata->>'denoised','false')='true'
        """)
        pinned = await pool.fetchval("""
            SELECT COUNT(*) FROM memories
            WHERE user_id='default' AND is_deleted=FALSE
              AND COALESCE(metadata->>'pinned','false')='true'
        """)
        total = await pool.fetchval("""
            SELECT COUNT(*) FROM memories WHERE user_id='default' AND is_deleted=FALSE
        """)
        garbage = await pool.fetchval("""
            SELECT COUNT(*) FROM memories
            WHERE user_id='default' AND is_deleted=FALSE
              AND COALESCE(metadata->>'is_garbage','false')='true'
        """)

        # 存储水位 (空间感知预警)
        import shutil
        du = shutil.disk_usage("/")
        disk_pct = round(du.used / du.total * 100, 1)
        storage_level = "low"
        if disk_pct >= 90:
            storage_level = "critical"
        elif disk_pct >= 70:
            storage_level = "warning"

        report = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "total_active": total,
            "temp_drawers": {r["temp_drawer"]: r["cnt"] for r in temp},
            "time_drawers": {r["time_drawer"]: r["cnt"] for r in time_d},
            "forget_candidates": len(forget) if forget else 0,
            "forget_top": [{"id": r["id"], "preview": r["preview"], "heat": r["heat_score"]} for r in forget],
            "garbage_marked": garbage or 0,
            "merged_total": merged or 0,
            "denoised_total": denoised or 0,
            "pinned_total": pinned or 0,
            "storage": {"disk_usage_pct": disk_pct, "level": storage_level,
                        "message": "空间充足" if storage_level == "low" else ("⚠️ 警戒水位, 建议人工处理: POST /drawers/authorize" if storage_level == "warning" else "🚨 高水位, 必须人工处理")},
            "health": "✅" if (forget and len(forget) > 50) else "📋",
        }
        fname = f"/tmp/drawer_report_{datetime.now().strftime('%Y%m%d')}.json"
        with open(fname, "w") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(json.dumps(report, ensure_ascii=False))
        print(f"报告已存: {fname}")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
