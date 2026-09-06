@echo off
rem think-zh watcher launcher (multi-root session monitoring)
chcp 65001 >nul
set DSH_HOME=E:\DSH011rc1\home
set DSH_SESSION_ROOTS=E:\deepseek\创造区\.rc8-lab-home;E:\deepseek\创造区\.wallpaper-layer-acceptance\home-coexist
cd /d D:\think-zh\app
python -X utf8 -u watcher_service.py
