# -*- coding: utf-8 -*-
"""
摸鱼小游戏合集 · 公共模块

统一提供：暗色主题配色、通用控件（按钮 / 卡片 / 状态行）、时间格式化、
资源与存档路径（区分只读资源与可写存档）、JSON 存档基类，以及所有游戏窗口
共用的基类 GameWindow（顶部「返回大厅」栏 + 关闭信号）。
"""
import json
import os
import sys
from datetime import datetime

from PySide6.QtCore import Qt, Signal, QStandardPaths, QSize
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QLabel, QPushButton, QFrame, QScrollArea)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# ------------------------------------------------------------------ 配色
C_BG = "#0b0e14"
C_PANEL = "#161b24"
C_PANEL2 = "#1c222d"
C_LINE = "#232b38"
C_LINE2 = "#3b4759"
C_TEXT = "#e8eef7"
C_DIM = "#8a97ab"
C_FAINT = "#5d6a7e"
C_ACCENT = "#4c8dff"
C_ACCENT2 = "#38bdf8"
C_GIVEN = "#e8eef7"
C_USER = "#5aa9ff"
C_HINT = "#34d399"
C_DANGER = "#ff5c5c"
C_OK = "#22c55e"
C_GOLD = "#f0b23c"

# 象棋红黑双方
C_RED = "#e5484d"
C_BLACK = "#9aa7b8"

# 每款游戏拥有自己的强调色，公共框架和控件保持一致。
GAME_ACCENTS = {
    "sudoku": "#38bdf8",
    "klotski": "#f0b23c",
    "number": "#a78bfa",
    "xiangqi": "#e5484d",
    "gomoku": "#22c55e",
    "point24": "#f472b6",
}


def rgba(hex_color, alpha):
    """Qt 的 8 位十六进制是 #AARRGGBB，容易写错，统一用 rgba() 表达透明色"""
    c = QColor(hex_color)
    return "rgba(%d,%d,%d,%.2f)" % (c.red(), c.green(), c.blue(), alpha)


# ------------------------------------------------------------------ 路径
def resource_dir():
    """只读资源目录（打包成 exe 后为解包目录 _MEIPASS）"""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", HERE)
    return HERE


SAVE_DIRNAME = "saves"
# 所有游戏的存档文件名（用于旧版本存档的自动归位）
SAVE_FILES = ("sudoku_save.json", "klotski_save.json", "number_save.json",
              "xiangqi_save.json", "gomoku_save.json", "point24_save.json")

_migrated = False


def base_dir():
    """可写的基目录：打包后是 exe 所在目录，源码运行是项目根目录"""
    return os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else ROOT


def _writable(d):
    """探测目录是否可写（顺便确保它存在）"""
    try:
        os.makedirs(d, exist_ok=True)
        probe = os.path.join(d, ".w_test")
        with open(probe, "w") as f:
            f.write("1")
        os.remove(probe)
        return True
    except Exception:
        return False


def _migrate_outer_saves(base, save_dir):
    """把旧版本散落在外的存档收进 saves/（只做一次）"""
    global _migrated
    if _migrated:
        return
    _migrated = True
    if os.path.abspath(base) == os.path.abspath(save_dir):
        return
    for name in SAVE_FILES:
        old = os.path.join(base, name)
        new = os.path.join(save_dir, name)
        if os.path.exists(old) and not os.path.exists(new):
            try:
                os.replace(old, new)
            except Exception:
                pass


def data_dir():
    """可写存档目录：exe / 项目根目录下的 saves/，不可写则退回 AppData/saves

    自检（--selftest）时改写到 _selftest/saves，绝不碰玩家的真实存档。
    """
    if "--selftest" in sys.argv:
        d = os.path.join(output_dir(), "saves")
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass
        return d
    base = base_dir()
    for root in (base, QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)):
        if not root:
            continue
        d = os.path.join(root, SAVE_DIRNAME)
        if _writable(d):
            _migrate_outer_saves(base, d)
            return d
    return os.path.join(base, SAVE_DIRNAME)


