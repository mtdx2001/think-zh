# -*- coding: utf-8 -*-
"""阶段0：从真实会话提取思维链样本（30句多样化）"""
import zstandard, json, io, re, glob, hashlib

SESSION_FILES = [
    r"E:\DSH011rc1\home\sessions\--E-DSH011rc1-workspace--\session-02ef6273-dab9-4925-a8db-e5b5676b474a\session.jsonl.zstd",
    r"E:\DSH011rc1\home\sessions\--E-DSH011rc1-workspace--\session-2764e268-3dc5-4e4d-ad20-c136b9ec6d1f\session.jsonl.zstd",
    r"C:\Users\Administrator\AppData\Roaming\deepseek-harness-desktop\harness-home\sessions\--E-deepseek-~521B~9020~533A--\session-97a5e4bf-a0bb-432f-9de6-dbe19fe1d725\session.jsonl.zstd",
]

# ---------- 代码段保护 ----------
PLACE = "\u27e6P{:03d}\u27e7"  # ⟦P001⟧
CODE_PATTERNS = [
    r"`[^`]+`",                                   # 行内代码
    r"https?://[^\s'\"<>)\u27e6]+",               # URL
    r"[A-Za-z]:\\[^\s'\"<>]+",                    # Windows 路径
    r"/(?:api|mvc|home|users|app)[/\w\-.,?=&%]*", # 服务端路径
    r"\b[\w]+\.(?:py|js|ts|json|md|yaml|yml|zstd|zip|gguf|exe|db|sqlite3)\b",  # 文件名
    r"\b[a-z]+(?:[A-Z][a-z]+)+\b",                # camelCase
    r"\b[a-z]+(?:_[a-z0-9]+)+\b",                 # snake_case
    r"\b\d+(?:\.\d+)?\s?(?:GB|MB|KB|ms|s|min|token|tokens)\b",  # 数字+单位
    r"⟦P\d{3}⟧",                                  # 已有占位符
]
def protect(text):
    slots = []
    def _sub(m):
        slots.append(m.group(0))
        return PLACE.format(len(slots))
    combined = "|".join(CODE_PATTERNS)
    protected = re.sub(combined, _sub, text)
    return protected, slots

def zh_ratio(s):
    if not s: return 0
    zh = sum(1 for c in s if '\u4e00' <= c <= '\u9fff')
    return zh / max(len(s), 1)

def split_sentences(text):
    # 按中英文句读/换行切，保留 20~400 字符
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z\u0022\u0027( ])|(?<=[。！？])|[\n\r]+', text)
    out = []
    for p in parts:
        p = p.strip()
        while len(p) > 400:
            cut = p.rfind(', ', 100, 400)
            if cut < 0: cut = p.rfind(' ', 100, 400)
            if cut < 0: break
            out.append(p[:cut+1].strip()); p = p[cut+1:].strip()
        if p: out.append(p)
    return [p for p in out if 20 <= len(p) <= 400]

def category(protected):
    codes = re.findall(r'⟦P\d{3}⟧', protected)
    if len(codes) >= 2 or re.search(r'⟦P\d{3}⟧[^\u27e6]*⟦P\d{3}⟧', protected): return 'code-mixed'
    if re.search(r'\b(wait|actually|hmm|no,|let me|on second thought)\b', protected, re.I): return 'self-correct'
    if len(protected) > 200: return 'long'
    if len(protected) < 80: return 'short'
    return 'plain'

# ---------- 提取 ----------
all_sentences = {}
stats = {}
for path in SESSION_FILES:
    tag = path.split('\\')[-2][:13]
    try:
        with open(path, 'rb') as f:
            text = io.TextIOWrapper(zstandard.ZstdDecompressor().stream_reader(f),
                                    encoding='utf-8', errors='replace').read()
    except Exception as e:
        print(f'[跳过] {tag}: {e}'); continue
    n_blocks = 0
    for line in text.split('\n'):
        if '"reasoning-chunks"' not in line: continue
        try: o = json.loads(line)
        except: continue
        d = o.get('data', {})
        block = ''.join(d.get('texts', []))
        if not block: continue
        n_blocks += 1
        for s in split_sentences(block):
            if zh_ratio(s) > 0.3: continue
            prot, slots = protect(s)
            key = hashlib.sha1(prot.encode()).hexdigest()[:12]
            if key in all_sentences: 
                all_sentences[key]['count'] += 1; continue
            all_sentences[key] = {'id': key, 'src': tag, 'turn': d.get('turn'),
                                  'text': s, 'protected': prot, 'count': 1,
                                  'cat': category(prot)}
    stats[tag] = n_blocks

print('各文件 reasoning 块数:', stats)
print('去重后句子总数:', len(all_sentences))

# ---------- 分层抽样 30 句 ----------
from collections import defaultdict
buckets = defaultdict(list)
for v in all_sentences.values(): buckets[v['cat']].append(v)
quota = {'code-mixed': 9, 'self-correct': 6, 'long': 5, 'short': 4, 'plain': 6}
sample = []
for cat, q in quota.items():
    pool = sorted(buckets.get(cat, []), key=lambda x: -x['count'])  # 重复多=常用句式优先
    sample.extend(pool[:q])
while len(sample) < 30:  # 补齐
    rest = sorted(all_sentences.values(), key=lambda x: -x['count'])
    for v in rest:
        if v not in sample: sample.append(v); break
    if len(rest) == 0: break
sample = sample[:30]
for i, v in enumerate(sample): v['sid'] = i + 1

out = r'E:\DSH011rc1\workspace\think-zh\out\sample_sentences.json'
import os; os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, 'w', encoding='utf-8') as f:
    json.dump(sample, f, ensure_ascii=False, indent=1)
print('样本 30 句 ->', out)
print('类别分布:', {c: sum(1 for v in sample if v["cat"]==c) for c in quota})
