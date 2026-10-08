# -*- coding: utf-8 -*-
"""
摸鱼小游戏 · 游戏大厅

一个轻量、离线优先的游戏启动页：卡片展示每款小游戏，关闭游戏后自动回到这里并刷新本地战绩。
"""
import importlib
import os
import sys

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (QColor, QPainter, QPen, QBrush, QRadialGradient,
                           QPixmap)
from PySide6.QtWidgets import (
    QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QMainWindow,
    QPushButton, QVBoxLayout, QWidget,
)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from shared.common import (  # noqa: E402
    C_ACCENT, C_ACCENT2, C_BG, C_DIM, C_FAINT, C_GOLD, C_LINE, C_LINE2,
    C_OK, C_PANEL, C_PANEL2, C_TEXT, app_icon, asset_path, load_game_json,
    load_save, rgba,
)

APP_TITLE = "摸鱼小游戏"


def logo_pixmap(size):
    """加载 assets/logo.png 并缩放到逻辑尺寸 size（按屏幕像素比放大，保证高分屏清晰）"""
    path = asset_path("logo.png")
    if not path:
        return QPixmap()
    pm = QPixmap(path)
    if pm.isNull():
        return pm
    app = QApplication.instance()
    dpr = app.devicePixelRatio() if app else 1.0
    pm = pm.scaled(int(round(size * dpr)), int(round(size * dpr)),
                   Qt.KeepAspectRatio, Qt.SmoothTransformation)
    pm.setDevicePixelRatio(dpr)
    return pm

# key -> (模块名, 类名, emoji, 名称, 说明, 主题色, 战绩函数)
GAMES = [
    ("sudoku", "sudoku.sudoku_app", "SudokuWindow", "🔢", "数独 100 关",
     "由易到难的自适应题库，支持笔记、提示、撤销与自动存档。",
     "#38bdf8", "_stat_sudoku"),
    ("klotski", "klotski.klotski_app", "KlotskiWindow", "🧩", "华容道 · 经典布局",
     "拖动曹操走出出口，30 个关卡按最少步数递增，并带 BFS 最优解提示。",
     "#f0b23c", "_stat_klotski"),
    ("number", "numberklotski.number_app", "NumberPuzzleWindow", "🧮", "数字华容道",
     "3×3 到 6×6 数字滑块，整排移动，归位方块会变成清爽的绿色。",
     "#a78bfa", "_stat_number"),
    ("xiangqi", "xiangqi.xiangqi_app", "XiangqiWindow", "♟", "中国象棋",
     "完整规则的人机对战，也可以和同一局域网内的朋友来一盘。",
     "#e5484d", "_stat_xiangqi"),
    ("gomoku", "gomoku.gomoku_app", "GomokuWindow", "⚫", "五子棋",
     "15×15 棋盘，三档 AI、落子编号、悔棋与战绩统计一应俱全。",
     "#22c55e", "_stat_gomoku"),
    ("point24", "point24.point24_app", "Point24Window", "🃏", "24 点",
     "四个数字各用一次凑出 24，连续通关会自动升档挑战更难题目。",
     "#f472b6", "_stat_point24"),
]


# ------------------------------------------------------------------ 战绩

def _level_total(name, folder, fallback):
    lv = load_game_json(name, folder).get("levels") or []
    return len(lv) or fallback


def _stat_sudoku():
    d = load_save("sudoku_save.json")
    lv = d.get("levels") or {}
    done = sum(1 for v in lv.values() if v.get("wins"))
    plays = sum((v.get("plays") or 0) for v in lv.values())
    return "已通关 %d / 100 关 · 挑战 %d 次" % (done, plays)


def _stat_klotski():
    d = load_save("klotski_save.json")
    lv = d.get("levels") or {}
    done = sum(1 for v in lv.values() if v.get("cleared"))
    best = [v.get("bestSteps") for v in lv.values() if v.get("bestSteps")]
    extra = " · 最少 %d 步" % min(best) if best else ""
    return "已通关 %d / %d 关%s" % (done, _level_total("levels.json", "klotski", 30), extra)


def _stat_number():
    d = load_save("number_save.json")
    lv = d.get("levels") or {}
    done = sum(1 for v in lv.values() if v.get("cleared"))
    return "已通关 %d / %d 关" % (done, _level_total("levels.json", "numberklotski", 15))


