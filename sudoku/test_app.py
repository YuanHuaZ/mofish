# -*- coding: utf-8 -*-
"""桌面应用离屏自测：校验题库 + 驱动游戏流程 + 截图"""
import json
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import engine as E                                             # noqa: E402
from PySide6.QtWidgets import QApplication                     # noqa: E402
from PySide6.QtCore import Qt                                  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SHOT = os.path.join(HERE, "shots")
os.makedirs(SHOT, exist_ok=True)


# ---------------------------------------------------------- 1. 题库校验
def check_pool():
    with open(os.path.join(HERE, "puzzles.json"), "r", encoding="utf-8") as f:
        data = json.load(f)
    levels = data["levels"]
    print("=== 题库校验 ===")
    print("关卡数: %d  题目总数: %d" % (len(levels), sum(len(v["puzzles"]) for v in levels.values())))
    bad = []
    rows = []
    for lv in range(1, 101):
        lm = levels.get(str(lv))
        if not lm:
            bad.append("%d 缺失" % lv)
            continue
        first = lm["puzzles"][0]
        assert lm["givens"] == first["givens"], lv
        rows.append((lv, lm["tierName"], lm["givens"], first["rating"],
                     first["difficulty"], lm["target"], len(lm["puzzles"])))
        for pz in lm["puzzles"]:
            board = E.from_string(pz["p"])
            sol = E.from_string(pz["s"])
            if len(pz["p"]) != 81 or len(pz["s"]) != 81:
                bad.append("%d 长度异常" % lv)
                continue
            # 题面必须是解的子集
            if any(board[i] and board[i] != sol[i] for i in range(81)):
                bad.append("%d 题面与解冲突" % lv)
            # 解必须合法
            if E.find_conflicts(sol) and any(E.find_conflicts(sol)):
                bad.append("%d 解答有冲突" % lv)
            # 唯一解
            if E.count_solutions(board, 3) != 1:
                bad.append("%d 解不唯一" % lv)
    print("提示数单调性:", "OK" if all(rows[i][2] >= rows[i + 1][2] - 3 for i in range(len(rows) - 1)) else "偏松")
    tiers = {}
    for r in rows:
        tiers.setdefault(r[1], 0)
        tiers[r[1]] += 1
    print("档位分布:", "  ".join("%s=%d" % (k, v) for k, v in tiers.items()))
    seg = []
    for s in range(0, 100, 10):
        seg.append(sum(r[4] for r in rows[s:s + 10]) / 10.0)
    print("每 10 关平均难度分:", " → ".join("%.1f" % x for x in seg))
    print("严格递增:", "是" if all(seg[i] < seg[i + 1] for i in range(len(seg) - 1)) else "否")
    print("偏差均值: %.2f  最大: %.1f" % (
        sum(abs(r[4] - r[5]) for r in rows) / len(rows),
        max(abs(r[4] - r[5]) for r in rows)))
    print("1-2 关锚点: 第1关 %s/%d提示/%s  第2关 %s/%d提示/%s" % (
        rows[0][1], rows[0][2], E.RATING_TEXT[rows[0][3]],
        rows[1][1], rows[1][2], E.RATING_TEXT[rows[1][3]]))
    print("错误:", "无" if not bad else bad[:8])
    return not bad


