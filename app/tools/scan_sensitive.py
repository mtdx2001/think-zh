# -*- coding: utf-8 -*-
"""分享前敏感扫描：库中的 protected 骨架是否真的不含密钥/凭据/敏感值。"""
import sys, re
sys.path.insert(0, r"E:\DSH011rc1\workspace\think-zh")
import tm_store

con = tm_store.conn()
total = con.execute("SELECT COUNT(*) FROM tm").fetchone()[0]
print(f"库总量: {total} 条\n")

patterns = {
    "API key 形态 (sk-xxxx)": r"sk-[A-Za-z0-9]{8,}",
    "Bearer/Cookie 头":       r"(?i)(bearer\s+[A-Za-z0-9]|cookie\s*[:=])",
    "长十六进制串(可能密钥)":  r"\b[0-9a-f]{32,}\b",
    "邮箱":                   r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    "带盘符本机路径":          r"[A-Z]:\\\\?[^\s⟦]{3,}",
    "IP:端口":                r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+\b",
    "password/passwd 字样":   r"(?i)password\s*[:=]\s*\S",
}
total_hits = 0
for name, pat in patterns.items():
    rows = con.execute("SELECT key, protected FROM tm").fetchall()
    hits = [(k, p) for k, p in rows if re.search(pat, p)]
    print(f"{name:28s} {len(hits):>5} 条")
    total_hits += len(hits)
    for k, p in hits[:2]:
        print(f"    例 [{k[:8]}]: {p[:80]}")
print(f"\n合计命中: {total_hits} 条（占 {total_hits/total*100:.2f}%）")
