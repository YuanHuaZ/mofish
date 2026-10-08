@echo off
chcp 65001 >nul
rem ============================================================
rem  五子棋  —— 单游戏启动器
rem  优先运行本目录下的 exe；没有则用本地 Python 环境直接跑源码
rem  想一次玩全部五款游戏，请双击项目根目录的「启动游戏合集.bat」
rem ============================================================
setlocal

if exist "%~dp0五子棋.exe" (
    start "" "%~dp0五子棋.exe"
    exit /b 0
)

set PYW="C:/Users/zrf/.workbuddy/binaries/python/envs/default/Scripts/pythonw.exe"
if exist %PYW% (
    start "" %PYW% "%~dp0gomoku_app.py"
    exit /b 0
)

echo 未找到 exe，也未找到运行环境。
echo 请用 Python 运行： python "%~dp0gomoku_app.py"
pause
