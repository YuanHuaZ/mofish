# -*- coding: utf-8 -*-
"""
摸鱼小游戏合集 · 统一入口

启动后进入游戏大厅，可从中选择 数独 / 华容道 / 数字华容道 /
中国象棋 / 五子棋 / 24 点；象棋与五子棋还支持局域网联机对战。
所有游戏共用一个 exe、一套本地存档（与 exe 同目录）。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from PySide6.QtWidgets import QApplication  # noqa: E402

from hall.launcher import Launcher, GAMES  # noqa: E402

APP_NAME = "摸鱼小游戏"


# ------------------------------------------------------------------ 自检
def selftest(app):
    """离屏跑一遍全部游戏：校验引擎 + 界面截图，结果写入 selftest.log"""
    import importlib
    import traceback
    import time
    from shared.common import data_dir, resource_dir

    lines = []
    ok_all = True

    def log(msg):
        lines.append(str(msg))

    def run(tag, fn):
        nonlocal ok_all
        try:
            r = fn()
            log("[OK]   %s：%s" % (tag, r))
            return r
        except Exception as exc:
            ok_all = False
            log("[FAIL] %s：%s" % (tag, exc))
            log(traceback.format_exc())
            return None

    log("SELFTEST %s" % APP_NAME)
    log("资源目录 = %s" % resource_dir())
    log("存档目录 = %s" % data_dir())
    log("Python  = %s" % sys.version.split()[0])
    try:
        import PySide6
        from PySide6 import QtCore
        log("PySide6 = %s / Qt %s" % (PySide6.__version__, QtCore.__version__))
    except Exception:
        pass
    log("-" * 62)

    outdir = os.path.join(data_dir(), "selftest_shots")
    os.makedirs(outdir, exist_ok=True)

    def shoot(win, name):
        for _ in range(12):
            app.processEvents()
        path = os.path.join(outdir, name + ".png")
        win.grab().save(path)
        return "%s.png (%d 字节)" % (name, os.path.getsize(path))

    # ---- 引擎校验
    def t_sudoku_engine():
        from sudoku import engine as SE
        from shared.common import load_game_json
        data = load_game_json("puzzles.json", "sudoku").get("levels") or {}
        assert len(data) == 100, "题池只有 %d 关" % len(data)
        for lv in (1, 50, 100):
            g = SE.generate(lv, 12)
            assert len(g["puzzle"]) == 81 and len(g["solution"]) == 81
            assert SE.is_solved(g["solution"], g["solution"])
            assert all(g["solution"]) and not any(g["puzzle"][i] != g["solution"][i]
                                                 for i in range(81)
                                                 if g["puzzle"][i])
        return "题池 100 关；第 1/50/100 关现算校验通过"

    def t_klotski_engine():
        from klotski import engine as KE
        from shared.common import load_game_json
        data = load_game_json("levels.json", "klotski")
        lv = data.get("levels") or []
        assert lv, "缺少 klotski_levels.json"
        for item in lv:
            g = KE.Klotski(item["layout"])
            for mv in item["solution"]:
                assert g.apply_move_dict(mv)
            assert g.solved()
        steps = [i["minSteps"] for i in lv]
        assert steps == sorted(steps), "关卡步数未按难度递增"
        return "%d 关最优解可重放，步数 %s" % (len(lv), steps)

    def t_xiangqi_engine():
        from xiangqi import engine as XE
        b = XE.initial_board()
        p1 = len(XE.legal_moves(b, XE.RED))
        assert p1 == 44, "初始着法数 %d != 44" % p1
        p2 = XE.perft(b, XE.RED, 2)
        assert p2 == 1920, "perft(2) = %d != 1920" % p2
        return "初始着法 44、perft(2) 1920 全部匹配标准值"

    def t_xiangqi_mate():
        from xiangqi import engine as XE
        b = [None] * 90
        b[XE.idx(4, 0)] = "bK"
        b[XE.idx(4, 9)] = "rK"
        b[XE.idx(4, 8)] = "rR"
        b[XE.idx(0, 0)] = "rR"
        assert XE.state_of(b, XE.BLACK) == "checkmate"
        return "双车将死判定正确"

    def t_gomoku_engine():
        from gomoku import engine as GE
        g = GE.Gomoku()
        for x in range(3, 7):
            g.board[7][x] = GE.BLACK
        g.moves = [(x, 7, GE.BLACK) for x in range(3, 7)]
        mv = g.best_move(GE.BLACK, "hard")
        assert mv and mv[1] == 7 and mv[0] in (2, 7), "四连必胜点判定失败：%s" % (mv,)
        g2 = GE.Gomoku()
        for x in range(5, 8):
            g2.board[7][x] = GE.WHITE
        mv2 = g2.best_move(GE.BLACK, "hard")
        return "连五取胜 %s、活三防守 %s" % (mv, mv2)

    def t_number_engine():
        from numberklotski import engine as NE
        from shared.common import load_game_json
        lv = load_game_json("levels.json", "numberklotski").get("levels") or []
        assert lv, "缺少 numberklotski/levels.json"
        prev_score, prev_n, sizes = -1, 0, []
        for item in lv:
            assert NE.is_solvable(item["tiles"], item["n"]), \
                "第%d关不可解" % item["level"]
            assert item["score"] > prev_score, "第%d关难度分未递增" % item["level"]
            assert item["n"] >= prev_n, "第%d关棋盘反而变小" % item["level"]
            prev_score, prev_n = item["score"], item["n"]
            if not sizes or sizes[-1] != item["n"]:
                sizes.append(item["n"])
        # 3×3 最优提示必须合法
        p = NE.NumberPuzzle(3, NE.shuffle(3, 40, 7))
        idx = p.hint()
        assert idx in p.movable(), "提示不是合法移动"
        # 打乱后必然可解
        for scr in (20, 120):
            for n in (3, 4, 5):
                t = NE.shuffle(n, scr, 42)
                assert NE.is_solvable(t, n)
        return ("%d 关全部可解、难度分 %d→%d 严格递增（%s）；3×3 最优提示与打乱可解性校验通过"
                % (len(lv), lv[0]["score"], lv[-1]["score"],
                   "/".join("%d×%d" % (n, n) for n in sizes)))

    # ---- 界面截图
    windows = []
    for key, mod_name, cls_name, _e, name, *_rest in GAMES:
        def build(mod_name=mod_name, cls_name=cls_name):
            mod = importlib.import_module(mod_name)
            w = getattr(mod, cls_name)()
            w.resize(1080, 900)
            windows.append(w)
            return shoot(w, "game_" + key)
        run("界面 %s" % name, build)

    def t_launcher():
        w = Launcher()
        w.resize(940, 640)
        windows.append(w)
        return shoot(w, "launcher")

    run("界面 游戏大厅", t_launcher)

    def t_point24_engine():
        from point24 import engine as P24
        from shared.common import load_game_json
        data = load_game_json("puzzles.json", "point24")
        bank = P24.bank_from_json(data)
        assert bank, "缺少 point24/puzzles.json"
        for tier in P24.TIER_ORDER:
            assert bank.get(tier), "档位 %s 题库为空" % tier
            for combo in bank[tier][:40]:
                assert P24.can_make(combo), "%s 里的 %s 无解" % (tier, combo)
        inner = sum(len(v) for v in bank.values())
        # 经典分数解：1 3 4 6 只有唯一解
        sols = P24.solutions((1, 3, 4, 6))
        assert len(sols) == 1 and sols[0]["expr"] == "6÷(1-3÷4)", \
            "1 3 4 6 的解法不对：%s" % [s["expr"] for s in sols]
        assert not P24.can_make((1, 3, 4, 6), int_only=True)
        # 加减乘除各种输入写法都能识别
        for text in ("8*3+3-3", "8×3+3-3", "8x3+3-3", "8＊3＋3－3", "８×３＋３－３"):
            assert P24.eval_expression(text, [8, 3, 3, 3])[0] == 24, text
        for bad in ("6*4", "8/0", "8+3*3"):
            try:
                P24.eval_expression(bad, [1, 3, 4, 6])
                raise AssertionError("非法输入未被拒绝：%s" % bad)
            except ValueError:
                pass
        return ("题库 %d 题、%d 个档位全部有解；1 3 4 6 唯一解为 6÷(1-3÷4)；"
                "加减乘除多种写法均可识别" % (inner, len(P24.TIER_ORDER)))

    def t_lan():
        """局域网联机：同机起两个会话，验证发现、连接、走子同步、悔棋一致"""
        from shared.lan import LanSession
        from gomoku import gomoku_app as GA
        from xiangqi import xiangqi_app as XA
        import xiangqi.engine as XE

        def wait(cond, t=6.0):
            t0 = time.time()
            while time.time() - t0 < t:
                app.processEvents()
                if cond():
                    return True
                time.sleep(0.02)
            return False

        rooms = []
        A = GA.GomokuWindow()
        B = GA.GomokuWindow()
        sa = LanSession("gomoku", "测试房主")
        sb = LanSession("gomoku", "测试加入")
        try:
            ok, err = sa.start_host(want_first=True)
            assert ok, "建房失败：%s" % err
            A.net = sa
            A.lan_seat, A.lan_peer, A.human = 0, "测试加入", 1
            sa.message.connect(A._on_lan_message)
            sa.closed.connect(A._on_lan_closed)
            # 广播发现
            sb.rooms.connect(lambda lst: (rooms.clear(), rooms.extend(lst)))
            sb.start_discover()
            assert wait(lambda: len(rooms) >= 1, 5), "没发现到房间"
            found = [r for r in rooms if r["port"] == sa.port]
            assert found, "发现的房间端口不对：%s" % rooms
            # 连接
            sb.start_join("127.0.0.1", sa.port)
            assert wait(lambda: sa.connected and sb.connected), "连接超时"
            B.net = sb
            B.lan_seat, B.lan_peer, B.human = int(sb.seat), "测试房主", 2
            sb.message.connect(B._on_lan_message)
            sb.closed.connect(B._on_lan_closed)
            assert int(sb.seat) == 1, "加入方座位号应为 1"
            A.restart(silent=True)
            B.restart(silent=True)
            assert not A.view.locked and B.view.locked, "先手/后手锁定状态不对"
            # 走子同步
            def play_two():
                A.restart(silent=True)
                B.restart(silent=True)
                A.human_play(7, 7)
                assert wait(lambda: len(B.view.game.moves) == 1), "对手没收到黑棋"
                assert not B.view.locked, "对手收到后应该轮到他走"
                B.human_play(7, 8)
                assert wait(lambda: len(A.view.game.moves) == 2), "房主没收到白棋"
                assert A.view.game.board == B.view.game.board, "两边棋盘不一致"

            play_two()
            # 最后一手是白方 → 白方悔棋只撤 1 手，回到白方行棋
            A._apply_undo(GA.GE.WHITE)
            B._apply_undo(GA.GE.WHITE)
            assert len(A.view.game.moves) == len(B.view.game.moves) == 1, "悔棋后手数不一致"
            assert A.view.game.current == GA.GE.WHITE == B.view.game.current, \
                "白方悔棋后应由白棋行棋"
            assert A.view.game.board == B.view.game.board
            # 最后一手是白方、黑方悔棋 → 撤 2 手，回到黑方行棋
            play_two()
            A._apply_undo(GA.GE.BLACK)
            B._apply_undo(GA.GE.BLACK)
            assert len(A.view.game.moves) == len(B.view.game.moves) == 0, "悔棋后手数不一致"
            assert A.view.game.current == GA.GE.BLACK == B.view.game.current, \
                "黑方悔棋后应由黑棋行棋"
            assert A.view.game.board == B.view.game.board
            # 象棋：同样跑 4 手 + 悔棋
            CA = XA.XiangqiWindow()
            CB = XA.XiangqiWindow()
            xa = LanSession("xiangqi", "棋A")
            xb = LanSession("xiangqi", "棋B")
            try:
                ok, err = xa.start_host(want_first=True)
                assert ok, "象棋建房失败：%s" % err
                CA.net, CA.mode, CA.lan_peer = xa, "lan", "棋B"
                CA.human_color = XE.RED
                xa.message.connect(CA._on_lan_message)
                xa.closed.connect(CA._on_lan_closed)
                xb.start_join("127.0.0.1", xa.port)
                assert wait(lambda: xa.connected and xb.connected), "象棋连接超时"
                CB.net, CB.mode, CB.lan_peer = xb, "lan", "棋A"
                CB.human_color = XE.BLACK
                xb.message.connect(CB._on_lan_message)
                xb.closed.connect(CB._on_lan_closed)
                CA._new_game()
                CB._new_game()
                seq = [("A", (1, 7), (4, 7)), ("B", (7, 0), (6, 2)),
                       ("A", (7, 9), (6, 7)), ("B", (1, 0), (2, 2))]
                for who, fr, to in seq:
                    w, o = (CA, CB) if who == "A" else (CB, CA)
                    need = len(w.history) + 1
                    w.do_move((XE.idx(*fr), XE.idx(*to)))
                    assert wait(lambda n=need: len(o.history) >= n), "象棋着法没同步"
                assert CA.board == CB.board, "象棋两边局面不一致"
                assert [h[3] for h in CA.history] == [h[3] for h in CB.history]
                CA._apply_undo(XE.RED)
                CB._apply_undo(XE.RED)
                assert CA.board == CB.board and len(CA.history) == len(CB.history) == 2
                assert CA.turn == XE.RED == CB.turn, "悔棋后应由红方行棋"
            finally:
                xa.close()
                xb.close()
                CA.close()
                CB.close()
        finally:
            sa.close()
            sb.close()
            A.close()
            B.close()
        return ("房间发现/连接正常；五子棋走子与悔棋同步；"
                "象棋 4 手着法一致 + 中文棋谱一致 + 悔棋后轮到红方")

    log("-" * 62)
    run("引擎 数独 100 关", t_sudoku_engine)
    run("引擎 华容道最优解", t_klotski_engine)
    run("引擎 数字华容道", t_number_engine)
    run("引擎 象棋规则", t_xiangqi_engine)
    run("引擎 象棋将死", t_xiangqi_mate)
    run("引擎 五子棋 AI", t_gomoku_engine)
    run("引擎 24 点", t_point24_engine)
    run("联机 局域网对战", t_lan)

    log("-" * 62)
    log("结论：%s" % ("全部通过 ✔" if ok_all else "存在失败项 ✘"))
    text = "\n".join(lines)
    for w in windows:
        try:
            w.close()
        except Exception:
            pass
    try:
        with open(os.path.join(data_dir(), "selftest.log"), "w", encoding="utf-8") as f:
            f.write(text + "\n")
    except Exception:
        pass
    try:
        print(text)
    except Exception:
        pass
    return 0 if ok_all else 1


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)     # 由大厅统一控制退出
    if "--selftest" in sys.argv:
        sys.exit(selftest(app))
    w = Launcher()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
