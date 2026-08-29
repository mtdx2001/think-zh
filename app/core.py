# -*- coding: utf-8 -*-
"""think-zh 核心：代码段保护、句切分（先保护后切分）、还原、提示词构建"""
import re

PLACE = "\u27e6P{:03d}\u27e7"  # ⟦P001⟧

CODE_PATTERNS = [
    r"`[^`\n]{1,200}`",                              # 行内代码
    r"https?://[^\s'\"<>)\u27e6]+",                  # URL
    r"[A-Za-z]:\\[^\s'\"<>]+",                       # Windows 路径
    r"(?:/[\w\-.,?=&%:]+){2,}",                      # POSIX 路径/服务路径
    r"\b[\w\-]+\.(?:py|js|ts|json|md|yaml|yml|zstd|zip|gguf|exe|db|sqlite3|dll|csv|docx|xlsx|pptx|lnk|html|css)\b",  # 文件名
    r"\b[a-z]+(?:[A-Z][a-z0-9]+){1,}\b",             # camelCase
    r"\b[a-z]+(?:_[a-z0-9]+){1,}\b",                 # snake_case
    r"\b\d+(?:\.\d+)?\s?(?:GB|MB|KB|ms|us|min|token|tokens|fps)\b",
    r"\b0x[0-9a-fA-F]+\b",                           # 十六进制
    r"\b[A-Z]{2,}(?:-[A-Za-z0-9]+)+\b",              # 大写连字符 (RC1, Hy-MT2)
    r"\b[a-z_]\w*\s*=\s*(?:true|false|null|True|False|None|\d+|[\w.\-/]+)\b",  # 赋值/参数 hit=true
    r"(?<![\w])--?[a-z][\w-]*\b",                    # 命令行参数 --jinja / -np
    r"\bsk-[A-Za-z0-9_\-]{10,}\b",                   # API key 形态（sk-xxx），永不入库
    r"\b[0-9a-f]{32,}\b",                            # 长十六进制（哈希/密钥指纹）
]

_PROTECT_RE = re.compile("|".join(CODE_PATTERNS))
_SENT_SPLIT_RE = re.compile(
    r"(?<=[.!?])\s+(?=[A-Z\u0022\u0027(\- ])|(?<=[。！？])|[\n\r]+")

def protect(text):
    """代码段 → 占位符。返回 (protected_text, slots列表)。"""
    slots = []
    def _sub(m):
        slots.append(m.group(0))
        return PLACE.format(len(slots))
    return _PROTECT_RE.sub(_sub, text), slots

def split_protected(protected, lo=15, hi=420):
    """对【已保护】文本切句（占位符是原子，不会被切断）。"""
    parts = _SENT_SPLIT_RE.split(protected)
    out = []
    for p in parts:
        p = p.strip()
        while len(p) > hi:
            cut = max(p.rfind(", ", lo, hi), p.rfind("; ", lo, hi), p.rfind(" ", lo, hi))
            if cut < lo: break
            out.append(p[:cut + 1].strip()); p = p[cut + 1:].strip()
        if p and len(p) >= lo:
            out.append(p)
    return out

def restore(translated_protected, slots):
    """占位符 → 原始代码段。"""
    def _sub(m):
        i = int(m.group(1)) - 1
        return slots[i] if 0 <= i < len(slots) else m.group(0)
    return re.sub(r"\u27e6P(\d{3})\u27e7", _sub, translated_protected)

def zh_ratio(s):
    if not s: return 0
    return sum(1 for c in s if "\u4e00" <= c <= "\u9fff") / max(len(s), 1)

PROMPT_DEFAULT = (
    "将以下文本翻译为 `中文`，注意只需要输出翻译后的结果，不要额外解释，"
    "不要在输出中添加任何反引号或代码块标记：\n\n{text}"
)
PROMPT_PLACEHOLDER = (
    "请将以下文本准确翻译为 `中文`。你必须在译文中保留等量的分隔符，"
    "形如 \u27e6P001\u27e7 的占位符号码绝对不可遗漏、转义或翻译，并注意占位符的位置。"
    "注意只需要输出翻译后的结果，不要额外解释，不要添加任何反引号：\n\n{text}"
)

def match_terms(text, terms, limit=8):
    """句中命中的术语对 [(en, zh)]，按官方 Terminology 模板注入。"""
    out = []
    for en, zh in (terms or {}).items():
        if re.search(r"(?<![\w])" + re.escape(en) + r"(?![\w])", text, re.I):
            out.append((en, zh))
            if len(out) >= limit: break
    return out

def build_prompt(protected_text, glossary=None):
    head = ""
    if glossary:
        lines = "\n".join("`%s` 翻译成 `%s`" % (e, z) for e, z in glossary)
        head = "*参考下面的翻译：*\n" + lines + "\n\n"
    if "\u27e6P" in protected_text:
        return head + PROMPT_PLACEHOLDER.format(text=protected_text)
    return head + PROMPT_DEFAULT.format(text=protected_text)

def clean_output(s):
    return (s or "").strip().strip("`").strip().replace("`", "")
