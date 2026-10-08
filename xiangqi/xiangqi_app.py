# -*- coding: utf-8 -*-
"""
中国象棋 · 人机 / 双人对战（PySide6 / Qt）

自绘 9x10 棋盘：楚河汉界、九宫斜线、炮兵位准星；
点选棋子后高亮可走点，走子生成中文记谱；Alpha-Beta AI 在后台线程运行。
"""
import os
import sys

from PySide6.QtCore import Qt, QThread, Signal, QPointF, QRectF, QTimer
from PySide6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QRadialGradient
from PySide6.QtWidgets import (QApplication, QWidget, QHBoxLayout, QVBoxLayout,
                               QGridLayout, QLabel, QComboBox, QMessageBox,
                               QTableWidget, QTableWidgetItem, QHeaderView)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from xiangqi import engine as XE  # noqa: E402
from shared.common import (C_BG, C_PANEL, C_PANEL2, C_LINE, C_LINE2, C_TEXT, C_DIM,
                    C_FAINT, C_ACCENT, C_ACCENT2, C_DANGER, C_OK, C_GOLD,
                    rgba, mk_button, ToolButton, card, stat_row, vscroll,
                    BaseStore, GameWindow, flash_status, WorkerKeeper,
                    remove_save, output_dir)  # noqa: E402
from shared.lan_dialog import ask_lan  # noqa: E402

LEVELS = [("easy", "简单"), ("normal", "普通"), ("hard", "困难")]
MODES = [("ai", "人机对战"), ("pvp", "双人对战")]
STAR_CANNON = [(1, 2), (7, 2), (1, 7), (7, 7)]
STAR_PAWN = [(0, 3), (2, 3), (4, 3), (6, 3), (8, 3),
             (0, 6), (2, 6), (4, 6), (6, 6), (8, 6)]


