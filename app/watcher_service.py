# -*- coding: utf-8 -*-
"""think-zh 实时观察服务（单属主）：
HTTP API(8765) + 会话文件尾随 + 实时翻译(1.8B 常驻) + 观察页。
启动: python watcher_service.py   停止: 结束进程即可（TM 数据落盘安全）
"""
import os, sys, json, time, glob, hashlib, threading, subprocess, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tm_store
from core import protect, split_protected, zh_ratio, build_prompt, clean_output, match_terms

_HERE = os.path.dirname(os.path.abspath(__file__))
try:
    TERMS = json.load(open(os.path.join(_HERE, "terms.json"), encoding="utf-8"))["terms"]
except Exception:
    TERMS = {}

PORT = 18765
# 自包含布局：<根>\app（代码） <根>\llama <根>\models —— 整个根目录可拷走
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LLAMA_DIR = os.environ.get("TZ_LLAMA", os.path.join(_BASE, "llama"))
MODEL_18B = os.environ.get("TZ_MODEL_18B", os.path.join(_BASE, "models", "Hy-MT2-1.8B-Q6_K.gguf"))
MPORT = 8199

def _newest_session():
    root = os.environ.get("DSH_HOME", os.path.expanduser("~/.dsh"))
    fs = glob.glob(os.path.join(root, "sessions", "**", "session.jsonl.zstd"), recursive=True)
    return max(fs, key=os.path.getmtime) if fs else None

SESSION = os.environ.get("DSH_SESSION_JSONL") or _newest_session()

# ---------------- 占位符规范化 ----------------
import re
_TOK = re.compile(r"\u27e6P(\d{3})\u27e7")

def canonicalize(protected):
    """占位符按首次出现顺序重编号 → 跨块同句式同键。返回 (canonical, mapping{canon_i: orig_i})"""
    seen, order = {}, []
    def _map(m):
        n = int(m.group(1))
        if n not in seen:
            seen[n] = len(seen) + 1
            order.append(n)
        return "\u27e6P%03d\u27e7" % seen[n]
    return _TOK.sub(_map, protected), order

# ---------------- TM 查询（含旧格式规范索引） ----------------
def _sha(s): return hashlib.sha1(s.encode()).hexdigest()[:12]

def tm_init():
    c = tm_store.conn()
    c.execute("CREATE TABLE IF NOT EXISTS canon (ckey TEXT PRIMARY KEY, key TEXT, mapping TEXT)")
    c.commit()

def tm_add_canon(key, protected, commit=True):
    canon, order = canonicalize(protected)
    ckey = _sha(canon)
    c = tm_store.conn()
    c.execute("INSERT OR IGNORE INTO canon(ckey, key, mapping) VALUES (?,?,?)",
              (ckey, key, json.dumps(order)))
    if commit: c.commit()
    return ckey, canon, order

def tm_build_canon_index():
    c = tm_store.conn()
    rows = c.execute("SELECT key, protected FROM tm").fetchall()
    for i, (key, protected) in enumerate(rows):
        tm_add_canon(key, protected, commit=False)
        if i % 2000 == 0: c.commit()
    c.commit()
    return len(rows)

def tm_lookup_by_canonical(ckey):
    c = tm_store.conn()
    return c.execute(
        "SELECT tm.key, tm.translation, tm.source, canon.mapping FROM canon JOIN tm ON tm.key=canon.key "
        "WHERE canon.ckey=?", (ckey,)).fetchone()

def tm_put_canonical(canon, translation, model, source):
    key = _sha(canon)
    tm_store.put(key, canon, translation, model, source)
    c = tm_store.conn()
    c.execute("INSERT OR IGNORE INTO canon(ckey, key, mapping) VALUES (?,?,?)",
              (key, key, json.dumps(list(range(1, 99)))))
    c.commit()
    return key

