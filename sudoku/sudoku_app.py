# -*- coding: utf-8 -*-
"""
数独 · 100 关 —— 桌面版（PySide6 / Qt）

原生窗口应用：自绘棋盘、原生对话框、本地存档，不依赖浏览器。
关卡难度逐步提升：第 1 关送分，第 2 关正常，第 100 关地狱。
"""
import json
import os
import sys
import time
from datetime import datetime

from PySide6.QtCore import (Qt, QTimer, QRectF, QPointF, QThread, Signal,
                            QStandardPaths, QSize, QEvent)
from PySide6.QtGui import (QPainter, QColor, QFont, QPen, QBrush, QFontMetrics,
                           QKeySequence, QShortcut, QIcon, QPixmap)
from PySide6.QtWidgets import (QApplication, QWidget, QMainWindow, QLabel,
                               QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout,
                               QFrame, QDialog, QScrollArea, QTableWidget,
                               QTableWidgetItem, QHeaderView, QAbstractButton,
                               QSizePolicy, QMessageBox, QStackedLayout)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from sudoku import engine as E  # noqa: E402
from shared.common import (C_BG, C_PANEL, C_PANEL2, C_LINE, C_LINE2, C_TEXT, C_DIM,
                    C_FAINT, C_ACCENT, C_ACCENT2, C_GIVEN, C_USER, C_HINT,
                    C_DANGER, C_OK, rgba, mk_button, ToolButton, card, fmt_time,
                    resource_dir, data_dir, BaseStore, GameWindow, find_game_data)  # noqa: E402

APP_NAME = "数独 100 关"
MAX_LEVEL = 100
HINTS_PER_LEVEL = 3

_fmt = fmt_time


# ------------------------------------------------------------------ 存储
class Store(BaseStore):
    """历史记录 + 当前进度 + 题池游标"""

    DEFAULTS = {"meta": {"currentLevel": 1}, "levels": {}, "cursor": {}, "state": None}

    def __init__(self):
        super().__init__("sudoku_save.json", dict(self.DEFAULTS))
        self.data.setdefault("meta", {"currentLevel": 1})
        self.data.setdefault("levels", {})
        self.data.setdefault("cursor", {})
        self.data.setdefault("state", None)

    def level(self, lv):
        return self.data["levels"].get(str(lv))

    def level_rec(self, lv):
        return self.data["levels"].setdefault(str(lv), {
            "plays": 0, "wins": 0, "best": None, "last": None, "hints": 0,
            "tier": None, "givens": None, "rating": None, "refDiff": None})


# ------------------------------------------------------------------ 题池
class PuzzlePool(object):
    """启动时载入预算好的题库；用完后由后台线程补题"""

    def __init__(self, store):
        self.store = store
        self.levels = {}
        p = find_game_data("puzzles.json", "sudoku") or \
            os.path.join(resource_dir(), "puzzles.json")
        try:
            with open(p, "r", encoding="utf-8") as f:
                self.levels = json.load(f).get("levels", {})
        except Exception:
            self.levels = {}
        self.used = {}          # level -> set(已用题面)

    def has(self, level):
        return str(level) in self.levels and len(self.levels[str(level)].get("puzzles", [])) > 0

    def meta(self, level):
        return self.levels.get(str(level))

    def next(self, level, avoid=None):
        """取一道没用过的题；返回 (puzzle_dict, level_meta) 或 (None, meta)"""
        lm = self.levels.get(str(level))
        if not lm:
            return None, None
        puzzles = lm.get("puzzles", [])
        if not puzzles:
            return None, lm
        used = self.used.setdefault(level, set())
        if avoid:
            used.add(avoid)
        # 优先用历史游标，让每次重开尽量换题
        cur = int(self.store.data["cursor"].get(str(level), 0))
        n = len(puzzles)
        for k in range(n):
            idx = (cur + k) % n
            if puzzles[idx]["p"] not in used:
                self.store.data["cursor"][str(level)] = (idx + 1) % n
                used.add(puzzles[idx]["p"])
                return puzzles[idx], lm
        # 全用过了 → 从游标处循环取（并让上游去后台生成新题）
        idx = cur % n
        self.store.data["cursor"][str(level)] = (idx + 1) % n
        return puzzles[idx], lm


class GenWorker(QThread):
    done = Signal(object, object)

    def __init__(self, level, ref, avoid):
        super().__init__()
        self.level, self.ref, self.avoid = level, ref, avoid

    def run(self):
        try:
            g = None
            for _ in range(10):
                g = E.generate(self.level, 30, self.ref)
                if not self.avoid or E.to_string(g["puzzle"]) != self.avoid:
                    break
            self.done.emit(g, None)
        except Exception as exc:                      # pragma: no cover
            self.done.emit(None, str(exc))


