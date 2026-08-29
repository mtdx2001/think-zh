# -*- coding: utf-8 -*-
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # app\ 根（tm_store.py 所在）
import tm_store

def count():
    con = tm_store.conn()
    return con.execute("SELECT COUNT(*) FROM tm WHERE source LIKE 'review-%'").fetchone()[0]

a = count()
print("当前已审校入库:", a, "条", flush=True)
time.sleep(60)
b = count()
print("60秒后:", b, "条  (速率 {:.1f} 条/分)".format(b - a), flush=True)