def _stat_xiangqi():
    d = load_save("xiangqi_save.json")
    s = d.get("stats") or {}
    total = sum(int(s.get(x, 0) or 0) for x in ("win", "lose", "draw"))
    if not total:
        return "还没有对局记录"
    return "人机 %d 胜 / %d 负 / %d 和" % (s.get("win", 0), s.get("lose", 0), s.get("draw", 0))


def _stat_gomoku():
    d = load_save("gomoku_save.json")
    s = d.get("stats") or {}
    total = sum(int(s.get(x, 0) or 0) for x in ("win", "lose", "draw"))
    if not total:
        return "还没有对局记录"
    rate = s.get("win", 0) * 100.0 / total
    return "人机 %d 胜 / %d 负 / %d 平 · 胜率 %.0f%%" % (
        s.get("win", 0), s.get("lose", 0), s.get("draw", 0), rate)


def _stat_point24():
    st = load_save("point24_save.json").get("stats") or {}
    solved = int(st.get("solved", 0) or 0)
    if not solved:
        return "还没有通关记录"
    fast = st.get("fastest")
    extra = " · 最快 %.1f 秒" % fast if fast else ""
    return "已通关 %d 题 · 最高连击 %d%s" % (solved, st.get("bestStreak", 0) or 0, extra)


STAT_FUNCS = {
    "_stat_sudoku": _stat_sudoku,
    "_stat_klotski": _stat_klotski,
    "_stat_number": _stat_number,
    "_stat_xiangqi": _stat_xiangqi,
    "_stat_gomoku": _stat_gomoku,
    "_stat_point24": _stat_point24,
}


class Backdrop(QWidget):
    """大厅背景：低对比度渐变与网格，让页面更有层次但不干扰内容。"""

    def paintEvent(self, event):  # noqa: N802
        del event
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(C_BG))

        glow = QRadialGradient(self.width() * 0.88, self.height() * 0.03, self.width() * 0.72)
        glow.setColorAt(0.0, QColor(rgba(C_ACCENT2, 0.10)))
        glow.setColorAt(0.58, QColor(rgba(C_ACCENT, 0.025)))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(self.rect(), QBrush(glow))

        left_glow = QRadialGradient(self.width() * 0.04, self.height() * 0.84, self.width() * 0.48)
        left_glow.setColorAt(0.0, QColor(rgba(C_GOLD, 0.045)))
        left_glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(self.rect(), QBrush(left_glow))

        p.setPen(QPen(QColor(rgba(C_LINE2, 0.20)), 1))
        step = 48
        for x in range(0, self.width(), step):
            p.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), step):
            p.drawLine(0, y, self.width(), y)


