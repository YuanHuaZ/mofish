@echo off
chcp 65001 >nul
rem ============================================================
rem  数独 · 100 关  —— 桌面版启动器
rem  优先运行打包好的 exe；没有则用本地 Python 环境直接跑源码
rem ============================================================
setlocal

if exist "%~dp0数独100关.exe" (
    start "" "%~dp0数独100关.exe"
    exit /b 0
)

set PY="C:\Users\zrf\.workbuddy\binaries\python\envs\default\Scripts\pythonw.exe"
if exist %PY% (
    start "" %PY% "%~dp0sudoku_app.py"
    exit /b 0
)

echo 未找到 exe，也未找到运行环境。
echo 请用 Python 运行： python sudoku_app.py
pause
