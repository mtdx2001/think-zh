#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""think-zh watcher 轻量启动器（2026-10-11）

存在理由（实测缺陷，不是设计洁癖）：
  start_watcher.cmd 原先用 `start /b pythonw ... >> log 2>&1` 启动，
  /b 让 pythonw 继承控制台，且 cmd 的内联重定向会让父 cmd 等到句柄关闭——
  开机自启场景下表现为「服务已就绪，但 cmd 壳挂着不退出」（实测两次，
  第二次留下挂死 cmd 壳 PID 31440）。改用本启动器：由 Python 自己 open() 持有
  日志句柄，父进程启动后立即返回，不再依赖 cmd 重定向语义。

顺带把幂等判据从 netstat 文本匹配升级为 socket 实测（更可靠）：
  netstat 输出含 TIME_WAIT 行，文本顺序写反即漏判；握手实测不会误判。

用法：pythonw.exe start_watcher.py   （python 亦可，仅多一个窗口）
"""
import glob
import json
import os
import shutil
import socket
import subprocess
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(APP_DIR, "watcher.log")
PORT = 18765
SCRIPT = os.path.join(APP_DIR, "watcher_service.py")


def find_pythonw():
    """定位 pythonw.exe：优先已配置值 → PATH → 常见安装位置。

    不写死解释器绝对路径：本仓库是公开的，写死会把本机环境暴露出去，
    且用户可能装在别的版本目录或用 conda 环境。
    若 local_config.json 里有 pythonw 字段则优先采用（本机可显式指定）。
    """
    import shutil
    cfg = load_local_config()
    if cfg.get("pythonw") and os.path.isfile(cfg["pythonw"]):
        return cfg["pythonw"]

    found = shutil.which("pythonw")
    if found:
        return found

    exe_dir = os.path.dirname(sys.executable)
    for name in ("pythonw.exe", "python.exe"):
        cand = os.path.join(exe_dir, name)
        if os.path.isfile(cand):
            return cand

    for pat in (
        r"C:\Python3*\pythonw.exe",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Programs\Python\Python3*\pythonw.exe"),
        os.path.join(os.environ.get("USERPROFILE", ""), r"AppData\Local\Programs\Python\Python3*\pythonw.exe"),
    ):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None


def port_listening(port, host="127.0.0.1", timeout=1.0):
    """握手实测：真有人监听才返回 True。

    优于 netstat 文本匹配——后者输出里同一端口会出现 LISTENING 与多条
    TIME_WAIT，靠 findstr 顺序筛容易漏判（本项目已实测踩中一次）。
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def load_local_config():
    """读取本机专属配置 `local_config.json`（**不入库**，见 .gitignore）。

    这样拆分的理由：本仓库是公开的，而 DSH_HOME / 会话根目录属本机私有
    环境信息（含用户名与私有目录名），不该出现在公开代码里。
    没有该文件时（社区用户/新机器）返回空字典，行为与不配置一致。
    """
    path = os.path.join(APP_DIR, "local_config.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"[start_watcher] local_config.json 解析失败，已忽略: {e}")
        return {}


def main():
    if port_listening(PORT):
        print(f"[start_watcher] {PORT} 已在监听，跳过重复启动")
        return 0

    env = os.environ.copy()
    cfg = load_local_config()

    # 环境变量在此补齐：从自启快捷方式拉起时可能没有父 shell 的 set 结果。
    # 优先级：已有环境变量 > local_config.json > 不设置（交给 watcher_service 自行探测）
    if not env.get("DSH_HOME") and cfg.get("dsh_home"):
        env["DSH_HOME"] = cfg["dsh_home"]
    if not env.get("DSH_SESSION_ROOTS") and cfg.get("dsh_session_roots"):
        roots = cfg["dsh_session_roots"]
        env["DSH_SESSION_ROOTS"] = ";".join(roots) if isinstance(roots, list) else str(roots)

    # 2026-10-11：清掉从 DSH 会话继承来的 DSH_SESSION_JSONL。
    #
    # 缘由（实测）：DSH 会向每个会话进程注入 DSH_SESSION_JSONL=<当前会话文件>。
    # 从 DSH 的终端里执行 start_watcher.cmd 时该变量被继承，watcher_service 见它
    # 非空即走「只跟这一个文件」的分支——于是**另一个同时活跃的会话完全不翻译**。
    # 实测现场：两个 DSH 会话同时活跃（ddfc4c7b 与 afe1e990），只有被注入的那个有译文。
    #
    # 该变量本意是调试/演示（手动指定单个会话回放），不该在正常启动时被动继承，
    # 故此处默认清除；确需单会话调试时，在 local_config.json 里显式写
    # "dsh_session_jsonl": "<路径>"，或直接设同名环境变量（显式设置优先，不清）。
    if cfg.get("dsh_session_jsonl"):
        env["DSH_SESSION_JSONL"] = cfg["dsh_session_jsonl"]
    elif not env.get("TZ_KEEP_SESSION_JSONL"):
        env.pop("DSH_SESSION_JSONL", None)

    # 由本进程持有日志句柄并传给子进程：这是不阻塞的关键
    exe = find_pythonw()
    if not exe:
        print("[start_watcher] 未找到 pythonw.exe，请确认 Python 已安装并加入 PATH"
              "（或在 local_config.json 里指定 pythonw）")
        return 1

    logf = open(LOG, "a", encoding="utf-8", errors="replace")
    try:
        subprocess.Popen(
            [exe, "-X", "utf8", "-u", SCRIPT],
            cwd=APP_DIR,
            env=env,
            stdout=logf,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=0x08000000 | 0x00000008,  # CREATE_NO_WINDOW | DETACHED_PROCESS
            close_fds=False,
        )
    finally:
        logf.close()   # 子进程已持有自己的副本，父侧可安全关闭

    print(f"[start_watcher] 已拉起 watcher_service.py（端口 {PORT}，解释器 {exe}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
