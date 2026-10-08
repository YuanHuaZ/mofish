# -*- coding: utf-8 -*-
"""
打包脚本：把五款小游戏打成一个 exe（输出到项目根目录 / 摸鱼游戏合集.exe）

用法（在项目根目录下执行）：
    python build_exe.py

说明：
- 通过 PyInstaller 的 Python API 调用，避免命令行里 `;` 分隔符被 shell 吃掉
- 不使用 --clean（会触发批量删除保护），改为每次使用全新的 workpath
- 各游戏目录下的关卡 JSON 通过 --add-data 打进包内同名子目录，
  运行时由 shared.common.find_game_data() 定位
"""
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
NAME = "摸鱼游戏合集"
# 每次都用全新的 workpath / distpath：既不触发批量删除保护，也不复用旧缓存
STAMP = int(time.time())
DIST = os.path.join(ROOT, "build", "dist-%d" % STAMP)
WORK = os.path.join(ROOT, "build", "work-%d" % STAMP)
SPEC = os.path.join(ROOT, "build")
ENTRY = os.path.join(ROOT, "main.py")

# 源码路径 -> 包内子目录
DATA_FILES = [
    ("sudoku/puzzles.json", "sudoku"),
    ("klotski/levels.json", "klotski"),
    ("numberklotski/levels.json", "numberklotski"),
    ("point24/puzzles.json", "point24"),
    ("assets/icon.ico", "assets"),        # 应用图标（窗口 / 任务栏）
    ("assets/logo.png", "assets"),        # 大厅 logo
]

ICON = os.path.join(ROOT, "assets", "icon.ico")

HIDDEN = [
    "shared.common", "hall.launcher",
    "sudoku.sudoku_app", "sudoku.engine",
    "klotski.klotski_app", "klotski.engine",
    "numberklotski.number_app", "numberklotski.engine",
    "xiangqi.xiangqi_app", "xiangqi.engine",
    "gomoku.gomoku_app", "gomoku.engine",
    "point24.point24_app", "point24.engine",
]

EXCLUDES = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQml", "PySide6.QtQuickWidgets",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtCharts",
    "PySide6.QtDataVisualization", "PySide6.QtSql", "PySide6.QtTest",
    "PySide6.QtDesigner", "PySide6.QtUiTools", "PySide6.QtHelp", "PySide6.QtPdf",
    "PySide6.QtPdfWidgets", "PySide6.Qt3DCore", "PySide6.QtBluetooth",
    "PySide6.QtPositioning", "PySide6.QtLocation", "PySide6.QtSensors",
    "PySide6.QtSerialPort", "PySide6.QtWebSockets", "PySide6.QtWebChannel",
    "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtStateMachine",
    "PySide6.QtTextToSpeech", "PySide6.QtNfc", "PySide6.QtSerialBus",
    "PySide6.QtSpatialAudio", "PySide6.QtGraphs", "PySide6.QtHttpServer",
    "tkinter", "unittest", "pydoc", "doctest", "email", "http", "xmlrpc",
    "pdb", "lib2to3", "distutils", "setuptools", "pip",
]


def main():
    try:
        import PyInstaller.__main__ as pim
    except ImportError:
        print("缺少 PyInstaller，请先安装：pip install pyinstaller")
        return 1

    os.makedirs(WORK, exist_ok=True)
    os.makedirs(SPEC, exist_ok=True)

    args = [ENTRY,
            "--noconfirm", "--onefile", "--windowed",
            "--name", NAME,
            "--distpath", DIST, "--workpath", WORK, "--specpath", SPEC,
            "--log-level", "WARN"]
    if os.path.exists(ICON):
        args += ["--icon", ICON]          # exe 文件图标
    else:
        print("!! 未找到图标 %s，将使用默认图标" % ICON)
    for src, dest in DATA_FILES:
        p = os.path.join(ROOT, src)
        if not os.path.exists(p):
            print("!! 缺少数据文件：%s" % p)
            return 1
        args += ["--add-data", "%s%s%s" % (p, os.pathsep, dest)]
    for m in HIDDEN:
        args += ["--hidden-import", m]
    for m in EXCLUDES:
        args += ["--exclude-module", m]

    print("开始打包…（首次约 1-3 分钟）")
    pim.run(args)

    out = os.path.join(DIST, NAME + ".exe")
    if not os.path.exists(out):
        print("!! 打包失败，未生成 %s" % out)
        return 1
    target = os.path.join(ROOT, NAME + ".exe")
    try:
        shutil.copy2(out, target)
    except Exception as exc:
        print("复制到项目根目录失败：%s" % exc)
    print("打包完成：%s（%.1f MB）" % (out, os.path.getsize(out) / 1024.0 / 1024.0))
    print("已复制到：%s" % target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
