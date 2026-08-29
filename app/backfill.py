# -*- coding: utf-8 -*-
"""批量回填/升级引擎。
用法:
  python backfill.py                       # 默认: 1.8B 铺量（补全 TM 缺失句）
  python backfill.py --model 7b            # 7B 铺量
  python backfill.py --upgrade             # 7B 升级: 重翻库中 1.8B 译文（夜间跑）
  python backfill.py --limit 500           # 限制条数（试跑）
断点续跑: 随时中断，重跑自动跳过已入库句。
"""
import json, os, sys, time, subprocess, urllib.request
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tm_store
from core import build_prompt, clean_output, match_terms

try:
    TERMS = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "terms.json"), encoding="utf-8"))["terms"]
except Exception:
    TERMS = {}

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LLAMA_DIR = os.environ.get("TZ_LLAMA", os.path.join(_BASE, "llama"))
SENT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "sentences.jsonl")

PRESETS = {
    "1.8b": dict(model=os.environ.get("TZ_MODEL_18B", os.path.join(_BASE, "models", "Hy-MT2-1.8B-Q6_K.gguf")),
                 tag="Hy-MT2-1.8B-Q6_K",
                 source="offline-1.8b", port=8199, np=3, threads=8),
    "7b":   dict(model=os.environ.get("TZ_MODEL_7B", os.path.join(_BASE, "models", "Hy-MT2-7B-Q4_K_M.gguf")),
                 tag="Hy-MT2-7B-Q4_K_M",
                 source="offline-7b", port=8198, np=4, threads=8),
}

def parse_args():
    model, upgrade, limit = "1.8b", False, None
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--model": model = args[i+1].lower(); i += 2
        elif args[i] == "--upgrade": upgrade = True; i += 1
        elif args[i] == "--limit": limit = int(args[i+1]); i += 2
        else: i += 1
    return model, upgrade, limit

def start_server(cfg):
    exe = os.path.join(LLAMA_DIR, "llama-server.exe")
    proc = subprocess.Popen(
        [exe, "-m", cfg["model"], "-ngl", "99", "-c", str(cfg.get("ctx", 8192)), "--port", str(cfg["port"]),
         "-np", str(cfg["np"]), "--threads", str(cfg["threads"]),
         "-b", "2048", "-ub", "512", "--no-warmup", "--jinja"],
        cwd=LLAMA_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    for _ in range(180):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{cfg['port']}/health", timeout=2) as r:
                if r.status == 200: return proc
        except Exception: time.sleep(1)
    proc.kill(); raise RuntimeError("llama-server 启动超时")

def translate_one(port, protected, tries=3):
    body = json.dumps({"messages": [{"role": "user", "content": build_prompt(protected, match_terms(protected, TERMS))}],
                       "temperature": 0.7, "top_p": 0.6, "top_k": 20, "repeat_penalty": 1.05,
                       "max_tokens": 1024, "stream": False}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    last = None
    for _ in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                resp = json.loads(r.read())
            return clean_output(resp["choices"][0]["message"]["content"])
        except Exception as e:
            last = e; time.sleep(2)
    raise last

def run_batch(cfg, items, mode):
    proc = start_server(cfg)
    done = [0]; t0 = time.time()
    def work(item):
        key, protected = item
        try:
            trans = translate_one(cfg["port"], protected)
            if mode == "upgrade":
                tm_store.update_translation(key, trans, cfg["tag"], "offline-upgrade-7b")
            else:
                tm_store.put(key, protected, trans, cfg["tag"], cfg["source"])
        except Exception as e:
            print(f"  ERR {key}: {str(e)[:80]}", flush=True)
        done[0] += 1
        if done[0] % 100 == 0:
            rate = done[0] / (time.time() - t0)
            eta = (len(items) - done[0]) / max(rate, 0.01) / 60
            print(f"进度 {done[0]}/{len(items)}  {rate:.1f} 句/s  剩余约 {eta:.0f} 分钟", flush=True)
    try:
        with ThreadPoolExecutor(max_workers=cfg["np"]) as ex:
            list(ex.map(work, items))
    finally:
        proc.kill()
    print("完成:", tm_store.stats())

def main():
    model, upgrade, limit = parse_args()
    cfg = PRESETS[model]
    if upgrade:
        rows = tm_store.upgrade_keys("offline-1.8b")
        items = [(k, p) for k, p in rows]
        mode = "upgrade"
        print(f"7B 升级模式: 待重翻 {len(items)} 条 1.8B 译文")
    else:
        with open(SENT, encoding="utf-8") as f:
            rows = [json.loads(l) for l in f if l.strip()]
        pending = set(tm_store.pending_keys([r["key"] for r in rows]))
        items = [(r["key"], r["protected"]) for r in rows if r["key"] in pending]
        mode = "fill"
        print(f"铺量模式[{model}]: 待翻译 {len(items)} / 总唯一 {len(rows)}")
    if limit: items = items[:limit]
    if not items: print("无事可做"); return
    run_batch(cfg, items, mode)

if __name__ == "__main__":
    main()
