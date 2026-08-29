# -*- coding: utf-8 -*-
"""第三方审校通道：把库中推理译文批量交给更强模型对照优化（审校优于盲翻）。

只针对推理翻译条目（realtime-1.8b / offline-upgrade-7b 来源），审过即打标记跳过。

用法:
  python review.py --dry-run 20    # 预览待审条目+费用估算（不调 API，零成本）
  python review.py --batch 100    # 审校 100 条（显示预估 → 确认 → 执行）
  python review.py --batch 100 --yes   # 跳过确认（明确授权时用）
  python review.py --all          # 全量待审（同样逐批确认）
  python review.py --all --mode rewrite   # 重写模式：不受初稿锚定，DeepSeek 按自己的中文推理习惯重写

模式:
  review  = 对照初稿审校（保守，保下限，token 略多）
  rewrite = 只给原文直接重写（上限高，DeepSeek 自由发挥，费用略省）

凭据（二选一，不落盘不进库）:
  环境变量 DEEPSEEK_API_KEY
  或 --key-file 指向仅本机可读的密钥文件

费用: 输入/输出单价在 PRICE 常量，跑前估算、跑后按 API usage 实报。
"""
import json, os, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tm_store
from core import match_terms, clean_output

try:
    TERMS = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "terms.json"), encoding="utf-8"))["terms"]
except Exception:
    TERMS = {}

API_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-v4-flash"   # 2026-08 实测可用模型: deepseek-v4-flash / deepseek-v4-pro
PRICE = {"in": 1.5 / 1e6, "out": 4.5 / 1e6}   # 元/token，V4-Flash 谷价（2026-08-17 峰谷定价）

def price_period():
    """官方脚注(1): 峰=周一至周五的 UTC 1-4 及 6-10（北京 9-12、14-18）；周末与其余时间全谷。"""
    import datetime
    now = datetime.datetime.now()
    weekday = now.weekday()   # 0=周一 ... 5=周六, 6=周日
    peak = weekday <= 4 and (9 <= now.hour < 12 or 14 <= now.hour < 18)
    return ("峰（2倍价）" if peak else "谷（半价）"), peak

SYSTEM = (
    "你是资深中文技术翻译审校，专长是 AI 推理过程（思考链）文本的中文化。"
    "用户给出英文原文和一段已有中文译文（机器翻译初稿），请改进译文。"
    "这类文本的特点：自言自语、碎片句、口语中夹杂技术术语、大量元话语（如 should probably / let me check）。"
    "译文目标是：像一位中文开发者在推理时自然说出来的话——口语化、直接、不书面腔；"
    "忠实原文、术语一致；初稿正确之处保留，只改有问题的地方。"
    "规则：⟦P001⟧ 形式的占位符是代码/命令/路径的保护槽位，必须原样保留在译文中；"
    "代码、命令、文件路径、URL、标识符一律不翻译。只输出改进后的译文，不要解释。"
)

SYSTEM_REWRITE = (
    "你是 DeepSeek，正在用中文自然地推理。下面是一段英文 AI 推理过程的原文，"
    "请把它重写为同等信息量的中文推理独白——像你自己思考时说出来的话："
    "口语化、直接、碎片句自然衔接、术语用中文开发者惯用说法。"
    "不是逐字翻译，是重写同样的思考；不可增删事实结论。"
    "规则：⟦P001⟧ 形式的占位符是代码/命令/路径的保护槽位，必须原样保留；"
    "代码、命令、文件路径、URL、标识符一律不翻译。只输出中文推理文本，不要解释。"
)

def build_user_prompt(protected, current):
    lines = []
    for term in match_terms(protected, TERMS, limit=8):
        lines.append(f"`{term[0]}` 翻译成 `{term[1]}`")
    glossary = ("参考下面的翻译：\n" + "\n".join("* " + l for l in lines) + "\n\n") if lines else ""
    return (glossary + f"原文：\n{protected}\n\n当前译文：\n{current}\n\n请输出改进后的译文。")

def build_user_prompt_plain(protected):
    lines = []
    for term in match_terms(protected, TERMS, limit=8):
        lines.append(f"`{term[0]}` 翻译成 `{term[1]}`")
    glossary = ("参考下面的翻译：\n" + "\n".join("* " + l for l in lines) + "\n\n") if lines else ""
    return (glossary + f"英文推理原文：\n{protected}\n\n请输出中文推理文本。")

def est_tokens(text):
    # 粗估：中英混合 ~0.7 token/字符（仅用于跑前预估，真实费用以 usage 为准）
    return max(int(len(text) * 0.7), 1)

def pending_review(limit):
    con = tm_store.conn()
    sql = ("SELECT key, protected, translation FROM tm "
           "WHERE ((source LIKE 'realtime-1.8b%' OR source LIKE 'offline-upgrade-7b%' "
           "OR source LIKE 'offline-1.8b%') "
           "AND source NOT LIKE 'review-%') OR needs_review=1 "
           "ORDER BY key")
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = con.execute(sql).fetchall()
    con.commit()
    return rows