class BoardView(QWidget):
    """自绘象棋棋盘"""

    clicked = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.board = XE.initial_board()
        self.sel = -1
        self.targets = []
        self.last = None
        self.check_pos = -1
        self.locked = True
        self.flip = False
        self.setMinimumSize(420, 470)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)

    # -------- 几何
    R = 0.44            # 棋子半径 / 格子
    PAD_L, PAD_R, PAD_T, LABEL_H = 28, 14, 10, 26

    def _geom(self):
        w, h = self.width(), self.height()
        aw = w - self.PAD_L - self.PAD_R
        ah = h - self.PAD_T - self.LABEL_H
        cell = min(aw / (8 + 2 * self.R), ah / (9 + 2 * self.R))
        ox = self.PAD_L + (aw - 8 * cell) / 2.0
        oy = self.PAD_T + self.R * cell + (ah - (9 + 2 * self.R) * cell) / 2.0
        return ox, oy, cell

    def _pt(self, x, y):
        ox, oy, cell = self._geom()
        return ox + x * cell, oy + y * cell

    def _cell_at(self, pos):
        ox, oy, cell = self._geom()
        x = round((pos.x() - ox) / cell)
        y = round((pos.y() - oy) / cell)
        if 0 <= x < 9 and 0 <= y < 10:
            return x, y
        return None

    def mousePressEvent(self, ev):
        p = self._cell_at(ev.position())
        if p:
            self.clicked.emit(p[0], p[1])

    def set_board(self, board, sel=-1, targets=None, last=None, check_pos=-1):
        self.board = board
        self.sel = sel
        self.targets = targets or []
        self.last = last
        self.check_pos = check_pos
        self.update()

    # -------- 绘制
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        ox, oy, cell = self._geom()
        # 暖色棋盘：保留深色应用背景，但让象棋区域更像一张精致的漆木棋盘。
        p.fillRect(self.rect(), QColor("#0d1016"))

        bw, bh = cell * 8, cell * 9
        board_grad = QRadialGradient(QPointF(ox + bw * .38, oy + bh * .25), max(bw, bh) * .9)
        board_grad.setColorAt(0.0, QColor("#3a2a27"))
        board_grad.setColorAt(0.7, QColor("#241d20"))
        board_grad.setColorAt(1.0, QColor("#151820"))
        p.setBrush(QBrush(board_grad))
        p.setPen(QPen(QColor("#6b5047"), 1.6))
        p.drawRoundedRect(QRectF(ox - 11, oy - 11, bw + 22, bh + 22), 12, 12)

        ink = QColor("#c29a78")
        thin = QPen(ink, 1.1)
        thick = QPen(QColor("#e0b78d"), 1.8)

        # 横线
        p.setPen(thin)
        for k in range(10):
            p.drawLine(QPointF(ox, oy + k * cell), QPointF(ox + bw, oy + k * cell))
        # 竖线（中间 7 条在河界断开）
        for k in range(9):
            x = ox + k * cell
            if k in (0, 8):
                p.drawLine(QPointF(x, oy), QPointF(x, oy + bh))
            else:
                p.drawLine(QPointF(x, oy), QPointF(x, oy + 4 * cell))
                p.drawLine(QPointF(x, oy + 5 * cell), QPointF(x, oy + bh))
        # 外框加粗
        p.setPen(thick)
        p.drawRect(QRectF(ox - 5, oy - 5, bw + 10, bh + 10))

        # 九宫斜线
        p.setPen(thin)
        for (x1, y1, x2, y2) in ((3, 0, 5, 2), (5, 0, 3, 2), (3, 7, 5, 9), (5, 7, 3, 9)):
            p.drawLine(QPointF(*self._pt(x1, y1)), QPointF(*self._pt(x2, y2)))

        # 炮兵位准星
        p.setPen(QPen(ink, 1.1))
        for (x, y) in STAR_CANNON + STAR_PAWN:
            px, py = self._pt(x, y)
            d, g = cell * 0.13, cell * 0.07
            for sx in (-1, 1):
                for sy in (-1, 1):
                    if (x == 0 and sx < 0) or (x == 8 and sx > 0):
                        continue
                    p.drawLine(QPointF(px + sx * g, py + sy * g),
                               QPointF(px + sx * (g + d), py + sy * g))
                    p.drawLine(QPointF(px + sx * g, py + sy * g),
                               QPointF(px + sx * g, py + sy * (g + d)))

        # 楚河汉界
        f = QFont()
        f.setPointSizeF(max(9.0, cell * 0.34))
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(rgba("#f08c6c", 0.78)))
        ry = oy + 4.5 * cell
        p.drawText(QRectF(ox + cell * 0.4, ry - cell * 0.5, cell * 3, cell),
                   Qt.AlignCenter, "楚  河")
        p.drawText(QRectF(ox + cell * 4.6, ry - cell * 0.5, cell * 3, cell),
                   Qt.AlignCenter, "漢  界")

        # 坐标（底部字母 + 左侧数字，避开棋子）
        f2 = QFont()
        f2.setPointSizeF(max(7.0, cell * 0.24))
        p.setFont(f2)
        p.setPen(QColor(C_FAINT))
        ly = oy + (9 + self.R) * cell + 1
        for k in range(9):
            px, _ = self._pt(k, 0)
            p.drawText(QRectF(px - cell / 2, ly, cell, self.LABEL_H - 6),
                       Qt.AlignCenter, "ABCDEFGHI"[k])
        lw = ox - self.R * cell - 4
        for k in range(10):
            _, py = self._pt(0, k)
            p.drawText(QRectF(1, py - cell / 2, lw, cell),
                       Qt.AlignRight | Qt.AlignVCenter, str(k + 1))

        # 上一步痕迹
        if self.last:
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(rgba(C_ACCENT2, 0.65)), 2.0))
            for i in self.last:
                x, y = XE.xy(i)
                px, py = self._pt(x, y)
                p.drawRect(QRectF(px - cell * 0.44, py - cell * 0.44,
                                  cell * 0.88, cell * 0.88))

        # 可走点
        for i in self.targets:
            x, y = XE.xy(i)
            px, py = self._pt(x, y)
            if self.board[i]:
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(QColor(C_DANGER), 3.0))
                p.drawEllipse(QPointF(px, py), cell * 0.44, cell * 0.44)
            else:
                p.setBrush(QBrush(QColor(rgba(C_ACCENT2, 0.85))))
                p.setPen(Qt.NoPen)
                p.drawEllipse(QPointF(px, py), cell * 0.11, cell * 0.11)

        # 棋子
        for i, pc in enumerate(self.board):
            if not pc:
                continue
            x, y = XE.xy(i)
            px, py = self._pt(x, y)
            r = cell * 0.44
            red = pc[0] == XE.RED
            g = QRadialGradient(QPointF(px - r * 0.3, py - r * 0.34), r * 1.8)
            g.setColorAt(0.0, QColor("#fdf6e6"))
            g.setColorAt(0.6, QColor("#e8dcc2"))
            g.setColorAt(1.0, QColor("#c3b393"))
            p.setBrush(QBrush(g))
            p.setPen(QPen(QColor(C_GOLD if i == self.sel else "#6b5f49"),
                          3.0 if i == self.sel else 1.4))
            p.drawEllipse(QPointF(px, py), r, r)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(rgba("#8a7c60", 0.9)), 1.0))
            p.drawEllipse(QPointF(px, py), r * 0.82, r * 0.82)

            f3 = QFont()
            f3.setPointSizeF(max(11.0, cell * 0.50))
            f3.setBold(True)
            p.setFont(f3)
            p.setPen(QColor("#c0392b" if red else "#20293a"))
            p.drawText(QRectF(px - r, py - r, r * 2, r * 2), Qt.AlignCenter,
                       XE.PIECE_NAME[pc[1]][0 if red else 1])

        # 被将军的将/帅
        if self.check_pos >= 0:
            x, y = XE.xy(self.check_pos)
            px, py = self._pt(x, y)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(C_DANGER), 3.0))
            p.drawEllipse(QPointF(px, py), cell * 0.5, cell * 0.5)


