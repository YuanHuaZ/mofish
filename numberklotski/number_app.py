# -*- coding: utf-8 -*-
"""
数字华容道 · 15 关（PySide6 / Qt）

数字滑块拼图：3×3 ~ 6×6，把 1..N²-1 按顺序归位。
自绘棋盘 + 滑动动画；点同一行/列的方块可整排滑动；方向键推方块；
3×3 给出最优提示，4×4 以上给出曼哈顿贪心提示。
"""
import os
import sys
import time

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QPointF, QRectF
from PySide6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QLinearGradient
from PySide6.QtWidgets import (QApplication, QWidget, QHBoxLayout, QVBoxLayout,
                               QGridLayout, QLabel, QDialog, QMessageBox,
                               QPushButton, QComboBox)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from numberklotski import engine as NE  # noqa: E402
from shared.common import (C_BG, C_PANEL, C_PANEL2, C_LINE, C_LINE2, C_TEXT, C_DIM,
                    C_FAINT, C_ACCENT, C_ACCENT2, C_DANGER, C_OK, C_GOLD,
                    rgba, mk_button, ToolButton, card, stat_row, vscroll,
                    load_game_json, BaseStore, GameWindow, flash_status, fmt_time,
                    WorkerKeeper, output_dir, remove_save)  # noqa: E402

ANIM_MS = 120