# ---------------------------------------------------------- 2. 驱动应用
def drive():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    import sudoku_app as S

    # 用临时存档目录，避免污染真实进度
    S.data_dir = lambda: SHOT
    S.HERE_PROBE = True

    w = S.MainWindow()
    w.resize(1000, 760)
    w.show()

    for _ in range(6):
        app.processEvents()
        time.sleep(0.05)

    print("\n=== 应用启动 ===")
    print("第 %d 关 | %s | 提示数 %s | 技巧 %s" % (
        w.level, w.diff["tier_name"], w.diff["givens"], E.RATING_TEXT[w.diff["rating"]]))
    assert w.board.ready, "棋盘未就绪"

    # 截图 1：初始界面
    w.grab().save(os.path.join(SHOT, "01-初始界面.png"))

    # 选一个空格，填一个错误数字，观察标红
    empty = [i for i in range(81) if not w.puzzle[i]][0]
    w.select_cell(empty)
    correct = w.solution[empty]
    wrong = 1 if correct != 1 else 2
    w.place(wrong)
    print("填入错误数字 %d → 冲突标红: %s" % (wrong, bool(E.find_conflicts(w.grid)[empty])))
    w.grab().save(os.path.join(SHOT, "02-冲突标红.png"))

    # 撤销
    w.undo()
    print("撤销后该格恢复为空:", w.grid[empty] == 0)

    # 备注模式
    w.toggle_note()
    w.place(correct)
    has_note = bool(w.notes[empty])
    print("备注模式填入 %d → 生成小字候选: %s" % (correct, has_note))
    w.toggle_note()
    w.grab().save(os.path.join(SHOT, "03-备注小字.png"))

    # 提示
    n0 = w.hints_left
    w.give_hint()
    print("提示：剩余 %d → %d，填充格=%s" % (n0, w.hints_left, w.sel))
    w.grab().save(os.path.join(SHOT, "04-提示填充.png"))

    # 暂停
    w.toggle_pause()
    print("暂停后 running=%s  棋盘遮罩=%s" % (w.running, w.board.paused))
    w.grab().save(os.path.join(SHOT, "05-暂停遮罩.png"))
    w.toggle_pause()

    # 选关对话框
    dlg = S.LevelDialog(w, w.store, w.level)
    dlg.resize(660, 560)
    dlg.show()
    for _ in range(4):
        app.processEvents(); time.sleep(0.03)
    dlg.grab().save(os.path.join(SHOT, "06-选关.png"))
    print("选关面板: 生成按钮数 =", len(dlg.findChildren(S.QPushButton)))
    dlg.close()

    # 记录对话框
    rd = S.RecordDialog(w, w.store)
    rd.resize(680, 580)
    rd.show()
    for _ in range(4):
        app.processEvents(); time.sleep(0.03)
    rd.grab().save(os.path.join(SHOT, "07-记录.png"))
    rd.close()

    # 通关流程：直接把解答灌进去
    # 无头环境下不能真弹模态窗，替换 exec 记录内容后返回
    from PySide6.QtWidgets import QLabel
    captured = {}

    def fake_exec(self):
        captured["labels"] = [c.text() for c in self.findChildren(QLabel)]
        captured["buttons"] = [c.text() for c in self.findChildren(S.QPushButton)]
        self.choice = "replay"          # 选“同难度再来一局”
        return 1

    S.WinDialog.exec = fake_exec
    lv_before = w.level
    w.grid = list(w.solution)
    w.refresh()
    w._check_win()
    app.processEvents()
    print("填满正确解答 → finished=%s" % w.finished)
    print("通关弹窗标签:", captured.get("labels"))
    print("通关弹窗按钮:", captured.get("buttons"))
    for _ in range(20):
        app.processEvents(); time.sleep(0.04)
        if w.board.ready and not w.finished:
            break
    rec = w.store.level(lv_before)
    print("记录: 最佳=%s ms, 完成=%s 次" % (rec["best"], rec["wins"]))
    print("当前进度已推进到第 %s 关" % w.store.data["meta"]["currentLevel"])
    print("点「同难度再来一局」→ 仍在第 %d 关, 已重置=%s" % (w.level, not w.finished))

    # 同难度换题：题面必须不同、难度档位保持一致
    before = E.to_string(w.puzzle)
    lv, tier_before = w.level, w.diff["tier_name"]
    w.start_level(w.level, avoid=before)
    for _ in range(30):
        app.processEvents(); time.sleep(0.05)
        if w.board.ready and E.to_string(w.puzzle) != before:
            break
    after = E.to_string(w.puzzle)
    print("换一题：题面不同=%s  档位 %s → %s  难度分 %s → %s" % (
        after != before, tier_before, w.diff["tier_name"],
        round(E.difficulty_score(81 - len([x for x in E.from_string(before) if x]),
                                 E.rate(E.from_string(before))[0]), 1),
        round(w.diff["difficulty"], 1)))
    w.grab().save(os.path.join(SHOT, "08-换题后.png"))

    # 跨关卡截几张，检查难度递增的外观
    for lv, name in ((1, "09-第1关送分"), (2, "10-第2关正常"), (50, "11-第50关"), (100, "12-第100关地狱")):
        w.start_level(lv, force_generate=False)
        for _ in range(20):
            app.processEvents(); time.sleep(0.04)
            if w.board.ready and w.level == lv:
                break
        w.grab().save(os.path.join(SHOT, name + ".png"))
        print("第 %3d 关 截图: %s · %s · %s" % (
            w.level, w.diff["tier_name"], str(w.diff["givens"]) + " 提示",
            E.RATING_TEXT[w.diff["rating"]]))

    # 存档/恢复
    w.save_state()
    saved = w.store.data.get("state")
    print("\n存档写入: %s" % (bool(saved)))
    if saved:
        w2 = S.MainWindow()
        for _ in range(5):
            app.processEvents(); time.sleep(0.05)
        print("重启恢复: 关卡=%d 已填格数=%d 用时=%s 暂停=%s" % (
            w2.level, sum(1 for v in w2.grid if v), int(w2.elapsed), w2.board.paused))
        w2.close()
    w.close()
    print("\n截图目录:", SHOT)
    for f in sorted(os.listdir(SHOT)):
        if f.endswith(".png"):
            print("   ", f)


if __name__ == "__main__":
    ok = check_pool()
    drive()
    print("\n题库校验:", "通过" if ok else "有问题")
