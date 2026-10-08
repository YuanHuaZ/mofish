# -*- coding: utf-8 -*-
"""
24 点 · 无限关（PySide6 / Qt）

随机出题、无限关：给定 4 个 1~13 的数，各用一次，用 + − × ÷ 和括号凑出 24。
- 点数字牌 + 运算符即可合并，分数用精确的 Fraction 计算（允许出现分数解）
- 「自动难度」下每连过 3 题升一档：入门 → 简单 → 普通 → 困难 → 大师
- 附带表达式输入框，可直接手写算式（例如 (8-2)×4）
"""
import os
import random
import sys
import time

from PySide6.QtCore import Qt, QTimer, Signal, QPointF, QRectF
from PySide6.QtGui import (QPainter, QColor, QFont, QFontMetrics, QPen, QBrush,
                           QLinearGradient)
from PySide6.QtWidgets import (QApplication, QWidget, QHBoxLayout, QVBoxLayout,
                               QGridLayout, QLabel, QComboBox, QLineEdit,
                               QPushButton, QMessageBox)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from point24 import engine as E  # noqa: E402
from shared.common import (C_BG, C_PANEL, C_PANEL2, C_LINE, C_LINE2, C_TEXT,
                           C_DIM, C_FAINT, C_ACCENT, C_ACCENT2, C_DANGER, C_OK,
                           C_GOLD, rgba, mk_button, ToolButton, card, stat_row,
                           vscroll, load_game_json, BaseStore, GameWindow,
                           flash_status, fmt_time)  # noqa: E402

OPS = [("+", "+ 加"), ("-", "− 减"), ("*", "× 乘"), ("/", "÷ 除")]
TIER_HINT = {"自动": "每连过 3 题自动升一档"}


def _num_text(v):
    return str(v.numerator) if v.denominator == 1 else "%d/%d" % (v.numerator, v.denominator)


