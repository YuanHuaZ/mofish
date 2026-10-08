@echo off
chcp 65001 >nul
rem ============================================================
rem  摸鱼小游戏合集  —— 总启动器（五款游戏）
rem  优先运行打包好的 exe；没有则用本地 Python 环境直接跑源码
rem ============================================================
setlocal

if exist "%~dp0摸鱼游戏合集.exe" (
    start "" "%~dp0摸鱼游戏合集.exe"
    exit /b 0
)

set PYW="C:/Users/zrf/.workbuddy/binaries/python/envs/default/Scripts/pythonw.exe"
if exist %PYW% (
    start "" %PYW% "%~dp0main.py"
    exit /b 0
)

echo 未找到 exe，也未找到运行环境。
echo 请用 Python 运行： python main.py
pause