# ---------------- 常驻 1.8B ----------------
_mproc = [None]
def ensure_model():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{MPORT}/health", timeout=2) as r:
            if r.status == 200:
                live["model_up"] = True; return True
    except Exception: pass
    if _mproc[0] is None:
        exe = os.path.join(LLAMA_DIR, "llama-server.exe")
        _mproc[0] = subprocess.Popen(
            [exe, "-m", MODEL_18B, "-ngl", "99", "-c", "1024", "--port", str(MPORT),
             "-np", "4", "--threads", "8", "-b", "2048", "-ub", "512", "--no-warmup", "--jinja"],
            cwd=LLAMA_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    for _ in range(120):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{MPORT}/health", timeout=2) as r:
                if r.status == 200:
                    live["model_up"] = True; return True
        except Exception: time.sleep(1)
    live["model_up"] = False; return False

def translate_realtime(protected):
    _touch_activity()
    if not ensure_model(): return None
    body = json.dumps({"messages": [{"role": "user", "content": build_prompt(protected, match_terms(protected, TERMS))}],
                       "temperature": 0.7, "top_p": 0.6, "top_k": 20, "repeat_penalty": 1.05,
                       "max_tokens": 1024, "stream": False}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{MPORT}/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            resp = json.loads(r.read())
        return clean_output(resp["choices"][0]["message"]["content"])
    except Exception:
        return None

# ---------------- 句级翻译（查库优先 → 未命中即席） ----------------
def translate_sentences(protected_block, slots, allow_model=True, count=True, keep_skipped=False):
    """块级保护文本 → 切句 → 每句查库/即席 → [{orig, zh, hit}]"""
    out = []
    for s in split_protected(protected_block):
        if zh_ratio(s) > 0.5:
            if keep_skipped:   # 中文过半：原文保留显示（不调模型）
                o = _restore_sentence(s, slots)
                out.append({"orig": o, "zh": o, "hit": "orig"})
            continue
        canon, order = canonicalize(s)
        ckey = _sha(canon)
        row = tm_lookup_by_canonical(ckey)
        hit = row is not None and row[1]
        if hit:
            translation, mapping = row[1], json.loads(row[3] or "[]")
            zh = _restore_via_mapping(translation, order, mapping, slots)
            if count: live["hits"] += 1
        elif allow_model:
            t = translate_realtime(canon)
            if t is None:
                out.append({"orig": _restore_sentence(s, slots), "zh": None, "hit": None}); continue
            try:
                tm_put_canonical(canon, t, "Hy-MT2-1.8B-Q6_K", "realtime-1.8b")
            except Exception as e:
                print("[tm] 写库失败(不影响返回):", str(e)[:80], flush=True)
            translation, mapping = t, list(range(1, 99))
            zh = _restore_via_mapping(t, order, mapping, slots)
            if count: live["misses"] += 1
        else:
            out.append({"orig": _restore_sentence(s, slots), "zh": None, "hit": None}); continue
        zh = zh.replace("`", "")   # 兼容旧库存译文里混入的反引号
        out.append({"orig": _restore_sentence(s, slots), "zh": zh, "hit": bool(hit)})
    return out

def _restore_sentence(protected, slots):
    return _TOK.sub(lambda m: slots[int(m.group(1)) - 1] if int(m.group(1)) - 1 < len(slots) else m.group(0), protected)

def _restore_via_mapping(translation, query_order, row_mapping, slots):
    """译文占位符(行侧编号) → 查询句槽位值。"""
    inv = {ln: i for i, ln in enumerate(row_mapping, 1)}  # 行编号 -> canon序号
    def _sub(m):
        L = int(m.group(1))
        i = inv.get(L, L)                # 行编号→canon序号（新条目行编号即canon）
        o = query_order[i - 1] if i - 1 < len(query_order) else i  # canon序号→查询原编号
        return slots[o - 1] if o - 1 < len(slots) else m.group(0)
    return _TOK.sub(_sub, translation)

# ---------------- 插件适配层（OpenAI 兼容，供 dsh-think-translate 调用） ----------------
_PAYLOAD_HEAD = re.compile(r"^Target language:\s*\S+\s*\n+", re.I)

def _extract_user_text(messages):
    user = ""
    for m in messages or []:
        if isinstance(m, dict) and m.get("role") == "user":
            user = m.get("content") or ""
    return _PAYLOAD_HEAD.sub("", user).strip()

def openai_translate(body):
    """剥插件包装 → TM 查库优先 → 1.8B 即席（术语表生效）→ 拼 OpenAI 响应。"""
    _touch_activity()
    text = _extract_user_text((body or {}).get("messages"))
    content = ""
    if text:
        protected, slots = protect(text)
        sents = translate_sentences(protected, slots, allow_model=True, keep_skipped=True)
        content = "\n".join((s["zh"] or s["orig"]) for s in sents)
    return {"id": "think-zh", "object": "chat.completion", "model": "think-zh",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": content}}]}

# ---------------- 会话尾随 ----------------
class TailDecoder:
    """多帧 zstd 增量解码：帧完整即产出，半帧保状态，失步自动重同步。"""
    MAGIC = b"\x28\xb5\x2f\xfd"
    def __init__(self):
        self.d = zstd.ZstdDecompressor().decompressobj()
        self.buf = b""
    def feed(self, data):
        self.buf += data
        out = []
        while self.buf:
            try:
                piece = self.d.decompress(self.buf)
                rest = self.d.unused_data
            except Exception:
                i = self.buf.find(self.MAGIC, 1)
                if i < 0:
                    self.buf = self.buf[-3:]   # 魔数可能跨读边界，留尾3字节
                    break
                print("[decoder] 帧失步，重同步 @" + str(i), flush=True)
                self.buf = self.buf[i:]
                self.d = zstd.ZstdDecompressor().decompressobj()
                continue
            out.append(piece)
            if rest:
                self.buf = rest
                self.d = zstd.ZstdDecompressor().decompressobj()
            else:
                self.buf = b""
                break
        return b"".join(out)

import zstandard as zstd

def watcher_loop():
    path = live["session"]
    if not path:
        print("[watcher] 无会话文件"); return
    dec = TailDecoder()
    off = 0
    caught_up = False
    f = open(path, "rb")
    live["tail_ready"] = True
    print(f"[watcher] tailing {path} (replay from 0)")
    # 会话切换自愈：SESSION 常量只在启动时定死，DSH 新开会话后本线程会盯着死文件静默停摆。
    # 每 20 秒重探测最新会话文件，发现切换则转向新文件并从其尾部继续（不回放历史，不刷屏）。
    # 显式指定 DSH_SESSION_JSONL 时视为调试/演示用法，不自动切换。
    explicit = bool(os.environ.get("DSH_SESSION_JSONL"))
    last_probe = time.time()
    last_switch = 0.0
    while True:
        try:
            if not explicit and time.time() - last_probe > 20 and time.time() - last_switch > 120:
                last_probe = time.time()
                newest = _newest_session()
                if newest and newest != path and os.path.exists(newest):
                    print(f"[watcher] 会话切换: ...\\{os.path.basename(os.path.dirname(path))} -> ...\\{os.path.basename(os.path.dirname(newest))}", flush=True)
                    try: f.close()
                    except Exception: pass
                    path = newest
                    with live["lock"]:
                        live["session"] = newest
                    f = open(path, "rb")
                    off = f.seek(0, 2)   # 只翻新会话的后续内容
                    dec = TailDecoder()
                    caught_up = True
                    last_switch = time.time()
            f.seek(off)
            data = f.read()
            if data:
                off += len(data)
                text = dec.feed(data).decode("utf-8", errors="replace")
                for line in text.split("\n")[:-1]:   # 只处理完整行
                    handle_line(line, allow_model=caught_up)
            elif not caught_up:
                caught_up = True
                print("[watcher] 回放追平，进入实时模式")
            time.sleep(0.4)
        except Exception as e:
            print("[watcher] err:", str(e)[:100]); time.sleep(2)

def handle_line(line, allow_model=True):
    if "reasoning" not in line: return
    try: o = json.loads(line)
    except: return
    t = o.get("type")
    if t == "reasoning-chunks":
        d = o.get("data", {})
        block = "".join(d.get("texts", []))
        if block.strip(): publish_block(block, d.get("turn"), allow_model)
        return
    if t != "assistant/chunk": return
    d2 = o.get("data", {})
    c = d2.get("chunk", {}) or {}
    ct = c.get("type")
    if ct == "reasoning-delta":
        key = (d2.get("turn"), d2.get("step"), c.get("index"))
        b = buffers.setdefault(key, {"text": "", "ts": time.time()})
        b["text"] += (c.get("text") or c.get("delta") or "")
        b["ts"] = time.time()
    elif ct == "block-end" and c.get("blockType") == "reasoning":
        key = (d2.get("turn"), d2.get("step"), c.get("index"))
        flush_key(key, allow_model)

def flush_key(key, allow_model=True):
    b = buffers.pop(key, None)
    if b and b["text"].strip():
        publish_block(b["text"], key[0], allow_model)

def idle_flusher():
    while True:
        time.sleep(2)
        now = time.time()
        for key in [k for k, b in buffers.items() if now - b["ts"] > 4]:
            flush_key(key, True)

def publish_block(block, turn, allow_model=True):
    protected, slots = protect(block)
    sents = translate_sentences(protected, slots, allow_model=allow_model)
    if not sents: return
    if not allow_model and not any(s["hit"] for s in sents):
        return  # 回放段：无库命中的块不入展示流
    with live["lock"]:
        live["seq"] += 1
        live["blocks_seen"] += 1
        live["blocks"].append({"seq": live["seq"], "ts": time.strftime("%H:%M:%S"),
                               "turn": turn, "sentences": sents})

# ---------------- HTTP 服务 ----------------
VIEWER = """<!doctype html><html><head><meta charset="utf-8"><title>think-zh 思维链中译</title>
<style>
body{background:#111418;color:#cfd8dc;font-family:Consolas,'Microsoft YaHei',monospace;margin:0;padding:12px}
h1{font-size:15px;color:#80cbc4;margin:0 0 4px}
#stat{font-size:12px;color:#78909c;margin-bottom:10px}
.blk{border-left:3px solid #37474f;padding:4px 10px;margin:8px 0}
.blk:hover{border-color:#80cbc4}
.meta{font-size:11px;color:#546e7a}
.zh{color:#a5d6a7;margin:2px 0}
.en{color:#607d8b;font-size:12px;white-space:pre-wrap;word-break:break-all}
.badge{font-size:10px;border:1px solid #455a64;border-radius:3px;padding:0 4px;margin-left:6px}
.b-hit{color:#81c784}.b-miss{color:#ffb74d}
#mode{background:#00695c;color:#fff;border:1px solid #80cbc4;border-radius:4px;font-size:13px;padding:4px 14px;cursor:pointer;margin-left:14px}
body.zh-only .en{display:none}
</style></head><body>
<h1>think-zh 思维链中译 · 实时观察<button id="mode">纯中文模式</button></h1>
<div id="stat">加载中…</div><div id="feed"></div>
<script>
let after=0, stick=true;
window.onscroll=()=>{stick = (innerHeight+scrollY >= document.body.offsetHeight-40)};
async function tick(){
  const s=await (await fetch('/api/stats')).json();
  document.getElementById('stat').textContent =
    `库 ${s.tm_total} 条 | 本会话块 ${s.blocks_seen} | 命中 ${s.hits} / 未命中 ${s.misses}` +
    ` (命中率 ${s.hits+s.misses?Math.round(100*s.hits/(s.hits+s.misses)):0}%) | 模型 ${s.model_up?'常驻●':'未启○'} | 会话 ${s.session_file}`;
  const r=await (await fetch('/api/recent?after='+after)).json();
  for(const b of r.blocks){
    const div=document.createElement('div');div.className='blk';
    let h=`<div class="meta">#${b.seq} ${b.ts} turn${b.turn??''}</div>`;
    for(const x of b.sentences){
      const badge = x.hit===true?'库':(x.hit===false?'模型':(x.hit==='orig'?'原文':'跳过'));
      const bcls = x.hit===true?'b-hit':(x.hit===false?'b-miss':'b-orig');
      h+=`<div class="zh">${x.zh??'(…模型未就绪)'}</div>`;
      if(x.zh!==null) h+=`<div class="en">${esc(x.orig)}<span class="badge ${bcls}">${badge}</span></div>`;
    }
    div.innerHTML=h;document.getElementById('feed').appendChild(div);
    after=b.seq;
  }
  if(stick) scrollTo(0,document.body.scrollHeight);
}
const esc=s=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;');
const btn=document.getElementById('mode');
if(localStorage.tzZhOnly!=='0'){document.body.classList.add('zh-only');btn.textContent='对照模式';}
btn.onclick=()=>{const on=document.body.classList.toggle('zh-only');
  btn.textContent=on?'对照模式':'纯中文模式';
  localStorage.tzZhOnly=on?'1':'0';};
setInterval(tick,1500);tick();
</script></body></html>"""

class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/":
            return self._send(200, VIEWER.encode(), "text/html; charset=utf-8")
        if p == "/api/stats":
            with live["lock"]:
                return self._send(200, {"tm_total": tm_store.stats()["total"],
                    "blocks_seen": live["blocks_seen"], "hits": live["hits"],
                    "misses": live["misses"], "model_up": live["model_up"],
                    "session_file": os.path.basename(live["session"] or ""),
                    "upgrade_pending": pending_upgrade_count(),
                    "corr_running": CORR["running"],
                    "corr_last_done": CORR["last_done"]})
        if p == "/api/recent":
            after = int(self.path.split("after=")[-1].split("&")[0] or 0)
            with live["lock"]:
                blocks = [b for b in live["blocks"] if b["seq"] > after]
            return self._send(200, {"blocks": blocks})
        if p == "/api/lookup":
            from urllib.parse import urlparse, parse_qs, unquote
            q = parse_qs(urlparse(self.path).query)
            text = unquote(q.get("text", [""])[0])
            return self._send(200, {"results": translate_sentences(text, [], allow_model=False)})
        return self._send(404, {"error": "not found"})
    def do_POST(self):
        try:
            p = self.path.split("?")[0]
            if p == "/v1/chat/completions":   # dsh-think-translate 适配入口
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"{}")
                return self._send(200, openai_translate(body))
            if p == "/api/translate":
                n = int(self.headers.get("Content-Length", 0))
                req = json.loads(self.rfile.read(n) or b"{}")
                text = req.get("text", "")
                protected, slots = protect(text)
                return self._send(200, {"results": translate_sentences(protected, slots, allow_model=req.get("model", True))})
            return self._send(404, {"error": "not found"})
        except Exception as e:
            return self._send(500, {"error": str(e)[:200]})
    def log_message(self, *a): pass

# ---------------- 空闲自动校正（事后 7B 升级循环） ----------------
CORR = {"last_activity": time.time(), "running": False, "last_done": None, "last_count": 0}
UPGRADE_IDLE_SECS = 600   # 连续 10 分钟无翻译活动才触发
UPGRADE_BATCH = 200       # 单轮条数上限，跑完即卸 7B

def _touch_activity():
    """任何真实翻译活动打点（用户在用 = 不校正）。"""
    CORR["last_activity"] = time.time()

def mining_enabled():
    """挖矿开关：out/mining.off 文件存在 = 停（动态生效，无需重启）。"""
    return not os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "mining.off"))

