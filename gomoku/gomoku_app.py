# -*- coding: utf-8 -*-
"""
五子棋 · 人机对战（PySide6 / Qt）

自绘 15x15 棋盘：暗色木纹底、渐变棋子、落子序号、最后一手标记、胜利连线高亮。
支持难度（简单 / 普通 / 困难）、执黑/执白、悔棋、提示、重开与战绩统计。
"""
import os
import sys
from PySide6.QtCore import Qt, QThread, Signal, QPointF, QRectF, QTimer
from PySide6.QtGui import (QPainter, QColor, QFont, QPen, QBrush, QRadialGradient,
                           QLinearGradient)
from PySide6.QtWidgets import (QApplication, QWidget, QHBoxLayout, QVBoxLayout,
                               QGridLayout, QLabel, QComboBox, QMessageBox,
                               QDialog, QTableWidget, QTableWidgetItem, QHeaderView)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from gomoku import engine as GE  # noqa: E402
from shared.common import (C_BG, C_PANEL, C_PANEL2, C_LINE, C_LINE2, C_TEXT, C_DIM,
                    C_FAINT, C_ACCENT, C_ACCENT2, C_DANGER, C_OK, C_GOLD,
                    rgba, mk_button, ToolButton, card, stat_row, vscroll,
                    BaseStore, GameWindow, flash_status, WorkerKeeper)  # noqa: E402
from shared.lan_dialog import ask_lan  # noqa: E402

N = GE.SIZE
STARS = [(3, 3), (11, 3), (3, 11), (11, 11), (7, 7)]

C_BOARD = "#1b2230"
C_BOARD2 = "#161c28"
C_GRID = "#4a5a72"
LEVELS = [("easy", "简单"), ("normal", "普通"), ("hard", "困难")]


