# -*- coding: utf-8 -*-
"""
华容道 · 8 关（PySide6 / Qt）

自绘 4x5 棋盘：拖动棋子或方向键滑动，曹操 2x2 逃出下方出口即通关。
自带 BFS 最优解：显示最少步数、给出提示、可一键演示自动求解。
"""
import json
import os
import sys
import time

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QPointF, QRectF
from PySide6.QtGui import (QPainter, QColor, QFont, QPen, QBrush, QPolygonF,
                           QLinearGradient)
from PySide6.QtWidgets import (QApplication, QWidget, QHBoxLayout, QVBoxLayout,
                               QGridLayout, QLabel, QDialog, QMessageBox,
                               QPushButton)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from klotski import engine as KE  # noqa: E402
from shared.common import (C_BG, C_PANEL, C_PANEL2, C_LINE, C_LINE2, C_TEXT, C_DIM,
                    C_FAINT, C_ACCENT, C_ACCENT2, C_DANGER, C_OK, C_GOLD,
                    rgba, mk_button, ToolButton, card, stat_row, vscroll,
                    load_game_json, BaseStore, GameWindow, flash_status, fmt_time,
                    WorkerKeeper)  # noqa: E402

# 棋子配色（按尺寸区分角色）
PIECE_STYLE = {
    (2, 2): ("#c0473d", "#f0b0a8", "#7d2b24"),   # 曹操
    (2, 1): ("#3d6ed6", "#b2cbf7", "#26478f"),   # 关羽
    (1, 2): ("#2b7f74", "#a6dcd2", "#186056"),   # 四将
    (1, 1): ("#54606f", "#cdd6e2", "#333c48"),   # 卒
}


