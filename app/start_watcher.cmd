@echo off
rem think-zh watcher launcher (windowless, idempotent)
rem Hardened 2026-10-11 - see start_watcher.py header for the full rationale:
rem   1) CRLF line endings (cmd mis-parses label/for blocks under LF)
rem   2) idempotent: never start a second instance fighting for port 18765
rem   3) no "start /b" (it made the child inherit the console, hanging the parent cmd)
rem   4) launch logic lives in start_watcher.py (python holds the log handle itself)
rem NOTE: keep this file ASCII-only. cmd parses the whole file with the ANSI
rem       codepage BEFORE chcp takes effect, so non-ASCII rem lines become
rem       bogus commands. Machine-specific paths go in local_config.json.
chcp 65001 >nul
cd /d %~dp0
pythonw -X utf8 -u start_watcher.py
exit /b 0