class BoardView(QWidget):
    """自绘五子棋棋盘"""

    placed = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.game = GE.Gomoku()
        self.hover = None
        self.show_numbers = False
        self.hint_pos = None
        self.locked = True
        self.setMinimumSize(420, 420)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)

    # -------- 几何
    ML, MT, MR, MB = 34, 30, 18, 18

    def _geom(self):
        w, h = self.width(), self.height()
        aw, ah = w - self.ML - self.MR, h - self.MT - self.MB
        cell = min(aw, ah) / float(N - 1)
        ox = self.ML + (aw - cell * (N - 1)) / 2.0
        oy = self.MT + (ah - cell * (N - 1)) / 2.0
        return ox, oy, cell

    def _at(self, pos):
        ox, oy, cell = self._geom()
        x = round((pos.x() - ox) / cell)
        y = round((pos.y() - oy) / cell)
        if 0 <= x < N and 0 <= y < N:
            return int(x), int(y)
        return None

    def mousePressEvent(self, ev):
        p = self._at(ev.position())
        if p and not self.locked:
            self.placed.emit(p[0], p[1])

    def mouseMoveEvent(self, ev):
        p = self._at(ev.position())
        if p != self.hover:
            self.hover = p
            self.update()

    def leaveEvent(self, ev):
        if self.hover:
            self.hover = None
            self.update()

    # -------- 绘制
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        ox, oy, cell = self._geom()
        p.fillRect(self.rect(), QColor(C_BG))

        size = cell * (N - 1)
        g = QLinearGradient(ox, oy, ox + size, oy + size)
        g.setColorAt(0, QColor(C_BOARD))
        g.setColorAt(1, QColor(C_BOARD2))
        p.setBrush(QBrush(g))
        p.setPen(QPen(QColor(C_LINE2), 1.4))
        p.drawRoundedRect(QRectF(ox - cell * 0.62, oy - cell * 0.62,
                                 size + cell * 1.24, size + cell * 1.24), 12, 12)

        p.setPen(QPen(QColor(C_GRID), 1.0))
        for k in range(N):
            p.drawLine(QPointF(ox, oy + k * cell), QPointF(ox + size, oy + k * cell))
            p.drawLine(QPointF(ox + k * cell, oy), QPointF(ox + k * cell, oy + size))

        p.setBrush(QBrush(QColor(C_GRID)))
        p.setPen(Qt.NoPen)
        for (sx, sy) in STARS:
            p.drawEllipse(QPointF(ox + sx * cell, oy + sy * cell), cell * 0.10, cell * 0.10)

        # 坐标
        f = QFont()
        f.setPointSizeF(max(7.0, cell * 0.30))
        p.setFont(f)
        p.setPen(QColor(C_FAINT))
        letters = "ABCDEFGHIJKLMNO"
        for k in range(N):
            p.drawText(QRectF(ox + k * cell - cell / 2, 1, cell, self.MT - 5),
                       Qt.AlignCenter, letters[k])
            p.drawText(QRectF(1, oy + k * cell - cell / 2, ox - 7, cell),
                       Qt.AlignRight | Qt.AlignVCenter, str(k + 1))

        # 落子序号
        move_index = {(mx, my): i + 1 for i, (mx, my, _p) in enumerate(self.game.moves)}

        # 最后一手的标记
        last = self.game.last_move()

        # 悬停虚影
        if self.hover and not self.locked:
            hx, hy = self.hover
            if self.game.board[hy][hx] == GE.EMPTY and not self.game.winner:
                col = QColor("#0d1117" if self.game.current == GE.BLACK else "#e8eef7")
                col.setAlpha(70)
                p.setBrush(QBrush(col))
                p.setPen(Qt.NoPen)
                p.drawEllipse(QPointF(ox + hx * cell, oy + hy * cell), cell * 0.44, cell * 0.44)

        # 棋子
        for y in range(N):
            for x in range(N):
                v = self.game.board[y][x]
                if not v:
                    continue
                cx, cy = ox + x * cell, oy + y * cell
                r = cell * 0.44
                cen = QPointF(cx - r * 0.28, cy - r * 0.32)
                rg = QRadialGradient(cen, r * 1.7)
                if v == GE.BLACK:
                    rg.setColorAt(0.0, QColor("#5b6675"))
                    rg.setColorAt(0.45, QColor("#252d3a"))
                    rg.setColorAt(1.0, QColor("#0a0d13"))
                else:
                    rg.setColorAt(0.0, QColor("#ffffff"))
                    rg.setColorAt(0.55, QColor("#dbe3ee"))
                    rg.setColorAt(1.0, QColor("#9fadc0"))
                p.setBrush(QBrush(rg))
                p.setPen(QPen(QColor(0, 0, 0, 90), 1.0))
                p.drawEllipse(QPointF(cx, cy), r, r)

                if self.show_numbers and move_index.get((x, y)):
                    f2 = QFont()
                    f2.setPointSizeF(max(6.0, cell * 0.34))
                    f2.setBold(True)
                    p.setFont(f2)
                    p.setPen(QColor("#e8eef7" if v == GE.BLACK else "#26303f"))
                    p.drawText(QRectF(cx - cell / 2, cy - cell / 2, cell, cell),
                               Qt.AlignCenter, str(move_index[(x, y)]))

        # 最后一手强调环
        if last and not self.game.winner:
            lx, ly, _ = last
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(C_GOLD), 2.2))
            p.drawEllipse(QPointF(ox + lx * cell, oy + ly * cell), cell * 0.17, cell * 0.17)

        # 提示点
        if self.hint_pos:
            hx, hy = self.hint_pos
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(C_OK), 2.4))
            p.drawEllipse(QPointF(ox + hx * cell, oy + hy * cell), cell * 0.46, cell * 0.46)

        # 胜利连线
        if self.game.win_cells:
            cells = self.game.win_cells
            xs = [c[0] for c in cells]
            ys = [c[1] for c in cells]
            p.setPen(QPen(QColor(C_DANGER), max(3.0, cell * 0.16), Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(ox + min(xs) * cell, oy + min(ys) * cell),
                       QPointF(ox + max(xs) * cell, oy + max(ys) * cell))


class AiWorker(QThread):
    done = Signal(object)

    def __init__(self, game, me, level):
        super().__init__()
        self.game, self.me, self.level = game, me, level

    def run(self):
        try:
            mv = self.game.best_move(self.me, self.level)
        except Exception:
            mv = None
        self.done.emit(mv)


# ------------------------------------------------------------------ 战绩
class RecordDialog(QDialog):
    def __init__(self, parent, store):
        super().__init__(parent)
        self.setWindowTitle("战绩")
        self.setModal(True)
        self.resize(560, 460)
        self.setStyleSheet(
            "QDialog{background:%s;}QLabel{color:%s;}"
            "QTableWidget{background:%s;color:%s;border:1px solid %s;"
            "gridline-color:%s;border-radius:10px;}"
            "QHeaderView::section{background:%s;color:%s;border:none;padding:7px;"
            "font-weight:600;}" % (C_BG, C_TEXT, C_PANEL, C_TEXT, C_LINE, C_LINE,
                                   C_PANEL, C_FAINT))
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)
        t = QLabel("五子棋战绩")
        t.setStyleSheet("font-size:17px;font-weight:700;")
        root.addWidget(t)
        rec = store.data.get("stats", {})
        row = QHBoxLayout()
        row.setSpacing(9)
        for val, cap in ((str(rec.get("win", 0)), "胜"),
                         (str(rec.get("lose", 0)), "负"),
                         (str(rec.get("draw", 0)), "平")):
            box = QLabel("%s\n%s" % (val, cap))
            box.setAlignment(Qt.AlignCenter)
            box.setStyleSheet("background:%s;border:1px solid %s;border-radius:10px;"
                              "padding:8px;font-size:16px;font-weight:700;"
                              % (C_PANEL2, C_LINE))
            row.addWidget(box, 1)
        root.addLayout(row)

        hist = store.data.get("history", [])[-60:][::-1]
        tb = QTableWidget(len(hist), 4)
        tb.setHorizontalHeaderLabels(["时间", "难度", "执子", "结果"])
        tb.verticalHeader().setVisible(False)
        tb.setEditTriggers(QTableWidget.NoEditTriggers)
        tb.setSelectionMode(QTableWidget.NoSelection)
        tb.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for r, h in enumerate(hist):
            for c, key in enumerate(("time", "level", "side", "result")):
                it = QTableWidgetItem(str(h.get(key, "")))
                if c == 3:
                    it.setForeground(QColor(C_OK if h.get("result") == "胜" else
                                            (C_DIM if h.get("result") == "平" else C_DANGER)))
                tb.setItem(r, c, it)
        root.addWidget(tb, 1)
        row2 = QHBoxLayout()
        row2.addStretch(1)
        b = mk_button("关闭", parent=self)
        b.clicked.connect(self.reject)
        row2.addWidget(b)
        root.addLayout(row2)