class BoardView(QWidget):
    """华容道棋盘：点击选中、拖动滑动、方向键移动"""

    moved = Signal()
    selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.game = KE.Klotski()
        self.sel = -1
        self.hint = None            # {'fx','fy','tx','ty','w','h'}
        self.locked = True
        self.drag = None            # (piece_idx, QPointF)
        self.animating = False
        self.setMinimumSize(400, 480)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)

    # -------- 几何
    MAX_CELL = 126
    LABEL_H = 34

    def _geom(self):
        w, h = self.width(), self.height()
        padx, pady = 22, 18
        avail_w = w - 2 * padx
        avail_h = h - 2 * pady - self.LABEL_H
        cell = min(avail_w / KE.W, avail_h / KE.H, self.MAX_CELL)
        ox = (w - cell * KE.W) / 2.0
        oy = pady + (avail_h - cell * KE.H) / 2.0
        return ox, oy, cell

    def _cell_at(self, pos):
        ox, oy, cell = self._geom()
        x = int((pos.x() - ox) // cell)
        y = int((pos.y() - oy) // cell)
        if 0 <= x < KE.W and 0 <= y < KE.H:
            return x, y
        return None

    # -------- 交互
    def mousePressEvent(self, ev):
        if self.locked or self.animating:
            return
        cell = self._cell_at(ev.position())
        if not cell:
            return
        i = self.game.piece_at(*cell)
        if i >= 0:
            self.sel = i
            self.drag = [i, ev.position()]
            self.selected.emit(i)
            self.update()

    def mouseMoveEvent(self, ev):
        if self.drag is None or self.locked or self.animating:
            return
        ox, oy, cell = self._geom()
        i, start = self.drag
        dx = ev.position().x() - start.x()
        dy = ev.position().y() - start.y()
        thr = cell * 0.42
        if max(abs(dx), abs(dy)) < thr:
            return
        if abs(dx) > abs(dy):
            step = (1, 0) if dx > 0 else (-1, 0)
        else:
            step = (0, 1) if dy > 0 else (0, -1)
        if self.game.move(i, *step):
            self.hint = None
            self.moved.emit()
            # 拖动起点随棋子一起移动，实现连续滑动
            self.drag[1] = QPointF(start.x() + step[0] * cell, start.y() + step[1] * cell)
        else:
            self.drag[1] = ev.position()
        self.update()

    def mouseReleaseEvent(self, ev):
        self.drag = None

    def keyPressEvent(self, ev):
        if self.locked or self.animating or self.sel < 0:
            super().keyPressEvent(ev)
            return
        m = {Qt.Key_Up: (0, -1), Qt.Key_W: (0, -1), Qt.Key_Down: (0, 1), Qt.Key_S: (0, 1),
             Qt.Key_Left: (-1, 0), Qt.Key_A: (-1, 0), Qt.Key_Right: (1, 0), Qt.Key_D: (1, 0)}
        if ev.key() in m:
            if self.game.move(self.sel, *m[ev.key()]):
                self.hint = None
                self.moved.emit()
                self.update()
            else:
                flash_status(self.window(), "这个方向走不动")
            return
        super().keyPressEvent(ev)

    # -------- 绘制
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        ox, oy, cell = self._geom()
        p.fillRect(self.rect(), QColor(C_BG))

        bw, bh = cell * KE.W, cell * KE.H
        p.setBrush(QBrush(QColor(C_PANEL)))
        p.setPen(QPen(QColor(C_LINE), 1.2))
        p.drawRoundedRect(QRectF(ox - 6, oy - 6, bw + 12, bh + 12), 12, 12)
        p.setBrush(QBrush(QColor("#0f141c")))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(ox - 1, oy - 1, bw + 2, bh + 2), 8, 8)

        # 网格 + 空格提示点
        p.setPen(QPen(QColor(C_LINE), 1.0))
        for k in range(KE.W + 1):
            p.drawLine(QPointF(ox + k * cell, oy), QPointF(ox + k * cell, oy + bh))
        for k in range(KE.H + 1):
            p.drawLine(QPointF(ox, oy + k * cell), QPointF(ox + bw, oy + k * cell))
        occ = self.game.occupancy()
        p.setBrush(QBrush(QColor(C_LINE2)))
        for cy in range(KE.H):
            for cx in range(KE.W):
                if (cx, cy) not in occ:
                    p.drawEllipse(QPointF(ox + (cx + 0.5) * cell, oy + (cy + 0.5) * cell),
                                  cell * 0.045, cell * 0.045)

        # 出口
        ex, ey = KE.EXIT
        gx = ox + ex * cell
        gap = QRectF(gx, oy + bh + 4, cell * 2, self.LABEL_H - 8)
        p.setBrush(QBrush(QColor(rgba(C_OK, 0.16))))
        p.setPen(QPen(QColor(rgba(C_OK, 0.55)), 1.4))
        p.drawRoundedRect(gap, 7, 7)
        f = QFont()
        f.setPointSizeF(max(8.5, cell * 0.135))
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(C_OK))
        p.drawText(gap, Qt.AlignCenter, "逃 生 出 口")

        # 棋子
        for i, piece in enumerate(self.game.pieces):
            x = ox + piece["x"] * cell
            y = oy + piece["y"] * cell
            w = piece["w"] * cell
            h = piece["h"] * cell
            self._draw_piece(p, x, y, w, h, piece, i == self.sel, cell)

        # 提示箭头
        if self.hint:
            self._draw_hint(p, ox, oy, cell)

    def _draw_piece(self, p, x, y, w, h, piece, sel, cell):
        base, light, dark = PIECE_STYLE[(piece["w"], piece["h"])]
        r = QRectF(x + 2.5, y + 2.5, w - 5, h - 5)
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0.0, QColor(light))
        g.setColorAt(0.35, QColor(base))
        g.setColorAt(1.0, QColor(dark))
        p.setBrush(QBrush(g))
        if sel:
            p.setPen(QPen(QColor(C_GOLD), 2.6))
        else:
            p.setPen(QPen(QColor(0, 0, 0, 110), 1.2))
        p.drawRoundedRect(r, 10, 10)

        # 名字（竖排棋子逐字竖写）
        name = piece["name"]
        f = QFont()
        f.setBold(True)
        if piece["w"] == 2 and piece["h"] == 2:
            f.setPointSizeF(max(15.0, cell * 0.50))
            p.setFont(f)
            p.setPen(QColor("#fff2ef"))
            p.drawText(r, Qt.AlignCenter, name)
        elif piece["h"] == 2:
            f.setPointSizeF(max(11.0, cell * 0.40))
            p.setFont(f)
            p.setPen(QColor("#eefbf8"))
            half = r.height() / 2.0
            for k, ch in enumerate(name[:2]):
                p.drawText(QRectF(r.x(), r.y() + k * half, r.width(), half),
                           Qt.AlignCenter, ch)
        elif piece["w"] == 2:
            f.setPointSizeF(max(11.0, cell * 0.42))
            p.setFont(f)
            p.setPen(QColor("#eaf1ff"))
            p.drawText(r, Qt.AlignCenter, name)
        else:
            f.setPointSizeF(max(10.5, cell * 0.38))
            p.setFont(f)
            p.setPen(QColor("#e3e9f2"))
            p.drawText(r, Qt.AlignCenter, name)

    def _draw_hint(self, p, ox, oy, cell):
        h = self.hint
        cx = ox + (h["fx"] + h["w"] / 2.0) * cell
        cy = oy + (h["fy"] + h["h"] / 2.0) * cell
        dx = (h["tx"] - h["fx"]) * cell
        dy = (h["ty"] - h["fy"]) * cell
        p.setBrush(QBrush(QColor(rgba(C_GOLD, 0.22))))
        p.setPen(QPen(QColor(C_GOLD), 2.4, Qt.SolidLine, Qt.RoundCap))
        p.drawRoundedRect(QRectF(ox + h["fx"] * cell + 2.5, oy + h["fy"] * cell + 2.5,
                                 h["w"] * cell - 5, h["h"] * cell - 5), 10, 10)
        # 箭头
        ex, ey = cx + dx * 0.42, cy + dy * 0.42
        p.setBrush(QBrush(QColor(C_GOLD)))
        p.setPen(Qt.NoPen)
        ang = 0 if dx > 0 else (180 if dx < 0 else (90 if dy > 0 else -90))
        size = cell * 0.26
        pts = [(size, 0), (-size * 0.6, size * 0.72), (-size * 0.6, -size * 0.72)]
        poly = QPolygonF()
        import math
        for (px, py) in pts:
            rad = math.radians(ang)
            poly.append(QPointF(ex + px * math.cos(rad) - py * math.sin(rad),
                                ey + px * math.sin(rad) + py * math.cos(rad)))
        p.drawPolygon(poly)


