# -*- coding: utf-8 -*-
"""全量提取：扫描三个数据根 → 思维块 → 保护 → 切句 → 去重 → sentences.jsonl
兼容两种事件格式：新版 reasoning-chunks 聚合事件；旧版 reasoning-delta 拼接。
"""
import zstandard, json, io, os, sys, glob, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import protect, split_protected, zh_ratio

ROOTS = [
    r"C:\Users\Administrator\.dsh\sessions",
    r"C:\Users\Administrator\AppData\Roaming\deepseek-harness-desktop\harness-home\sessions",
    r"E:\DSH011rc1\home\sessions",
]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "sentences.jsonl")

def decompress(path):
    """容错解压（会话文件可能在写入中，帧不完整时保留已解出的部分）。"""
    dctx = zstandard.ZstdDecompressor()
    out = bytearray()
    with open(path, "rb") as f:
        reader = dctx.stream_reader(f, read_across_frames=True)
        while True:
            try:
                chunk = reader.read(1 << 22)
            except Exception:
                break  # 帧截断（文件写入中）——保留已有部分
            if not chunk: break
            out += chunk
    return out.decode("utf-8", errors="replace")

def iter_blocks(path):
    """产出 (key, block_text)。
    新格式：reasoning-chunks 聚合事件本身就是完整块，逐条产出；
    旧格式（无聚合事件）：reasoning-delta 按键拼接。
    """
    text = decompress(path)
    has_agg = False
    for line in text.split("\n"):
        if '"reasoning-chunks"' not in line: continue
        try: o = json.loads(line)
        except: continue
        d = o.get("data", {})
        txt = "".join(d.get("texts", []))
        if txt.strip():
            has_agg = True
            yield (d.get("turn"), d.get("step"), d.get("index")), txt
    if has_agg: return
    deltas = {}
    for line in text.split("\n"):
        if "reasoning-delta" not in line: continue
        try: o = json.loads(line)
        except: continue
        if o.get("type") != "assistant/chunk": continue
        d2 = o.get("data", {})
        c = d2.get("chunk", {}) or {}
        if c.get("type") != "reasoning-delta": continue
        key = (d2.get("turn"), d2.get("step"), c.get("index"))
        txt = c.get("text") or c.get("delta") or ""
        if txt: deltas.setdefault(key, []).append(txt)
    for key, parts in deltas.items():
        txt = "".join(parts)
        if txt.strip(): yield key, txt

def main():
    files = []
    for root in ROOTS:
        files.extend(glob.glob(os.path.join(root, "**", "session.jsonl.zstd"), recursive=True))
    print(f"发现会话文件: {len(files)}")
    uniq, total_blocks, total_sentences = {}, 0, 0
    for i, path in enumerate(sorted(files)):
        sid = os.path.basename(os.path.dirname(path))[:20]
        n_b = n_s = 0
        for key, block in iter_blocks(path):
            n_b += 1
            protected, _ = protect(block)
            for s in split_protected(protected):
                if zh_ratio(s) > 0.3: continue
                k = hashlib.sha1(s.encode()).hexdigest()[:12]
                if k in uniq:
                    uniq[k]["count"] += 1
                else:
                    uniq[k] = {"key": k, "protected": s, "count": 1, "src": sid}
                n_s += 1
        total_blocks += n_b; total_sentences += n_s
        print(f"[{i+1}/{len(files)}] {sid}: 块 {n_b}, 句 {n_s}")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for v in sorted(uniq.values(), key=lambda x: -x["count"]):
            f.write(json.dumps(v, ensure_ascii=False) + "\n")
    print(f"合计: 块 {total_blocks}, 句(含重复) {total_sentences}, 去重唯一 {len(uniq)}")
    print(f"-> {OUT}")

if __name__ == "__main__":
    main()
