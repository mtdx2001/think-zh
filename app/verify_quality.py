# -*- coding: utf-8 -*-
"""think-zh 成果验收：速度 × 质量 一次跑完。"""
import sys, os, json, time, urllib.request, urllib.parse, statistics
sys.path.insert(0, r"E:\DSH011rc1\workspace\think-zh")
import tm_store
from core import match_terms

TERMS = json.load(open(r"E:\DSH011rc1\workspace\think-zh\terms.json", encoding="utf-8"))["terms"]
con = tm_store.conn()

print("=" * 62)
print("一、覆盖率（质量基础）")
print("=" * 62)
for src, n in con.execute("SELECT source, COUNT(*) FROM tm GROUP BY source ORDER BY COUNT(*) DESC"):
    print(f"  {src:28s} {n:>6} 条")
total = con.execute("SELECT COUNT(*) FROM tm").fetchone()[0]
reviewed = con.execute("SELECT COUNT(*) FROM tm WHERE source LIKE 'review-%'").fetchone()[0]
print(f"  {'-- 审校覆盖率':26s} {reviewed}/{total} = {reviewed/total*100:.1f}%")

print()
print("=" * 62)
print("二、占位符完整性（⟦P00x⟧ 必须原样保留）")
print("=" * 62)
rows = con.execute("SELECT key, protected, translation FROM tm WHERE source LIKE 'review-%' AND protected LIKE '%⟦P%'").fetchall()
bad = 0
for k, p, t in rows:
    import re
    if set(re.findall(r"⟦P\d+⟧", p)) != set(re.findall(r"⟦P\d+⟧", t)):
        bad += 1
print(f"  含占位符的审校条目: {len(rows)} 条，占位符丢失/错乱: {bad} 条  {'✓ 全部完整' if bad==0 else '✗ 有问题'}")

print()
print("=" * 62)
print("三、术语一致性抽查（hit→命中 等 38 词）")
print("=" * 62)
sample_terms = {k: v for k, v in list(TERMS.items())[:8]}
ok_cnt, tot_cnt = 0, 0
missed = []
for en, zh in sample_terms.items():
    rows = con.execute("SELECT translation FROM tm WHERE source LIKE 'review-%' AND protected LIKE ? LIMIT 30",
                       (f"%{en}%",)).fetchall()
    for (t,) in rows:
        if en.lower() in t.lower():   # 译文保留了英文原词 = 未按术语表翻译
            tot_cnt += 1; missed.append((en, zh, t[:50]))
        else:
            tot_cnt += 1; ok_cnt += 1
print(f"  抽查 8 个术语 × 命中句: {tot_cnt} 例，译文按术语表中文表达: {ok_cnt} ({ok_cnt/max(tot_cnt,1)*100:.0f}%)")
for en, zh, t in missed[:3]:
    print(f"    未译例: [{en}→{zh}] {t}")

print()
print("=" * 62)
print("四、残留物检查")
print("=" * 62)
tick = con.execute("SELECT COUNT(*) FROM tm WHERE source LIKE 'review-%' AND translation LIKE '%`%'").fetchone()[0]
empty = con.execute("SELECT COUNT(*) FROM tm WHERE source LIKE 'review-%' AND (translation IS NULL OR TRIM(translation)='')").fetchone()[0]
engdom = con.execute("SELECT COUNT(*) FROM tm WHERE source LIKE 'review-%' AND protected GLOB '*[a-zA-Z]*' "
                     "AND translation = protected").fetchone()[0]
print(f"  反引号残留: {tick} 条   空译文: {empty} 条   译文=原文(未翻): {engdom} 条")

print()
print("=" * 62)
print("五、速度实测")
print("=" * 62)
# 5a. TM 纯命中（观察页 API，库路径，不含模型）
lat = []
for _ in range(6):
    t0 = time.time()
    q = urllib.parse.quote("The watcher service tails the live session file")
    urllib.request.urlopen(f"http://127.0.0.1:18765/api/lookup?text={q}", timeout=10).read()
    lat.append((time.time() - t0) * 1000)
print(f"  a) TM 纯命中路径: 中位 {statistics.median(lat):.0f} ms / 波动 {min(lat):.0f}~{max(lat):.0f} ms")

# 5b. 端到端（插件视角）: 库内句 vs 全新句（走 1.8B）
uniq = f"Acceptance probe {time.time():.0f}: the glossary pipeline maps hit, lookup and batch terms correctly."
body = json.dumps({"text": uniq, "target": "zh-CN"}).encode()
req = urllib.request.Request("http://127.0.0.1:4589/_xlate/translate", data=body,
                             headers={"Content-Type": "application/json"})
t0 = time.time()
resp = json.loads(urllib.request.urlopen(req, timeout=60).read())
e2e_new = (time.time() - t0) * 1000
print(f"  b) 端到端·全新句(1.8B实时): {e2e_new:.0f} ms")
print(f"     译文: {resp.get('text','')[:60]}")
t0 = time.time()
req2 = urllib.request.Request("http://127.0.0.1:4589/_xlate/translate", data=body,
                              headers={"Content-Type": "application/json"})
resp2 = json.loads(urllib.request.urlopen(req2, timeout=60).read())
print(f"  c) 端到端·同句重放(应走缓存): {(time.time()-t0)*1000:.0f} ms")
print(f"     DeepSeek 实测: 审校 223 条/分钟（0.20 元/500 条）")

print()
print("=" * 62)
print("六、质量抽样盲评（审校版，随机 6 条）")
print("=" * 62)
rows = con.execute("SELECT protected, translation FROM tm WHERE source LIKE 'review-%' "
                   "AND LENGTH(protected) BETWEEN 40 AND 160 ORDER BY RANDOM() LIMIT 6").fetchall()
for i, (p, t) in enumerate(rows, 1):
    print(f"  [{i}] EN: {p[:90]}")
    print(f"      ZH: {t[:90]}")
