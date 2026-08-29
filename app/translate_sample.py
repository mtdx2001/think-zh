# -*- coding: utf-8 -*-
"""阶段0：双模型对照翻译测试台
用法: python translate_sample.py <model_path> <model_tag> [port]
前置: llama-server.exe 已解压到 D:\think-zh\llama\ 下（含 cudart DLL 同目录）
"""
import json, os, subprocess, sys, time, urllib.request

MODEL = sys.argv[1]
TAG = sys.argv[2]
PORT = int(sys.argv[3]) if len(sys.argv) > 3 else 8181
LLAMA_DIR = r"D:\think-zh\llama"
SAMPLE = r"E:\DSH011rc1\workspace\think-zh\out\sample_sentences.json"
OUT = rf"E:\DSH011rc1\workspace\think-zh\out\translations_{TAG}.json"

PROMPT_DEFAULT = (
    "将以下文本翻译为 `中文`，注意只需要输出翻译后的结果，不要额外解释，"
    "不要在输出中添加任何反引号或代码块标记：\n\n{text}"
)
PROMPT_PLACEHOLDER = (
    "请将以下文本准确翻译为 `中文`。你必须在译文中保留等量的分隔符，"
    "形如 ⟦P001⟧ 的占位符号码绝对不可遗漏、转义或翻译，并注意占位符的位置。"
    "注意只需要输出翻译后的结果，不要额外解释，不要添加任何反引号：\n\n{text}"
)

def build_prompt(text):
    if "\u27e6P" in text:  # ⟦P
        return PROMPT_PLACEHOLDER.format(text=text)
    return PROMPT_DEFAULT.format(text=text)

def clean_output(s):
    return s.strip().strip("`").strip()

def start_server():
    exe = os.path.join(LLAMA_DIR, "llama-server.exe")
    if not os.path.exists(exe):
        # zip 解压后的子目录里找
        for root, _, files in os.walk(LLAMA_DIR):
            if "llama-server.exe" in files:
                exe = os.path.join(root, "llama-server.exe"); break
    proc = subprocess.Popen(
        [exe, "-m", MODEL, "-ngl", "99", "-c", "4096", "--port", str(PORT),
         "--threads", "8", "-b", "2048", "-ub", "512", "--no-warmup"],
        cwd=os.path.dirname(exe), stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    # 等健康检查
    for _ in range(120):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2) as r:
                if r.status == 200: return proc
        except Exception:
            time.sleep(1)
    proc.kill(); raise RuntimeError("llama-server 启动超时")

def translate(prompt, timeout=180):
    body = json.dumps({
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0, "max_tokens": 1024, "stream": False,
    }).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.loads(r.read())
    ms = (time.perf_counter() - t0) * 1000
    msg = resp["choices"][0]["message"]["content"]
    usage = resp.get("usage", {})
    return msg, ms, usage

def main():
    with open(SAMPLE, encoding="utf-8") as f:
        samples = json.load(f)
    proc = start_server()
    results, total_ms = [], 0.0
    try:
        translate(build_prompt("Warm up the model with this short sentence."), timeout=120)  # 预热，不计入
        for s in samples:
            prompt = build_prompt(s["protected"])
            try:
                out, ms, usage = translate(prompt)
                total_ms += ms
                results.append({**s, "translation": clean_output(out), "ms": round(ms),
                                "ptok": usage.get("prompt_tokens"), "ctok": usage.get("completion_tokens")})
                print(f"[{s['sid']:2d}] {ms:7.0f} ms  {s['text'][:60]}")
            except Exception as e:
                results.append({**s, "translation": None, "error": str(e)[:200], "ms": None})
                print(f"[{s['sid']:2d}] ERROR {e}")
    finally:
        proc.kill()
    ok = [r for r in results if r.get("ms")]
    n = len(ok)
    stats = {"tag": TAG, "model": os.path.basename(MODEL), "n_ok": n,
             "avg_ms": round(total_ms / n) if n else None,
             "median_ms": sorted(r["ms"] for r in ok)[n // 2] if n else None,
             "total_min": round(total_ms / 60000, 1)}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"stats": stats, "results": results}, f, ensure_ascii=False, indent=1)
    print(json.dumps(stats, ensure_ascii=False))

if __name__ == "__main__":
    main()
