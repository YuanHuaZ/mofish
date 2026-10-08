# -*- coding: utf-8 -*-
"""
中国象棋引擎（无 GUI，可独立测试）

棋盘：9 列 x 10 行；索引 i = y*9 + x，y=0 为黑方底线，y=9 为红方底线。
棋子：'rK' / 'bP' 形式（小写颜色 + 大写类型）
  K 将/帅  A 士/仕  B 象/相  N 马  R 车  C 炮  P 卒/兵

包含：完整走子规则（蹩马腿、塞象眼、炮翻山、飞将、过河兵横走）、
将军/将死/困毙判定、Alpha-Beta 搜索 + 静态搜索的 AI、中文着法记谱。
"""
import time

RED, BLACK = "r", "b"
DIRS = ((0, 1), (0, -1), (1, 0), (-1, 0))
ADIRS = ((1, 1), (1, -1), (-1, 1), (-1, -1))
BMOVES = ((2, 2), (2, -2), (-2, 2), (-2, -2))
NMOVES = ((1, 2), (2, 1), (2, -1), (1, -2), (-1, -2), (-2, -1), (-2, 1), (-1, 2))

CN_NUM = "一二三四五六七八九"
PIECE_NAME = {"K": ("帅", "将"), "A": ("仕", "士"), "B": ("相", "象"),
              "N": ("马", "馬"), "R": ("车", "車"), "C": ("炮", "砲"),
              "P": ("兵", "卒")}

# 起始局面
START = (
    [(x, 0, "b" + t) for x, t in enumerate("RNBAKABNR")] +
    [(1, 2, "bC"), (7, 2, "bC")] +
    [(x, 3, "bP") for x in (0, 2, 4, 6, 8)] +
    [(x, 9, "r" + t) for x, t in enumerate("RNBAKABNR")] +
    [(1, 7, "rC"), (7, 7, "rC")] +
    [(x, 6, "rP") for x in (0, 2, 4, 6, 8)]
)


def idx(x, y):
    return y * 9 + x


def xy(i):
    return i % 9, i // 9


def opp(c):
    return BLACK if c == RED else RED


def inside(x, y):
    return 0 <= x < 9 and 0 <= y < 10


def initial_board():
    b = [None] * 90
    for (x, y, p) in START:
        b[idx(x, y)] = p
    return b


def clone(board):
    return list(board)


def in_palace(x, y, color):
    if not 3 <= x <= 5:
        return False
    return 7 <= y <= 9 if color == RED else 0 <= y <= 2


def own_half(y, color):
    return y >= 5 if color == RED else y <= 4


def crossed(y, color):
    return y <= 4 if color == RED else y >= 5


def forward(color):
    return -1 if color == RED else 1


def find_king(board, color):
    want = color + "K"
    for i, p in enumerate(board):
        if p == want:
            return i
    return None