class NumberBoard(QWidget):
    """自绘数字滑块棋盘"""

    moved = Signal()
    settled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.puzzle = NE.NumberPuzzle(3)
        self.locked = True
        self.hint_idx = -1
        self.anim = None
        self.anim_p = 1.0
        self.last_moved = -1
        self.setMinimumSize(400, 400)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)

    # -------- 几何
    def _geom(self):
        w, h = self.width(), self.height()
        pad = 16
        avail = min(w - 2 * pad, h - 2 * pad)
        cell = avail / float(self.puzzle.n)
        ox = (w - cell * self.puzzle.n) / 2.0
        oy = (h - cell * self.puzzle.n) / 2.0
        return ox, oy, cell

    def _cell_at(self, pos):
        ox, oy, cell = self._geom()
        c = int((pos.x() - ox) // cell)
        r = int((pos.y() - oy) // cell)
        n = self.puzzle.n
        if 0 <= r < n and 0 <= c < n:
            return r * n + c
        return None

    # -------- 交互
    def mousePressEvent(self, ev):
        if self.locked or self.anim:
            return
        i = self._cell_at(ev.position())
        if i is None:
            return
        items = self.puzzle.slide_to(i)
        if items:
            self.hint_idx = -1
            self.last_moved = i
            self._start_anim(items)
            self.moved.emit()

    def keyPressEvent(self, ev):
        if self.locked or self.anim:
            super().keyPressEvent(ev)
            return
        m = {Qt.Key_Up: (1, 0), Qt.Key_Down: (-1, 0), Qt.Key_Left: (0, 1),
             Qt.Key_Right: (0, -1), Qt.Key_W: (1, 0), Qt.Key_S: (-1, 0),
             Qt.Key_A: (0, 1), Qt.Key_D: (0, -1)}
        if ev.key() in m:
            mv = self.puzzle.move_dir(*m[ev.key()])
            if mv:
                self.hint_idx = -1
                self.last_moved = mv[1]
                self._start_anim([mv])
                self.moved.emit()
            return
        super().keyPressEvent(ev)

    # -------- 动画
    def _start_anim(self, items):
        hole_from = items[0][1]
        hole_to = items[-1][0]
        self.anim = {"items": items, "hole": (hole_from, hole_to), "t0": time.time()}
        self.anim_p = 0.0
        self.timer.start()
        self.update()

    def _tick(self):
        if not self.anim:
            self.timer.stop()
            return
        p = (time.time() - self.anim["t0"]) * 1000.0 / ANIM_MS
        if p >= 1.0:
            self.anim = None
            self.anim_p = 1.0
            self.timer.stop()
            self.update()
            self.settled.emit()
            return
        self.anim_p = p
        self.update()

    # -------- 绘制
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        ox, oy, cell = self._geom()
        n = self.puzzle.n
        p.fillRect(self.rect(), QColor(C_BG))

        bw = cell * n
        p.setBrush(QBrush(QColor("#0f141c")))
        p.setPen(QPen(QColor(C_LINE), 1.3))
        p.drawRoundedRect(QRectF(ox - 8, oy - 8, bw + 16, bw + 16), 14, 14)

        over = {}
        hole_pos = None
        if self.anim:
            pr = self.anim_p
            for (src, dst) in self.anim["items"]:
                sr, sc = divmod(src, n)
                dr, dc = divmod(dst, n)
                over[dst] = (dr + (sr - dr) * (1 - pr), dc + (sc - dc) * (1 - pr))
            hf, ht = self.anim["hole"]
            hr, hc = divmod(hf, n)
            tr, tc = divmod(ht, n)
            hole_pos = (tr + (hr - tr) * (1 - pr), tc + (hc - tc) * (1 - pr))

        blank = self.puzzle.blank()
        for i in range(n * n):
            if i == blank:
                continue
            v = self.puzzle.tiles[i]
            if over:
                r, c = over.get(i, divmod(i, n))
            else:
                r, c = divmod(i, n)
            self._draw_tile(p, ox, oy, cell, r, c, v, i)

        if hole_pos is None:
            hole_pos = divmod(blank, n)
        hr, hc = hole_pos
        gap = cell * 0.055
        rect = QRectF(ox + hc * cell + gap, oy + hr * cell + gap,
                      cell - gap * 2, cell - gap * 2)
        p.setBrush(QBrush(QColor("#080b11")))
        p.setPen(QPen(QColor(C_LINE), 1.0))
        p.drawRoundedRect(rect, cell * 0.16, cell * 0.16)

    def _draw_tile(self, p, ox, oy, cell, r, c, v, idx):
        n = self.puzzle.n
        gap = cell * 0.055
        rect = QRectF(ox + c * cell + gap, oy + r * cell + gap,
                      cell - gap * 2, cell - gap * 2)
        radius = cell * 0.16
        inplace = self.puzzle.in_place(idx)
        g = QLinearGradient(rect.topLeft(), rect.bottomRight())
        if inplace:
            g.setColorAt(0.0, QColor("#3ddc97"))
            g.setColorAt(1.0, QColor("#1f9d68"))
        else:
            g.setColorAt(0.0, QColor("#4f8de8"))
            g.setColorAt(1.0, QColor("#2f5fb8"))
        p.setBrush(QBrush(g))
        if idx == self.hint_idx:
            p.setPen(QPen(QColor(C_GOLD), 3.0))
        elif idx == self.last_moved:
            p.setPen(QPen(QColor(C_ACCENT2), 2.0))
        else:
            p.setPen(QPen(QColor(0, 0, 0, 110), 1.0))
        p.drawRoundedRect(rect, radius, radius)

        f = QFont()
        f.setBold(True)
        f.setPointSizeF(max(9.0, cell * (0.40 if n <= 4 else 0.34)))
        p.setFont(f)
        p.setPen(QColor("#f2f7ff"))
        p.drawText(rect, Qt.AlignCenter, str(v))


class HintWorker(QThread):
    done = Signal(object)

    def __init__(self, puzzle):
        super().__init__()
        self.puzzle = puzzle

    def run(self):
        try:
            idx = self.puzzle.hint()
        except Exception:
            idx = None
        self.done.emit(idx)


# ------------------------------------------------------------------ 选关
class LevelDialog(QDialog):
    def __init__(self, parent, levels, store, cur):
        super().__init__(parent)
        self.setWindowTitle("选择关卡")
        self.setModal(True)
        self.picked = None
        self.resize(560, 520)
        self.setStyleSheet("QDialog{background:%s;}QLabel{color:%s;}" % (C_BG, C_TEXT))
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)
        t = QLabel("选择关卡")
        t.setStyleSheet("font-size:17px;font-weight:700;")
        root.addWidget(t)
        sub = QLabel("从 3×3 到 6×6，难度分逐关递增（入门 → 大师）；"
                     "点同一行/列的方块可整排滑动")
        sub.setStyleSheet("color:%s;font-size:12px;" % C_DIM)
        sub.setWordWrap(True)
        root.addWidget(sub)

        inner = QWidget()
        grid = QGridLayout(inner)
        grid.setSpacing(8)
        grid.setContentsMargins(0, 0, 6, 0)
        for idx, lv in enumerate(levels):
            no = lv["level"]
            rec = store.data.get("levels", {}).get(str(no), {})
            best = rec.get("bestMoves")
            txt = "第 %d 关  %s\n%s · 难度分 %d" % (
                no, lv["name"], lv.get("tier") or NE.tier_of(lv.get("score", 0))[0],
                lv.get("score", 0))
            if best:
                txt += " · 最佳 %d 步" % best
            b = QPushButton(txt)
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(60)
            ring = C_ACCENT if no == cur else C_LINE
            b.setStyleSheet(
                "QPushButton{background:%s;color:%s;border:1px solid %s;"
                "border-radius:10px;font-size:12px;%s}"
                "QPushButton:hover{background:#232b38;color:%s;border-color:%s;}"
                % (C_PANEL2, C_TEXT if rec.get("cleared") else C_DIM, ring,
                   "font-weight:700;" if rec.get("cleared") else "", C_TEXT, C_ACCENT2))
            b.clicked.connect(lambda _=False, x=no: self._pick(x))
            grid.addWidget(b, idx // 3, idx % 3)
        root.addWidget(vscroll(inner), 1)
        row = QHBoxLayout()
        row.addStretch(1)
        c = mk_button("关闭", parent=self)
        c.clicked.connect(self.reject)
        row.addWidget(c)
        root.addLayout(row)

    def _pick(self, no):
        self.picked = no
        self.accept()


class CustomDialog(QDialog):
    """自定义：选边长与打乱程度"""

    SIZES = [3, 4, 5, 6]
    SCRAMBLES = [20, 60, 150, 300]

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("自定义局面")
        self.setModal(True)
        self.result_val = None
        self.resize(360, 260)
        self.setStyleSheet("QDialog{background:%s;}QLabel{color:%s;}" % (C_BG, C_TEXT))
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)
        t = QLabel("自定义数字华容道")
        t.setStyleSheet("font-size:16px;font-weight:700;")
        root.addWidget(t)
        qss = ("QComboBox{background:%s;color:%s;border:1px solid %s;border-radius:9px;"
               "padding:6px 10px;font-size:13px;}"
               "QComboBox QAbstractItemView{background:%s;color:%s;"
               "selection-background-color:%s;outline:none;}"
               % (C_PANEL2, C_TEXT, C_LINE, C_PANEL2, C_TEXT, C_ACCENT))

        self.cmb_size = QComboBox()
        self.cmb_size.addItems(["%d×%d" % (n, n) for n in self.SIZES])
        self.cmb_size.setCurrentIndex(1)
        self.cmb_size.setStyleSheet(qss)
        root.addWidget(self._labeled("棋盘边长", self.cmb_size))

        self.cmb_scr = QComboBox()
        self.cmb_scr.addItems(["轻松 %d 步" % s for s in self.SCRAMBLES])
        self.cmb_scr.setCurrentIndex(1)
        self.cmb_scr.setStyleSheet(qss)
        root.addWidget(self._labeled("打乱程度", self.cmb_scr))

        root.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        ok = mk_button("开始", "primary", self)
        ok.clicked.connect(self._ok)
        cancel = mk_button("取消", parent=self)
        cancel.clicked.connect(self.reject)
        row.addWidget(ok)
        row.addWidget(cancel)
        root.addLayout(row)

    def _labeled(self, title, widget):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lb = QLabel(title)
        lb.setStyleSheet("color:%s;font-size:12px;" % C_DIM)
        lay.addWidget(lb)
        lay.addWidget(widget)
        return w

    def _ok(self):
        n = self.SIZES[self.cmb_size.currentIndex()]
        s = self.SCRAMBLES[self.cmb_scr.currentIndex()]
        self.result_val = (n, s)
        self.accept()


class WinDialog(QDialog):
    def __init__(self, parent, level, name, moves, elapsed, is_best, best,
                 has_next):
        super().__init__(parent)
        self.setWindowTitle("完成")
        self.setModal(True)
        self.choice = "next"
        self.resize(420, 300)
        self.setStyleSheet("QDialog{background:%s;}QLabel{color:%s;}" % (C_PANEL, C_TEXT))
        root = QVBoxLayout(self)
        root.setContentsMargins(25, 22, 25, 20)
        root.setSpacing(8)
        t = QLabel("第 %d 关 · %s · 归位完成！" % (level, name))
        t.setStyleSheet("font-size:16px;font-weight:700;")
        t.setAlignment(Qt.AlignCenter)
        root.addWidget(t)
        v = QLabel("%d 步" % moves)
        v.setStyleSheet("font-size:38px;font-weight:700;color:%s;" % C_ACCENT2)
        v.setAlignment(Qt.AlignCenter)
        root.addWidget(v)
        note = QLabel("用时 %s　·　%s" % (fmt_time(elapsed),
                                        ("新纪录 ✦" if is_best else
                                         "本关最佳 %s 步" % (best if best else "--"))))
        note.setStyleSheet("color:%s;font-size:12.5px;" % C_DIM)
        note.setAlignment(Qt.AlignCenter)
        root.addWidget(note)
        root.addSpacing(6)
        nxt = mk_button(("进入第 %d 关" % (level + 1)) if has_next else "全部关卡完成 🎉",
                        "primary", self)
        nxt.setEnabled(has_next)
        nxt.clicked.connect(lambda: self._go("next"))
        root.addWidget(nxt)
        row = QHBoxLayout()
        rep = mk_button("再玩一次", parent=self)
        rep.clicked.connect(lambda: self._go("replay"))
        sel = mk_button("选关", parent=self)
        sel.clicked.connect(lambda: self._go("levels"))
        row.addWidget(rep)
        row.addWidget(sel)
        root.addLayout(row)

    def _go(self, c):
        self.choice = c
        self.accept()


# ------------------------------------------------------------------ 主窗口
class NumberPuzzleWindow(GameWindow):
    game_key = "number"
    game_name = "数字华容道"
    game_emoji = "🧮"

    def __init__(self):
        super().__init__()
        data = load_game_json("levels.json", "numberklotski")
        self.levels = data.get("levels") or NE.build_levels()
        self.store = BaseStore("number_save.json",
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
        self.custom = None
        self._last_tick = time.time()
        self.resize(1010, 880)
        self.setMinimumSize(840, 640)
        self._build_ui()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(200)
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
        self.lb_name = QLabel("3×3")
        self.lb_name.setStyleSheet("font-size:16px;font-weight:700;")
        head.addWidget(self.lb_name)
        self.lb_scr = QLabel("难度 10")
        self.lb_scr.setStyleSheet("color:%s;background:%s;border:1px solid %s;"
                                  "border-radius:11px;padding:3px 9px;font-size:11.5px;"
                                  "font-weight:600;"
                                  % (C_GOLD, rgba(C_GOLD, 0.12), rgba(C_GOLD, 0.35)))
        head.addWidget(self.lb_scr)
        head.addStretch(1)
        self.lb_moves = QLabel("0 步")
        self.lb_moves.setStyleSheet("font-size:22px;font-weight:700;color:%s;" % C_ACCENT2)
        head.addWidget(self.lb_moves)
        left.addLayout(head)

        self.board = NumberBoard()
        self.board.moved.connect(self.on_moved)
        self.board.settled.connect(self.on_settled)
        left.addWidget(self.board, 1)

        self.lb_meta = QLabel("点方块滑动（同行/同列可整排滑）；方向键推动方块")
        self.lb_meta.setStyleSheet("color:%s;font-size:11.5px;" % C_FAINT)
        left.addWidget(self.lb_meta)
        root.addLayout(left, 1)

        side = QVBoxLayout()
        side.setSpacing(12)
        act = QGridLayout()
        act.setSpacing(8)
        self.btn_undo = mk_button("撤销一步", parent=self)
        self.btn_undo.clicked.connect(self.undo)
        self.btn_reshuffle = mk_button("重开本关", parent=self)
        self.btn_reshuffle.clicked.connect(self.restart)
        act.addWidget(self.btn_undo, 0, 0)
        act.addWidget(self.btn_reshuffle, 0, 1)
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
        self.btn_custom = mk_button("自定义局面", parent=self)
        self.btn_custom.clicked.connect(self.open_custom)
        side.addWidget(self.btn_custom)

        c, l = card("本关信息")
        self.sb_size = stat_row(l, "棋盘", "3×3")
        self.sb_tier = stat_row(l, "难度档位", "--")
        self.sb_score = stat_row(l, "难度分", "--")
        self.sb_placed = stat_row(l, "已归位", "0 / 8")
        self.sb_dist = stat_row(l, "当前还差（曼哈顿）", "0")
        self.sb_best = stat_row(l, "最佳纪录", "--")
        self.sb_win = stat_row(l, "完成次数", "0 次")
        side.addWidget(c)

        c2, l2 = card("玩法")
        for k, v in (("滑动", "点相邻方块"), ("整排滑", "点同行/列方块"),
                     ("键盘", "方向键 / WASD"), ("绿块", "已经归位")):
            stat_row(l2, k, v)
        side.addWidget(c2)

        c3, l3 = card("快捷键")
        for k, v in (("撤销", "Ctrl+Z"), ("提示", "H"), ("重开", "Ctrl+R")):
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
        if st and st.get("tiles"):
            self.custom = None
            self._load(st.get("config"), state=st)
            QTimer.singleShot(300, lambda: flash_status(self, "已恢复上次进度"))
        else:
            self._load(self._level_data(int(self.store.data["meta"].get("currentLevel", 1))))

    def _level_data(self, no):
        for lv in self.levels:
            if lv["level"] == no:
                return lv
        return self.levels[0]

    def _load(self, cfg, state=None):
        """cfg：关卡 dict（含 level/n/tiles）或自定义 dict"""
        self.gen += 1
        n = int(cfg.get("n", 3))
        tiles = list(cfg.get("tiles") or NE.shuffle(n, cfg.get("scramble", 20)))
        self.cfg = dict(cfg)
        self.board.puzzle = NE.NumberPuzzle(n, tiles)
        self.board.hint_idx = -1
        self.board.last_moved = -1
        self.board.anim = None
        self.elapsed = 0.0
        self.finished = False
        if state and state.get("moves"):
            self.board.puzzle.moves = int(state.get("moves", 0))
            self.elapsed = state.get("elapsed", 0.0)
        self.lb_name.setText(cfg.get("name") or "%d×%d" % (n, n))
        score = cfg.get("score")
        tier = cfg.get("tier")
        if score is None:
            dist0 = self.board.puzzle.manhattan()
            score = NE.difficulty_score(n, dist0)
            tier = NE.tier_of(score)[0]
        self.lb_scr.setText("%s · 难度分 %d" % (tier, score))
        col = NE.tier_of(score)[1]
        self.lb_scr.setStyleSheet(
            "color:%s;background:%s;border:1px solid %s;border-radius:11px;"
            "padding:3px 9px;font-size:11.5px;font-weight:600;"
            % (col, rgba(col, 0.12), rgba(col, 0.35)))
        self._tier = tier
        self._score = score
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

    # -------- 状态
    def _refresh(self):
        pz = self.board.puzzle
        n = pz.n
        total = n * n - 1
        self.lb_level.setText(("第 %d 关" % self.cfg["level"]) if self.cfg.get("level")
                              else "自定义")
        self.lb_moves.setText("%d 步" % pz.moves)
        self.sb_size.setText("%d×%d" % (n, n))
        self.sb_tier.setText(getattr(self, "_tier", "--"))
        self.sb_score.setText(str(getattr(self, "_score", "--")))
        self.sb_placed.setText("%d / %d" % (pz.placed(), total))
        self.sb_dist.setText(str(pz.manhattan()))
        rec = self.store.data["levels"].get(str(self.cfg.get("level")), {})
        self.sb_best.setText(("%d 步" % rec["bestMoves"]) if rec.get("bestMoves") else "--")
        self.sb_win.setText("%d 次" % rec.get("clears", 0))
        self.lb_timer.setStyleSheet("font-size:20px;font-weight:700;color:%s;"
                                    % (C_TEXT if self.running else C_FAINT))
        self.board.locked = self.finished
        self.board.update()

    def on_moved(self):
        self._refresh()
        self._save()

    def on_settled(self):
        if self.board.puzzle.solved():
            self._win()

    # -------- 操作
    def undo(self):
        if self.finished or self.board.anim:
            return
        if self.board.puzzle.undo():
            self.board.hint_idx = -1
            self._refresh()
            self._save()

    def restart(self):
        cfg = dict(self.cfg)
        cfg.pop("level", None)
        cfg["tiles"] = NE.shuffle(int(cfg["n"]), int(cfg.get("scramble", 20)))
        self._load(cfg)

    def hint(self):
        if self.finished or self.board.anim or self.worker:
            return
        if self.board.puzzle.solved():
            return
        if self.board.puzzle.n == 3:
            flash_status(self, "正在计算最优解…")
        else:
            flash_status(self, "正在计算提示…")
        self.btn_hint.setEnabled(False)
        gen = self.gen
        self.worker = HintWorker(self.board.puzzle)
        self.keeper.add(self.worker)
        self.worker.done.connect(lambda idx, g=gen: self._on_hint(idx, g))
        self.worker.start()

    def _on_hint(self, idx, gen=0):
        self.btn_hint.setEnabled(True)
        self.worker = None
        if gen != self.gen:
            return
        if idx is None:
            flash_status(self, "已经归位了")
            return
        self.board.hint_idx = idx
        self.board.update()
        r, c = divmod(idx, self.board.puzzle.n)
        flash_status(self, "提示：滑动第 %d 行第 %d 列格" % (r + 1, c + 1))

    def open_levels(self):
        dlg = LevelDialog(self, self.levels, self.store, self.cfg.get("level"))
        if dlg.exec() == QDialog.Accepted and dlg.picked:
            self._load(self._level_data(dlg.picked))

    def open_custom(self):
        dlg = CustomDialog(self)
        if dlg.exec() == QDialog.Accepted and dlg.result_val:
            n, scr = dlg.result_val
            cfg = {"n": n, "scramble": scr, "name": "自定义 %d×%d" % (n, n),
                   "tiles": NE.shuffle(n, scr)}
            self._load(cfg)

    # -------- 通关
    def _win(self):
        if self.finished:
            return
        self.finished = True
        self.running = False
        pz = self.board.puzzle
        no = self.cfg.get("level")
        is_best = False
        best = None
        if no:
            rec = self.store.data["levels"].setdefault(str(no), {})
            rec["clears"] = rec.get("clears", 0) + 1
            prev = rec.get("bestMoves")
            is_best = prev is None or pz.moves < prev
            if is_best:
                rec["bestMoves"] = pz.moves
            best = rec.get("bestMoves")
            meta = self.store.data["meta"]
            meta["currentLevel"] = min(len(self.levels),
                                       max(int(meta.get("currentLevel", 1)), no + 1))
        self.store.data["state"] = None
        self.store.save()
        self._refresh()
        if not no:
            flash_status(self, "自定义局面完成：%d 步" % pz.moves, 4000)
            return
        dlg = WinDialog(self, no, self.cfg.get("name", ""), pz.moves,
                        int(self.elapsed * 1000), is_best, best, no < len(self.levels))
        dlg.exec()
        if dlg.choice == "next" and no < len(self.levels):
            self._load(self._level_data(no + 1))
        elif dlg.choice == "levels":
            self.open_levels()
        else:
            self._load(self._level_data(no))

    def _save(self):
        if self.finished:
            return
        self.store.data["state"] = {
            "config": {k: v for k, v in self.cfg.items() if k != "tiles"},
            "tiles": list(self.board.puzzle.tiles),
            "moves": self.board.puzzle.moves,
            "elapsed": self.elapsed}
        self.store.save()

    # -------- 键盘
    def keyPressEvent(self, ev):
        k = ev.key()
        if k == Qt.Key_Z and (ev.modifiers() & Qt.ControlModifier):
            self.undo()
        elif k == Qt.Key_H:
            self.hint()
        elif k == Qt.Key_R and (ev.modifiers() & Qt.ControlModifier):
            self.restart()
        elif k == Qt.Key_Escape:
            self.close()
        else:
            self.board.setFocus()
            self.board.keyPressEvent(ev)

    def closeEvent(self, ev):
        self._save()
        self.store.save()
        self.keeper.stop_all()
        super().closeEvent(ev)


def launch():
    w = NumberPuzzleWindow()
    w.show()
    return w


if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("数字华容道")
    app.setStyle("Fusion")
    if "--selftest" in sys.argv:
        remove_save("number_save.json")
        w = NumberPuzzleWindow()
        w.resize(1010, 880)
        lv = w.levels[5]
        w._load(lv)
        # 走几步展示归位效果
        for i in w.board.puzzle.movable()[:3]:
            w.board.puzzle.move_at(i)
        w.board.puzzle.moves = 12
        w.board.hint_idx = w.board.puzzle.movable()[0]
        w._refresh()
        for _ in range(15):
            app.processEvents()
        shot = os.path.join(output_dir(), "_selftest_number.png")
        w.grab().save(shot)
        print("NUMBER SELFTEST OK ->", shot, os.path.getsize(shot), "字节")
        w.close()
        sys.exit(0)
    w = NumberPuzzleWindow()
    w.show()
    sys.exit(app.exec())
