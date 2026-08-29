# -*- coding: utf-8 -*-
"""一次性全量升级：realtime-1.8b 条目 → 7B 重译（显存瘦身配置，与常驻 1.8B 并存）。"""
import sys, time
sys.path.insert(0, r"E:\DSH011rc1\workspace\think-zh")
import tm_store, backfill
from concurrent.futures import ThreadPoolExecutor

items = tm_store.upgrade_keys("realtime-1.8b")
print(f"待升级 {len(items)} 条", flush=True)
cfg = dict(backfill.PRESETS["7b"]); cfg.update(np=2, ctx=2048)
proc = backfill.start_server(cfg)
print("7B 已启动 (ctx=2048 np=2, 与 1.8B 并存)", flush=True)
done = [0]; t0 = time.time()

def work(item):
    key, protected = item
    try:
        trans = backfill.translate_one(cfg["port"], protected)
        tm_store.update_translation(key, trans, cfg["tag"], "offline-upgrade-7b")
    except Exception as e:
        print(f"ERR {str(key)[:10]}: {str(e)[:80]}", flush=True)
    done[0] += 1
    if done[0] % 200 == 0:
        rate = done[0] / (time.time() - t0)
        print(f"进度 {done[0]}/{len(items)}  {rate:.1f} 句/s  剩余约 {(len(items)-done[0])/max(rate,0.01)/60:.0f} 分钟", flush=True)

try:
    with ThreadPoolExecutor(max_workers=2) as ex:
        list(ex.map(work, items))
finally:
    proc.kill()
print(f"全部完成，耗时 {(time.time()-t0)/60:.0f} 分钟", flush=True)
print("库状态:", tm_store.stats(), flush=True)