# ------------------------------------------------------------------ 走子生成
def gen_moves(board, color):
    """伪合法着法（不检查自将），返回 [(from, to)]"""
    res = []
    for i, p in enumerate(board):
        if not p or p[0] != color:
            continue
        x, y = i % 9, i // 9
        t = p[1]
        if t == "K":
            for dx, dy in DIRS:
                nx, ny = x + dx, y + dy
                if not in_palace(nx, ny, color):
                    continue
                q = board[idx(nx, ny)]
                if not q or q[0] != color:
                    res.append((i, idx(nx, ny)))
            # 飞将：同列且中间无子 → 可直接吃掉对方将/帅
            ek = find_king(board, opp(color))
            if ek is not None:
                ex, ey = xy(ek)
                if ex == x:
                    lo, hi = (min(y, ey), max(y, ey))
                    clear = all(board[idx(x, k)] is None for k in range(lo + 1, hi))
                    if clear:
                        res.append((i, ek))
        elif t == "A":
            for dx, dy in ADIRS:
                nx, ny = x + dx, y + dy
                if not in_palace(nx, ny, color):
                    continue
                q = board[idx(nx, ny)]
                if not q or q[0] != color:
                    res.append((i, idx(nx, ny)))
        elif t == "B":
            for dx, dy in BMOVES:
                nx, ny = x + dx, y + dy
                if not inside(nx, ny) or not own_half(ny, color):
                    continue
                if board[idx(x + dx // 2, y + dy // 2)] is not None:
                    continue                      # 塞象眼
                q = board[idx(nx, ny)]
                if not q or q[0] != color:
                    res.append((i, idx(nx, ny)))
        elif t == "N":
            for dx, dy in NMOVES:
                nx, ny = x + dx, y + dy
                if not inside(nx, ny):
                    continue
                lx, ly = (x + dx // 2, y) if abs(dx) == 2 else (x, y + dy // 2)
                if board[idx(lx, ly)] is not None:
                    continue                      # 蹩马腿
                q = board[idx(nx, ny)]
                if not q or q[0] != color:
                    res.append((i, idx(nx, ny)))
        elif t == "R":
            for dx, dy in DIRS:
                nx, ny = x + dx, y + dy
                while inside(nx, ny) and board[idx(nx, ny)] is None:
                    res.append((i, idx(nx, ny)))
                    nx += dx
                    ny += dy
                if inside(nx, ny) and board[idx(nx, ny)][0] != color:
                    res.append((i, idx(nx, ny)))
        elif t == "C":
            for dx, dy in DIRS:
                nx, ny = x + dx, y + dy
                while inside(nx, ny) and board[idx(nx, ny)] is None:
                    res.append((i, idx(nx, ny)))
                    nx += dx
                    ny += dy
                if not inside(nx, ny):
                    continue
                nx += dx
                ny += dy
                while inside(nx, ny) and board[idx(nx, ny)] is None:
                    nx += dx
                    ny += dy
                if inside(nx, ny) and board[idx(nx, ny)][0] != color:
                    res.append((i, idx(nx, ny)))
        elif t == "P":
            dy = forward(color)
            ny = y + dy
            if inside(x, ny):
                q = board[idx(x, ny)]
                if not q or q[0] != color:
                    res.append((i, idx(x, ny)))
            if crossed(y, color):
                for dx in (-1, 1):
                    nx = x + dx
                    if not inside(nx, y):
                        continue
                    q = board[idx(nx, y)]
                    if not q or q[0] != color:
                        res.append((i, idx(nx, y)))
    return res


# ------------------------------------------------------------------ 将军判定
def in_check(board, color):
    k = find_king(board, color)
    if k is None:
        return True
    kx, ky = k % 9, k // 9
    ek = opp(color)
    # 车 / 将（飞将）
    for dx, dy in DIRS:
        px, py = kx + dx, ky + dy
        while inside(px, py) and board[idx(px, py)] is None:
            px += dx
            py += dy
        if inside(px, py):
            p = board[idx(px, py)]
            if p[0] == ek and (p[1] == "R" or (p[1] == "K" and dx == 0)):
                return True
    # 炮（需要一个炮架）
    for dx, dy in DIRS:
        px, py = kx + dx, ky + dy
        while inside(px, py) and board[idx(px, py)] is None:
            px += dx
            py += dy
        if not inside(px, py):
            continue
        px += dx
        py += dy
        while inside(px, py) and board[idx(px, py)] is None:
            px += dx
            py += dy
        if inside(px, py):
            p = board[idx(px, py)]
            if p[0] == ek and p[1] == "C":
                return True
    # 马（含蹩腿）
    for dx, dy in NMOVES:
        nx, ny = kx + dx, ky + dy
        if not inside(nx, ny):
            continue
        p = board[idx(nx, ny)]
        if not (p and p[0] == ek and p[1] == "N"):
            continue
        lx, ly = (nx - dx // 2, ny) if abs(dx) == 2 else (nx, ny - dy // 2)
        if inside(lx, ly) and board[idx(lx, ly)] is None:
            return True
    # 兵/卒
    cand = ((kx, ky - 1), (kx, ky + 1), (kx - 1, ky), (kx + 1, ky))
    for (px, py) in cand:
        if not inside(px, py):
            continue
        p = board[idx(px, py)]
        if not (p and p[0] == ek and p[1] == "P"):
            continue
        if ek == BLACK:
            if px == kx and py == ky - 1:
                return True
            if py >= 5 and abs(px - kx) == 1 and py == ky:
                return True
        else:
            if px == kx and py == ky + 1:
                return True
            if py <= 4 and abs(px - kx) == 1 and py == ky:
                return True
    return False


def legal_moves(board, color):
    res = []
    for mv in gen_moves(board, color):
        cap = board[mv[1]]
        if cap and cap[1] == "K":
            res.append(mv)
            continue
        board[mv[1]] = board[mv[0]]
        board[mv[0]] = None
        ok = not in_check(board, color)
        board[mv[0]] = board[mv[1]]
        board[mv[1]] = cap
        if ok:
            res.append(mv)
    return res


def make(board, mv):
    """执行着法，返回被吃棋子以便撤销"""
    fr, to = mv
    cap = board[to]
    board[to] = board[fr]
    board[fr] = None
    return cap


def unmake(board, mv, cap):
    fr, to = mv
    board[fr] = board[to]
    board[to] = cap


def state_of(board, color):
    """返回 playing / check / checkmate / stalemate（困毙同样判负）"""
    moves = legal_moves(board, color)
    if not moves:
        return "checkmate" if in_check(board, color) else "stalemate"
    return "check" if in_check(board, color) else "playing"


# ------------------------------------------------------------------ 中文记谱
def notation(board, mv):
    """生成中文着法（如 炮二平五 / 马8进7）"""
    fr, to = mv
    p = board[fr]
    if not p:
        return "(非法着法)"
    c, t = p[0], p[1]
    fx, fy = fr % 9, fr // 9
    tx, ty = to % 9, to // 9
    name = PIECE_NAME[t][0 if c == RED else 1]

    def flabel(x):
        return CN_NUM[8 - x] if c == RED else str(x + 1)

    same = [i for i in range(90) if board[i] == p]
    same = [i for i in same if i % 9 == fx]
    if len(same) > 1 and t != "K":
        same.sort(key=lambda i: i // 9, reverse=(c == BLACK))
        if same[0] == fr:
            head = "前" + name
        elif same[1] == fr:
            head = "后" + name
        else:
            head = name + flabel(fx)
    else:
        head = name + flabel(fx)

    if ty == fy:
        return head + "平" + flabel(tx)
    fwd = (ty < fy) if c == RED else (ty > fy)
    verb = "进" if fwd else "退"
    if t in ("R", "C", "P", "K"):
        n = abs(ty - fy)
        tail = CN_NUM[n - 1] if c == RED else str(n)
    else:
        tail = flabel(tx)
    return head + verb + tail


def describe_move(board, mv):
    p = board[mv[0]]
    color = "红" if p[0] == RED else "黑"
    return "%s %s（%s%d→%s%d）" % (color, notation(board, mv),
                                  "ABCDEFGHI"[mv[0] % 9], 10 - mv[0] // 9,
                                  "ABCDEFGHI"[mv[1] % 9], 10 - mv[1] // 9)


# ------------------------------------------------------------------ 评估
BASE = {"K": 60000, "R": 900, "C": 450, "N": 400, "A": 180, "B": 180, "P": 100}
MATE = 50000
INF = 10 ** 9


def evaluate(board, color):
    s = 0
    for i, p in enumerate(board):
        if not p:
            continue
        c, t = p[0], p[1]
        if t == "K":
            continue
        v = BASE[t]
        x, y = i % 9, i // 9
        if t == "P":
            if crossed(y, c):
                v += 60
                v += ((y - 5) if c == BLACK else (4 - y)) * 10
            else:
                v += ((y - 3) if c == BLACK else (6 - y)) * 6
        elif t in ("R", "C", "N"):
            v += (4 - abs(x - 4)) * 6
            if t == "N" and x in (0, 8):
                v -= 25
            # 鼓励出子：车马停留在底线略作惩罚
            if (c == RED and y == 9) or (c == BLACK and y == 0):
                v -= (10 if t == "N" else 8)
        elif t in ("A", "B"):
            v += 5
        s += v if c == color else -v
    return s


class Timeout(Exception):
    pass


class Engine(object):
    def __init__(self, level="normal"):
        self.set_level(level)
        self.nodes = 0

    def set_level(self, level):
        self.level = level
        self.depth = {"easy": 2, "normal": 3, "hard": 4}[level]
        self.time_limit = {"easy": 0.5, "normal": 1.5, "hard": 3.0}[level]

    # -------- 搜索
    def _quiesce(self, board, color, alpha, beta, dq, deadline):
        self.nodes += 1
        if time.time() > deadline:
            raise Timeout()
        stand = evaluate(board, color)
        if dq <= 0:
            return stand
        if stand >= beta:
            return beta
        if stand > alpha:
            alpha = stand
        caps = []
        for mv in gen_moves(board, color):
            if board[mv[1]]:
                caps.append(mv)
        caps.sort(key=lambda m: BASE[board[m[1]][1]], reverse=True)
        for mv in caps:
            cap = board[mv[1]]
            if cap[1] == "K":
                return MATE
            make(board, mv)
            sc = -self._quiesce(board, opp(color), -beta, -alpha, dq - 1, deadline)
            unmake(board, mv, cap)
            if sc > alpha:
                alpha = sc
            if alpha >= beta:
                break
        return alpha

    def _search(self, board, color, depth, alpha, beta, ply, deadline):
        self.nodes += 1
        if time.time() > deadline:
            raise Timeout()
        if depth <= 0:
            return self._quiesce(board, color, alpha, beta, 3, deadline)
        moves = gen_moves(board, color)
        if not moves:
            return -MATE + ply
        moves.sort(key=lambda m: (BASE[board[m[1]][1]] * 10 - BASE[board[m[0]][1]])
                   if board[m[1]] else 0, reverse=True)
        best = -INF
        for mv in moves:
            cap = board[mv[1]]
            if cap and cap[1] == "K":
                return MATE - ply
            make(board, mv)
            sc = -self._search(board, opp(color), depth - 1, -beta, -alpha, ply + 1,
                               deadline)
            unmake(board, mv, cap)
            if sc > best:
                best = sc
            if best > alpha:
                alpha = best
            if alpha >= beta:
                break
        return best

    def choose_move(self, board, color):
        """返回 (from, to)；无合法着法返回 None"""
        moves = legal_moves(board, color)
        if not moves:
            return None
        if len(moves) == 1:
            return moves[0]
        deadline = time.time() + self.time_limit
        self.nodes = 0
        best = moves[0]
        scored = {m: 0 for m in moves}
        for d in range(1, self.depth + 1):
            try:
                alpha, beta = -INF, INF
                local_best, local_val = None, -INF
                ordered = sorted(moves, key=lambda m: scored.get(m, 0), reverse=True)
                for mv in ordered:
                    cap = board[mv[1]]
                    if cap and cap[1] == "K":
                        scored[mv] = MATE
                        return mv
                    make(board, mv)
                    sc = -self._search(board, opp(color), d - 1, -beta, -alpha, 1,
                                       deadline)
                    unmake(board, mv, cap)
                    scored[mv] = sc
                    if sc > local_val:
                        local_val, local_best = sc, mv
                    if sc > alpha:
                        alpha = sc
                if local_best is not None:
                    best = local_best
                    if local_val >= MATE - 100:
                        break
            except Timeout:
                break
        return best


# ------------------------------------------------------------------ 自测
def perft(board, color, depth):
    if depth == 0:
        return 1
    total = 0
    for mv in legal_moves(board, color):
        cap = make(board, mv)
        total += perft(board, opp(color), depth - 1)
        unmake(board, mv, cap)
    return total


if __name__ == "__main__":
    b = initial_board()
    print("初始局面合法着法数 =", len(legal_moves(b, RED)), "（标准值为 44）")
    t0 = time.time()
    print("perft(2) =", perft(b, RED, 2), "（标准值为 1920）")
    print("perft(3) =", perft(b, RED, 3), "（标准值为 79666）")
    print("perft 用时 %.2fs" % (time.time() - t0))
    # 中文记谱样例
    for mv in [(idx(1, 7), idx(4, 7)), (idx(7, 9), idx(6, 7))]:
        print("记谱:", notation(b, mv))
    eng = Engine("hard")
    t0 = time.time()
    mv = eng.choose_move(b, RED)
    print("AI 首选:", describe_move(b, mv), "节点 %d 用时 %.2fs"
          % (eng.nodes, time.time() - t0))