class TileBoard(QWidget):
    """自绘数字牌区：点牌选中，配合运算符合并"""

    clicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tiles = []
        self.sel = -1
        self.op = None
        self.locked = True
        self.done = False
        self.flash = -1
        self.flash_t0 = 0.0
        self.setMinimumSize(420, 210)
        self.setCursor(Qt.PointingHandCursor)
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)

    # -------- 几何
    def _geom(self):
        n = max(1, len(self.tiles))
        w, h = self.width(), self.height()
        gap = 14
        avail = w - 2 * 16 - gap * (n - 1)
        slot = min(196.0, avail / float(n)) if n else 0
        tw = min(slot, 196.0)
        th = min(h - 34.0, 168.0)
        ox = (w - (tw * n + gap * (n - 1))) / 2.0
        oy = (h - th) / 2.0
        return ox, oy, tw, th, gap

    def _rect_at(self, pos):
        ox, oy, tw, th, gap = self._geom()
        for i in range(len(self.tiles)):
            x = ox + i * (tw + gap)
            if QRectF(x, oy, tw, th).contains(pos):
                return i
        return -1

    def mousePressEvent(self, ev):
        if self.locked:
            return
        i = self._rect_at(ev.position())
        if i >= 0:
            self.clicked.emit(i)

    def set_tiles(self, tiles, sel=-1, op=None):
        self.tiles, self.sel, self.op = tiles, sel, op
        self.update()

    def flash_new(self, idx):
        self.flash = idx
        self.flash_t0 = time.time()
        self.timer.start()

    def _tick(self):
        if time.time() - self.flash_t0 > 0.22:
            self.flash = -1
            self.timer.stop()
        self.update()

    def _flash_scale(self):
        if self.flash < 0:
            return 1.0
        p = (time.time() - self.flash_t0) / 0.22
        return 1.0 + 0.09 * (1 - abs(p * 2 - 1))

    # -------- 绘制
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), QColor(C_BG))
        ox, oy, tw, th, gap = self._geom()
        scale = self._flash_scale()

        if not self.tiles:
            p.setPen(QColor(C_FAINT))
            f = QFont()
            f.setPointSizeF(13)
            p.setFont(f)
            p.drawText(self.rect(), Qt.AlignCenter, "点「换一题」开始")
            return

        for i, node in enumerate(self.tiles):
            r = QRectF(ox + i * (tw + gap), oy, tw, th)
            if i == self.flash:
                c = r.center()
                r = QRectF(c.x() - r.width() * scale / 2, c.y() - r.height() * scale / 2,
                           r.width() * scale, r.height() * scale)
            self._draw_tile(p, r, node, i)

    def _draw_tile(self, p, rect, node, idx):
        leaf = node.kind == "n"
        good = self.done and node.value == E.TARGET
        g = QLinearGradient(rect.topLeft(), rect.bottomRight())
        if good:
            g.setColorAt(0.0, QColor("#4ee2a3"))
            g.setColorAt(1.0, QColor("#1f9d68"))
        elif self.sel == idx:
            g.setColorAt(0.0, QColor("#4d7fd8"))
            g.setColorAt(1.0, QColor("#2b4a94"))
        else:
            g.setColorAt(0.0, QColor("#252e3d"))
            g.setColorAt(1.0, QColor("#1a2230"))
        p.setBrush(QBrush(g))
        if self.sel == idx:
            p.setPen(QPen(QColor(C_GOLD), 3.0))
        elif self.op is not None and self.sel == idx:
            p.setPen(QPen(QColor(C_GOLD), 3.0))
        else:
            p.setPen(QPen(QColor(C_LINE2 if not leaf else C_LINE), 1.4))
        p.drawRoundedRect(rect, 16, 16)

        # 主数值
        f = QFont()
        f.setBold(True)
        size = min(rect.height() * (0.40 if leaf else 0.36), rect.width() * 0.42)
        f.setPointSizeF(max(16.0, size))
        p.setFont(f)
        p.setPen(QColor("#f2f7ff"))
        txt_rect = QRectF(rect.x(), rect.y() + rect.height() * (0.06 if leaf else 0.02),
                          rect.width(), rect.height() * (0.60 if leaf else 0.52))
        p.drawText(txt_rect, Qt.AlignCenter, _num_text(node.value))

        # 子表达式
        if not leaf:
            f2 = QFont()
            expr = node.text()
            size = 15.0
            f2.setPointSizeF(size)
            while size > 8.0 and QFontMetrics(f2).horizontalAdvance(expr) > rect.width() - 14:
                size -= 0.5
                f2.setPointSizeF(size)
            p.setFont(f2)
            p.setPen(QColor(rgba(C_ACCENT2, 0.9)))
            p.drawText(QRectF(rect.x() + 4, rect.y() + rect.height() * 0.63,
                              rect.width() - 8, rect.height() * 0.30),
                       Qt.AlignCenter, expr)

        # 选中时的运算符角标
        if self.sel == idx and self.op:
            badge = QRectF(rect.right() - 40, rect.y() + 8, 32, 32)
            p.setBrush(QBrush(QColor(C_GOLD)))
            p.setPen(Qt.NoPen)
            p.drawEllipse(badge)
            f3 = QFont()
            f3.setBold(True)
            f3.setPointSizeF(13)
            p.setFont(f3)
            p.setPen(QColor("#0b0e14"))
            p.drawText(badge, Qt.AlignCenter, E.OP_CHAR[self.op])


