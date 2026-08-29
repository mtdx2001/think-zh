# -*- coding: utf-8 -*-
"""TM 翻译库：SQLite 存储（WAL 模式）。"""
import sqlite3, os, threading

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "tm.sqlite3")
_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS tm (
  key        TEXT PRIMARY KEY,
  protected  TEXT NOT NULL,
  translation TEXT,
  model      TEXT,
  source     TEXT,          -- offline-7b / realtime-1.8b / human / offline-upgrade
  created    TEXT DEFAULT (datetime('now','localtime')),
  hits       INTEGER DEFAULT 0,
  needs_review INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tm_source ON tm(source);
CREATE TABLE IF NOT EXISTS terms (
  en TEXT PRIMARY KEY, zh TEXT NOT NULL, version INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""

def conn():
    c = getattr(_local, "c", None)
    if c is None:
        os.makedirs(os.path.dirname(DB), exist_ok=True)
        c = sqlite3.connect(DB, check_same_thread=False, timeout=15)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.execute("PRAGMA busy_timeout=15000")
        c.executescript(SCHEMA)
        _local.c = c
    return c

def has(key):
    return conn().execute("SELECT 1 FROM tm WHERE key=?", (key,)).fetchone() is not None

def pending_keys(keys):
    """返回 keys 中尚未入库的子集合。"""
    con = conn()
    out = []
    for i in range(0, len(keys), 500):
        chunk = keys[i:i+500]
        q = ",".join("?" * len(chunk))
        have = {r[0] for r in con.execute(f"SELECT key FROM tm WHERE key IN ({q})", chunk)}
        out.extend(k for k in chunk if k not in have)
    return out

def put(key, protected, translation, model, source):
    con = conn()
    con.execute(
        "INSERT OR IGNORE INTO tm(key, protected, translation, model, source) VALUES (?,?,?,?,?)",
        (key, protected, translation, model, source))
    con.commit()

def upgrade_keys(source_prefix):
    """取需要升级重翻的条目 [(key, protected)]。"""
    return conn().execute(
        "SELECT key, protected FROM tm WHERE source LIKE ? OR needs_review=1",
        (source_prefix + "%",)).fetchall()

def update_translation(key, translation, model, source):
    con = conn()
    con.execute(
        "UPDATE tm SET translation=?, model=?, source=?, needs_review=0 WHERE key=?",
        (translation, model, source, key))
    con.commit()

def stats():
    con = conn()
    total = con.execute("SELECT COUNT(*) FROM tm").fetchone()[0]
    by_src = con.execute("SELECT source, COUNT(*) FROM tm GROUP BY source").fetchall()
    return {"total": total, "by_source": dict(by_src)}

if __name__ == "__main__":
    print(stats())