def output_dir():
    """自检 / 临时产物目录，与存档分开存放，避免污染 saves/"""
    d = os.path.join(base_dir(), "_selftest")
    try:
        os.makedirs(d, exist_ok=True)
        return d
    except Exception:
        return base_dir()


def load_json(name):
    """从只读资源目录读取 JSON（先试资源目录，再试脚本目录）"""
    for base in (resource_dir(), HERE):
        p = os.path.join(base, name)
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
    return {}


def find_game_data(filename, folder):
    """定位某个游戏目录下的数据文件（源码运行 / exe 解包目录都能找到）"""
    for base in (os.path.join(resource_dir(), folder), resource_dir(),
                 os.path.join(ROOT, folder), HERE):
        p = os.path.join(base, filename)
        if os.path.exists(p):
            return p
    return None


def asset_path(name):
    """定位 assets/ 下的静态资源（图标 / logo），源码运行与 exe 解包目录都能找到"""
    for base in (os.path.join(resource_dir(), "assets"),
                 os.path.join(ROOT, "assets"),
                 os.path.join(HERE, "assets")):
        p = os.path.join(base, name)
        if os.path.exists(p):
            return p
    return None


def app_icon():
    """应用图标 QIcon（找不到资源时返回空 QIcon，不影响运行）"""
    from PySide6.QtGui import QIcon
    p = asset_path("icon.ico") or asset_path("logo.png")
    return QIcon(p) if p else QIcon()