def pending_upgrade_count():
    try:
        con = tm_store.conn()
        rt = con.execute(
            "SELECT COUNT(*) FROM tm WHERE source LIKE 'realtime-1.8b%' OR needs_review=1"
        ).fetchone()[0]
        off = con.execute(
            "SELECT COUNT(*) FROM tm WHERE source LIKE 'offline-1.8b%'"
        ).fetchone()[0]
        return {"realtime": rt, "offline_stock": off}
    except Exception:
        return {"realtime": 0, "offline_stock": 0}

def idle_upgrade_loop():
    import backfill
    cfg = dict(backfill.PRESETS["7b"]); cfg.update(np=1, ctx=2048)   # 校正专用：串行+小上下文省显存
    idle_since = None   # 空闲起点；挖矿模式下保持已满足状态，连续分批消化存量
    while True:
        time.sleep(20)
        try:
            if CORR["running"]: continue
            if not mining_enabled(): continue
            active = time.time() - CORR["last_activity"] < 30
            if active:
                idle_since = None            # 用户回来了，重新计时
                continue
            if idle_since is None:
                idle_since = time.time()     # 首次检测到空闲
                continue
            if time.time() - idle_since < UPGRADE_IDLE_SECS:
                continue                     # 空闲未满 10 分钟
            # realtime 新句优先；清完则啃 offline-1.8b 铺量存量
            items = tm_store.upgrade_keys("realtime-1.8b") or tm_store.upgrade_keys("offline-1.8b")
            if not items: continue
            batch = items[:UPGRADE_BATCH]
            CORR["running"] = True
            print(f"[校正] 空闲触发: 库中待升级 {len(items)} 条, 本轮 {len(batch)} 条", flush=True)
            try:
                proc = backfill.start_server(cfg)
            except Exception as e:
                print("[校正] 7B 启动失败(显存不足?), 推迟到下个空闲窗口:", str(e)[:120], flush=True)
                continue
            done, t0 = 0, time.time()
            try:
                for key, protected in batch:
                    if time.time() - CORR["last_activity"] < 30:   # 用户回来了，提前收尾
                        print("[校正] 检测到活动, 本轮提前结束", flush=True)
                        break
                    try:
                        trans = backfill.translate_one(cfg["port"], protected)
                        tm_store.update_translation(key, trans, cfg["tag"], "offline-upgrade-7b")
                        done += 1
                    except Exception as e:
                        print(f"[校正] 单条失败 {str(key)[:10]}: {str(e)[:80]}", flush=True)
            finally:
                try: proc.kill()
                except Exception: pass
            CORR["last_done"] = time.time(); CORR["last_count"] = done
            rate = done / max(time.time() - t0, 0.01)
            print(f"[校正] 本轮完成 {done}/{len(batch)} 条  {rate:.1f} 句/s  7B 已卸载", flush=True)
        except Exception as e:
            print("[校正] 循环异常:", str(e)[:120], flush=True)
        finally:
            CORR["running"] = False
            # 挖矿模式：保持"已空闲"状态，20 秒后下一轮连续挖；用户活动会重置 idle_since
            idle_since = time.time() - UPGRADE_IDLE_SECS

# ---------------- 启动 ----------------
buffers = {}
live = {"seq": 0, "blocks": deque(maxlen=200), "lock": threading.Lock(),
        "hits": 0, "misses": 0, "blocks_seen": 0, "model_up": False,
        "session": SESSION, "tail_ready": False}

if __name__ == "__main__":
    tm_init()
    n = tm_build_canon_index()
    print(f"[tm] 规范索引构建: {n} 条")
    threading.Thread(target=watcher_loop, daemon=True).start()
    threading.Thread(target=idle_flusher, daemon=True).start()
    threading.Thread(target=ensure_model, daemon=True).start()
    threading.Thread(target=idle_upgrade_loop, daemon=True).start()
    print(f"[http] http://127.0.0.1:{PORT}  (观察页 / · API /api/lookup /api/translate /api/stats)")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