class GameCard(QFrame):
    clicked = Signal(str)

    def __init__(self, key, index, emoji, name, desc, accent, stat_text, parent=None):
        super().__init__(parent)
        self.key = key
        self.accent = accent
        self._hover = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(172)
        self.setMinimumWidth(330)
        self.setAttribute(Qt.WA_Hover, True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 17, 18, 16)
        lay.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(12)
        self.lb_icon = QLabel(emoji)
        self.lb_icon.setAlignment(Qt.AlignCenter)
        self.lb_icon.setFixedSize(48, 48)
        self.lb_icon.setStyleSheet(
            "background:%s;border:1px solid %s;border-radius:15px;font-size:26px;" %
            (rgba(accent, 0.14), rgba(accent, 0.34)))
        top.addWidget(self.lb_icon)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        self.lb_index = QLabel("0%d  /  GAME" % (index + 1))
        self.lb_index.setStyleSheet(
            "color:%s;font-size:10px;font-weight:700;letter-spacing:1px;" % rgba(accent, 0.92))
        self.lb_name = QLabel(name)
        self.lb_name.setStyleSheet("color:%s;font-size:18px;font-weight:800;" % C_TEXT)
        title_box.addWidget(self.lb_index)
        title_box.addWidget(self.lb_name)
        top.addLayout(title_box, 1)

        self.btn_go = QPushButton("开始  ›")
        self.btn_go.setCursor(Qt.PointingHandCursor)
        self.btn_go.setFixedHeight(30)
        self.btn_go.setStyleSheet(
            "QPushButton{background:%s;color:%s;border:1px solid %s;border-radius:9px;"
            "padding:0 10px;font-size:12px;font-weight:700;}"
            "QPushButton:hover{background:%s;color:#fff;border-color:%s;}" %
            (rgba(accent, 0.10), accent, rgba(accent, 0.38), accent, accent))
        self.btn_go.clicked.connect(lambda: self.clicked.emit(self.key))
        top.addWidget(self.btn_go, 0, Qt.AlignVCenter)
        lay.addLayout(top)

        d = QLabel(desc)
        d.setWordWrap(True)
        d.setMinimumHeight(40)
        d.setStyleSheet("color:%s;font-size:12px;line-height:1.35;" % C_DIM)
        lay.addWidget(d)
        lay.addStretch(1)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background:%s;" % C_LINE)
        lay.addWidget(divider)

        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        self.lb_dot = QLabel("●")
        self.lb_dot.setStyleSheet("color:%s;font-size:10px;" % accent)
        self.lb_stat = QLabel(stat_text)
        self.lb_stat.setStyleSheet("color:%s;font-size:11.5px;font-weight:600;" % C_DIM)
        bottom.addWidget(self.lb_dot)
        bottom.addWidget(self.lb_stat, 1)
        self.lb_arrow = QLabel("↗")
        self.lb_arrow.setStyleSheet("color:%s;font-size:16px;font-weight:700;" % C_FAINT)
        bottom.addWidget(self.lb_arrow)
        lay.addLayout(bottom)
        self._apply_style()

    def _apply_style(self):
        if self._hover:
            bg = "qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 %s,stop:1 %s)" % (C_PANEL2, C_PANEL)
            border = rgba(self.accent, 0.62)
        else:
            bg = "qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 %s,stop:1 #111721)" % C_PANEL
            border = C_LINE
        self.setStyleSheet(
            "GameCard{background:%s;border:1px solid %s;border-radius:18px;}" % (bg, border))
        self.lb_arrow.setStyleSheet(
            "color:%s;font-size:16px;font-weight:700;" % (self.accent if self._hover else C_FAINT))

    def enterEvent(self, event):  # noqa: N802
        self._hover = True
        self._apply_style()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        self._hover = False
        self._apply_style()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit(self.key)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(self.accent)))
        p.drawRoundedRect(18, 0, self.width() - 36, 3, 1.5, 1.5)


class InfoPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(268)
        self.setStyleSheet(
            "InfoPanel{background:%s;border:1px solid %s;border-radius:20px;}" % (C_PANEL, C_LINE))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 21, 20, 20)
        lay.setSpacing(13)

        eyebrow = QLabel("YOUR PLAYGROUND")
        eyebrow.setStyleSheet("color:%s;font-size:10px;font-weight:800;letter-spacing:1.5px;" % C_ACCENT2)
        lay.addWidget(eyebrow)
        title = QLabel("今日状态")
        title.setStyleSheet("font-size:22px;font-weight:800;color:%s;" % C_TEXT)
        lay.addWidget(title)

        self.lb_total = QLabel("统计中…")
        self.lb_total.setStyleSheet("color:%s;font-size:13px;font-weight:600;" % C_DIM)
        lay.addWidget(self.lb_total)

        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background:%s;" % C_LINE)
        lay.addWidget(line)

        section = QLabel("快捷入口")
        section.setStyleSheet("color:%s;font-size:11px;font-weight:700;" % C_FAINT)
        lay.addWidget(section)
        shortcuts = [
            ("1 - 6", "快速启动游戏"),
            ("Esc", "返回大厅"),
            ("本地", "无需联网也能玩"),
        ]
        for key, text in shortcuts:
            row = QHBoxLayout()
            row.setSpacing(9)
            pill = QLabel(key)
            pill.setAlignment(Qt.AlignCenter)
            pill.setFixedWidth(50)
            pill.setStyleSheet(
                "color:%s;background:%s;border:1px solid %s;border-radius:7px;"
                "padding:4px 2px;font-size:10px;font-weight:800;" %
                (C_ACCENT2, rgba(C_ACCENT2, 0.10), rgba(C_ACCENT2, 0.25)))
            lb = QLabel(text)
            lb.setStyleSheet("color:%s;font-size:12px;" % C_DIM)
            row.addWidget(pill)
            row.addWidget(lb, 1)
            lay.addLayout(row)

        lay.addStretch(1)
        note = QFrame()
        note.setStyleSheet(
            "QFrame{background:%s;border:1px solid %s;border-radius:13px;}" %
            (rgba(C_GOLD, 0.08), rgba(C_GOLD, 0.23)))
        note_lay = QVBoxLayout(note)
        note_lay.setContentsMargins(12, 11, 12, 11)
        note_lay.setSpacing(5)
        note_title = QLabel("✦  摸鱼小贴士")
        note_title.setStyleSheet("color:%s;font-size:12px;font-weight:700;" % C_GOLD)
        note_text = QLabel("想放松几分钟？先从数独或 24 点开始吧。所有进度都会保存在本地。")
        note_text.setWordWrap(True)
        note_text.setStyleSheet("color:%s;font-size:11px;line-height:1.35;" % C_DIM)
        note_lay.addWidget(note_title)
        note_lay.addWidget(note_text)
        lay.addWidget(note)

        self.lb_where = QLabel("")
        self.lb_where.setWordWrap(True)
        self.lb_where.setStyleSheet("color:%s;font-size:10px;" % C_FAINT)
        lay.addWidget(self.lb_where)