# ------------------------------------------------------------------ 主窗口
class Point24Window(GameWindow):
    game_key = "point24"
    game_name = "24 点"
    game_emoji = "🃏"

    def __init__(self):
        super().__init__()
        self.store = BaseStore("point24_save.json", {})
        for k, v in (("stats", {}), ("state", None)):
            self.store.data.setdefault(k, v)
        self.rng = random.Random()
        self.bank = E.bank_from_json(load_game_json("puzzles.json", "point24"))
        if not self.bank:
            flash_status(self, "未找到题库，将实时生成题目")
        self.nums = (3, 3, 8, 8)
        self.tiles = []
        self.stack = []
        self.sel = -1
        self.op = None
        self.hinted = False
        self.solved = False
        self.elapsed = 0.0
        self.running = False
        self.start_time = time.time()
        self.history = []              # 最近出过的题，避免连续重复
        self.resize(1060, 800)
        self.setMinimumSize(920, 660)
        self._build_ui()
        self.tick = QTimer(self)
        self.tick.timeout.connect(self._on_tick)
        self.tick.start(200)
        self._boot()

    # -------- UI
    def _build_ui(self):
        self.lb_tier = QLabel("入门")
        self.lb_tier.setStyleSheet("font-weight:700;font-size:13px;padding:5px 12px;"
                                   "border-radius:13px;background:%s;border:1px solid %s;"
                                   % (C_PANEL, C_LINE))
        self.bar_right.addWidget(self.lb_tier)
        self.lb_streak = QLabel("连击 0")
        self.lb_streak.setStyleSheet("color:%s;font-size:13px;font-weight:700;" % C_GOLD)
        self.bar_right.addWidget(self.lb_streak)
        self.lb_timer = QLabel("00:00")
        self.lb_timer.setStyleSheet("font-size:20px;font-weight:700;")
        self.bar_right.addWidget(self.lb_timer)

        root = QHBoxLayout()
        root.setSpacing(16)

        left = QVBoxLayout()
        left.setSpacing(12)
        head = QHBoxLayout()
        self.lb_target = QLabel("用 4 个数凑出 24")
        self.lb_target.setStyleSheet("font-size:14px;color:%s;" % C_DIM)
        head.addWidget(self.lb_target)
        head.addStretch(1)
        self.lb_state = QLabel("")
        self.lb_state.setStyleSheet("font-size:13px;font-weight:700;")
        head.addWidget(self.lb_state)
        left.addLayout(head)

        self.board = TileBoard()
        self.board.setMaximumHeight(320)
        self.board.clicked.connect(self.on_tile)
        left.addWidget(self.board)

        ops = QHBoxLayout()
        ops.setSpacing(10)
        self.op_buttons = {}
        for key, label in OPS:
            b = QPushButton(label)
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(52)
            b.setStyleSheet(
                "QPushButton{background:%s;color:%s;border:1px solid %s;border-radius:12px;"
                "font-size:17px;font-weight:700;}"
                "QPushButton:hover{background:#232b38;color:%s;border-color:%s;}"
                "QPushButton:checked{background:rgba(240,178,60,.18);color:%s;"
                "border-color:rgba(240,178,60,.65);}"
                % (C_PANEL2, C_TEXT, C_LINE, C_TEXT, C_LINE2, C_GOLD))
            b.clicked.connect(lambda _c=False, k=key: self.on_op(k))
            b.setFocusPolicy(Qt.NoFocus)
            self.op_buttons[key] = b
            ops.addWidget(b, 1)
        left.addLayout(ops)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.btn_undo = mk_button("撤销一步", parent=self)
        self.btn_undo.clicked.connect(self.undo)
        self.btn_reset = mk_button("重来本题", parent=self)
        self.btn_reset.clicked.connect(self.reset_puzzle)
        self.btn_hint = mk_button("提示", parent=self)
        self.btn_hint.clicked.connect(self.hint)
        self.btn_next = mk_button("换一题", parent=self)
        self.btn_next.clicked.connect(lambda: self.new_puzzle())
        for b in (self.btn_undo, self.btn_reset, self.btn_hint, self.btn_next):
            b.setFocusPolicy(Qt.NoFocus)
            row.addWidget(b, 1)
        left.addLayout(row)

        typed = QHBoxLayout()
        typed.setSpacing(8)
        self.ed_input = QLineEdit()
        self.ed_input.setPlaceholderText("直接写算式也行：8×3+3-3 或 6÷(1-3÷4) 或 6/(1-3/4)")
        self.ed_input.setFixedHeight(38)
        self.ed_input.setStyleSheet(
            "QLineEdit{background:%s;color:%s;border:1px solid %s;border-radius:10px;"
            "padding:4px 10px;font-size:13.5px;}"
            "QLineEdit:focus{border-color:%s;}" % (C_PANEL2, C_TEXT, C_LINE, C_ACCENT))
        self.ed_input.returnPressed.connect(self.submit_text)
        typed.addWidget(self.ed_input, 1)
        self.btn_submit = mk_button("提交", "primary", self)
        self.btn_submit.setFixedWidth(92)
        self.btn_submit.setFocusPolicy(Qt.NoFocus)
        self.btn_submit.clicked.connect(self.submit_text)
        typed.addWidget(self.btn_submit)
        left.addLayout(typed)

        self.lb_input_hint = QLabel("加减乘除都能输入：＋ − × ÷ 或 + - * / 都行，"
                                    "也可用 x 代替乘号；支持括号，四个数各用一次（全角符号也认）")
        self.lb_input_hint.setWordWrap(True)
        self.lb_input_hint.setStyleSheet("color:%s;font-size:11.5px;" % C_FAINT)
        left.addWidget(self.lb_input_hint)
        left.addStretch(1)
        root.addLayout(left, 1)

        side = QVBoxLayout()
        side.setSpacing(12)

        c1, l1 = card("本题")
        self.sb_tier = stat_row(l1, "难度档位", "入门")
        self.sb_score = stat_row(l1, "难度分", "--")
        self.sb_branch = stat_row(l1, "可用分支", "--")
        self.sb_sols = stat_row(l1, "解法数量", "?")
        self.sb_time = stat_row(l1, "本题用时", "00:00")
        self.lb_ref = QLabel("提示或通关后显示参考解法")
        self.lb_ref.setWordWrap(True)
        self.lb_ref.setStyleSheet("color:%s;font-size:12px;" % C_FAINT)
        l1.addWidget(self.lb_ref)
        side.addWidget(c1)

        c2, l2 = card("难度")
        self.cmb_tier = QComboBox()
        self.cmb_tier.addItems(["自动"] + E.TIER_ORDER)
        self.cmb_tier.currentIndexChanged.connect(self.on_tier_change)
        self.cmb_tier.setStyleSheet(
            "QComboBox{background:%s;color:%s;border:1px solid %s;border-radius:9px;"
            "padding:6px 10px;font-size:13px;}"
            "QComboBox::drop-down{border:none;width:22px;}"
            "QComboBox QAbstractItemView{background:%s;color:%s;"
            "selection-background-color:%s;outline:none;}"
            % (C_PANEL2, C_TEXT, C_LINE, C_PANEL2, C_TEXT, C_ACCENT))
        l2.addWidget(self.cmb_tier)
        self.lb_tier_note = QLabel(TIER_HINT["自动"])
        self.lb_tier_note.setWordWrap(True)
        self.lb_tier_note.setStyleSheet("color:%s;font-size:11.5px;" % C_FAINT)
        l2.addWidget(self.lb_tier_note)
        side.addWidget(c2)

        c3, l3 = card("战绩")
        self.sb_solved = stat_row(l3, "累计通关", "0 题")
        self.sb_streak = stat_row(l3, "当前连击", "0")
        self.sb_best = stat_row(l3, "最高连击", "0")
        self.sb_fast = stat_row(l3, "最快用时", "--")
        self.sb_avg = stat_row(l3, "平均用时", "--")
        self.sb_hint = stat_row(l3, "提示 / 跳过", "0 / 0")
        b = mk_button("清空战绩", "danger", self)
        b.clicked.connect(self.clear_stats)
        l3.addWidget(b)
        side.addWidget(c3)

        c4, l4 = card("玩法")
        for k, v in (("点牌", "选中数字"), ("点运算符", "+ − × ÷ 四种"),
                     ("再点牌", "两数合并"), ("手写算式", "加减乘除都能输"),
                     ("键盘", "Enter 下一题 / Ctrl+Z 撤销 / H 提示 / N 换题")):
            stat_row(l4, k, v)
        side.addWidget(c4)
        side.addStretch(1)

        wrap = QWidget()
        wrap.setLayout(side)
        wrap.setFixedWidth(288)
        root.addWidget(vscroll(wrap, 312))
        self.body.addLayout(root, 1)

    # -------- 生命周期
    def _boot(self):
        st = self.store.data.get("state")
        tier_idx = st.get("tierIndex", 0) if st else 0
        self.cmb_tier.blockSignals(True)
        self.cmb_tier.setCurrentIndex(max(0, min(len(E.TIER_ORDER), tier_idx)))
        self.cmb_tier.blockSignals(False)
        if st and st.get("nums"):
            self._load(tuple(st["nums"]))
            flash_status(self, "已恢复上次的题目")
        else:
            self.new_puzzle(first=True)
        self._refresh()

    def _tier_name(self):
        """当前实际生效的档位（自动模式下随连击提升）"""
        idx = self.cmb_tier.currentIndex()
        if idx > 0:
            return E.TIER_ORDER[idx - 1]
        return E.next_tier(E.TIER_ORDER[0], self.store.data["stats"].get("streak", 0),
                           step=3)

    def _on_tick(self):
        if self.running and not self.solved:
            self.elapsed = time.time() - self.start_time
        self.lb_timer.setText(fmt_time(int(self.elapsed * 1000)))
        self.sb_time.setText(fmt_time(int(self.elapsed * 1000)))
        self.lb_timer.setStyleSheet("font-size:20px;font-weight:700;color:%s;"
                                    % (C_TEXT if self.running else C_FAINT))

    # -------- 出题
    def new_puzzle(self, first=False):
        tier = self._tier_name()
        nums = E.pick(self.bank, tier, self.rng, avoid=self.history[-6:])
        self.history.append(tuple(sorted(nums)))
        self._load(nums)
        if not first:
            flash_status(self, "新题目：%s" % " ".join(map(str, nums)))

    def _load(self, nums):
        self.nums = tuple(sorted(int(v) for v in nums))
        self.tiles = [E.leaf(v) for v in self.nums]
        self.stack = []
        self.sel = -1
        self.op = None
        self.hinted = False
        self.solved = False
        self.elapsed = 0.0
        self.start_time = time.time()
        self.running = True
        info = E.analyse(self.nums)
        self.info = info
        self.score = E.difficulty_score(info)
        self.tier = E.tier_of(self.score)[0]
        self.all_sols = E.solutions(self.nums)
        self.board.done = False
        self.board.locked = False
        self.board.set_tiles(self.tiles, -1, None)
        self.lb_ref.setText("提示或通关后显示参考解法")
        self.ed_input.clear()
        self._refresh()
        self._save()

    # -------- 状态刷新
    def _refresh(self):
        st = self.store.data["stats"]
        self.lb_tier.setText("%s · 难度分 %d" % (self.tier, self.score))
        col = E.tier_of(self.score)[1]
        self.lb_tier.setStyleSheet(
            "font-weight:700;font-size:13px;padding:5px 12px;border-radius:13px;"
            "color:%s;background:%s;border:1px solid %s;"
            % (col, rgba(col, 0.13), rgba(col, 0.4)))
        self.lb_streak.setText("连击 %d" % st.get("streak", 0))
        self.sb_tier.setText("%s（%s）" % (self.tier, self.cmb_tier.currentText()))
        self.sb_score.setText(str(self.score))
        self.sb_branch.setText(str(self.info["nFirst"]))
        self.sb_sols.setText(str(len(self.all_sols)) if (self.hinted or self.solved) else "?")
        self.sb_solved.setText("%d 题" % st.get("solved", 0))
        self.sb_streak.setText(str(st.get("streak", 0)))
        self.sb_best.setText(str(st.get("bestStreak", 0)))
        self.sb_fast.setText(fmt_time(int(st["fastest"] * 1000)) if st.get("fastest") else "--")
        n = st.get("timed", 0)
        self.sb_avg.setText(fmt_time(int(st.get("totalTime", 0) / n * 1000)) if n else "--")
        self.sb_hint.setText("%d / %d" % (st.get("hints", 0), st.get("skips", 0)))
        self.lb_target.setText("本题 4 个数：" + "  ".join(map(str, self.nums)))

        left = len(self.tiles)
        if self.solved:
            self.lb_state.setText("✅ 已经凑出 24")
            self.lb_state.setStyleSheet("font-size:13px;font-weight:700;color:%s;" % C_OK)
        elif left == 1:
            self.lb_state.setText("结果是 %s，不是 24" % _num_text(self.tiles[0].value))
            self.lb_state.setStyleSheet("font-size:13px;font-weight:700;color:%s;"
                                        % C_DANGER)
        elif self.op:
            self.lb_state.setText("已选 %s，再点一张牌" % E.OP_CHAR[self.op])
            self.lb_state.setStyleSheet("font-size:13px;font-weight:700;color:%s;" % C_GOLD)
        elif self.sel >= 0:
            self.lb_state.setText("已选中 %s" % _num_text(self.tiles[self.sel].value))
            self.lb_state.setStyleSheet("font-size:13px;font-weight:700;color:%s;" % C_GOLD)
        else:
            self.lb_state.setText("剩下 %d 个数" % left)
            self.lb_state.setStyleSheet("font-size:13px;font-weight:700;color:%s;" % C_DIM)

        self.btn_undo.setEnabled(bool(self.stack))
        for key, b in self.op_buttons.items():
            b.setChecked(self.op == key)
        self.btn_next.setText("下一题" if self.solved else "换一题")
        self.board.done = self.solved
        self.board.set_tiles(self.tiles, self.sel, self.op)

    # -------- 交互
    def on_tile(self, i):
        if self.solved or i < 0 or i >= len(self.tiles):
            return
        if self.op is None:
            self.sel = -1 if self.sel == i else i
            self._refresh()
            return
        if self.sel < 0:
            self.sel = i
            self._refresh()
            return
        if self.sel == i:
            self.sel = -1
            self._refresh()
            return
        self._merge(self.sel, self.op, i)

    def on_op(self, key):
        if self.solved:
            return
        if self.op == key:
            self.op = None
        else:
            self.op = key
        self._refresh()

    def _merge(self, i, op, j):
        a, b = self.tiles[i], self.tiles[j]
        node = E.build(op, a, b)
        if node is None:
            flash_status(self, "不能除以 0")
            self.op = None
            self._refresh()
            return
        self.stack.append((list(self.tiles), self.sel, self.op))
        keep = min(i, j)
        rest = [t for k, t in enumerate(self.tiles) if k not in (i, j)]
        rest.insert(keep, node)
        self.tiles = rest
        self.sel = -1
        self.op = None
        self._refresh()
        self.board.flash_new(keep)
        if len(self.tiles) == 1 and self.tiles[0].value == E.TARGET:
            self._win()

    def undo(self):
        if self.solved or not self.stack:
            return
        self.tiles, self.sel, self.op = self.stack.pop()
        self._refresh()

    def reset_puzzle(self):
        self._load(self.nums)

    def hint(self):
        if self.solved or self.hinted:
            return
        self.hinted = True
        self.store.data["stats"]["hints"] = self.store.data["stats"].get("hints", 0) + 1
        self.store.save()
        sol = self.all_sols[0]["expr"] if self.all_sols else "—"
        self.lb_ref.setText("参考解法：%s = 24（共 %d 种解法）" % (sol, len(self.all_sols)))
        self.lb_ref.setStyleSheet("color:%s;font-size:12.5px;font-weight:600;" % C_GOLD)
        flash_status(self, "参考解法：%s = 24" % sol)
        self._refresh()

    def submit_text(self):
        if self.solved:
            return
        text = self.ed_input.text().strip()
        try:
            value, _nums = E.eval_expression(text, self.nums)
        except ValueError as exc:
            flash_status(self, "算式有问题：%s" % exc, 4200)
            return
        except Exception:
            flash_status(self, "算式解析失败，检查一下括号与运算符", 4200)
            return
        if value == E.TARGET:
            self.tiles = [E.leaf(E.TARGET)]
            self.sel = -1
            self.op = None
            self._refresh()
            self._win(text=text)
        else:
            flash_status(self, "算出来是 %s，不是 24" % _num_text(value), 4200)

    # -------- 通关 / 统计
    def _win(self, text=None):
        if self.solved:
            return
        self.solved = True
        self.running = False
        self.elapsed = max(self.elapsed, time.time() - self.start_time)
        st = self.store.data["stats"]
        st["solved"] = st.get("solved", 0) + 1
        st["streak"] = st.get("streak", 0) + 1
        st["bestStreak"] = max(st.get("bestStreak", 0), st["streak"])
        st["timed"] = st.get("timed", 0) + 1
        st["totalTime"] = st.get("totalTime", 0) + self.elapsed
        if not self.hinted:
            fast = st.get("fastest")
            if fast is None or self.elapsed < fast:
                st["fastest"] = self.elapsed
        self.store.data["state"] = None
        self.store.save()

        sols = " ／ ".join(s["expr"] + " = 24" for s in self.all_sols[:3])
        self.lb_ref.setText("参考解法：%s" % (sols or "—"))
        self.lb_ref.setStyleSheet("color:%s;font-size:12.5px;" % C_OK)
        tag = "（用了提示）" if self.hinted else ""
        mine = ("你的算式：%s = 24　" % text) if text else ""
        flash_status(self, "🎉 %s用时 %.1f 秒 连击 %d%s　%s"
                     % (mine, self.elapsed, st["streak"], tag,
                        ("自动升档 → " + self._tier_name()) if self.cmb_tier.currentIndex() == 0
                        else ""), 6000)
        self._refresh()

    def clear_stats(self):
        if QMessageBox.question(self, "清空战绩", "确定清空通关记录与连击？",
                                QMessageBox.Yes | QMessageBox.No,
                                QMessageBox.No) != QMessageBox.Yes:
            return
        self.store.data["stats"] = {}
        self.store.data["state"] = None
        self.store.save()
        self._refresh()
        flash_status(self, "战绩已清空")

    def on_tier_change(self, idx):
        name = self.cmb_tier.currentText()
        self.lb_tier_note.setText(TIER_HINT.get(name, "固定在该档位出题"))
        if idx == 0:
            self.store.data["stats"]["streak"] = 0
        self.new_puzzle()

    def _save(self):
        if self.solved:
            return
        self.store.data["state"] = {"nums": list(self.nums),
                                    "tierIndex": self.cmb_tier.currentIndex()}
        self.store.save()

    # -------- 键盘
    def keyPressEvent(self, ev):
        k = ev.key()
        m = {Qt.Key_Plus: "+", Qt.Key_Equal: "+", Qt.Key_Minus: "-",
             Qt.Key_Asterisk: "*", Qt.Key_X: "*", Qt.Key_Slash: "/"}
        if k in m:
            self.on_op(m[k])
        elif k in (Qt.Key_Return, Qt.Key_Enter) and self.solved:
            self.new_puzzle()
        elif k == Qt.Key_Z and (ev.modifiers() & Qt.ControlModifier):
            self.undo()
        elif k == Qt.Key_R:
            self.reset_puzzle()
        elif k == Qt.Key_H:
            self.hint()
        elif k == Qt.Key_N:
            self.new_puzzle()
        elif k == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(ev)

    def closeEvent(self, ev):
        self._save()
        self.store.save()
        super().closeEvent(ev)


def launch():
    w = Point24Window()
    w.show()
    return w


if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("24 点")
    app.setStyle("Fusion")
    if "--selftest" in sys.argv:
        w = Point24Window()
        w.resize(1060, 800)
        w._load((1, 3, 4, 6))
        w.tiles = [E.leaf(6), E.build("/", E.leaf(1), E.leaf(3))]
        w.sel = 0
        w.op = "/"
        w._refresh()
        for _ in range(15):
            app.processEvents()
        shot = os.path.join(HERE, "_selftest_point24.png")
        w.grab().save(shot)
        print("POINT24 SELFTEST OK ->", shot, os.path.getsize(shot), "字节")
        w.close()
        sys.exit(0)
    w = Point24Window()
    w.show()
    sys.exit(app.exec())
