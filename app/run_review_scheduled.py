# -*- coding: utf-8 -*-
"""定时精修启动器（供 schtasks 调用）：从本机凭据读 key → 调 review.py 全量审校（仅谷价）。"""
import os, re, sys, subprocess, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
CREDS = r"E:\DSH011rc1\home\.credentials.yaml"
LOG = os.path.join(HERE, "out", "review_scheduled.log")

m = re.search(r"DEEPSEEK_API_KEY:\s*(\S+)", open(CREDS, encoding="utf-8").read())
if not m:
    print("凭据缺失"); sys.exit(1)

env = dict(os.environ, DEEPSEEK_API_KEY=m.group(1))
with open(LOG, "a", encoding="utf-8") as log:
    log.write(f"\n===== 定时精修启动 {datetime.datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
    log.flush()
    subprocess.run(
        [sys.executable, "-X", "utf8", "-u", os.path.join(HERE, "review.py"),
         "--all", "--yes", "--valley-only"],
        env=env, stdout=log, stderr=subprocess.STDOUT)