# ------------------------------------------------------------------ 主窗口
class GomokuWindow(GameWindow):
    game_key = "gomoku"
    game_name = "五子棋"
    game_emoji = "⚫"

    SIZE_BY_LEVEL = {"easy": 2200, "normal": 800, "hard": 380}

    def __init__(self):
        super().__init__()
        self.store = BaseStore("gomoku_save.json",
                               {"stats": {"win": 0, "lose": 0, "draw": 0},
                                "history": [], "state": None})
        self.store.data.setdefault("stats", {"win": 0, "lose": 0, "draw": 0})
        self.store.data.setdefault("history", [])
        self.worker = None
        self.keeper = WorkerKeeper()
        self.gen = 0
        self.human = GE.BLACK
        self.level = "normal"
        self.thinking = False
        self.finished = False
        self.net = None               # 局域网联机会话
        self.lan_seat = None
        self.lan_peer = ""
        self.resize(1000, 860)
        self.setMinimumSize(820, 640)
        self._build_ui()
        self._boot()

    # -------- UI
    def _build_ui(self):
        self.lb_turn = QLabel("黑棋先行")
        self.lb_turn.setStyleSheet("font-size:13px;font-weight:700;padding:5px 12px;"
                                   "border-radius:13px;background:%s;border:1px solid %s;"
                                   % (C_PANEL, C_LINE))
        self.bar_right.addWidget(self.lb_turn)
        self.lb_moves = QLabel("0 手")
        self.lb_moves.setStyleSheet("color:%s;font-size:13px;" % C_DIM)
        self.bar_right.addWidget(self.lb_moves)
        self.lb_lan = QLabel("")
        self.lb_lan.setStyleSheet("font-size:12.5px;font-weight:700;")
        self.bar_right.addWidget(self.lb_lan)

        root = QHBoxLayout()
        root.setSpacing(16)

        self.view = BoardView()
        self.view.placed.connect(self.human_play)
        root.addWidget(self.view, 1)

        side = QVBoxLayout()
        side.setSpacing(12)

        c1, l1 = card("对局")
        self.cmb_level = QComboBox()
        for _k, name in LEVELS:
            self.cmb_level.addItem(name)
        self.cmb_level.setCurrentIndex(1)
        self.cmb_level.currentIndexChanged.connect(self.on_level_change)
        self.cmb_level.setStyleSheet(self._combo_qss())
        l1.addWidget(self._labeled("难度", self.cmb_level))

        self.cmb_side = QComboBox()
        self.cmb_side.addItems(["我执黑（先手）", "我执白（后手）"])
        self.cmb_side.currentIndexChanged.connect(self.on_side_change)
        self.cmb_side.setStyleSheet(self._combo_qss())
        l1.addWidget(self._labeled("执子", self.cmb_side))
        side.addWidget(c1)

        c2, l2 = card("操作")
        grid = QGridLayout()
        grid.setSpacing(7)
        self.btn_undo = ToolButton("悔棋")
        self.btn_undo.clicked.connect(self.undo)
        self.btn_hint = ToolButton("提示")
        self.btn_hint.clicked.connect(self.hint)
        self.btn_num = ToolButton("手数")
        self.btn_num.setCheckable(True)
        self.btn_num.clicked.connect(self.toggle_numbers)
        self.btn_restart = ToolButton("重开")
        self.btn_restart.clicked.connect(self.restart)
        for i, b in enumerate((self.btn_undo, self.btn_hint, self.btn_num, self.btn_restart)):
            grid.addWidget(b, i // 2, i % 2)
        l2.addLayout(grid)
        side.addWidget(c2)

        c3, l3 = card("战绩")
        self.stat_win = stat_row(l3, "胜 / 负 / 平", "0 / 0 / 0")
        self.stat_rate = stat_row(l3, "胜率", "--")
        self.stat_len = stat_row(l3, "本局手数", "0")
        b = mk_button("查看战绩", parent=self)
        b.clicked.connect(lambda: RecordDialog(self, self.store).exec())
        l3.addWidget(b)
        side.addWidget(c3)

        c4, l4 = card("局域网联机")
        self.lb_net = QLabel("未联机")
        self.lb_net.setWordWrap(True)
        self.lb_net.setStyleSheet("color:%s;font-size:12px;" % C_FAINT)
        l4.addWidget(self.lb_net)
        self.btn_lan = mk_button("创建 / 加入房间", "primary", parent=self)
        self.btn_lan.clicked.connect(self.open_lan)
        l4.addWidget(self.btn_lan)
        self.btn_resign = mk_button("认输", parent=self)
        self.btn_resign.clicked.connect(self.resign)
        self.btn_lan_leave = mk_button("断开联机", parent=self)
        self.btn_lan_leave.setEnabled(False)
        self.btn_lan_leave.clicked.connect(self.leave_lan)
        row2 = QHBoxLayout()
        row2.setSpacing(7)
        row2.addWidget(self.btn_resign)
        row2.addWidget(self.btn_lan_leave)
        l4.addLayout(row2)
        side.addWidget(c4)

        c5, l5 = card("快捷键")
        for k, v in (("悔棋", "Ctrl+Z"), ("提示", "H"), ("重开", "Ctrl+R"),
                     ("手数", "M")):
            stat_row(l5, k, v)
        side.addWidget(c5)
        side.addStretch(1)

        wrap = QWidget()
        wrap.setLayout(side)
        wrap.setFixedWidth(258)
        root.addWidget(vscroll(wrap, 284))
        self.body.addLayout(root, 1)

    def _combo_qss(self):
        return ("QComboBox{background:%s;color:%s;border:1px solid %s;border-radius:9px;"
                "padding:6px 10px;font-size:13px;}"
                "QComboBox::drop-down{border:none;width:22px;}"
                "QComboBox QAbstractItemView{background:%s;color:%s;"
                "selection-background-color:%s;border:1px solid %s;outline:none;}"
                % (C_PANEL2, C_TEXT, C_LINE, C_PANEL2, C_TEXT, C_ACCENT, C_LINE))

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

    # -------- 启动
    def _boot(self):
        st = self.store.data.get("state")
        if st and st.get("moves"):
            self.view.game.load(st)
            self.human = st.get("human", GE.BLACK)
            self.level = st.get("level", "normal")
            self.cmb_side.setCurrentIndex(0 if self.human == GE.BLACK else 1)
            self.cmb_level.setCurrentIndex([k for k, _ in LEVELS].index(self.level))
            flash_status(self, "已恢复上次对局")
        self._refresh()
        if (not self.finished and self.view.game.current != self.human
                and not self.view.game.winner):
            self._ai_turn()

    # -------- 状态
    def _refresh(self):
        g = self.view.game
        self.view.locked = bool(g.winner) or g.current != self.human or self.thinking
        self.lb_moves.setText("%d 手" % len(g.moves))
        self.stat_len.setText(str(len(g.moves)))
        if self.net and self.net.connected:
            mine = "黑" if self.human == GE.BLACK else "白"
            self.lb_lan.setText("联机 · 我执%s · 对手 %s" % (mine, self.lan_peer or "对手"))
            self.lb_lan.setStyleSheet("font-size:12.5px;font-weight:700;color:%s;"
                                      % C_ACCENT2)
            self.lb_net.setText("对手：%s\n你执：%s方（%s）"
                                % (self.lan_peer or "对手", mine,
                                   "房主" if self.net.is_host else "加入方"))
            self.lb_net.setStyleSheet("color:%s;font-size:12px;" % C_OK)
        elif self.net:
            self.lb_lan.setText("联机 · 等待对手")
            self.lb_lan.setStyleSheet("font-size:12.5px;font-weight:700;color:%s;" % C_GOLD)
        else:
            self.lb_lan.setText("")
            self.lb_net.setText("未联机")
            self.lb_net.setStyleSheet("color:%s;font-size:12px;" % C_FAINT)
        rec = self.store.data["stats"]
        self.stat_win.setText("%d / %d / %d" % (rec.get("win", 0), rec.get("lose", 0),
                                                rec.get("draw", 0)))
        tot = sum(rec.values())
        self.stat_rate.setText("%.0f%%" % (rec.get("win", 0) * 100.0 / tot) if tot else "--")
        p = g.current
        if g.winner:
            txt = "黑棋胜" if g.winner == GE.BLACK else "白棋胜"
            self.lb_turn.setText(txt)
            self.lb_turn.setStyleSheet("font-size:13px;font-weight:700;padding:5px 12px;"
                                       "border-radius:13px;color:%s;background:%s;"
                                       "border:1px solid %s;" % (C_OK, rgba(C_OK, .14),
                                                                 rgba(C_OK, .4)))
        else:
            self.lb_turn.setText(("黑棋" if p == GE.BLACK else "白棋")
                                 + ("思考中…" if self.thinking else "落子"))
            self.lb_turn.setStyleSheet("font-size:13px;font-weight:700;padding:5px 12px;"
                                       "border-radius:13px;background:%s;border:1px solid %s;"
                                       % (C_PANEL, C_LINE))
        self.view.update()

    # -------- 落子
    def human_play(self, x, y):
        g = self.view.game
        if g.winner or self.thinking or g.current != self.human:
            return
        if not g.play(x, y):
            return
        self.view.hint_pos = None
        if self.net and self.net.connected:
            self.net.send({"t": "move", "mv": [x, y]})
        self._after_move()

    def _after_move(self):
        g = self.view.game
        self._refresh()
        self._save()
        if g.winner:
            self._finish()
            return
        if not g.can_play():
            self._finish(draw=True)
            return
        if self.net and self.net.connected:
            return                     # 联机：等对方落子
        if g.current != self.human:
            self._ai_turn()

    def _ai_turn(self):
        if self.net:
            return                     # 联机模式没有 AI
        if self.view.game.winner or not self.view.game.can_play():
            return
        self.thinking = True
        self._refresh()
        self._ai_started = QTimer(self)
        self._ai_started.setSingleShot(True)
        self._ai_started.timeout.connect(self._start_ai_worker)
        self._ai_started.start(60)

    def _start_ai_worker(self):
        me = GE.opponent(self.human)
        gen = self.gen
        self.worker = AiWorker(self.view.game, me, self.level)
        self.keeper.add(self.worker)
        self.worker.done.connect(lambda mv, p=me, g=gen: self._ai_done(mv, p, g))
        self.worker.start()

    def _ai_done(self, mv, player, gen=0):
        if gen != self.gen:
            return
        self.thinking = False
        g = self.view.game
        if mv and g.current == player and not g.winner:
            g.play(*mv)
        # 保证有最小停顿观感
        self._after_move()

    # -------- 结果
    def _finish(self, draw=False, lan_result=None):
        g = self.view.game
        self.finished = True
        if self.net and self.net.connected:
            if lan_result is None:
                if draw or not g.winner:
                    lan_result = "平"
                else:
                    lan_result = "胜" if g.winner == self.human else "负"
            self.store.data["state"] = None
            self.store.save()
            self._refresh()
            text = {"胜": "🎉 你赢了！", "负": "本局你输了。",
                    "平": "棋盘已满，平局。"}[lan_result]
            QMessageBox.information(self, "联机对局结束",
                                    "%s\n\n想再来一局就点「重开」向对手发起邀请。" % text)
            return
        rec = self.store.data["stats"]
        if draw:
            rec["draw"] = rec.get("draw", 0) + 1
            result = "平"
        elif g.winner == self.human:
            rec["win"] = rec.get("win", 0) + 1
            result = "胜"
        else:
            rec["lose"] = rec.get("lose", 0) + 1
            result = "负"
        from datetime import datetime
        self.store.data.setdefault("history", []).append({
            "time": datetime.now().strftime("%m-%d %H:%M"),
            "level": dict(LEVELS)[self.level],
            "side": "黑" if self.human == GE.BLACK else "白",
            "result": result})
        self.store.data["state"] = None
        self.store.save()
        self._refresh()
        if draw:
            QMessageBox.information(self, "平局", "棋盘已满，本局平局。")
        else:
            QMessageBox.information(self, "对局结束",
                                    "你%s了本局！" % ("赢" if result == "胜" else "输"))
        self.restart(silent=True)

    # -------- 操作
    def undo(self):
        if self.thinking or self.view.game.winner:
            return
        if self.net and self.net.connected:
            self.net.send({"t": "undo_req", "color": self.human})
            flash_status(self, "已向对手发起悔棋请求…")
            return
        g = self.view.game
        # 悔到轮到玩家为止（撤销 AI 的一手 + 自己的一手）
        steps = 1
        if g.moves and g.moves[-1][2] != self.human:
            steps = 2
        g.undo(min(steps, len(g.moves)))
        if g.moves and g.current != self.human:
            g.undo(1)
        self.view.hint_pos = None
        self.finished = False
        self._refresh()
        self._save()

    def hint(self):
        if self.thinking or self.view.game.winner or self.view.game.current != self.human:
            return
        mv = self.view.game.best_move(self.human, "hard")
        self.view.hint_pos = mv
        self.view.update()
        if mv:
            flash_status(self, "建议落点：%s%d" % ("ABCDEFGHIJKLMNO"[mv[0]], mv[1] + 1))

    def toggle_numbers(self):
        self.view.show_numbers = self.btn_num.isChecked()
        self.view.update()

    def restart(self, silent=False):
        if not silent:
            if self.net and self.net.connected:
                self.net.send({"t": "rematch_req"})
                flash_status(self, "已向对手发起「再来一局」，等待同意…", 4200)
                return
            r = QMessageBox.question(self, "重开", "确定重新开始一局？",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if r != QMessageBox.Yes:
                return
        self.gen += 1
        self.thinking = False
        self.finished = False
        self.view.game.reset()
        self.view.hint_pos = None
        self.store.data["state"] = None
        self.store.save()
        self._refresh()
        if self.view.game.current != self.human:
            self._ai_turn()

    def on_level_change(self, idx):
        self.level = LEVELS[idx][0]
        self.view.hint_pos = None
        self._save()

    def on_side_change(self, idx):
        if self.net:
            return                     # 联机时由房间决定执子
        self.human = GE.BLACK if idx == 0 else GE.WHITE
        self.restart(silent=True)

    # -------- 局域网联机
    def open_lan(self):
        if self.net and self.net.active:
            flash_status(self, "已经在联机了，先「断开联机」再重新创建")
            return
        info, sess = ask_lan(self, "gomoku", "黑方", "白方")
        if not info:
            return
        self.net = sess
        self.lan_seat = int(info.get("seat", 0))
        self.lan_peer = (info.get("peer") or {}).get("name", "对手")
        self.human = GE.BLACK if self.lan_seat == 0 else GE.WHITE
        sess.message.connect(self._on_lan_message)
        sess.closed.connect(self._on_lan_closed)
        sess.failed.connect(lambda e: flash_status(self, "联机出错：%s" % e, 5000))
        self.cmb_side.setEnabled(False)
        self.cmb_level.setEnabled(False)
        self.btn_lan_leave.setEnabled(True)
        self.btn_lan.setEnabled(False)
        self.restart(silent=True)
        flash_status(self, "已联机：你执%s棋，%s执%s棋。"
                     % ("黑" if self.human == GE.BLACK else "白", self.lan_peer,
                        "白" if self.human == GE.BLACK else "黑"), 5000)

    def leave_lan(self):
        if not self.net:
            return
        self._close_net()
        flash_status(self, "已断开联机，回到人机对战")

    def _close_net(self):
        net = self.net
        self.net = None
        if net is not None:
            try:
                net.close()
            except Exception:
                pass
        self.lan_seat = None
        self.lan_peer = ""
        if hasattr(self, "cmb_side"):
            self.cmb_side.setEnabled(True)
            self.cmb_level.setEnabled(True)
            self.btn_lan_leave.setEnabled(False)
            self.btn_lan.setEnabled(True)
        self._refresh()

    def _on_lan_closed(self, reason):
        if self.net is None:
            return
        self._close_net()
        QMessageBox.warning(self, "联机中断", "%s\n现在可以继续人机对战。" % reason)

    def _apply_undo(self, requester=None):
        """联机悔棋：撤销到发起方重新可下为止；双方按同一规则计算出同样的步数"""
        if requester is None:
            requester = self.human
        g = self.view.game
        if g.moves:
            g.undo(1)
            if g.moves and g.current != requester:
                g.undo(1)
        self.finished = False
        self.view.hint_pos = None
        self._refresh()

    def _on_lan_message(self, m):
        t = m.get("t")
        g = self.view.game
        if t == "move":
            if self.finished or not self.net:
                return
            mv = m.get("mv") or []
            if (g.current == self.human or g.winner or len(mv) != 2):
                return                 # 不是对手的回合 / 数据异常，忽略
            if g.play(int(mv[0]), int(mv[1])):
                self._after_move()
        elif t == "undo_req":
            who = m.get("color", GE.opponent(self.human))
            r = QMessageBox.question(self, "对手请求悔棋",
                                     "%s 请求悔棋，同意吗？" % self.lan_peer,
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if r == QMessageBox.Yes:
                self._apply_undo(who)
                self.net.send({"t": "undo_ok"})
                flash_status(self, "已同意对手悔棋")
            else:
                self.net.send({"t": "undo_no"})
        elif t == "undo_ok":
            self._apply_undo(self.human)
            flash_status(self, "对手同意悔棋")
        elif t == "undo_no":
            flash_status(self, "对手拒绝了悔棋", 4000)
        elif t == "rematch_req":
            r = QMessageBox.question(self, "对手邀请再来一局",
                                     "%s 想再来一局，接受吗？" % self.lan_peer,
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if r == QMessageBox.Yes:
                self._lan_rematch()
                self.net.send({"t": "rematch_ok"})
            else:
                self.net.send({"t": "rematch_no"})
        elif t == "rematch_ok":
            self._lan_rematch()
        elif t == "rematch_no":
            flash_status(self, "对手拒绝了再来一局", 4000)
        elif t == "resign":
            self.finished = True
            self.store.data["state"] = None
            self.store.save()
            self._refresh()
            QMessageBox.information(self, "对手认输", "%s 认输了，你赢了！🎉" % self.lan_peer)
        elif t == "bye":
            self._on_lan_closed("对手离开了房间")

    def _lan_rematch(self):
        """再来一局并交换先手（双方同时交换，保持一致）"""
        self.human = GE.WHITE if self.human == GE.BLACK else GE.BLACK
        self.restart(silent=True)
        flash_status(self, "新一局开始：你执%s棋"
                     % ("黑" if self.human == GE.BLACK else "白"), 4200)

    def resign(self):
        if self.finished:
            return
        side = "黑" if self.human == GE.BLACK else "白"
        if QMessageBox.question(self, "认输", "你执%s棋，确定认输？" % side,
                                QMessageBox.Yes | QMessageBox.No,
                                QMessageBox.No) != QMessageBox.Yes:
            return
        if self.net and self.net.connected:
            self.net.send({"t": "resign"})
            self.finished = True
            self.store.data["state"] = None
            self.store.save()
            self._refresh()
            QMessageBox.information(self, "认输", "你认输了，本局算对手赢。")
        else:
            if QMessageBox.question(self, "认输", "人机模式下认输会记为一场负，继续？",
                                    QMessageBox.Yes | QMessageBox.No,
                                    QMessageBox.No) != QMessageBox.Yes:
                return
            rec = self.store.data["stats"]
            rec["lose"] = rec.get("lose", 0) + 1
            self.store.data["state"] = None
            self.store.save()
            self.finished = True
            self._refresh()
            self.restart(silent=True)

    def _save(self):
        if self.finished or not self.view.game.moves or self.net:
            return
        self.store.data["state"] = dict(self.view.game.dump(), human=self.human,
                                        level=self.level)
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
        elif k == Qt.Key_M:
            self.btn_num.setChecked(not self.btn_num.isChecked())
            self.toggle_numbers()
        elif k == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(ev)

    def closeEvent(self, ev):
        self._save()
        self.store.save()
        self.keeper.stop_all()
        if self.net is not None:
            try:
                self.net.close()
            except Exception:
                pass
        super().closeEvent(ev)


def launch():
    w = GomokuWindow()
    w.show()
    return w


if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("五子棋")
    app.setStyle("Fusion")
    if "--selftest" in sys.argv:
        w = GomokuWindow()
        w.resize(1000, 860)
        for _ in range(20):
            app.processEvents()
        w.view.game.play(7, 7)
        w.view.game.play(7, 8)
        w.view.game.play(8, 7)
        w.view.game.play(6, 7)
        w.view.show_numbers = True
        w._refresh()
        for _ in range(10):
            app.processEvents()
        shot = os.path.join(HERE, "_selftest_gomoku.png")
        w.grab().save(shot)
        print("GOMOKU SELFTEST OK ->", shot, os.path.getsize(shot), "字节")
        w.close()
        sys.exit(0)
    w = GomokuWindow()
    w.show()
    sys.exit(app.exec())
