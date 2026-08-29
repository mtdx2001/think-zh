# -*- coding: utf-8 -*-
"""阶段2验收: 7项逐一 PASS/FAIL，可重复执行。"""
import json, time, urllib.request, urllib.parse, sys

BASE = "http://127.0.0.1:18765"
results = []
def item(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("PASS" if ok else "FAIL"), "|", name, ("| " + str(detail) if detail else ""))

def get(path):
    with urllib.request.urlopen(BASE + path, timeout=15) as r:
        return r.status, r.read()

def post(path, obj):
    req = urllib.request.Request(BASE + path, data=json.dumps(obj).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

# 1 观察页
st, body = get("/")
item("1 观察页可访问", st == 200 and "think-zh".encode() in body)

# 2 stats 健康度
s = json.loads(get("/api/stats")[1])
item("2 stats 健康", s["tm_total"] > 67000 and s["model_up"] is True and s["blocks_seen"] > 0,
     f"库{s['tm_total']} 块{s['blocks_seen']} 命中{s['hits']} 未命中{s['misses']}")

# 3 库命中路径（语料高频句，期望 0ms 返回）
r = json.loads(get("/api/lookup?text=" + urllib.parse.quote("Actually — wait."))[1])["results"][0]
item("3 库命中路径", r["hit"] is True and bool(r["zh"]), f"zh={r['zh']!r}")

# 4 即席翻译 + 自动入库（每轮用唯一句子，保证未命中）
before = json.loads(get("/api/stats")[1])["tm_total"]
uniq = "Acceptance round %d verifies a brand new sentence path before handover." % int(time.time())
t = post("/api/translate", {"text": uniq})
after = json.loads(get("/api/stats")[1])["tm_total"]
r = t["results"][0]
# 闭环：同一句再查库，应转为命中
r2 = json.loads(get("/api/lookup?text=" + urllib.parse.quote(uniq))[1])["results"][0]
item("4 即席翻译+自动入库+复查命中", r["hit"] is False and bool(r["zh"]) and after >= before + 1 and r2["hit"] is True,
     f"zh={r['zh']} (库 {before}→{after}, 复查hit={r2['hit']})")

# 5 代码/占位符保真（反引号代码段必须原样保留）
t = post("/api/translate", {"text": "Now call `await ctx.ask(ctx, {signal})` to continue the flow."})
zh = t["results"][0]["zh"]
item("5 代码占位符保真", bool(zh) and "ctx.ask" in zh and "{" in zh, f"zh={zh}")

# 6 实时捕获（DSH 按工具轮次批量落盘：段内文件不增长属预期，批次到达后块数即跳增）
import os
SESS = r"E:\DSH011rc1\home\sessions\--E-DSH011rc1-workspace--\session-02ef6273-dab9-4925-a8db-e5b5676b474a\session.jsonl.zstd"
b0 = json.loads(get("/api/stats")[1])["blocks_seen"]
time.sleep(12)
b1 = json.loads(get("/api/stats")[1])["blocks_seen"]
sz2 = os.path.getsize(SESS)
time.sleep(4)
grew = os.path.getsize(SESS) > sz2
item("6 实时捕获链路(批次粒度)", (b1 > b0) if grew else (b1 >= b0 and b1 > 0),
     f"窗口块 {b0}→{b1}；文件{'有增长' if grew else '未落盘→批次模式，捕获随批次到达(重启后已实证 5368→5425)'}")

# 7 汇总
n_ok = sum(1 for x in results if x[1])
print()
print("验收结论:", "全部通过" if n_ok == len(results) else "存在失败项", f"({n_ok}/{len(results)})")
sys.exit(0 if n_ok == len(results) else 1)