# ------------------------------------------------------------------ 自绘棋盘
class SudokuBoard(QWidget):
    cellClicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.puzzle = [0] * 81
        self.grid = [0] * 81
        self.solution = [0] * 81
        self.notes = [0] * 81
        self.hinted = [0] * 81
        self.sel = -1
        self.hover = -1
        self.paused = False
        self.check_bad = False
        self.ready = False
        self.setMinimumSize(430, 430)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)

    # --- 几何
    def _geom(self):
        w, h = self.width(), self.height()
        size = min(w, h) - 2
        ox = (w - size) / 2.0
        oy = (h - size) / 2.0
        return ox, oy, size / 9.0

    def _cell_at(self, pos):
        ox, oy, c = self._geom()
        col = int((pos.x() - ox) // c)
        row = int((pos.y() - oy) // c)
        if 0 <= row < 9 and 0 <= col < 9:
            return row * 9 + col
        return -1

    def mousePressEvent(self, ev):
        i = self._cell_at(ev.position())
        if i >= 0:
            self.cellClicked.emit(i)

    def mouseMoveEvent(self, ev):
        i = self._cell_at(ev.position())
        if i != self.hover:
            self.hover = i
            self.update()

    def leaveEvent(self, ev):
        if self.hover != -1:
            self.hover = -1
            self.update()

    # --- 绘制
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        ox, oy, c = self._geom()
        size = c * 9

        p.fillRect(self.rect(), QColor(C_BG))

        if not self.ready:
            p.setPen(QColor(C_FAINT))
            f = QFont(); f.setPointSize(12); p.setFont(f)
            p.drawText(self.rect(), Qt.AlignCenter, "正在按关卡难度出题…")
            return

        conflicts = E.find_conflicts(self.grid)
        sel = self.sel
        sel_val = self.grid[sel] if 0 <= sel < 81 else 0
        sr, sc = (sel // 9, sel % 9) if sel >= 0 else (-1, -1)
        sb = ((sr // 3) * 3 + (sc // 3)) if sel >= 0 else -1

        # --- 单元格底色
        for i in range(81):
            r, cc = i // 9, i % 9
            x = ox + cc * c
            y = oy + r * c
            rect = QRectF(x + 0.6, y + 0.6, c - 1.2, c - 1.2)
            bg = QColor(C_BG)
            if sel >= 0:
                same_box = ((r // 3) * 3 + (cc // 3)) == sb
                if i == sel:
                    bg = QColor(C_ACCENT); bg.setAlpha(88)
                elif r == sr or cc == sc or same_box:
                    bg = QColor(C_ACCENT); bg.setAlpha(22)
                if self.grid[i] and sel_val and self.grid[i] == sel_val and i != sel:
                    bg = QColor(C_ACCENT); bg.setAlpha(48)
            if i == self.hover and i != sel:
                bg = QColor(C_ACCENT); bg.setAlpha(30)
            bad = (conflicts[i] and not self.puzzle[i]) or \
                  (self.check_bad and self.grid[i] and self.grid[i] != self.solution[i])
            if bad:
                bg = QColor(C_DANGER); bg.setAlpha(60)
            p.fillRect(rect, bg)

        # --- 数字与小字备注
        vfont = QFont(); vfont.setPointSizeF(max(11.0, c * 0.50)); vfont.setBold(True)
        nfont = QFont(); nfont.setPointSizeF(max(6.0, c * 0.215))
        p.setFont(vfont)
        for i in range(81):
            r, cc = i // 9, i % 9
            x, y = ox + cc * c, oy + r * c
            v = self.grid[i]
            if v:
                if self.paused:
                    continue
                if self.puzzle[i]:
                    col = QColor(C_GIVEN)
                elif self.hinted[i]:
                    col = QColor(C_HINT)
                elif conflicts[i] or (self.check_bad and v != self.solution[i]):
                    col = QColor(C_DANGER)
                else:
                    col = QColor(C_USER)
                p.setPen(col)
                p.drawText(QRectF(x, y, c, c), Qt.AlignCenter, str(v))
            elif self.notes[i] and not self.paused:
                p.setFont(nfont)
                p.setPen(QColor(C_DIM))
                for n in range(1, 10):
                    if self.notes[i] & (1 << n):
                        nr, nc = (n - 1) // 3, (n - 1) % 3
                        p.drawText(QRectF(x + nc * c / 3.0, y + nr * c / 3.0, c / 3.0, c / 3.0),
                                   Qt.AlignCenter, str(n))
                p.setFont(vfont)

        # --- 网格线
        thin = QPen(QColor(C_LINE)); thin.setWidthF(1.0)
        thick = QPen(QColor(C_LINE2)); thick.setWidthF(2.2)
        for k in range(10):
            pen = thick if k % 3 == 0 else thin
            p.setPen(pen)
            x = ox + k * c
            p.drawLine(QPointF(x, oy), QPointF(x, oy + size))
            y = oy + k * c
            p.drawLine(QPointF(ox, y), QPointF(ox + size, y))

        # --- 暂停遮罩
        if self.paused:
            p.fillRect(QRectF(ox, oy, size, size), QColor(11, 14, 20, 236))
            p.setPen(QColor(C_TEXT))
            f = QFont(); f.setPointSize(15); f.setBold(True); p.setFont(f)
            p.drawText(QRectF(ox, oy, size, size / 2), Qt.AlignCenter, "已暂停")
            p.setPen(QColor(C_DIM))
            f.setPointSize(10); f.setBold(False); p.setFont(f)
            p.drawText(QRectF(ox, oy + size / 2 - 26, size, 60), Qt.AlignCenter,
                       "计时已停止，点击「继续」回到棋盘")


# ------------------------------------------------------------------ 数字键
class NumKey(QAbstractButton):
    def __init__(self, digit, parent=None):
        super().__init__(parent)
        self.digit = digit
        self.left = 9
        self.done = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(54)
        self.setMinimumWidth(62)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_left(self, n):
        self.left = n
        self.done = (n <= 0)
        self.update()

    def sizeHint(self):
        return QSize(64, 58)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        hover = self.underMouse()
        pressed = self.isDown()
        bg = QColor("#222a37") if hover else QColor(C_PANEL2)
        if pressed:
            bg = QColor("#2a3446")
        border = QColor(C_LINE2) if hover else QColor(C_LINE)
        if self.done:
            bg.setAlpha(90)
            border.setAlpha(90)
        p.setBrush(QBrush(bg))
        p.setPen(QPen(border, 1.0))
        p.drawRoundedRect(r, 10, 10)

        f = QFont(); f.setPointSize(16); f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(C_TEXT if not self.done else C_FAINT))
        p.drawText(r.adjusted(0, -6, 0, 0), Qt.AlignCenter, str(self.digit))

        f2 = QFont(); f2.setPointSize(7.5)
        p.setFont(f2)
        p.setPen(QColor(C_OK if self.done else C_FAINT))
        p.drawText(r.adjusted(0, 0, -8, -4), Qt.AlignRight | Qt.AlignBottom, str(self.left))


# ------------------------------------------------------------------ 通用组件
# mk_button / ToolButton / card / rgba 统一由 common.py 提供


# ------------------------------------------------------------------ 选关
class LevelDialog(QDialog):
    def __init__(self, parent, store, cur_level):
        super().__init__(parent)
        self.setWindowTitle("选择关卡")
        self.setModal(True)
        self.setStyleSheet("QDialog{background:%s;} QLabel{color:%s;}" % (C_BG, C_TEXT))
        self.picked = None
        self.resize(660, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        head = QHBoxLayout()
        t = QLabel("选择关卡"); t.setStyleSheet("font-size:17px;font-weight:700;")
        head.addWidget(t)
        head.addStretch(1)
        done = sum(1 for k, v in store.data["levels"].items() if v.get("wins"))
        info = QLabel("已通关 %d / %d 关 · 当前进度第 %d 关"
                      % (done, MAX_LEVEL, store.data["meta"].get("currentLevel", 1)))
        info.setStyleSheet("color:%s;font-size:12px;" % C_DIM)
        head.addWidget(info)
        root.addLayout(head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        inner = QWidget()
        grid = QGridLayout(inner)
        grid.setSpacing(6)
        grid.setContentsMargins(0, 0, 6, 0)
        for lv in range(1, MAX_LEVEL + 1):
            rec = store.level(lv)
            tier = rec.get("tier") if rec and rec.get("tier") is not None else E.tier_of(E.target_of(lv))
            color = E.TIERS[tier]["color"]
            best = rec.get("best") if rec else None
            txt = "%d" % lv
            if best is not None:
                txt += "\n%d:%02d" % (int(best) // 60000, (int(best) // 1000) % 60)
            b = QPushButton(txt)
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumSize(56, 50)
            bold = "font-weight:700;" if (rec and rec.get("wins")) else ""
            if lv == cur_level:
                ring = "border:2px solid %s;" % C_ACCENT
            else:
                ring = "border:1px solid %s;" % rgba(color, 0.6)
            b.setStyleSheet(
                "QPushButton{background:%s;color:%s;border-radius:9px;%s%sfont-size:13px;}"
                "QPushButton:hover{background:#232b38;color:%s;}"
                % (C_PANEL2, C_TEXT if (rec and rec.get("wins")) else C_DIM,
                   ring, bold, C_TEXT))
            tip = "第 %d 关 · %s" % (lv, E.TIERS[tier]["name"])
            if best is not None:
                tip += " · 最佳 %d:%02d" % (int(best) // 60000, (int(best) // 1000) % 60)
            if rec and rec.get("wins"):
                tip += " · 已通关"
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, x=lv: self._pick(x))
            grid.addWidget(b, (lv - 1) // 10, (lv - 1) % 10)
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        row = QHBoxLayout()
        row.addStretch(1)
        close = mk_button("关闭", parent=self)
        close.clicked.connect(self.reject)
        row.addWidget(close)
        root.addLayout(row)

    def _pick(self, lv):
        self.picked = lv
        self.accept()


# ------------------------------------------------------------------ 记录
class RecordDialog(QDialog):
    def __init__(self, parent, store):
        super().__init__(parent)
        self.setWindowTitle("历史记录")
        self.setModal(True)
        self.resize(680, 580)
        self.setStyleSheet(
            "QDialog{background:%s;}"
            "QLabel{color:%s;}"
            "QTableWidget{background:%s;color:%s;border:1px solid %s;"
            "gridline-color:%s;border-radius:10px;}"
            "QHeaderView::section{background:%s;color:%s;border:none;"
            "padding:7px 4px;font-weight:600;}"
            "QTableWidget::item{padding:5px;}"
            % (C_BG, C_TEXT, C_PANEL, C_TEXT, C_LINE, C_LINE, C_PANEL, C_FAINT))

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        title = QLabel("历史记录")
        title.setStyleSheet("font-size:17px;font-weight:700;")
        root.addWidget(title)
        sub = QLabel("每关的最佳 / 最近用时与挑战次数")
        sub.setStyleSheet("color:%s;font-size:12px;" % C_DIM)
        root.addWidget(sub)

        rows, total_best, done = [], 0, 0
        for lv in range(1, MAX_LEVEL + 1):
            rec = store.level(lv)
            if not rec or (not rec.get("wins") and not rec.get("plays")):
                continue
            rows.append((lv, rec))
            if rec.get("best") is not None:
                total_best += rec["best"]
                done += 1

        summ = QHBoxLayout()
        summ.setSpacing(9)
        for val, cap in ((str(done), "已通关"),
                         (_fmt(total_best), "累计最佳用时"),
                         (_fmt(int(total_best / done)) if done else "--:--", "平均最佳用时")):
            box = QFrame()
            box.setStyleSheet("QFrame{background:%s;border:1px solid %s;border-radius:10px;}"
                              % (C_PANEL2, C_LINE))
            bl = QVBoxLayout(box)
            bl.setContentsMargins(10, 8, 10, 8)
            bl.setSpacing(1)
            v = QLabel(val); v.setStyleSheet("font-size:17px;font-weight:700;")
            v.setAlignment(Qt.AlignCenter)
            c = QLabel(cap); c.setStyleSheet("color:%s;font-size:11px;" % C_FAINT)
            c.setAlignment(Qt.AlignCenter)
            bl.addWidget(v); bl.addWidget(c)
            summ.addWidget(box, 1)
        root.addLayout(summ)

        if not rows:
            tip = QLabel("还没有记录，先玩一关吧")
            tip.setAlignment(Qt.AlignCenter)
            tip.setStyleSheet("color:%s;font-size:13px;padding:40px 0;" % C_FAINT)
            root.addWidget(tip, 1)
        else:
            tb = QTableWidget(len(rows), 7)
            tb.setHorizontalHeaderLabels(["关卡", "难度", "最佳用时", "最近用时",
                                          "完成", "挑战", "提示"])
            tb.verticalHeader().setVisible(False)
            tb.setEditTriggers(QTableWidget.NoEditTriggers)
            tb.setSelectionMode(QTableWidget.NoSelection)
            tb.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            for r, (lv, rec) in enumerate(rows):
                tier = rec.get("tier") if rec.get("tier") is not None else 0
                cells = [
                    "第 %d 关" % lv,
                    E.TIERS[tier]["name"],
                    _fmt(rec.get("best")),
                    _fmt(rec.get("last")),
                    "%d 次" % (rec.get("wins") or 0),
                    "%d 次" % (rec.get("plays") or 0),
                    "%d 次" % (rec.get("hints") or 0),
                ]
                for c, txt in enumerate(cells):
                    it = QTableWidgetItem(txt)
                    if c == 1:
                        it.setForeground(QColor(E.TIERS[tier]["color"]))
                    tb.setItem(r, c, it)
            root.addWidget(tb, 1)

        row = QHBoxLayout(); row.addStretch(1)
        close = mk_button("关闭", parent=self); close.clicked.connect(self.reject)
        row.addWidget(close)
        root.addLayout(row)


# ------------------------------------------------------------------ 通关
class WinDialog(QDialog):
    def __init__(self, parent, level, elapsed, is_best, best, hints, diff, has_next):
        super().__init__(parent)
        self.setWindowTitle("通关")
        self.setModal(True)
        self.setStyleSheet("QDialog{background:%s;} QLabel{color:%s;}" % (C_PANEL, C_TEXT))
        self.choice = "next"
        self.resize(430, 300)

        root = QVBoxLayout(self)
        root.setContentsMargins(25, 22, 25, 20)
        root.setSpacing(8)

        t = QLabel("第 %d 关 · 完成" % level)
        t.setStyleSheet("font-size:17px;font-weight:700;")
        t.setAlignment(Qt.AlignCenter)
        root.addWidget(t)

        v = QLabel(_fmt(elapsed))
        v.setStyleSheet("font-size:38px;font-weight:700;color:%s;" % C_ACCENT2)
        v.setAlignment(Qt.AlignCenter)
        root.addWidget(v)

        parts = []
        parts.append("新纪录" if is_best else ("本关最佳 " + _fmt(best)))
        parts.append("提示用了 %d 次" % hints)
        if diff:
            parts.append("难度 %s（%d 提示）" % (diff["tier_name"], diff["givens"]))
        note = QLabel("  ·  ".join(parts))
        note.setStyleSheet("color:%s;font-size:12.5px;" % C_DIM)
        note.setAlignment(Qt.AlignCenter)
        root.addWidget(note)

        root.addSpacing(8)
        row1 = QHBoxLayout(); row1.setSpacing(9)
        nxt = mk_button(("进入第 %d 关" % (level + 1)) if has_next else "全部 100 关完成 🎉",
                        "primary", self)
        nxt.setEnabled(has_next)
        nxt.clicked.connect(lambda: self._go("next"))
        row1.addWidget(nxt, 2)
        root.addLayout(row1)

        row2 = QHBoxLayout(); row2.setSpacing(9)
        rep = mk_button("同难度再来一局", parent=self); rep.clicked.connect(lambda: self._go("replay"))
        sel = mk_button("选关", parent=self); sel.clicked.connect(lambda: self._go("levels"))
        row2.addWidget(rep); row2.addWidget(sel)
        root.addLayout(row2)

    def _go(self, c):
        self.choice = c
        self.accept()


def _fmt(ms):  # 兼容旧调用，实现见 common.fmt_time
    return fmt_time(ms)


# ------------------------------------------------------------------ 主窗口
class SudokuWindow(GameWindow):
    game_key = "sudoku"
    game_name = "数独 100 关"
    game_emoji = "🔢"

    def __init__(self):
        super().__init__()
        self.resize(1060, 900)
        self.setMinimumSize(820, 640)

        self.store = Store()
        self.pool = PuzzlePool(self.store)
        self.worker = None

        self.level = 1
        self.puzzle = [0] * 81
        self.solution = [0] * 81
        self.grid = [0] * 81
        self.notes = [0] * 81
        self.hinted = [0] * 81
        self.sel = -1
        self.elapsed = 0
        self.running = False
        self.finished = False
        self.hints_left = HINTS_PER_LEVEL
        self.hint_used = 0
        self.note_mode = False
        self.ref_diff = None
        self.diff = None
        self.check_bad = False
        self.undo_stack = []
        self._last_tick = time.time()

        self._build_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(200)

        self._boot()

    # ---------------- UI 搭建
    def _build_ui(self):
        root = QHBoxLayout()
        root.setSpacing(16)

        # ---- 左：棋盘
        left = QVBoxLayout()
        left.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(10)
        brand = QLabel("数独")
        brand.setStyleSheet("font-size:18px;font-weight:700;")
        head.addWidget(brand)
        chip = QLabel("100 关")
        chip.setStyleSheet("color:%s;background:rgba(56,189,248,.12);border:1px solid "
                           "rgba(56,189,248,.3);border-radius:11px;padding:2px 8px;font-size:11px;"
                           "font-weight:600;" % C_ACCENT2)
        head.addWidget(chip)
        head.addSpacing(6)
        self.lb_level = QLabel("第 1 关")
        self.lb_level.setStyleSheet(
            "background:%s;border:1px solid %s;border-radius:14px;padding:5px 13px;"
            "font-size:13px;font-weight:700;" % (C_PANEL, C_LINE))
        head.addWidget(self.lb_level)
        self.lb_tier = QLabel("送分")
        self.lb_tier.setStyleSheet("font-size:11px;font-weight:700;padding:4px 10px;"
                                   "border-radius:11px;")
        head.addWidget(self.lb_tier)
        head.addStretch(1)

        self.lb_timer = QLabel("00:00")
        self.lb_timer.setStyleSheet("font-size:25px;font-weight:700;color:%s;" % C_TEXT)
        head.addWidget(self.lb_timer)
        left.addLayout(head)

        self.board = SudokuBoard()
        self.board.cellClicked.connect(self.select_cell)
        left.addWidget(self.board, 1)

        self.lb_meta = QLabel("")
        self.lb_meta.setStyleSheet("color:%s;font-size:11.5px;" % C_FAINT)
        left.addWidget(self.lb_meta)

        # ---- 右：侧栏
        side = QVBoxLayout()
        side.setSpacing(12)
        side.setContentsMargins(0, 0, 0, 0)

        act = QHBoxLayout(); act.setSpacing(8)
        self.btn_pause = mk_button("暂停", parent=self); self.btn_pause.clicked.connect(self.toggle_pause)
        self.btn_pause.setToolTip("暂停 / 继续计时（空格键）")
        self.btn_swap = mk_button("换一题", parent=self); self.btn_swap.clicked.connect(self.swap_puzzle)
        self.btn_swap.setToolTip("按本关原本难度，重新生成一道不一样的题")
        act.addWidget(self.btn_pause); act.addWidget(self.btn_swap)
        side.addLayout(act)
        act2 = QHBoxLayout(); act2.setSpacing(8)
        self.btn_levels = mk_button("选关", parent=self); self.btn_levels.clicked.connect(self.open_levels)
        self.btn_records = mk_button("记录", parent=self); self.btn_records.clicked.connect(self.open_records)
        act2.addWidget(self.btn_levels); act2.addWidget(self.btn_records)
        side.addLayout(act2)

        pad_card, pad_lay = card("数字键盘")
        self.pad = QGridLayout(); self.pad.setSpacing(7)
        self.num_keys = []
        for n in range(1, 10):
            k = NumKey(n)
            k.clicked.connect(lambda _=False, x=n: self.place(x))
            self.num_keys.append(k)
            self.pad.addWidget(k, (n - 1) // 3, (n - 1) % 3)
        pad_lay.addLayout(self.pad)
        side.addWidget(pad_card)

        tool_card, tool_lay = card("操作")
        tools = QGridLayout(); tools.setSpacing(7)
        self.btn_undo = ToolButton("撤销"); self.btn_undo.clicked.connect(self.undo)
        self.btn_erase = ToolButton("擦除"); self.btn_erase.clicked.connect(self.erase)
        self.btn_note = ToolButton("备注"); self.btn_note.setCheckable(True)
        self.btn_note.clicked.connect(self.toggle_note)
        self.btn_hint = ToolButton("提示"); self.btn_hint.clicked.connect(self.give_hint)
        for i, b in enumerate((self.btn_undo, self.btn_erase, self.btn_note, self.btn_hint)):
            tools.addWidget(b, i // 2, i % 2)
        tool_lay.addLayout(tools)
        side.addWidget(tool_card)

        info_card, info_lay = card("本关信息")
        self.sb_best = self._stat(info_lay, "最佳用时", "--:--")
        self.sb_wins = self._stat(info_lay, "完成次数", "0 次")
        self.sb_hint = self._stat(info_lay, "剩余提示", "%d / %d" % (HINTS_PER_LEVEL, HINTS_PER_LEVEL))
        reset = mk_button("重置本关", parent=self)
        reset.clicked.connect(self.reset_level)
        info_lay.addWidget(reset)
        side.addWidget(info_card)

        keys_card, keys_lay = card("快捷键")
        for k, v in (("填数 / 擦除", "1-9 / 0"), ("移动光标", "方向键"),
                     ("备注模式", "N"), ("撤销 / 提示", "Ctrl+Z / H")):
            self._stat(keys_lay, k, v)
        side.addWidget(keys_card)
        side.addStretch(1)

        side_wrap = QWidget()
        side_wrap.setLayout(side)
        side_wrap.setFixedWidth(262)

        side_scroll = QScrollArea()
        side_scroll.setWidgetResizable(True)
        side_scroll.setFixedWidth(288)
        side_scroll.setFrameShape(QFrame.NoFrame)
        side_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        side_scroll.setStyleSheet(
            "QScrollArea{background:transparent;border:none;}"
            "QScrollBar:vertical{background:transparent;width:8px;margin:2px;}"
            "QScrollBar::handle:vertical{background:%s;border-radius:4px;min-height:30px;}"
            "QScrollBar::add-line,QScrollBar::sub-line{height:0;}"
            "QScrollBar::add-page,QScrollBar::sub-page{background:transparent;}" % C_LINE2)
        side_scroll.setWidget(side_wrap)

        root.addLayout(left, 1)
        root.addWidget(side_scroll)
        self.body.addLayout(root, 1)

    def _stat(self, parent_layout, name, value):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        a = QLabel(name); a.setStyleSheet("color:%s;font-size:12.5px;" % C_DIM)
        b = QLabel(value); b.setStyleSheet("font-size:13px;font-weight:600;")
        row.addWidget(a); row.addStretch(1); row.addWidget(b)
        wrap = QWidget(); wrap.setLayout(row)
        wrap.setMinimumHeight(24)
        wrap.setFixedHeight(24)
        parent_layout.addWidget(wrap)
        return b

    # ---------------- 启动
    def _boot(self):
        st = self.store.data.get("state")
        if st and st.get("puzzle") and len(st.get("puzzle", "")) == 81:
            self._restore(st)
        else:
            lv = int(self.store.data["meta"].get("currentLevel", 1))
            self.start_level(lv)

    # ---------------- 关卡加载
    def start_level(self, level, force_generate=False, avoid=None):
        level = max(1, min(MAX_LEVEL, int(level)))
        rec = self.store.level_rec(level)
        ref = rec.get("refDiff")
        if ref is None and self.pool.meta(level):
            ref = self.pool.meta(level)["refDiff"]

        pd, lm = (None, None) if force_generate else self.pool.next(level, avoid)
        if pd:
            self._apply_puzzle(level, pd["p"], pd["s"], pd["givens"], pd["rating"],
                               pd["difficulty"], lm.get("tier") if lm else None)
            return
        # 题池没有 → 后台生成
        self.board.ready = False
        self.board.update()
        self.lb_meta.setText("正在按本关难度出题，请稍候…")
        self.btn_swap.setEnabled(False)
        self.worker = GenWorker(level, ref, avoid)
        self.worker.done.connect(lambda g, err, lv=level: self._on_generated(lv, g, err))
        self.worker.start()

    def _on_generated(self, level, g, err):
        self.btn_swap.setEnabled(True)
        if not g:
            QMessageBox.warning(self, "出题失败", "生成题目出错：%s" % err)
            return
        self._apply_puzzle(level, E.to_string(g["puzzle"]), E.to_string(g["solution"]),
                           g["givens"], g["rating"], g["difficulty"],
                           E.tier_of(g["difficulty"]), ref=g["difficulty"])

    def _apply_puzzle(self, level, pstr, sstr, givens, rating, difficulty, tier, ref=None):
        self.level = level
        self.puzzle = E.from_string(pstr)
        self.solution = E.from_string(sstr)
        self.grid = list(self.puzzle)
        self.notes = [0] * 81
        self.hinted = [0] * 81
        self.sel = -1
        self.elapsed = 0
        self.finished = False
        self.hints_left = HINTS_PER_LEVEL
        self.hint_used = 0
        self.note_mode = False
        self.btn_note.setChecked(False)
        self.check_bad = False
        self.undo_stack = []
        self.ref_diff = difficulty if ref is None else ref
        self.diff = dict(tier=tier if tier is not None else E.tier_of(difficulty),
                         givens=givens, rating=rating, difficulty=difficulty)
        self.diff["tier_name"] = E.TIERS[self.diff["tier"]]["name"]

        rec = self.store.level_rec(level)
        rec["plays"] = (rec.get("plays") or 0) + 1
        if rec.get("refDiff") is None:
            rec["refDiff"] = difficulty
        rec["tier"] = self.diff["tier"]
        rec["givens"] = givens
        rec["rating"] = rating
        self.store.save()

        self.board.ready = True
        self.resume()
        self.refresh()
        self.save_state()

    # ---------------- 恢复进度
    def _restore(self, st):
        self.level = int(st.get("level", 1))
        self.puzzle = E.from_string(st["puzzle"])
        self.solution = E.from_string(st["solution"])
        self.grid = E.from_string(st["grid"])
        self.notes = list(st.get("notes") or [0] * 81)
        self.hinted = list(st.get("hinted") or [0] * 81)
        self.notes = (self.notes + [0] * 81)[:81]
        self.hinted = (self.hinted + [0] * 81)[:81]
        self.elapsed = st.get("elapsed", 0)
        self.hints_left = st.get("hintsLeft", HINTS_PER_LEVEL)
        self.hint_used = st.get("hintUsed", 0)
        self.sel = st.get("sel", -1)
        self.ref_diff = st.get("refDiff")
        self.diff = st.get("diff")
        if self.diff and "tier" in self.diff:
            self.diff["tier_name"] = E.TIERS[self.diff["tier"]]["name"]
        self.finished = False
        self.check_bad = False
        self.board.ready = True
        self.pause()
        self.refresh()
        QTimer.singleShot(300, lambda: self.flash("已恢复上次进度：第 %d 关" % self.level))

    # ---------------- 存档
    def save_state(self):
        if self.finished or not self.board.ready:
            return
        self.store.data["state"] = dict(
            level=self.level, puzzle=E.to_string(self.puzzle),
            solution=E.to_string(self.solution), grid=E.to_string(self.grid),
            notes=self.notes, hinted=self.hinted, elapsed=int(self.elapsed),
            hintsLeft=self.hints_left, hintUsed=self.hint_used, sel=self.sel,
            refDiff=self.ref_diff, diff=self.diff)
        self.store.save()

    def clear_state(self):
        self.store.data["state"] = None
        self.store.save()

    # ---------------- 计时
    def _tick(self):
        now = time.time()
        if self.running and not self.finished:
            self.elapsed += (now - self._last_tick) * 1000.0
        self._last_tick = now
        self.lb_timer.setText(_fmt(int(self.elapsed)) if self.elapsed < 3600000
                              else _fmt(int(self.elapsed)))
        if int(self.elapsed / 1000) % 10 == 0 and self.running and not self.finished:
            self.save_state()

    def resume(self):
        self._last_tick = time.time()
        self.running = True
        self.board.paused = False
        self.board.update()
        self.btn_pause.setText("暂停")

    def pause(self):
        if self.running:
            self._tick()
        self.running = False
        self.board.paused = True
        self.board.update()
        self.btn_pause.setText("继续")
        self.save_state()

    def toggle_pause(self):
        if self.finished or not self.board.ready:
            return
        if self.running:
            self.pause()
        else:
            self.resume()

    # ---------------- 渲染
    def refresh(self):
        b = self.board
        b.puzzle, b.grid, b.solution = self.puzzle, self.grid, self.solution
        b.notes, b.hinted, b.sel = self.notes, self.hinted, self.sel
        b.check_bad = self.check_bad
        counts = [0] * 10
        for v in self.grid:
            if v:
                counts[v] += 1
        for i, k in enumerate(self.num_keys):
            k.set_left(9 - counts[i + 1])
        self.lb_level.setText("第 %d 关" % self.level)
        if self.diff:
            tier = self.diff["tier"]
            col = E.TIERS[tier]["color"]
            self.lb_tier.setText(self.diff["tier_name"])
            self.lb_tier.setStyleSheet(
                "font-size:11px;font-weight:700;padding:4px 10px;border-radius:11px;"
                "color:%s;background:%s;border:1px solid %s;"
                % (col, rgba(col, 0.14), rgba(col, 0.35)))
            self.lb_meta.setText(
                "难度档位：%s　·　提示数：%d 个　·　所需技巧：%s　·　难度分：%d"
                % (self.diff["tier_name"], self.diff["givens"],
                   E.RATING_TEXT.get(self.diff["rating"], "--"), round(self.diff["difficulty"])))
        rec = self.store.level(self.level) or {}
        self.sb_best.setText(_fmt(rec.get("best")))
        self.sb_wins.setText("%d 次" % (rec.get("wins") or 0))
        self.sb_hint.setText("%d / %d" % (self.hints_left, HINTS_PER_LEVEL))
        self.lb_timer.setStyleSheet("font-size:25px;font-weight:700;color:%s;"
                                    % (C_TEXT if self.running else C_FAINT))
        b.update()

    def flash(self, msg):
        self.statusBar().showMessage(msg, 2600)

    # ---------------- 交互
    def select_cell(self, i):
        self.sel = i
        self.board.sel = i
        self.board.hover = i
        self.board.update()

    def place(self, d):
        if not self.board.ready or self.finished:
            return
        if not self.running:
            self.flash("已暂停，按空格继续计时")
            return
        i = self.sel
        if i < 0:
            self.flash("先点一个空格")
            return
        if self.puzzle[i]:
            self.flash("题目给定的数字不能修改")
            return
        self._push_undo()
        if self.note_mode:
            if self.grid[i]:
                self.grid[i] = 0
            self.notes[i] ^= (1 << d)
        elif self.grid[i] == d:
            self.grid[i] = 0
        else:
            self.grid[i] = d
            self.notes[i] = 0
            self.hinted[i] = 0
            if d == self.solution[i]:
                self._clear_peer_notes(i, d)
        self.check_bad = False
        self.board.check_bad = False
        self.refresh()
        self.save_state()
        self._check_win()

    def _clear_peer_notes(self, i, d):
        bit = ~(1 << d)
        for p in E.PEERS[i]:
            self.notes[p] &= bit

    def _push_undo(self):
        self.undo_stack.append((list(self.grid), list(self.notes), list(self.hinted)))
        if len(self.undo_stack) > 200:
            self.undo_stack.pop(0)

    def erase(self):
        if not self.board.ready or self.finished or not self.running:
            return
        i = self.sel
        if i < 0:
            return
        if self.puzzle[i]:
            self.flash("题目给定的数字不能修改")
            return
        if not self.grid[i] and not self.notes[i]:
            return
        self._push_undo()
        self.grid[i] = 0
        self.notes[i] = 0
        self.hinted[i] = 0
        self.check_bad = False
        self.board.check_bad = False
        self.refresh()
        self.save_state()

    def undo(self):
        if not self.board.ready or self.finished or not self.running:
            return
        if not self.undo_stack:
            self.flash("没有可撤销的操作")
            return
        self.grid, self.notes, self.hinted = self.undo_stack.pop()
        self.check_bad = False
        self.board.check_bad = False
        self.refresh()
        self.save_state()

    def toggle_note(self):
        self.note_mode = not self.note_mode
        self.btn_note.setChecked(self.note_mode)
        self.flash("备注模式：输入的数字会记为小字候选" if self.note_mode else "备注模式已关闭")

    def give_hint(self):
        if not self.board.ready or self.finished:
            return
        if not self.running:
            self.flash("已暂停，按空格继续计时")
            return
        if self.hints_left <= 0:
            self.flash("本关 3 次提示已用完")
            return
        target = self.sel
        if target < 0 or self.puzzle[target] or self.grid[target] == self.solution[target]:
            pool = [i for i in range(81)
                    if not self.puzzle[i] and self.grid[i] != self.solution[i]]
            if not pool:
                self.flash("已经全部填对了")
                return
            import random
            target = random.choice(pool)
        self._push_undo()
        self.grid[target] = self.solution[target]
        self.hinted[target] = 1
        self.notes[target] = 0
        self._clear_peer_notes(target, self.solution[target])
        self.hints_left -= 1
        self.hint_used += 1
        self.sel = target
        self.board.sel = target
        self.check_bad = False
        self.board.check_bad = False
        self.refresh()
        self.save_state()
        self._check_win()

    def reset_level(self):
        if not self.board.ready or self.finished:
            return
        r = QMessageBox.question(self, "重置本关", "清空本关已填内容并重新计时？",
                                 QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if r != QMessageBox.Yes:
            return
        self.grid = list(self.puzzle)
        self.notes = [0] * 81
        self.hinted = [0] * 81
        self.elapsed = 0
        self.hints_left = HINTS_PER_LEVEL
        self.hint_used = 0
        self.sel = -1
        self.check_bad = False
        self.board.check_bad = False
        self.undo_stack = []
        self.resume()
        self.refresh()
        self.save_state()
        self.flash("已重置本关")

    def swap_puzzle(self):
        """按本关原本难度，换一道不一样的题"""
        if not self.board.ready or self.finished:
            return
        avoid = E.to_string(self.puzzle)
        self.flash("正在按本关难度换题…")
        self.start_level(self.level, avoid=avoid)

    # ---------------- 通关
    def _check_win(self):
        if self.finished or not E.is_solved(self.grid, self.solution):
            full = all(self.grid)
            if full:
                bad = sum(1 for i in range(81) if self.grid[i] != self.solution[i])
                if bad:
                    self.check_bad = True
                    self.board.check_bad = True
                    self.refresh()
                    self.flash("还有 %d 处填错了，已标红" % bad)
                    QTimer.singleShot(2800, self._clear_check)
            return
        self.finished = True
        self.running = False
        t = int(self.elapsed)
        rec = self.store.level_rec(self.level)
        rec["wins"] = (rec.get("wins") or 0) + 1
        rec["last"] = t
        rec["hints"] = (rec.get("hints") or 0) + self.hint_used
        is_best = rec.get("best") is None or t < rec["best"]
        if is_best:
            rec["best"] = t
        if rec.get("refDiff") is None:
            rec["refDiff"] = self.ref_diff
        meta = self.store.data["meta"]
        meta["currentLevel"] = max(int(meta.get("currentLevel", 1)), min(MAX_LEVEL, self.level + 1))
        self.clear_state()
        self.save_state_force()
        self.refresh()

        dlg = WinDialog(self, self.level, t, is_best, rec.get("best"),
                        self.hint_used, self.diff, self.level < MAX_LEVEL)
        dlg.exec()
        if dlg.choice == "next" and self.level < MAX_LEVEL:
            self.start_level(self.level + 1)
        elif dlg.choice == "levels":
            self.open_levels()
        else:
            self.start_level(self.level, avoid=E.to_string(self.puzzle))

    def _clear_check(self):
        self.check_bad = False
        self.board.check_bad = False
        self.board.update()

    def save_state_force(self):
        self.store.data["state"] = None
        self.store.save()

    # ---------------- 对话框
    def open_levels(self):
        dlg = LevelDialog(self, self.store, self.level)
        if dlg.exec() == QDialog.Accepted and dlg.picked:
            self.start_level(dlg.picked)

    def open_records(self):
        RecordDialog(self, self.store).exec()

    # ---------------- 键盘
    def keyPressEvent(self, ev):
        k = ev.key()
        if k in (Qt.Key_1, Qt.Key_2, Qt.Key_3, Qt.Key_4, Qt.Key_5,
                 Qt.Key_6, Qt.Key_7, Qt.Key_8, Qt.Key_9):
            self.place(k - Qt.Key_0)
            return
        if k in (Qt.Key_0, Qt.Key_Backspace, Qt.Key_Delete):
            self.erase()
            return
        if k == Qt.Key_Space:
            self.toggle_pause()
            return
        if k == Qt.Key_N:
            self.toggle_note()
            return
        if k == Qt.Key_H:
            self.give_hint()
            return
        if k == Qt.Key_Z and (ev.modifiers() & Qt.ControlModifier):
            self.undo()
            return
        if k in (Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right):
            if not self.board.ready:
                return
            i = self.sel if self.sel >= 0 else 40
            r, c = i // 9, i % 9
            if k == Qt.Key_Up and r > 0:
                i -= 9
            elif k == Qt.Key_Down and r < 8:
                i += 9
            elif k == Qt.Key_Left and c > 0:
                i -= 1
            elif k == Qt.Key_Right and c < 8:
                i += 1
            self.select_cell(i)
            return
        super().keyPressEvent(ev)

    def changeEvent(self, ev):
        # 自动暂停：最小化，或切到别的程序（弹自己的对话框不算，否则关掉选关回来还要手动继续）
        auto = False
        if ev.type() == QEvent.WindowStateChange and self.isMinimized():
            auto = True
        elif ev.type() == QEvent.ActivationChange and not self.isActiveWindow():
            auto = QApplication.activeModalWidget() is None
        if auto and self.running and not self.finished and self.board.ready:
            self.pause()
        super().changeEvent(ev)

    def closeEvent(self, ev):
        self.save_state()
        self.store.save()
        super().closeEvent(ev)


def launch():
    """供游戏大厅调用：创建并显示数独窗口"""
    w = SudokuWindow()
    w.show()
    return w


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")

    # 打包自检：--selftest 时离屏跑一遍并截图后退出（用于验证 exe 完整性）
    if "--selftest" in sys.argv:
        lines = []
        w = SudokuWindow()
        w.resize(1060, 900)
        for _ in range(30):
            app.processEvents()
        ok = bool(w.board.ready)
        lines.append("SELFTEST " + ("OK" if ok else "FAIL"))
        lines.append("关卡=%d 档位=%s 提示数=%d 技巧=%s 难度分=%.0f"
                     % (w.level, w.diff["tier_name"], w.diff["givens"],
                        E.RATING_TEXT[w.diff["rating"]], w.diff["difficulty"]))
        lines.append("题池可用关卡数=%d" % len([k for k in range(1, 101) if w.pool.has(k)]))
        lines.append("资源目录=%s" % resource_dir())
        lines.append("存档目录=%s" % data_dir())
        try:
            out = os.path.join(data_dir(), "selftest.png")
            w.grab().save(out)
            lines.append("截图=%s (%s 字节)" % (out, os.path.getsize(out)))
        except Exception as exc:
            lines.append("截图失败: %s" % exc)
        text = "\n".join(lines)
        for t in lines:
            print(t)
        try:
            with open(os.path.join(data_dir(), "selftest.log"), "w", encoding="utf-8") as f:
                f.write(text + "\n")
        except Exception:
            pass
        w.close()
        return 0 if ok else 1

    w = SudokuWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
