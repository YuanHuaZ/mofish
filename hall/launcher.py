# -*- coding: utf-8 -*-
"""
摸鱼小游戏 · 大厅（PySide6 / Qt）

启动后先进入这里：四张游戏卡片（数独 / 华容道 / 中国象棋 / 五子棋），
点卡片进入对应游戏窗口；关闭游戏窗口自动回到大厅，并刷新战绩。
"""
import os
import sys
import importlib

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QPainter, QFont, QPen, QBrush, QLinearGradient
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QGridLayout, QLabel, QFrame)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from shared.common import (C_BG, C_PANEL, C_PANEL2, C_LINE, C_LINE2, C_TEXT, C_DIM,
                    C_FAINT, C_ACCENT, C_ACCENT2, C_GOLD, C_OK, C_DANGER,
                    rgba, load_save, load_game_json)  # noqa: E402

APP_TITLE = "摸鱼小游戏"

# key -> (模块名, 类名, emoji, 名称, 说明, 主题色, 战绩函数)
GAMES = [
    ("sudoku", "sudoku.sudoku_app", "SudokuWindow", "🔢", "数独 100 关",
     "100 关由易到难的自适应难度题库，四个技巧档位、笔记与提示、自动存档计时。",
     "#38bdf8", "_stat_sudoku"),
    ("klotski", "klotski.klotski_app", "KlotskiWindow", "🧩", "华容道 · 经典布局",
     "不规则棋子：2x2 曹操 + 关羽 + 四将 + 四卒，拖动曹操从下方出口逃走；"
     "30 关按最少步数递增，自带 BFS 最优解提示与自动演示。",
     "#f0b23c", "_stat_klotski"),
    ("number", "numberklotski.number_app", "NumberPuzzleWindow", "🧮", "数字华容道",
     "数字滑块：3×3 到 6×6，把 1~N²-1 依次归位。点同行/列可整排滑动，"
     "归位方块变绿，3×3 支持最优提示。",
     "#a78bfa", "_stat_number"),
    ("xiangqi", "xiangqi.xiangqi_app", "XiangqiWindow", "♟", "中国象棋",
     "完整规则（蹩马腿 / 塞象眼 / 炮翻山 / 飞将）：人机对战或双人切磋，含中文棋谱。",
     "#e5484d", "_stat_xiangqi"),
    ("gomoku", "gomoku.gomoku_app", "GomokuWindow", "⚫", "五子棋",
     "15x15 无禁手自由规则，简单 / 普通 / 困难三档 AI，落子编号、悔棋与战绩统计。",
     "#22c55e", "_stat_gomoku"),
    ("point24", "point24.point24_app", "Point24Window", "🃏", "24 点",
     "无限关随机出题：4 个数各用一次凑出 24。点牌 + 运算符合并，加减乘除都能输入；"
     "连续通关会自动升档（入门 → 大师）。",
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
    tot = (s.get("win", 0) or 0) + (s.get("lose", 0) or 0) + (s.get("draw", 0) or 0)
    if not tot:
        return "还没有对局记录"
    return "人机 %d 胜 / %d 负 / %d 和" % (s.get("win", 0), s.get("lose", 0),
                                          s.get("draw", 0))


def _stat_gomoku():
    d = load_save("gomoku_save.json")
    s = d.get("stats") or {}
    tot = (s.get("win", 0) or 0) + (s.get("lose", 0) or 0) + (s.get("draw", 0) or 0)
    if not tot:
        return "还没有对局记录"
    rate = s.get("win", 0) * 100.0 / tot
    return "人机 %d 胜 / %d 负 / %d 平 · 胜率 %.0f%%" % (
        s.get("win", 0), s.get("lose", 0), s.get("draw", 0), rate)


def _stat_point24():
    st = (load_save("point24_save.json").get("stats") or {})
    solved = int(st.get("solved", 0) or 0)
    if not solved:
        return "还没有通关记录"
    fast = st.get("fastest")
    extra = " · 最快 %.1f 秒" % fast if fast else ""
    return "已通关 %d 题 · 最高连击 %d%s" % (solved, st.get("bestStreak", 0) or 0, extra)


STAT_FUNCS = {"_stat_sudoku": _stat_sudoku, "_stat_klotski": _stat_klotski,
              "_stat_number": _stat_number, "_stat_xiangqi": _stat_xiangqi,
              "_stat_gomoku": _stat_gomoku, "_stat_point24": _stat_point24}


class GameCard(QFrame):
    clicked = Signal(str)

    def __init__(self, key, emoji, name, desc, accent, stat_text, parent=None):
        super().__init__(parent)
        self.key = key
        self.accent = accent
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(178)
        self.setMinimumWidth(300)
        self.setAttribute(Qt.WA_Hover, True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(11)
        self.lb_emoji = QLabel(emoji)
        self.lb_emoji.setFixedSize(40, 40)
        self.lb_emoji.setAlignment(Qt.AlignCenter)
        self.lb_emoji.setStyleSheet("font-size:24px;")
        top.addWidget(self.lb_emoji, 0, Qt.AlignVCenter)
        self.lb_name = QLabel(name)
        self.lb_name.setStyleSheet("font-size:19px;font-weight:700;color:%s;" % C_TEXT)
        top.addWidget(self.lb_name, 0, Qt.AlignVCenter)
        top.addStretch(1)
        self.lb_go = QLabel("进入 →")
        self.lb_go.setStyleSheet("font-size:12.5px;font-weight:700;color:%s;" % accent)
        top.addWidget(self.lb_go, 0, Qt.AlignVCenter)
        lay.addLayout(top)

        d = QLabel(desc)
        d.setWordWrap(True)
        d.setStyleSheet("color:%s;font-size:12px;" % C_DIM)
        d.setMinimumHeight(46)
        lay.addWidget(d)
        lay.addStretch(1)

        self.lb_stat = QLabel(stat_text)
        self.lb_stat.setStyleSheet("color:%s;font-size:12px;font-weight:600;" % accent)
        lay.addWidget(self.lb_stat)

        self._hover = False
        self._apply_style()

    def _apply_style(self):
        if self._hover:
            bg = "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 %s,stop:1 %s)" % (
                C_PANEL2, C_PANEL)
            border = rgba(self.accent, 0.55)
        else:
            bg = "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 %s,stop:1 %s)" % (
                C_PANEL, "#111721")
            border = C_LINE
        self.setStyleSheet(
            "GameCard{background:%s;border:1px solid %s;border-radius:14px;}" % (bg, border))

    def enterEvent(self, ev):
        self._hover = True
        self._apply_style()
        self.update()

    def leaveEvent(self, ev):
        self._hover = False
        self._apply_style()
        self.update()

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.LeftButton and self.rect().contains(ev.position().toPoint()):
            self.clicked.emit(self.key)

    def paintEvent(self, ev):
        super().paintEvent(ev)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        # 左侧主题色竖条
        p.setBrush(QBrush(QColor(self.accent if self._hover else rgba(self.accent, 0.55))))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 14, 4, self.height() - 28, 2, 2)


class Launcher(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1200, 790)
        self.setMinimumSize(1000, 700)
        self.setStyleSheet(
            "QMainWindow{background:%s;}QLabel{color:%s;}"
            "QWidget{font-family:'Microsoft YaHei UI','Microsoft YaHei',sans-serif;}"
            % (C_BG, C_TEXT))
        self.game_win = None
        self.cards = []
        self._build_ui()
        self._refresh_stats()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(26, 20, 26, 18)
        root.setSpacing(14)

        head = QHBoxLayout()
        t = QLabel(APP_TITLE)
        t.setStyleSheet("font-size:26px;font-weight:800;letter-spacing:1px;")
        head.addWidget(t)
        chip = QLabel("%d 款小游戏 · 离线可玩" % len(GAMES))
        chip.setFixedHeight(28)
        chip.setStyleSheet("color:%s;background:%s;border:1px solid %s;border-radius:11px;"
                           "padding:0 10px;font-size:11.5px;font-weight:600;"
                           % (C_ACCENT2, rgba(C_ACCENT2, 0.12), rgba(C_ACCENT2, 0.3)))
        head.addWidget(chip, 0, Qt.AlignVCenter)
        head.addStretch(1)
        tip = QLabel("点击卡片进入游戏　·　游戏中按左上角「返回大厅」或 Esc 回到这里")
        tip.setStyleSheet("color:%s;font-size:12px;" % C_FAINT)
        head.addWidget(tip, 0, Qt.AlignVCenter)
        root.addLayout(head)

        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background:%s;" % C_LINE)
        root.addWidget(line)

        cols = 3 if len(GAMES) > 4 else 2
        grid = QGridLayout()
        grid.setSpacing(14)
        for idx, (key, mod, cls, emoji, name, desc, accent, statfn) in enumerate(GAMES):
            c = GameCard(key, emoji, name, desc, accent, "统计中…")
            c.clicked.connect(self.open_game)
            self.cards.append((c, statfn))
            grid.addWidget(c, idx // cols, idx % cols)
        row, col = len(GAMES) // cols, len(GAMES) % cols
        grid.addWidget(self._about_card(cols - col), row, col, 1, cols - col)
        root.addLayout(grid, 1)

        foot = QHBoxLayout()
        self.lb_total = QLabel("")
        self.lb_total.setStyleSheet("color:%s;font-size:12px;" % C_DIM)
        foot.addWidget(self.lb_total)
        foot.addStretch(1)
        self.lb_hint = QLabel("快捷键：" + "　".join("%d %s" % (i + 1, g[4])
                                          for i, g in enumerate(GAMES)))
        self.lb_hint.setStyleSheet("color:%s;font-size:12px;" % C_FAINT)
        foot.addWidget(self.lb_hint)
        root.addLayout(foot)

    def _about_card(self, span=1):
        f = QFrame()
        f.setFixedHeight(178 if span <= 1 else 132)
        f.setMinimumWidth(300)
        f.setStyleSheet("QFrame{background:%s;border:1px dashed %s;border-radius:14px;}"
                        % ("#111721", C_LINE2))
        lay = QVBoxLayout(f)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(6)
        t = QLabel("关于")
        t.setStyleSheet("font-size:15px;font-weight:700;color:%s;" % C_DIM)
        lay.addWidget(t)
        for line in ("%d 款单机小游戏打包在同一个 exe 中，零联网、零依赖。" % len(GAMES),
                     "所有进度与战绩都存在 exe 同目录的 * _save.json 里。",
                     "游戏中按 Esc 或左上角「返回大厅」即可回到本页。"):
            lb = QLabel(line)
            lb.setWordWrap(True)
            lb.setStyleSheet("color:%s;font-size:12px;" % C_FAINT)
            lay.addWidget(lb)
        lay.addStretch(1)
        self.lb_where = QLabel("")
        self.lb_where.setWordWrap(True)
        self.lb_where.setStyleSheet("color:%s;font-size:11px;" % C_FAINT)
        lay.addWidget(self.lb_where)
        return f

    def _refresh_stats(self):
        for card, statfn in self.cards:
            try:
                card.lb_stat.setText(STAT_FUNCS[statfn]())
            except Exception:
                card.lb_stat.setText("暂无记录")
        total = 0
        d = load_save("sudoku_save.json").get("levels") or {}
        total += sum((v.get("plays") or 0) for v in d.values())
        for name in ("klotski_save.json", "number_save.json"):
            lv = load_save(name).get("levels") or {}
            total += sum((v.get("clears") or 0) for v in lv.values())
        for name in ("xiangqi_save.json", "gomoku_save.json"):
            s = (load_save(name).get("stats") or {})
            total += sum(int(s.get(x, 0) or 0) for x in ("win", "lose", "draw"))
        total += int((load_save("point24_save.json").get("stats") or {}).get("solved", 0) or 0)
        self.lb_total.setText("累计游玩 %d 局" % total if total else "本地存档：还没开始玩过")
        try:
            from shared.common import data_dir
            self.lb_where.setText("存档目录：%s" % data_dir())
        except Exception:
            pass

    # -------- 打开游戏
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

    # -------- 键盘
    def keyPressEvent(self, ev):
        if Qt.Key_1 <= ev.key() <= Qt.Key_9:
            idx = ev.key() - Qt.Key_1
            if idx < len(GAMES):
                self.open_game(GAMES[idx][0])
                return
        super().keyPressEvent(ev)

    def closeEvent(self, ev):
        if self.game_win is not None:
            try:
                self.game_win.close()
            except Exception:
                pass
        super().closeEvent(ev)
        QApplication.quit()


def launch():
    w = Launcher()
    w.show()
    return w


if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)
    w = Launcher()
    w.show()
    sys.exit(app.exec())
