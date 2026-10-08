# -*- coding: utf-8 -*-
"""
五子棋引擎（无 GUI，可独立测试）

- 15x15 标准棋盘，无禁手（自由规则）
- 胜负判定 / 候选点生成 / 棋型窗口打分
- 启发式 AI：一步制胜、必堵、双威胁、可选两层预判
"""
import random

SIZE = 15
EMPTY, BLACK, WHITE = 0, 1, 2
DIRS = ((1, 0), (0, 1), (1, 1), (1, -1))

# ---------------------------------------------------------------- 棋型分值
S_FIVE = 1000000        # 连五
S_LIVE4 = 100000        # 活四
S_RUSH4 = 12000         # 冲四 / 跳四
S_LIVE3 = 10000         # 活三
S_SLEEP3 = 1200         # 眠三
S_LIVE2 = 800           # 活二
S_SLEEP2 = 120          # 眠二
S_LIVE1 = 20            # 活一

# 9 格窗口内的棋型（1=己方 2=对方/界外 0=空），取窗口内最高分棋型
PATTERNS = [
    ("11111", S_FIVE),
    ("011110", S_LIVE4),
    ("011112", S_RUSH4), ("211110", S_RUSH4),
    ("11011", S_RUSH4), ("10111", S_RUSH4), ("11101", S_RUSH4),
    ("01110", S_LIVE3),
    ("010110", S_LIVE3), ("011010", S_LIVE3),
    ("001112", S_SLEEP3), ("211100", S_SLEEP3),
    ("010112", S_SLEEP3), ("211010", S_SLEEP3),
    ("011012", S_SLEEP3), ("210110", S_SLEEP3),
    ("10011", S_SLEEP3), ("11001", S_SLEEP3), ("10101", S_SLEEP3),
    ("001100", S_LIVE2),
    ("001010", S_LIVE2), ("010100", S_LIVE2),
    ("000100", S_LIVE1),
]


def opponent(p):
    return WHITE if p == BLACK else BLACK


def new_board():
    return [[EMPTY] * SIZE for _ in range(SIZE)]


def in_board(x, y):
    return 0 <= x < SIZE and 0 <= y < SIZE


def win_line(board, x, y):
    """若 (x,y) 落子后成五（或长连），返回构成连线的坐标列表，否则 None"""
    p = board[y][x]
    if p == EMPTY:
        return None
    for dx, dy in DIRS:
        cells = [(x, y)]
        for s in (1, -1):
            k = 1
            while True:
                nx, ny = x + dx * k * s, y + dy * k * s
                if in_board(nx, ny) and board[ny][nx] == p:
                    cells.append((nx, ny))
                    k += 1
                else:
                    break
        if len(cells) >= 5:
            return cells
    return None


def point_score(board, x, y, p):
    """假定 p 在 (x,y) 落子，返回该点的威胁分（4 个方向求和）"""
    if board[y][x] != EMPTY:
        return -1
    black_view = (p == BLACK)
    total = 0
    for dx, dy in DIRS:
        s = _window_side(board, x, y, dx, dy, black_view)
        total += _best_pattern(s)
    return total


def _window_side(board, x, y, dx, dy, black_view):
    """按指定视角构造窗口：己方=1 对方=2"""
    chars = []
    for k in range(-4, 5):
        if k == 0:
            chars.append("1")
            continue
        nx, ny = x + dx * k, y + dy * k
        if not in_board(nx, ny):
            chars.append("2")
            continue
        v = board[ny][nx]
        if v == EMPTY:
            chars.append("0")
        elif (v == BLACK) == black_view:
            chars.append("1")
        else:
            chars.append("2")
    return "".join(chars)


def _best_pattern(s):
    best = 0
    for pat, val in PATTERNS:
        if pat in s:
            if val > best:
                best = val
    return best


def candidates(board, radius=2):
    """候选点：已有棋子附近 radius 格内的空点；空盘返回中心"""
    pts = []
    has_stone = False
    for y in range(SIZE):
        for x in range(SIZE):
            if board[y][x]:
                has_stone = True
                break
        if has_stone:
            break
    if not has_stone:
        c = SIZE // 2
        return [(c, c)]
    seen = set()
    for y in range(SIZE):
        for x in range(SIZE):
            if not board[y][x]:
                continue
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    nx, ny = x + dx, y + dy
                    if in_board(nx, ny) and board[ny][nx] == EMPTY and (nx, ny) not in seen:
                        seen.add((nx, ny))
                        pts.append((nx, ny))
    return pts


def _center_bonus(x, y):
    c = SIZE // 2
    return -(abs(x - c) + abs(y - c))


