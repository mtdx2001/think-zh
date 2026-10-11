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
import os
import socket
import subprocess
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(APP_DIR, "watcher.log")
PORT = 18765
PYTHONW = r"C:\Python314\pythonw.exe"
SCRIPT = os.path.join(APP_DIR, "watcher_service.py")


def port_listening(port, host="127.0.0.1", timeout=1.0):
    """握手实测：真有人监听才返回 True。

    优于 netstat 文本匹配——后者输出里同一端口会出现 LISTENING 与多条
    TIME_WAIT，靠 findstr 顺序筛容易漏判（本项目已实测踩中一次）。
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def main():
    if port_listening(PORT):
        print(f"[start_watcher] {PORT} 已在监听，跳过重复启动")
        return 0

    env = os.environ.copy()
    env["DSH_HOME"] = env.get("DSH_HOME") or r"E:\DSH011rc1\home"

    # 环境变量在此显式补齐：从自启快捷方式拉起时可能没有父 shell 的 set 结果
    roots = [
        r"E:\deepseek\创造区\.rc8-lab-home",
        r"E:\deepseek\创造区\.wallpaper-layer-acceptance\home-coexist",
        r"C:\Users\Administrator\AppData\Roaming\deepseek-harness-desktop\harness-home",
    ]
    env["DSH_SESSION_ROOTS"] = env.get("DSH_SESSION_ROOTS") or ";".join(roots)

    # 由本进程持有日志句柄并传给子进程：这是不阻塞的关键
    logf = open(LOG, "a", encoding="utf-8", errors="replace")
    try:
        subprocess.Popen(
            [PYTHONW, "-X", "utf8", "-u", SCRIPT],
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

    print(f"[start_watcher] 已拉起 watcher_service.py（端口 {PORT}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