def call_api(key, protected, current, mode="review", tries=3):
    sys_prompt = SYSTEM_REWRITE if mode == "rewrite" else SYSTEM
    user = (build_user_prompt_plain(protected) if mode == "rewrite"
            else build_user_prompt(protected, current))
    body = json.dumps({"model": MODEL, "temperature": 1.3, "stream": False,
                       "thinking": {"type": "disabled"},   # 翻译无需思考链，省 ~90% 输出 token
                       "messages": [{"role": "system", "content": sys_prompt},
                                    {"role": "user", "content": user}]}).encode()
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(API_URL, data=body, headers={
                "Content-Type": "application/json", "Authorization": "Bearer " + key})
            with urllib.request.urlopen(req, timeout=180) as r:
                j = json.loads(r.read())
            text = j["choices"][0]["message"]["content"].strip()
            return text, j.get("usage", {})
        except Exception as e:
            last = e; time.sleep(3)
    raise last

def main():
    args = sys.argv[1:]
    dry = "--dry-run" in args
    allmode = "--all" in args
    batch = 0
    yes = "--yes" in args
    key_file = None
    mode = "review"
    valley_only = "--valley-only" in args
    for i, a in enumerate(args):
        if a == "--batch": batch = int(args[i + 1])
        elif a == "--key-file": key_file = args[i + 1]
        elif a == "--mode": mode = args[i + 1]   # review=对照审校 | rewrite=DeepSeek 按自己的推理习惯重写
        elif a == "--valley-only": pass
    if mode not in ("review", "rewrite"):
        print("--mode 只接受 review 或 rewrite"); sys.exit(1)
    period, is_peak = price_period()
    if valley_only and is_peak:
        print(f"当前为{period}，--valley-only 拒绝启动（谷时段: 12-14 / 18-次日9）。未花钱。"); sys.exit(0)
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key and key_file and os.path.isfile(key_file):
        key = open(key_file, encoding="utf-8").read().strip()
    if not dry and not key:
        print("缺凭据：设置环境变量 DEEPSEEK_API_KEY 或用 --key-file。未调用任何 API。"); sys.exit(1)

    limit = None if allmode else (batch or (None if dry else 0))
    if dry and not batch and not allmode: limit = 20
    rows = pending_review(limit)
    if not rows:
        print("没有待审条目。"); return

    period, is_peak = price_period()
    in_tok = sum(est_tokens(p) + est_tokens(c) + est_tokens(SYSTEM) + 120 for _, p, c in rows)
    out_tok = sum(est_tokens(c) for _, _, c in rows)
    cost = in_tok * PRICE["in"] + out_tok * PRICE["out"]
    print(f"当前为{period} | 待审 {len(rows)} 条 | 预估输入 {in_tok/1000:.0f}k tok, 输出 {out_tok/1000:.0f}k tok"
          f" | 预估费用 {cost:.2f} 元" + (f"（峰价，谷时段跑约 {cost/2:.2f} 元）" if is_peak else "（谷价）")
          + "（粗估，实报以 usage 为准）")
    for k, p, c in rows[:3]:
        print(f"  例 {k[:10]}: {p[:44]}...")
    if dry:
        print("（dry-run 未调用 API）"); return
    if not yes:
        ans = input(f"确认审校以上 {len(rows)} 条？[y/N] ").strip().lower()
        if ans != "y":
            print("已取消，未花钱。"); return

    done = cost_real = tok_in = tok_out = 0
    t0 = time.time()
    source_mark = "review-deepseek" if mode == "review" else "review-rewrite-deepseek"
    def work(item):
        nonlocal done, cost_real, tok_in, tok_out
        k, p, c = item
        try:
            text, usage = call_api(key, p, c, mode=mode)
            if text:
                tm_store.update_translation(k, clean_output(text), MODEL, source_mark)
            done += 1
            u_in, u_out = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
            tok_in += u_in; tok_out += u_out
            cost_real += u_in * PRICE["in"] + u_out * PRICE["out"]
            if done % 50 == 0:
                print(f"  进度 {done}/{len(rows)}  实际费用 {cost_real:.2f} 元", flush=True)
        except Exception as e:
            print(f"  ERR {str(k)[:10]}: {str(e)[:90]}", flush=True)
    with ThreadPoolExecutor(max_workers=3) as ex:
        list(ex.map(work, rows))
    print(f"完成 {done}/{len(rows)}  输入 {tok_in} tok, 输出 {tok_out} tok"
          f"  实际费用 {cost_real:.2f} 元  耗时 {time.time()-t0:.0f}s")

if __name__ == "__main__":
    main()