class Gomoku(object):
    """一局五子棋的状态与 AI"""

    def __init__(self):
        self.reset()

    def reset(self):
        self.board = new_board()
        self.moves = []            # [(x, y, player)]
        self.winner = 0
        self.win_cells = None
        self.current = BLACK

    # -------- 基础操作
    def play(self, x, y):
        if self.winner or not in_board(x, y) or self.board[y][x] != EMPTY:
            return False
        self.board[y][x] = self.current
        self.moves.append((x, y, self.current))
        line = win_line(self.board, x, y)
        if line:
            self.winner = self.current
            self.win_cells = line
        self.current = opponent(self.current)
        return True

    def undo(self, steps=1):
        for _ in range(steps):
            if not self.moves:
                return
            x, y, p = self.moves.pop()
            self.board[y][x] = EMPTY
            self.winner = 0
            self.win_cells = None
            self.current = p

    def can_play(self):
        return not self.winner and len(self.moves) < SIZE * SIZE

    def last_move(self):
        return self.moves[-1] if self.moves else None

    # -------- AI
    def best_move(self, me, level="normal"):
        """返回 (x, y)；level ∈ easy / normal / hard"""
        opp = opponent(me)
        cands = candidates(self.board)
        if not cands:
            return None

        scored = []
        for (x, y) in cands:
            atk = point_score(self.board, x, y, me)
            dfd = point_score(self.board, x, y, opp)
            scored.append((atk, dfd, x, y))
        scored.sort(key=lambda t: (t[0] + t[1] * 0.9), reverse=True)

        # 1) 自己能连五 → 直接赢
        for atk, dfd, x, y in scored:
            if atk >= S_FIVE:
                return (x, y)
        # 2) 对手能连五 → 必须堵（选堵点中自己收益最高的）
        blocks = [(atk, dfd, x, y) for atk, dfd, x, y in scored if dfd >= S_FIVE]
        if blocks:
            blocks.sort(key=lambda t: t[0], reverse=True)
            return (blocks[0][2], blocks[0][3])

        if level == "easy":
            # 只按固定权重打分，并保留一定随机性，避免过于凶狠
            top = sorted(scored, key=lambda t: t[0] + t[1] * 0.5, reverse=True)[:4]
            weights = [4, 3, 2, 1][:len(top)]
            pick = random.choices(top, weights=weights)[0]
            return (pick[2], pick[3])

        weight = 0.9 if level == "hard" else 0.8
        scored.sort(key=lambda t: t[0] + t[1] * weight + _center_bonus(t[2], t[3]) * 2,
                    reverse=True)

        if level != "hard":
            atk, dfd, x, y = scored[0]
            return (x, y)

        # hard：对前若干候选做一层「对手最佳回应」预判
        top = scored[:10]
        best_move, best_val = top[0][2:], -1e18
        for atk, dfd, x, y in top:
            self.board[y][x] = me
            opp_best = 0
            for (ox, oy) in candidates(self.board)[:36]:
                s = point_score(self.board, ox, oy, opp)
                if s > opp_best:
                    opp_best = s
            self.board[y][x] = EMPTY
            val = atk + dfd * weight - opp_best * 0.85 + _center_bonus(x, y) * 2
            if val > best_val:
                best_val, best_move = val, (x, y)
        return best_move

    # -------- 序列化
    def dump(self):
        return {"moves": self.moves, "current": self.current, "winner": self.winner}

    def load(self, data):
        self.reset()
        for mv in (data or {}).get("moves", []):
            x, y, p = mv
            if in_board(x, y) and self.board[y][x] == EMPTY:
                self.board[y][x] = p
                self.moves.append((x, y, p))
        if self.moves:
            line = win_line(self.board, self.moves[-1][0], self.moves[-1][1])
            if line:
                self.winner = self.moves[-1][2]
                self.win_cells = line
        self.current = data.get("current", BLACK) if data else BLACK
        if self.winner:
            self.current = self.winner


if __name__ == "__main__":
    # 简易自检：AI 对 AI + 必胜/必堵用例
    b = new_board()
    g = Gomoku()
    # 用例：黑有四连，白必须堵
    for k in range(4):
        b[7][3 + k] = BLACK
    b[7][2] = WHITE
    move = Gomoku()
    move.board = [row[:] for row in b]
    print("堵四连:", move.best_move(WHITE, "hard"))
    # 自对弈
    g = Gomoku()
    while g.can_play():
        mv = g.best_move(g.current, "hard")
        if not mv:
            break
        g.play(*mv)
    print("自对弈手数:", len(g.moves), "胜者:", g.winner)