class SolverWorker(QThread):
    done = Signal(object)

    def __init__(self, game):
        super().__init__()
        self.game = game

    def run(self):
        try:
            path = self.game.solve_from_here()
        except Exception:
            path = None
        self.done.emit(path)


# ------------------------------------------------------------------ 选关
class LevelDialog(QDialog):
    def __init__(self, parent, levels, store, cur):
        super().__init__(parent)
        self.setWindowTitle("选择关卡")
        self.setModal(True)
        self.picked = None
        self.resize(720, 600)
        self.setStyleSheet("QDialog{background:%s;}QLabel{color:%s;}" % (C_BG, C_TEXT))
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)
        head = QHBoxLayout()
        t = QLabel("选择关卡")
        t.setStyleSheet("font-size:17px;font-weight:700;")
        head.addWidget(t)
        head.addStretch(1)
        done = sum(1 for k, v in store.data.get("levels", {}).items() if v.get("cleared"))
        info = QLabel("已通关 %d / %d 关" % (done, len(levels)))
        info.setStyleSheet("color:%s;font-size:12px;" % C_DIM)
        head.addWidget(info)
        root.addLayout(head)

        inner = QWidget()
        grid = QGridLayout(inner)
        grid.setSpacing(8)
        grid.setContentsMargins(0, 0, 6, 0)
        for idx, lv in enumerate(levels):
            lv_no = lv["level"]
            rec = store.data.get("levels", {}).get(str(lv_no), {})
            best = rec.get("bestSteps")
            txt = "第 %d 关  %s" % (lv_no, lv["name"])
            if best:
                txt += "\n最佳 %d 步" % best
            else:
                txt += "\n最少 %d 步" % (lv["minSteps"] or 0)
            b = QPushButton(txt)
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(58)
            ring = C_ACCENT if lv_no == cur else C_LINE
            b.setStyleSheet(
                "QPushButton{background:%s;color:%s;border:1px solid %s;border-radius:10px;"
                "font-size:12.5px;%s}"
                "QPushButton:hover{background:#232b38;color:%s;border-color:%s;}"
                % (C_PANEL2, C_TEXT if rec.get("cleared") else C_DIM, ring,
                   "font-weight:700;" if rec.get("cleared") else "", C_TEXT, C_ACCENT2))
            b.setToolTip("最少 %d 步" % (lv["minSteps"] or 0))
            b.clicked.connect(lambda _=False, n=lv_no: self._pick(n))
            grid.addWidget(b, idx // 3, idx % 3)
        root.addWidget(vscroll(inner), 1)
        row = QHBoxLayout()
        row.addStretch(1)
        c = mk_button("关闭", parent=self)
        c.clicked.connect(self.reject)
        row.addWidget(c)
        root.addLayout(row)

    def _pick(self, n):
        self.picked = n
        self.accept()


# ------------------------------------------------------------------ 通关
class WinDialog(QDialog):
    def __init__(self, parent, level, name, steps, optimal, elapsed, best,
                 has_next):
        super().__init__(parent)
        self.setWindowTitle("通关")
        self.setModal(True)
        self.choice = "next"
        self.resize(430, 320)
        self.setStyleSheet("QDialog{background:%s;}QLabel{color:%s;}" % (C_PANEL, C_TEXT))
        root = QVBoxLayout(self)
        root.setContentsMargins(25, 22, 25, 20)
        root.setSpacing(8)
        t = QLabel("第 %d 关 · %s · 曹操逃脱！" % (level, name))
        t.setStyleSheet("font-size:16px;font-weight:700;")
        t.setAlignment(Qt.AlignCenter)
        root.addWidget(t)
        v = QLabel("%d 步" % steps)
        v.setStyleSheet("font-size:38px;font-weight:700;color:%s;" % C_ACCENT2)
        v.setAlignment(Qt.AlignCenter)
        root.addWidget(v)
        parts = ["用时 " + fmt_time(elapsed)]
        parts.append("最少 %d 步" % optimal)
        if steps == optimal:
            parts.append("完美 ✦")
        parts.append("本关最佳 %s" % (("%d 步" % best) if best is not None else "--"))
        note = QLabel("  ·  ".join(parts))
        note.setStyleSheet("color:%s;font-size:12.5px;" % C_DIM)
        note.setAlignment(Qt.AlignCenter)
        root.addWidget(note)
        root.addSpacing(6)
        row1 = QHBoxLayout()
        nxt = mk_button(("进入第 %d 关" % (level + 1)) if has_next else "全部关卡完成 🎉",
                        "primary", self)
        nxt.setEnabled(has_next)
        nxt.clicked.connect(lambda: self._go("next"))
        row1.addWidget(nxt)
        root.addLayout(row1)
        row2 = QHBoxLayout()
        rep = mk_button("再玩一次", parent=self)
        rep.clicked.connect(lambda: self._go("replay"))
        sel = mk_button("选关", parent=self)
        sel.clicked.connect(lambda: self._go("levels"))
        row2.addWidget(rep)
        row2.addWidget(sel)
        root.addLayout(row2)

    def _go(self, c):
        self.choice = c
        self.accept()


# ------------------------------------------------------------------ 主窗口
class KlotskiWindow(GameWindow):
    game_key = "klotski"
    game_name = "华容道"
    game_emoji = "🧩"

    def __init__(self):
        super().__init__()
        data = load_game_json("levels.json", "klotski")
        self.levels = data.get("levels") or [
            {"level": i + 1, "name": n, "layout": t, "minSteps": None, "solution": None}
            for i, (n, t) in enumerate(KE.LAYOUTS)]
        self.store = BaseStore("klotski_save.json",
                               {"meta": {"currentLevel": 1}, "levels": {}, "state": None})
        self.store.data.setdefault("meta", {"currentLevel": 1})
        self.store.data.setdefault("levels", {})
        self.store.data.setdefault("state", None)
        self.worker = None
        self.keeper = WorkerKeeper()
        self.gen = 0
        self.elapsed = 0.0
        self.running = False
        self.finished = False
        self.auto_playing = False
        self.auto_path = []
        self._last_tick = time.time()
        self.resize(1040, 900)
        self.setMinimumSize(860, 660)
        self._build_ui()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(200)
        self.auto_timer = QTimer(self)
        self.auto_timer.timeout.connect(self._auto_step)
        self._boot()

    # -------- UI
    def _build_ui(self):
        self.lb_level = QLabel("第 1 关")
        self.lb_level.setStyleSheet("background:%s;border:1px solid %s;border-radius:14px;"
                                    "padding:5px 13px;font-size:13px;font-weight:700;"
                                    % (C_PANEL, C_LINE))
        self.bar_right.addWidget(self.lb_level)
        self.lb_timer = QLabel("00:00")
        self.lb_timer.setStyleSheet("font-size:20px;font-weight:700;")
        self.bar_right.addWidget(self.lb_timer)

        root = QHBoxLayout()
        root.setSpacing(16)

        left = QVBoxLayout()
        left.setSpacing(10)
        head = QHBoxLayout()
        self.lb_name = QLabel("齐头并进")
        self.lb_name.setStyleSheet("font-size:16px;font-weight:700;")
        head.addWidget(self.lb_name)
        self.lb_min = QLabel("最少 0 步")
        self.lb_min.setStyleSheet("color:%s;background:%s;border:1px solid %s;"
                                  "border-radius:11px;padding:3px 9px;font-size:11.5px;"
                                  % (C_GOLD, rgba(C_GOLD, 0.12), rgba(C_GOLD, 0.35)))
        head.addWidget(self.lb_min)
        head.addStretch(1)
        self.lb_steps = QLabel("0 步")
        self.lb_steps.setStyleSheet("font-size:22px;font-weight:700;color:%s;" % C_ACCENT2)
        head.addWidget(self.lb_steps)
        left.addLayout(head)

        self.board = BoardView()
        self.board.moved.connect(self.on_moved)
        self.board.selected.connect(lambda _i: None)
        left.addWidget(self.board, 1)

        self.lb_meta = QLabel("拖动棋子滑动；也可选中后按方向键 / WASD")
        self.lb_meta.setStyleSheet("color:%s;font-size:11.5px;" % C_FAINT)
        left.addWidget(self.lb_meta)
        root.addLayout(left, 1)

        side = QVBoxLayout()
        side.setSpacing(12)
        act = QGridLayout()
        act.setSpacing(8)
        self.btn_undo = mk_button("撤销一步", parent=self)
        self.btn_undo.clicked.connect(self.undo)
        self.btn_reset = mk_button("重置本关", parent=self)
        self.btn_reset.clicked.connect(self.reset_level)
        act.addWidget(self.btn_undo, 0, 0)
        act.addWidget(self.btn_reset, 0, 1)
        side.addLayout(act)
        act2 = QGridLayout()
        act2.setSpacing(8)
        self.btn_levels = mk_button("选关", parent=self)
        self.btn_levels.clicked.connect(self.open_levels)
        self.btn_hint = mk_button("提示", parent=self)
        self.btn_hint.clicked.connect(self.hint)
        act2.addWidget(self.btn_levels, 0, 0)
        act2.addWidget(self.btn_hint, 0, 1)
        side.addLayout(act2)

        self.btn_auto = mk_button("自动求解演示", parent=self)
        self.btn_auto.clicked.connect(self.toggle_auto)
        side.addWidget(self.btn_auto)

        c, l = card("本关信息")
        self.sb_min = stat_row(l, "最少步数", "--")
        self.sb_best = stat_row(l, "最佳纪录", "--")
        self.sb_win = stat_row(l, "通关次数", "0 次")
        self.sb_size = stat_row(l, "有效步数", "0")
        side.addWidget(c)

        c2, l2 = card("棋子")
        for name, color in (("曹操（2x2）", PIECE_STYLE[(2, 2)][0]),
                            ("关羽（2x1）", PIECE_STYLE[(2, 1)][0]),
                            ("四将（1x2）", PIECE_STYLE[(1, 2)][0]),
                            ("卒（1x1）", PIECE_STYLE[(1, 1)][0])):
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            dot = QLabel()
            dot.setFixedSize(11, 11)
            dot.setStyleSheet("background:%s;border-radius:5px;" % color)
            lb = QLabel(name)
            lb.setStyleSheet("color:%s;font-size:12px;" % C_DIM)
            rl.addWidget(dot)
            rl.addSpacing(4)
            rl.addWidget(lb)
            rl.addStretch(1)
            row.setFixedHeight(20)
            l2.addWidget(row)
        l2.addWidget(QLabel(""))
        side.addWidget(c2)

        c3, l3 = card("快捷键")
        for k, v in (("选中后移动", "方向键 / WASD"), ("撤销", "Ctrl+Z"),
                     ("提示", "H"), ("重置", "R")):
            stat_row(l3, k, v)
        side.addWidget(c3)
        side.addStretch(1)

        wrap = QWidget()
        wrap.setLayout(side)
        wrap.setFixedWidth(258)
        root.addWidget(vscroll(wrap, 284))
        self.body.addLayout(root, 1)

    # -------- 生命周期
    def _boot(self):
        st = self.store.data.get("state")
        lv = int(self.store.data["meta"].get("currentLevel", 1))
        if st and st.get("layout"):
            self._load_level(int(st.get("level", lv)), st)
            QTimer.singleShot(300, lambda: flash_status(self, "已恢复上次进度"))
        else:
            self._load_level(lv)

    def _level_data(self, no):
        for lv in self.levels:
            if lv["level"] == no:
                return lv
        return self.levels[0]

    def _load_level(self, no, state=None):
        self.gen += 1
        lv = self._level_data(no)
        self.current = lv["level"]
        self.board.game.reset(lv["layout"])
        if state and state.get("pieces"):
            for p, saved in zip(self.board.game.pieces, state["pieces"]):
                p["x"], p["y"] = saved["x"], saved["y"]
            self.board.game.moves = state.get("moves", 0)
            self.elapsed = state.get("elapsed", 0.0)
        else:
            self.board.game.moves = 0
            self.elapsed = 0.0
        self.board.sel = -1
        self.board.hint = None
        self.finished = False
        self.auto_playing = False
        self._stop_auto()
        self.lb_name.setText(lv["name"])
        self.lb_min.setText("最少 %s 步" % (lv["minSteps"] if lv["minSteps"] else "--"))
        self.sb_min.setText(str(lv["minSteps"]) if lv["minSteps"] else "--")
        self.running = True
        self._last_tick = time.time()
        self._refresh()
        self._save()

    # -------- 计时
    def _tick(self):
        now = time.time()
        if self.running and not self.finished:
            self.elapsed += now - self._last_tick
        self._last_tick = now
        self.lb_timer.setText(fmt_time(int(self.elapsed * 1000)))
        if int(self.elapsed) % 5 == 0 and self.running and not self.finished:
            self._save()

    # -------- 状态
    def _refresh(self):
        g = self.board.game
        self.lb_level.setText("第 %d 关" % self.current)
        self.lb_steps.setText("%d 步" % g.moves)
        self.sb_size.setText(str(g.moves))
        rec = self.store.data["levels"].get(str(self.current), {})
        self.sb_best.setText("%d 步" % rec["bestSteps"] if rec.get("bestSteps") else "--")
        self.sb_win.setText("%d 次" % rec.get("clears", 0))
        self.lb_timer.setStyleSheet("font-size:20px;font-weight:700;color:%s;"
                                    % (C_TEXT if self.running else C_FAINT))
        self.board.locked = self.finished or self.auto_playing
        self.board.update()

    def on_moved(self):
        self._refresh()
        self._save()
        if self.board.game.solved():
            self._win()

    # -------- 操作
    def undo(self):
        if self.auto_playing:
            self._stop_auto()
        if self.board.game.undo():
            self.board.hint = None
            self.finished = False
            self._refresh()
            self._save()

    def reset_level(self):
        self._stop_auto()
        self._load_level(self.current)

    def hint(self):
        if self.finished or self.auto_playing:
            return
        g = self.board.game
        lv = self._level_data(self.current)
        # 若还在初始局面且已有预算好的最优解，直接用第一手
        if g.moves == 0 and lv.get("solution"):
            mv = lv["solution"][0]
            self.board.hint = mv
            self.board.update()
            flash_status(self, "按高亮棋子与箭头方向移动")
            return
        if self.worker and self.worker.isRunning():
            return
        flash_status(self, "正在计算最优走法…")
        self.btn_hint.setEnabled(False)
        self.worker = SolverWorker(g)
        self.keeper.add(self.worker)
        self.worker.done.connect(lambda p, gen=self.gen: self._on_hint(p, gen))
        self.worker.start()

    def _on_hint(self, path, gen=0):
        self.btn_hint.setEnabled(True)
        if gen != self.gen:
            return
        if not path:
            flash_status(self, "从当前局面已无法通关，建议撤销或重置")
            return
        self.board.hint = path[0]
        self.board.update()
        flash_status(self, "按高亮棋子与箭头方向移动，剩余 %d 步" % len(path))

    def toggle_auto(self):
        if self.auto_playing:
            self._stop_auto()
            return
        if self.finished:
            return
        lv = self._level_data(self.current)
        if self.board.game.moves == 0 and lv.get("solution"):
            self._start_auto(list(lv["solution"]))
            return
        if self.worker and self.worker.isRunning():
            return
        flash_status(self, "正在计算最优走法…")
        self.btn_auto.setEnabled(False)
        self.worker = SolverWorker(self.board.game)
        self.keeper.add(self.worker)
        self.worker.done.connect(lambda p, gen=self.gen: self._on_auto_ready(p, gen))
        self.worker.start()

    def _on_auto_ready(self, path, gen=0):
        self.btn_auto.setEnabled(True)
        if gen != self.gen:
            return
        if not path:
            flash_status(self, "当前局面无法通关")
            return
        self._start_auto(path)

    def _start_auto(self, path):
        self.auto_playing = True
        self.auto_path = list(path)
        self.btn_auto.setText("停止演示")
        self.board.hint = None
        self._refresh()
        self.auto_timer.start(220)

    def _auto_step(self):
        if not self.auto_playing or not self.auto_path:
            self._stop_auto()
            return
        mv = self.auto_path.pop(0)
        if not self.board.game.apply_move_dict(mv):
            self._stop_auto()
            return
        self._refresh()
        if not self.auto_path:
            self._stop_auto()
            if self.board.game.solved():
                self._win(auto=True)
            return
        if self.board.game.solved():
            self._stop_auto()
            self._win(auto=True)

    def _stop_auto(self):
        self.auto_playing = False
        self.auto_path = []
        self.auto_timer.stop()
        self.btn_auto.setText("自动求解演示")
        self.board.locked = self.finished
        self.board.update()

    # -------- 通关
    def _win(self, auto=False):
        if self.finished:
            return
        self.finished = True
        self.running = False
        g = self.board.game
        lv = self._level_data(self.current)
        if auto:
            # 自动演示不计成绩、不推进关卡
            self.store.data["state"] = None
            self.store.save()
            self._refresh()
            flash_status(self, "自动演示完成：%d 步（最少 %s 步）；点「重置本关」可自己再走一遍"
                         % (g.moves, lv["minSteps"]), 6000)
            return
        rec = self.store.data["levels"].setdefault(str(self.current), {})
        rec["clears"] = rec.get("clears", 0) + 1
        prev = rec.get("bestSteps")
        is_best = prev is None or g.moves < prev
        if is_best:
            rec["bestSteps"] = g.moves
        meta = self.store.data["meta"]
        meta["currentLevel"] = min(len(self.levels),
                                   max(int(meta.get("currentLevel", 1)), self.current + 1))
        self.store.data["state"] = None
        self.store.save()
        self._refresh()
        self.board.update()
        QTimer.singleShot(220, lambda: self._show_win(g, lv, is_best))

    def _show_win(self, g, lv, is_best):
        rec = self.store.data["levels"].get(str(self.current), {})
        dlg = WinDialog(self, self.current, lv["name"], g.moves,
                        lv["minSteps"] or g.moves, int(self.elapsed * 1000),
                        rec.get("bestSteps"), self.current < len(self.levels))
        dlg.exec()
        if dlg.choice == "next" and self.current < len(self.levels):
            self._load_level(self.current + 1)
        elif dlg.choice == "levels":
            self.open_levels()
        else:
            self._load_level(self.current)

    def open_levels(self):
        dlg = LevelDialog(self, self.levels, self.store, self.current)
        if dlg.exec() == QDialog.Accepted and dlg.picked:
            self._load_level(dlg.picked)

    def _save(self):
        if self.finished:
            return
        self.store.data["state"] = {
            "level": self.current,
            "layout": self.board.game.layout,
            "moves": self.board.game.moves,
            "elapsed": self.elapsed,
            "pieces": [{"x": p["x"], "y": p["y"]} for p in self.board.game.pieces]}
        self.store.save()

    # -------- 键盘
    def keyPressEvent(self, ev):
        k = ev.key()
        if k == Qt.Key_Z and (ev.modifiers() & Qt.ControlModifier):
            self.undo()
        elif k == Qt.Key_H:
            self.hint()
        elif k == Qt.Key_R:
            self.reset_level()
        elif k == Qt.Key_Escape:
            self.close()
        else:
            self.board.setFocus()
            self.board.keyPressEvent(ev)

    def closeEvent(self, ev):
        self._stop_auto()
        self._save()
        self.store.save()
        self.keeper.stop_all()
        super().closeEvent(ev)


def launch():
    w = KlotskiWindow()
    w.show()
    return w


if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("华容道")
    app.setStyle("Fusion")
    if "--selftest" in sys.argv:
        w = KlotskiWindow()
        w.resize(1040, 900)
        for _ in range(20):
            app.processEvents()
        w.board.sel = 0
        w.board.hint = w._level_data(w.current).get("solution", [None])[0]
        w._refresh()
        for _ in range(10):
            app.processEvents()
        shot = os.path.join(HERE, "_selftest_klotski.png")
        w.grab().save(shot)
        print("KLOTSKI SELFTEST OK ->", shot, os.path.getsize(shot), "字节")
        w.close()
        sys.exit(0)
    w = KlotskiWindow()
    w.show()
    sys.exit(app.exec())
