@echo off
rem think-zh watcher launcher (multi-root, windowless)
rem 2026-10-11 hardened by DSH assistant - see start_watcher.py header for the full rationale.
rem   1) CRLF line endings (cmd mis-parses label/for blocks under LF)
rem   2) idempotent: never start a second instance fighting for port 18765
rem   3) no more "start /b" (it made the child inherit the console and hang the parent cmd)
rem   4) launch logic moved into start_watcher.py (python holds the log handle itself)
rem NOTE: keep this file ASCII-only. cmd parses the whole file with the ANSI codepage
rem       BEFORE chcp 65001 takes effect, so non-ASCII rem lines become bogus commands.
chcp 65001 >nul
set "DSH_HOME=E:\DSH011rc1\home"
set "DSH_SESSION_ROOTS=E:\deepseek\创造区\.rc8-lab-home;E:\deepseek\创造区\.wallpaper-layer-acceptance\home-coexist;C:\Users\Administrator\AppData\Roaming\deepseek-harness-desktop\harness-home"
cd /d D:\think-zh\app
C:\Python314\pythonw.exe -X utf8 -u start_watcher.py
exit /b 0
