# -*- coding: utf-8 -*-
"""生成可分享的库副本：剔除含敏感模式的条目（protected 与 translation 双侧检查）。

2026-10-11 补强缘由（本次刷库实测）：
  原规则只覆盖凭据类模式，对「本机身份/路径」类完全无防护。对 14.6 万条现役库
  全量扫描后发现漏网：本机用户名 129 条 / 本机安装路径标识 221 条 / 带盘符路径 38 条 /
  邮箱 91 条——这些会随种子库公开发布。现已并入 PATTERNS，与 scan_sensitive.py
  的规则集取并集。
  另：本次扫描同时确认凭据类拦截有效（真实 sk- key 9 条、明文密码等均被剔除）。
"""
import sys, os, re, shutil, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # app\ 根

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(APP, "cache", "tm.sqlite3")
DST = os.path.join(APP, "seed", "tm-share.sqlite3")

PATTERNS = [
    r"sk-[A-Za-z0-9]{8,}",                                   # API key
    r"(?i)bearer\s+[A-Za-z0-9_\-\.]{10,}",                   # Bearer 实值
    r"(?i)cookie\s*[:=]\s*\S{10,}",                          # Cookie 实值
    r"\b[0-9a-f]{32,}\b",                                    # 长十六进制（哈希/密钥）
    r"(?i)(password|passwd|secret|token)\s*[:=]\s*[A-Za-z0-9_\-]{8,}",  # 凭据赋值
    r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b",                    # IP（含内网，稳妥全剔）
    r"(?i)api[_-]?key\s*[:=]\s*\S",

    # ---- 2026-10-11 补强（本次刷库实测漏网，见文件头说明）----
    r"(?i)administrator",                                    # 本机用户名（实测漏网 129 条）
    r"(?i)DSH011rc1",                                        # 本机 DSH 安装路径标识（实测漏网 221 条）
    r"[A-Za-z]:\\\\?[^\s⟦]{3,}",                             # 带盘符本机路径（实测漏网 38 条）
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",      # 邮箱（实测漏网 91 条）
]

def sensitive(text):
    return any(re.search(p, text) for p in PATTERNS)

shutil.copyfile(SRC, DST)
con = sqlite3.connect(DST)
rows = con.execute("SELECT key, protected, translation FROM tm").fetchall()
drop = [k for k, p, t in rows if sensitive(p) or sensitive(t)]
for k in drop:
    con.execute("DELETE FROM canon WHERE key=?", (k,))
    con.execute("DELETE FROM tm WHERE key=?", (k,))
con.commit()
con.execute("VACUUM")
left = con.execute("SELECT COUNT(*) FROM tm").fetchone()[0]
size = os.path.getsize(DST) / 1e6
print(f"源库 {len(rows)} 条 → 剔除敏感 {len(drop)} 条 → 干净副本 {left} 条")
print(f"导出: {DST}  ({size:.1f} MB)")

# 复扫确认
rescan = con.execute("SELECT key, protected, translation FROM tm").fetchall()
leak = [(k, p[:40]) for k, p, t in rescan if sensitive(p) or sensitive(t)]
print(f"复扫残留: {len(leak)} 条  {'✓ 干净' if not leak else '✗ 仍需处理'}")
for k, p in leak[:3]:
    print("   ", k[:8], p)