class Launcher(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(app_icon())
        self.resize(1240, 820)
        self.setMinimumSize(1080, 760)
        self.setStyleSheet(
            "QMainWindow{background:%s;}"
            "QWidget{font-family:'Microsoft YaHei UI','Microsoft YaHei',sans-serif;}"
            "QLabel{color:%s;}"
            "QToolTip{background:%s;color:%s;border:1px solid %s;padding:5px 7px;}" %
            (C_BG, C_TEXT, C_PANEL2, C_TEXT, C_LINE2))
        self.game_win = None
        self.cards = []
        self._build_ui()
        self._refresh_stats()

    def _build_ui(self):
        central = Backdrop()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(30, 22, 30, 18)
        root.setSpacing(15)

        # 顶部品牌区
        header = QHBoxLayout()
        header.setSpacing(14)
        logo = QLabel()
        logo.setAlignment(Qt.AlignCenter)
        logo.setFixedSize(56, 56)
        pm = logo_pixmap(56)
        if pm.isNull():                       # 资源缺失时退回原来的文字标
            logo.setText("MF")
            logo.setStyleSheet(
                "color:#07111e;background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                "stop:0 #5ee7ff,stop:1 #4c8dff);border-radius:15px;"
                "font-size:17px;font-weight:900;letter-spacing:1px;")
        else:
            logo.setPixmap(pm)
            logo.setStyleSheet("background:transparent;")
            logo.setToolTip("摸鱼小游戏 · Mofish")
        header.addWidget(logo)

        brand = QVBoxLayout()
        brand.setSpacing(2)
        kicker = QLabel("OFFLINE GAME COLLECTION")
        kicker.setStyleSheet("color:%s;font-size:10px;font-weight:800;letter-spacing:2px;" % C_ACCENT2)
        headline = QLabel("摸鱼一下，轻松玩一局")
        headline.setStyleSheet("font-size:28px;font-weight:900;letter-spacing:.5px;color:%s;" % C_TEXT)
        brand.addWidget(kicker)
        brand.addWidget(headline)
        header.addLayout(brand)
        header.addStretch(1)

        chip = QLabel("●  离线可玩")
        chip.setAlignment(Qt.AlignCenter)
        chip.setFixedHeight(30)
        chip.setStyleSheet(
            "color:%s;background:%s;border:1px solid %s;border-radius:10px;"
            "padding:0 11px;font-size:11px;font-weight:700;" %
            (C_OK, rgba(C_OK, 0.10), rgba(C_OK, 0.30)))
        header.addWidget(chip, 0, Qt.AlignVCenter)
        root.addLayout(header)

        intro = QHBoxLayout()
        intro.setSpacing(8)
        intro_text = QLabel("六款轻量小游戏，打开即玩。挑一个喜欢的，给自己几分钟专注的空档。")
        intro_text.setStyleSheet("color:%s;font-size:13px;" % C_DIM)
        intro.addWidget(intro_text)
        intro.addStretch(1)
        hint = QLabel("点击卡片开始  ·  支持键盘 1 - 6")
        hint.setStyleSheet("color:%s;font-size:11px;" % C_FAINT)
        intro.addWidget(hint)
        root.addLayout(intro)

        content = QHBoxLayout()
        content.setSpacing(18)
        library = QVBoxLayout()
        library.setSpacing(12)
        library_title = QHBoxLayout()
        library_title.setSpacing(10)
        title = QLabel("游戏库")
        title.setStyleSheet("font-size:17px;font-weight:800;color:%s;" % C_TEXT)
        count = QLabel("%d GAMES" % len(GAMES))
        count.setStyleSheet("color:%s;font-size:10px;font-weight:800;letter-spacing:1.2px;" % C_FAINT)
        library_title.addWidget(title)
        library_title.addWidget(count)
        library_title.addStretch(1)
        library.addLayout(library_title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        for idx, (key, _mod, _cls, emoji, name, desc, accent, statfn) in enumerate(GAMES):
            card = GameCard(key, idx, emoji, name, desc, accent, "统计中…")
            card.clicked.connect(self.open_game)
            self.cards.append((card, statfn))
            grid.addWidget(card, idx // 2, idx % 2)
        library.addLayout(grid, 1)
        content.addLayout(library, 1)
        content.addWidget(InfoPanel(), 0)
        self.info_panel = content.itemAt(1).widget()
        root.addLayout(content, 1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        footer_text = QLabel("✦  本地存档会在退出游戏时自动更新")
        footer_text.setStyleSheet("color:%s;font-size:11px;" % C_FAINT)
        footer.addWidget(footer_text)
        footer.addStretch(1)
        version = QLabel("Mofish  /  Play a little, feel a lot")
        version.setStyleSheet("color:%s;font-size:10px;letter-spacing:.4px;" % C_FAINT)
        footer.addWidget(version)
        root.addLayout(footer)

    def _refresh_stats(self):
        for card, statfn in self.cards:
            try:
                card.lb_stat.setText(STAT_FUNCS[statfn]())
            except Exception:
                card.lb_stat.setText("暂无记录")

        total = 0
        sudoku = load_save("sudoku_save.json").get("levels") or {}
        total += sum((v.get("plays") or 0) for v in sudoku.values())
        for name in ("klotski_save.json", "number_save.json"):
            levels = load_save(name).get("levels") or {}
            total += sum((v.get("clears") or 0) for v in levels.values())
        for name in ("xiangqi_save.json", "gomoku_save.json"):
            stats = load_save(name).get("stats") or {}
            total += sum(int(stats.get(x, 0) or 0) for x in ("win", "lose", "draw"))
        total += int((load_save("point24_save.json").get("stats") or {}).get("solved", 0) or 0)

        panel = getattr(self, "info_panel", None)
        if panel is not None:
            panel.lb_total.setText("累计游玩 %d 局" % total if total else "还没有开始游戏，等你来挑战")
            try:
                from shared.common import data_dir
                panel.lb_where.setText("存档目录：%s" % data_dir())
            except Exception:
                pass

    def open_game(self, key):
        info = next((g for g in GAMES if g[0] == key), None)
        if not info:
            return
        _, mod_name, cls_name = info[0], info[1], info[2]
        try:
            mod = importlib.import_module(mod_name)
            win = getattr(mod, cls_name)()
        except Exception as exc:  # pragma: no cover
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "启动失败", "无法打开该游戏：\n%s" % exc)
            return
        if self.game_win is not None:
            try:
                self.game_win.close()
            except Exception:
                pass
        self.game_win = win
        win.windowClosed.connect(self._on_game_closed)
        self.hide()
        win.show()
        win.raise_()
        win.activateWindow()

    def _on_game_closed(self):
        self.game_win = None
        self._refresh_stats()
        self.show()
        self.raise_()
        self.activateWindow()

    def keyPressEvent(self, event):  # noqa: N802
        if Qt.Key_1 <= event.key() <= Qt.Key_9:
            idx = event.key() - Qt.Key_1
            if idx < len(GAMES):
                self.open_game(GAMES[idx][0])
                return
        super().keyPressEvent(event)

    def closeEvent(self, event):  # noqa: N802
        if self.game_win is not None:
            try:
                self.game_win.close()
            except Exception:
                pass
        super().closeEvent(event)
        QApplication.quit()


def launch():
    window = Launcher()
    window.show()
    return window


if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)
    window = Launcher()
    window.show()
    sys.exit(app.exec())