def load_game_json(filename, folder):
    """读取某个游戏目录下的 JSON 关卡数据"""
    p = find_game_data(filename, folder)
    if not p:
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def load_save(name):
    """读取某个游戏的存档（用于大厅展示战绩）"""
    try:
        with open(os.path.join(data_dir(), name), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def remove_save(name):
    """删除某个存档文件（重置进度 / 自检前清场用）"""
    try:
        os.remove(os.path.join(data_dir(), name))
        return True
    except Exception:
        return False


# ------------------------------------------------------------------ 存档
class BaseStore(object):
    """通用 JSON 存档：原子写入，字段缺失自动兜底"""

    def __init__(self, filename, defaults=None):
        self.path = os.path.join(data_dir(), filename)
        self.data = dict(defaults or {})
        self.load()

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                self.data.update(d)
        except Exception:
            pass

    def save(self):
        self.data.setdefault("meta", {})
        self.data["meta"]["updatedAt"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tmp = self.path + ".tmp"
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, separators=(",", ":"))
            os.replace(tmp, self.path)
        except Exception:
            pass


# ------------------------------------------------------------------ 时间
def fmt_time(ms):
    """毫秒 → 时间字符串；超过一小时带小时位"""
    if ms is None:
        return "--:--"
    s = int(ms) // 1000
    return "%d:%02d:%02d" % (s // 3600, (s // 60) % 60, s % 60) if s >= 3600 \
        else "%02d:%02d" % ((s // 60) % 60, s % 60)


# ------------------------------------------------------------------ 控件
def mk_button(text, kind="normal", parent=None):
    b = QPushButton(text, parent)
    b.setCursor(Qt.PointingHandCursor)
    b.setMinimumHeight(36)
    if kind == "primary":
        b.setStyleSheet(
            "QPushButton{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #3d7bf0,stop:1 #38bdf8);color:#06121f;border:none;"
            "border-radius:10px;font-weight:700;padding:9px 18px;}"
            "QPushButton:hover{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #4d8bff,stop:1 #4ac4f8);}"
            "QPushButton:disabled{background:%s;color:%s;}"
            % (C_PANEL2, C_FAINT))
    elif kind == "danger":
        b.setStyleSheet(
            "QPushButton{background:%s;color:%s;border:1px solid %s;"
            "border-radius:10px;padding:8px 14px;font-size:13px;}"
            "QPushButton:hover{color:%s;border-color:%s;}"
            % (C_PANEL2, C_DIM, C_LINE, C_DANGER, rgba(C_DANGER, 0.55)))
    else:
        b.setStyleSheet(
            "QPushButton{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 %s,stop:1 #151b26);"
            "color:%s;border:1px solid %s;border-radius:10px;padding:8px 14px;font-size:13px;}"
            "QPushButton:hover{background:#2a3545;color:%s;border-color:%s;}"
            "QPushButton:pressed{background:#111722;}"
            % (C_PANEL2, C_DIM, C_LINE, C_TEXT, C_LINE2))
    return b


class ToolButton(QPushButton):
    """侧栏工具按钮（可选中态）"""

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(46)
        self.setStyleSheet(
            "QPushButton{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 %s,stop:1 #151b26);"
            "color:%s;border:1px solid %s;border-radius:11px;font-size:12px;font-weight:600;}"
            "QPushButton:hover{background:#293548;color:%s;border-color:%s;}"
            "QPushButton:pressed{background:#111722;}"
            "QPushButton:checked{color:%s;border-color:rgba(56,189,248,.55);"
            "background:rgba(56,189,248,.12);}"
            "QPushButton:disabled{color:%s;}"
            % (C_PANEL2, C_DIM, C_LINE, C_TEXT, C_LINE2, C_ACCENT2, C_FAINT))

    def sizeHint(self):
        return QSize(120, 46)


def card(title=""):
    f = QFrame()
    f.setStyleSheet("QFrame{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 %s,stop:1 #121821);"
                    "border:1px solid %s;border-radius:15px;}" % (C_PANEL, C_LINE))
    lay = QVBoxLayout(f)
    lay.setContentsMargins(16, 14, 16, 15)
    lay.setSpacing(9)
    if title:
        lb = QLabel(title)
        lb.setStyleSheet("color:%s;font-size:11px;font-weight:800;letter-spacing:1px;"
                         % C_ACCENT2)
        lay.addWidget(lb)
    return f, lay


def stat_row(parent_layout, name, value):
    """一行「左标题 / 右数值」，返回数值 QLabel 以便后续更新"""
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    a = QLabel(name)
    a.setStyleSheet("color:%s;font-size:12.5px;" % C_DIM)
    b = QLabel(value)
    b.setStyleSheet("font-size:13px;font-weight:600;")
    row.addWidget(a)
    row.addStretch(1)
    row.addWidget(b)
    wrap = QWidget()
    wrap.setLayout(row)
    wrap.setFixedHeight(24)
    parent_layout.addWidget(wrap)
    return b


def vscroll(inner_widget, width=None):
    """给侧栏套一层不显眼的滚动条，窗口变小时不被裁切"""
    sc = QScrollArea()
    sc.setWidgetResizable(True)
    sc.setFrameShape(QFrame.NoFrame)
    sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    if width:
        sc.setFixedWidth(width)
    sc.setStyleSheet(
        "QScrollArea{background:transparent;border:none;}"
        "QScrollBar:vertical{background:transparent;width:8px;margin:2px;}"
        "QScrollBar::handle:vertical{background:%s;border-radius:4px;min-height:30px;}"
        "QScrollBar::add-line,QScrollBar::sub-line{height:0;}"
        "QScrollBar::add-page,QScrollBar::sub-page{background:transparent;}" % C_LINE2)
    sc.viewport().setStyleSheet("background:transparent;")
    inner_widget.setAttribute(Qt.WA_StyledBackground, True)
    inner_widget.setStyleSheet("background:transparent;")
    sc.setWidget(inner_widget)
    return sc


# ------------------------------------------------------------------ 游戏窗口基类
class GameWindow(QMainWindow):
    """所有小游戏的基类：顶部统一「返回大厅」栏，关闭时通知大厅重新显示"""

    windowClosed = Signal()
    game_key = "game"
    game_name = "游戏"
    game_emoji = "🎮"

    def __init__(self, app_name="摸鱼小游戏"):
        super().__init__()
        self.setWindowTitle("%s · %s" % (self.game_name, app_name))
        self.setWindowIcon(app_icon())
        self.accent = GAME_ACCENTS.get(self.game_key, C_ACCENT2)
        self.setStyleSheet(
            "QMainWindow{background:%s;}"
            "QLabel{color:%s;}"
            "QWidget{font-family:'Microsoft YaHei UI','Microsoft YaHei',sans-serif;}"
            "QStatusBar{background:%s;color:%s;border-top:1px solid %s;padding-left:10px;}"
            "QToolTip{background:%s;color:%s;border:1px solid %s;padding:5px 7px;}"
            % (C_BG, C_TEXT, C_PANEL, C_DIM, C_LINE, C_PANEL2, C_TEXT, C_LINE))

        root = QWidget()
        self.setCentralWidget(root)
        self.outer = QVBoxLayout(root)
        self.outer.setContentsMargins(0, 0, 0, 0)
        self.outer.setSpacing(0)

        bar = QFrame()
        bar.setFixedHeight(58)
        bar.setStyleSheet("QFrame{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 %s,stop:1 #111722);"
                          "border-bottom:1px solid %s;}" % (C_PANEL, C_LINE))
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(18, 0, 18, 0)
        bl.setSpacing(12)
        self.btn_back = QPushButton("←  返回大厅")
        self.btn_back.setCursor(Qt.PointingHandCursor)
        self.btn_back.setFixedHeight(34)
        self.btn_back.setStyleSheet(
            "QPushButton{background:%s;color:%s;border:1px solid %s;"
            "border-radius:10px;padding:4px 14px;font-size:12.5px;font-weight:700;}"
            "QPushButton:hover{color:%s;border-color:%s;background:%s;}"
            % (C_PANEL2, C_DIM, C_LINE, C_TEXT, self.accent, rgba(self.accent, .14)))
        self.btn_back.setToolTip("返回游戏大厅（Esc）")
        self.btn_back.clicked.connect(self.close)
        bl.addWidget(self.btn_back)
        t = QLabel("%s  %s" % (self.game_emoji, self.game_name))
        t.setStyleSheet(
            "color:%s;background:%s;border:1px solid %s;border-radius:11px;"
            "padding:6px 13px;font-size:15px;font-weight:800;" %
            (C_TEXT, rgba(self.accent, .10), rgba(self.accent, .34)))
        bl.addWidget(t)
        bl.addStretch(1)
        self.bar_right = QHBoxLayout()
        self.bar_right.setSpacing(8)
        bl.addLayout(self.bar_right)
        self.outer.addWidget(bar)
        self._accent_rule = QFrame()
        self._accent_rule.setFixedHeight(2)
        self._accent_rule.setStyleSheet("background:%s;" % self.accent)
        self.outer.addWidget(self._accent_rule)

        self.body = QVBoxLayout()
        self.body.setContentsMargins(20, 18, 20, 18)
        self.body.setSpacing(16)
        self.outer.addLayout(self.body, 1)

    def closeEvent(self, ev):
        try:
            self.windowClosed.emit()
        except Exception:
            pass
        super().closeEvent(ev)


def flash_status(win, msg, ms=2600):
    """统一的底部状态提示"""
    try:
        win.statusBar().showMessage(msg, ms)
    except Exception:
        pass


class WorkerKeeper(object):
    """持有后台 QThread 引用，避免线程运行中被回收；关闭窗口时统一等待结束"""

    def __init__(self):
        self._ws = []

    def add(self, w):
        self._ws = [x for x in self._ws if x.isRunning()]
        self._ws.append(w)

    def busy(self):
        return any(x.isRunning() for x in self._ws)

    def stop_all(self, timeout_ms=12000):
        for w in self._ws:
            if w.isRunning():
                sig = getattr(w, "done", None)
                if sig is not None:
                    try:
                        sig.disconnect()
                    except Exception:
                        pass
                w.wait(timeout_ms)
        self._ws = []
