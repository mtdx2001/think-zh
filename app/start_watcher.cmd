@echo off
rem think-zh watcher launcher (multi-root, windowless: start /b prevents cmd waiting on pythonw redirect)
chcp 65001 >nul
set DSH_HOME=E:\DSH011rc1\home
set DSH_SESSION_ROOTS=E:\deepseek\创造区\.rc8-lab-home;E:\deepseek\创造区\.wallpaper-layer-acceptance\home-coexist;C:\Users\Administrator\AppData\Roaming\deepseek-harness-desktop\harness-home
cd /d D:\think-zh\app
start "" /b C:\Python314\pythonw.exe -X utf8 -u watcher_service.py >> D:\think-zh\app\watcher.log 2>&1