class AiWorker(QThread):
    done = Signal(object)

    def __init__(self, board, color, level):
        super().__init__()
        self.board, self.color, self.level = board, color, level

    def run(self):
        try:
            eng = XE.Engine(self.level)
            mv = eng.choose_move(self.board, self.color)
        except Exception:
            mv = None
        self.done.emit(mv)


# ------------------------------------------------------------------ 主窗口
class XiangqiWindow(GameWindow):
    game_key = "xiangqi"
    game_name = "中国象棋"
    game_emoji = "♟"

    def __init__(self):
        super().__init__()
        self.store = BaseStore("xiangqi_save.json",
                               {"stats": {"win": 0, "lose": 0, "draw": 0},
                                "state": None})
        self.store.data.setdefault("stats", {"win": 0, "lose": 0, "draw": 0})
        self.store.data.setdefault("state", None)
        self.worker = None
        self.keeper = WorkerKeeper()
        self.gen = 0
        self.level = "normal"
        self.mode = "ai"
        self.human_color = XE.RED
        self.turn = XE.RED
        self.history = []          # [(fr, to, color, notation, captured)]
        self.finished = False
        self.thinking = False
        self.sel = -1
        self.targets = []
        self.last = None
        self.board = XE.initial_board()
        self.net = None               # 局域网联机会话
        self.lan_seat = None
        self.lan_peer = ""
        self.resize(1080, 900)
        self.setMinimumSize(900, 700)
        self._build_ui()
        self._boot()

    # -------- UI
    def _build_ui(self):
        self.lb_turn = QLabel("红方行棋")
        self.lb_turn.setStyleSheet("font-size:13px;font-weight:700;padding:5px 12px;"
                                   "border-radius:13px;background:%s;border:1px solid %s;"
                                   % (C_PANEL, C_LINE))
        self.bar_right.addWidget(self.lb_turn)
        self.lb_check = QLabel("")
        self.lb_check.setStyleSheet("color:%s;font-size:13px;font-weight:700;" % C_DANGER)
        self.bar_right.addWidget(self.lb_check)
        self.lb_lan = QLabel("")
        self.lb_lan.setStyleSheet("font-size:12.5px;font-weight:700;")
        self.bar_right.addWidget(self.lb_lan)

        root = QHBoxLayout()
        root.setSpacing(16)

        self.view = BoardView()
        self.view.clicked.connect(self.on_click)
        root.addWidget(self.view, 1)

        side = QVBoxLayout()
        side.setSpacing(12)

        c1, l1 = card("对局设置")
        self.cmb_mode = QComboBox()
        for _k, n in MODES:
            self.cmb_mode.addItem(n)
        self.cmb_mode.currentIndexChanged.connect(self.on_mode_change)
        self.cmb_mode.setStyleSheet(self._qss())
        l1.addWidget(self._labeled("模式", self.cmb_mode))

        self.cmb_level = QComboBox()
        for _k, n in LEVELS:
            self.cmb_level.addItem(n)
        self.cmb_level.setCurrentIndex(1)
        self.cmb_level.currentIndexChanged.connect(
            lambda i: setattr(self, "level", LEVELS[i][0]))
        self.cmb_level.setStyleSheet(self._qss())
        l1.addWidget(self._labeled("AI 难度", self.cmb_level))

        self.cmb_side = QComboBox()
        self.cmb_side.addItems(["我执红（先行）", "我执黑（后行）"])
        self.cmb_side.currentIndexChanged.connect(self.on_side_change)
        self.cmb_side.setStyleSheet(self._qss())
        l1.addWidget(self._labeled("执子", self.cmb_side))
        side.addWidget(c1)

        c2, l2 = card("操作")
        grid = QGridLayout()
        grid.setSpacing(7)
        self.btn_undo = ToolButton("悔棋")
        self.btn_undo.clicked.connect(self.undo)
        self.btn_hint = ToolButton("提示")
        self.btn_hint.clicked.connect(self.hint)
        self.btn_restart = ToolButton("重开")
        self.btn_restart.clicked.connect(self.restart)
        self.btn_resign = ToolButton("认输")
        self.btn_resign.clicked.connect(self.resign)
        for i, b in enumerate((self.btn_undo, self.btn_hint, self.btn_restart,
                               self.btn_resign)):
            grid.addWidget(b, i // 2, i % 2)
        l2.addLayout(grid)
        side.addWidget(c2)

        c3, l3 = card("棋谱")
        self.tb = QTableWidget(0, 3)
        self.tb.setHorizontalHeaderLabels(["#", "红方", "黑方"])
        self.tb.verticalHeader().setVisible(False)
        self.tb.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tb.setSelectionMode(QTableWidget.NoSelection)
        self.tb.setShowGrid(False)
        self.tb.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.tb.setColumnWidth(0, 34)
        self.tb.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tb.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tb.setMinimumHeight(210)
        self.tb.setStyleSheet(
            "QTableWidget{background:%s;color:%s;border:1px solid %s;border-radius:9px;}"
            "QHeaderView::section{background:%s;color:%s;border:none;padding:5px;"
            "font-weight:600;}" % (C_PANEL2, C_TEXT, C_LINE, C_PANEL, C_FAINT))
        l3.addWidget(self.tb)
        side.addWidget(c3, 1)

        c4, l4 = card("局域网联机")
        self.lb_net = QLabel("未联机")
        self.lb_net.setWordWrap(True)
        self.lb_net.setStyleSheet("color:%s;font-size:12px;" % C_FAINT)
        l4.addWidget(self.lb_net)
        self.btn_lan = mk_button("创建 / 加入房间", "primary", parent=self)
        self.btn_lan.clicked.connect(self.open_lan)
        l4.addWidget(self.btn_lan)
        self.btn_lan_leave = mk_button("断开联机", parent=self)
        self.btn_lan_leave.setEnabled(False)
        self.btn_lan_leave.clicked.connect(self.leave_lan)
        l4.addWidget(self.btn_lan_leave)
        side.addWidget(c4)

        c5, l5 = card("战绩")
        self.sb_stat = stat_row(l5, "胜 / 负", "0 / 0")
        self.sb_turn = stat_row(l5, "当前回合", "红方")
        self.sb_plies = stat_row(l5, "着法数", "0")
        side.addWidget(c5)

        wrap = QWidget()
        wrap.setLayout(side)
        wrap.setFixedWidth(300)
        root.addWidget(vscroll(wrap, 324))
        self.body.addLayout(root, 1)

    def _qss(self):
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

    # -------- 生命周期
    def _boot(self):
        st = self.store.data.get("state")
        if st and st.get("moves"):
            self.level = st.get("level", "normal")
            self.mode = st.get("mode", "ai")
            self.human_color = st.get("human", XE.RED)
            for cmb, idx in ((self.cmb_mode, 0 if self.mode == "ai" else 1),
                             (self.cmb_level, [k for k, _ in LEVELS].index(self.level)),
                             (self.cmb_side, 0 if self.human_color == XE.RED else 1)):
                cmb.blockSignals(True)
                cmb.setCurrentIndex(idx)
                cmb.blockSignals(False)
            self.board = XE.initial_board()
            self.history = []
            for mv in st["moves"]:
                fr, to = mv[0], mv[1]
                nota = XE.notation(self.board, (fr, to))
                cap = XE.make(self.board, (fr, to))
                self.history.append((fr, to, mv[2], nota, cap))
            self.turn = st.get("turn", XE.RED)
            self.last = (self.history[-1][0], self.history[-1][1]) if self.history \
                else None
            self.finished = False
            flash_status(self, "已恢复上次对局")
        self._refresh()
        if self._ai_to_move():
            self._ai_turn()

    def _ai_to_move(self):
        return (self.mode == "ai" and not self.finished and not self.thinking
                and self.turn != self.human_color)

    # -------- 状态刷新
    def _refresh(self, check_pos=-1):
        p = self.view
        p.set_board(self.board, self.sel if hasattr(self, "sel") else -1,
                    self.targets if hasattr(self, "targets") else [],
                    self.last if hasattr(self, "last") else None, check_pos)
        side = "红方" if self.turn == XE.RED else "黑方"
        st = XE.state_of(self.board, self.turn)
        if st == "check":
            self.lb_check.setText("将 军 !")
            self.lb_turn.setText("%s行棋" % side)
        else:
            self.lb_check.setText("")
            self.lb_turn.setText(("AI 思考中…" if self.thinking else "%s行棋" % side))
        col = C_DANGER if self.turn == XE.RED else C_TEXT
        self.lb_turn.setStyleSheet(
            "font-size:13px;font-weight:700;padding:5px 12px;border-radius:13px;"
            "color:%s;background:%s;border:1px solid %s;" % (col, C_PANEL, C_LINE))
        self.sb_turn.setText(side)
        self.sb_plies.setText(str(len(self.history)))
        if self.net and self.net.connected:
            mine = "红方" if self.human_color == XE.RED else "黑方"
            self.lb_lan.setText("联机 · 我执%s · 对手 %s" % (mine, self.lan_peer or "对手"))
            self.lb_lan.setStyleSheet("font-size:12.5px;font-weight:700;color:%s;"
                                      % C_ACCENT2)
            self.lb_net.setText("对手：%s\n你执：%s（%s）"
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
        self.sb_stat.setText("%d / %d" % (rec.get("win", 0), rec.get("lose", 0)))
        self._rebuild_table()
        human_turn = (self.mode == "pvp") or (self.turn == self.human_color)
        self.view.locked = self.finished or self.thinking or not human_turn
        self.view.update()

    def _rebuild_table(self):
        rows = (len(self.history) + 1) // 2
        self.tb.setRowCount(rows)
        for r in range(rows):
            idx = r * 2
            self.tb.setItem(r, 0, QTableWidgetItem(str(r + 1)))
            for k in (0, 1):
                j = idx + k
                if j < len(self.history):
                    fr, to, color, nota = self.history[j][:4]
                    it = QTableWidgetItem(nota)
                    it.setForeground(QColor("#e06a5c" if color == XE.RED else "#9fb0c6"))
                    self.tb.setItem(r, k + 1, it)
        if rows:
            self.tb.scrollToBottom()

    # -------- 交互
    def on_click(self, x, y):
        if self.view.locked or self.finished:
            return
        i = XE.idx(x, y)
        pc = self.board[i]
        if pc and pc[0] == self.turn:
            self.sel = i
            self.targets = [mv[1] for mv in XE.legal_moves(self.board, self.turn)
                            if mv[0] == i]
            self.view.set_board(self.board, self.sel, self.targets, self.last,
                                self._check_pos())
            return
        if hasattr(self, "sel") and self.sel >= 0 and i in self.targets:
            self.do_move((self.sel, i))
            return
        # 点空白处取消选择
        self.sel = -1
        self.targets = []
        self.view.set_board(self.board, -1, [], self.last, self._check_pos())

    def _check_pos(self):
        if XE.in_check(self.board, self.turn):
            k = XE.find_king(self.board, self.turn)
            return k if k is not None else -1
        return -1

    def do_move(self, mv, from_net=False):
        nota = XE.notation(self.board, mv)
        cap = XE.make(self.board, mv)
        self.history.append((mv[0], mv[1], self.board[mv[1]][0], nota, cap))
        self.last = (mv[0], mv[1])
        self.sel = -1
        self.targets = []
        self.turn = XE.opp(self.turn)
        self._save()
        if self.net and self.net.connected and not from_net:
            self.net.send({"t": "move", "mv": [int(mv[0]), int(mv[1])]})
        st = XE.state_of(self.board, self.turn)
        self._refresh(check_pos=self._check_pos())
        if st in ("checkmate", "stalemate"):
            self._finish(st)
            return
        if self._ai_to_move():
            self._ai_turn()

    def _ai_turn(self):
        if self.net:
            return                     # 联机模式没有 AI
        if self.finished:
            return
        self.thinking = True
        self._refresh(check_pos=self._check_pos())
        QTimer.singleShot(50, self._start_worker)

    def _start_worker(self):
        clone = XE.clone(self.board)
        color = self.turn
        gen = self.gen
        self.worker = AiWorker(clone, color, self.level)
        self.keeper.add(self.worker)
        self.worker.done.connect(lambda mv, c=color, g=gen: self._ai_done(mv, c, g))
        self.worker.start()

    def _ai_done(self, mv, color, gen=0):
        if gen != self.gen:
            return
        self.thinking = False
        if mv and not self.finished and self.turn == color:
            self.do_move(mv)
        else:
            self._refresh(check_pos=self._check_pos())

    # -------- 操作
    def undo(self):
        if self.thinking or not self.history:
            return
        if self.net and self.net.connected:
            self.net.send({"t": "undo_req", "color": self.human_color})
            flash_status(self, "已向对手发起悔棋请求…")
            return
        # 至少撤 1 手；人机模式下继续撤直到轮到玩家行棋
        while self.history:
            fr, to, color, _nota, cap = self.history.pop()
            XE.unmake(self.board, (fr, to), cap)
            self.turn = color
            if self.mode == "pvp" or color == self.human_color:
                break
        self.finished = False
        self.sel = -1
        self.targets = []
        self.last = (self.history[-1][0], self.history[-1][1]) if self.history else None
        self._save()
        self._refresh(check_pos=self._check_pos())
        if self._ai_to_move():
            self._ai_turn()

    def _apply_undo(self, requester=None):
        """联机悔棋：撤销到发起方重新可下为止；双方按同一规则得到同样的步数"""
        if requester is None:
            requester = self.human_color
        if not self.history:
            return
        fr, to, color, _nota, cap = self.history.pop()
        XE.unmake(self.board, (fr, to), cap)
        self.turn = color
        if self.history and self.turn != requester:
            fr, to, color, _nota, cap = self.history.pop()
            XE.unmake(self.board, (fr, to), cap)
            self.turn = color
        self.finished = False
        self.sel = -1
        self.targets = []
        self.last = (self.history[-1][0], self.history[-1][1]) if self.history else None
        self._refresh(check_pos=self._check_pos())

    def hint(self):
        if self.thinking or self.finished or self.view.locked:
            return
        if not self.net and self.cmb_mode.currentIndex() == 0 \
                and self.turn != self.human_color:
            return
        eng = XE.Engine(self.level)
        mv = eng.choose_move(XE.clone(self.board), self.turn)
        if not mv:
            return
        self.sel = mv[0]
        self.targets = [mv[1]]
        self.view.set_board(self.board, self.sel, self.targets, self.last,
                            self._check_pos())
        flash_status(self, "建议：%s" % XE.notation(self.board, mv))

    def restart(self):
        if self.net and self.net.connected:
            self.net.send({"t": "rematch_req"})
            flash_status(self, "已向对手发起「再来一局」，等待同意…", 4200)
            return
        r = QMessageBox.question(self, "重开", "确定重新开始一局？",
                                 QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if r != QMessageBox.Yes:
            return
        self._new_game()

    def _new_game(self):
        self.gen += 1
        self.board = XE.initial_board()
        self.history = []
        self.turn = XE.RED
        self.sel = -1
        self.targets = []
        self.last = None
        self.finished = False
        self.thinking = False
        self.store.data["state"] = None
        self.store.save()
        self._refresh()
        if self._ai_to_move():
            self._ai_turn()

    def resign(self):
        if self.finished:
            return
        side = "红方" if self.turn == XE.RED else "黑方"
        r = QMessageBox.question(self, "认输", "%s确认认输？" % side,
                                 QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if r != QMessageBox.Yes:
            return
        if self.net and self.net.connected:
            self.net.send({"t": "resign"})
            self._finish("resign", "lose" if self.turn == self.human_color else "win")
            return
        if self.mode == "ai":
            result = "lose" if self.turn == self.human_color else "win"
        else:
            result = "draw"
        self._finish("resign", result)

    def on_mode_change(self, idx):
        if self.net:
            return                     # 联机时不能切模式
        self.mode = MODES[idx][0]
        self._new_game()

    def on_side_change(self, idx):
        if self.net:
            return
        self.human_color = XE.RED if idx == 0 else XE.BLACK
        self._new_game()

    # -------- 局域网联机
    def open_lan(self):
        if self.net and self.net.active:
            flash_status(self, "已经在联机了，先「断开联机」再重新创建")
            return
        info, sess = ask_lan(self, "xiangqi", "红方", "黑方")
        if not info:
            return
        self.net = sess
        self.lan_seat = int(info.get("seat", 0))
        self.lan_peer = (info.get("peer") or {}).get("name", "对手")
        self.human_color = XE.RED if self.lan_seat == 0 else XE.BLACK
        self.mode = "lan"
        sess.message.connect(self._on_lan_message)
        sess.closed.connect(self._on_lan_closed)
        sess.failed.connect(lambda e: flash_status(self, "联机出错：%s" % e, 5000))
        for cmb in (self.cmb_mode, self.cmb_level, self.cmb_side):
            cmb.setEnabled(False)
        self.btn_lan.setEnabled(False)
        self.btn_lan_leave.setEnabled(True)
        self._new_game()
        flash_status(self, "已联机：你执%s，%s执%s。"
                     % ("红方" if self.human_color == XE.RED else "黑方", self.lan_peer,
                        "黑方" if self.human_color == XE.RED else "红方"), 5000)

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
        self.mode = MODES[self.cmb_mode.currentIndex()][0]
        for cmb in (self.cmb_mode, self.cmb_level, self.cmb_side):
            cmb.setEnabled(True)
        self.btn_lan.setEnabled(True)
        self.btn_lan_leave.setEnabled(False)
        self._refresh(check_pos=self._check_pos())

    def _on_lan_closed(self, reason):
        if self.net is None:
            return
        self._close_net()
        QMessageBox.warning(self, "联机中断", "%s\n现在可以继续人机对战。" % reason)

    def _on_lan_message(self, m):
        t = m.get("t")
        if t == "move":
            if self.finished or not self.net:
                return
            mv = m.get("mv") or []
            if len(mv) != 2:
                return
            fr, to = int(mv[0]), int(mv[1])
            if self.turn == self.human_color or self.board[fr] is None:
                return                 # 不是对手的回合 / 数据异常，忽略
            if self.board[fr][0] != self.turn:
                return
            self.do_move((fr, to), from_net=True)
        elif t == "undo_req":
            who = m.get("color", XE.opp(self.human_color))
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
            self._apply_undo(self.human_color)
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
            self._refresh(check_pos=self._check_pos())
            QMessageBox.information(self, "对手认输", "%s 认输了，你赢了！🎉" % self.lan_peer)
        elif t == "bye":
            self._on_lan_closed("对手离开了房间")

    def _lan_rematch(self):
        """再来一局并交换先行方（双方同时交换，保持一致）"""
        self.human_color = XE.BLACK if self.human_color == XE.RED else XE.RED
        self._new_game()
        flash_status(self, "新一局开始：你执%s"
                     % ("红方" if self.human_color == XE.RED else "黑方"), 4200)

    # -------- 结束
    def _finish(self, kind, forced=None):
        self.finished = True
        self.thinking = False
        lan = bool(self.net and self.net.connected)
        rec = self.store.data["stats"]
        if forced:
            result = forced
        elif kind == "checkmate":
            winner = XE.opp(self.turn)
            if self.mode == "pvp":
                result = "draw"
            else:
                result = "win" if winner == self.human_color else "lose"
        else:                                    # stalemate = 困毙判负
            winner = XE.opp(self.turn)
            result = "draw" if self.mode == "pvp" else \
                ("win" if winner == self.human_color else "lose")
        if not lan:                              # 联机战绩不混进人机统计
            if result == "win":
                rec["win"] = rec.get("win", 0) + 1
            elif result == "lose":
                rec["lose"] = rec.get("lose", 0) + 1
            else:
                rec["draw"] = rec.get("draw", 0) + 1
        self.store.data["state"] = None
        self.store.save()
        self._refresh(check_pos=self._check_pos())

        loser = "红方" if self.turn == XE.RED else "黑方"
        winner = "黑方" if self.turn == XE.RED else "红方"
        if kind == "resign":
            msg = "%s认输，%s胜。" % (loser, winner)
        elif kind == "checkmate":
            msg = "%s被将死，%s胜！" % (loser, winner)
        else:
            msg = "%s无子可动（困毙），%s胜！" % (loser, winner)
        if lan:
            msg += "\n\n你%s了本局。想再来一局就点「重开」向对手发起邀请。" % (
                "赢" if result == "win" else ("输" if result == "lose" else "和"))
        elif self.mode == "ai":
            msg += "\n\n你%s了本局。" % ("赢" if result == "win" else
                                        ("输" if result == "lose" else "和"))
        QMessageBox.information(self, "对局结束", msg)

    def _save(self):
        if self.finished or self.net:
            return
        self.store.data["state"] = {
            "moves": [[fr, to, c] for (fr, to, c, _n, _cap) in self.history],
            "turn": self.turn, "level": self.level, "mode": self.mode,
            "human": self.human_color}
        self.store.save()

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
    w = XiangqiWindow()
    w.show()
    return w


if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("中国象棋")
    app.setStyle("Fusion")
    if "--selftest" in sys.argv:
        remove_save("xiangqi_save.json")
        w = XiangqiWindow()
        w.resize(1080, 900)
        w.cmb_mode.setCurrentIndex(1)          # 双人模式，避免后台 AI 线程
        w._new_game()
        for _ in range(10):
            app.processEvents()
        w.do_move((XE.idx(1, 7), XE.idx(4, 7)))       # 红 炮八平五
        w.do_move((XE.idx(7, 0), XE.idx(6, 2)))       # 黑 马2进3
        w.sel = XE.idx(1, 9)
        w.targets = [mv[1] for mv in XE.legal_moves(w.board, w.turn)
                     if mv[0] == XE.idx(1, 9)]
        w._refresh(check_pos=w._check_pos())
        for _ in range(10):
            app.processEvents()
        shot = os.path.join(output_dir(), "_selftest_xiangqi.png")
        w.grab().save(shot)
        print("XIANGQI SELFTEST OK ->", shot, os.path.getsize(shot), "字节")
        w.close()
        sys.exit(0)
    w = XiangqiWindow()
    w.show()
    sys.exit(app.exec())
