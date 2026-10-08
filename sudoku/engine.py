# -*- coding: utf-8 -*-
"""
数独 100 关 —— 出题引擎（Python 版，与 engine.js 算法一致）

难度模型：
    难度分 = 空格数 + 技巧加成
    1 显性唯一 +0   2 隐性唯一 +8   3 数对/三链 +16   4 隐性数对 +22
    5 区块删减 +28  6 X-Wing +36    7 XY-Wing +44     8 需要试填 +52
"""

ALL = 0x3FE

BITCOUNT = [0] * 1024
for _i in range(1, 1024):
    BITCOUNT[_i] = BITCOUNT[_i >> 1] + (_i & 1)

LOG2 = [0] * 1024
for _i in range(1, 1024):
    LOG2[_i] = _i.bit_length() - 1

ROW_OF = [i // 9 for i in range(81)]
COL_OF = [i % 9 for i in range(81)]
BOX_OF = [(i // 9 // 3) * 3 + (i % 9 // 3) for i in range(81)]

# 27 个单元（9 行 + 9 列 + 9 宫）
_units = []
for _r in range(9):
    _units.append(tuple(_r * 9 + _c for _c in range(9)))
for _c in range(9):
    _units.append(tuple(_r * 9 + _c for _r in range(9)))
for _b in range(9):
    _br, _bc = (_b // 3) * 3, (_b % 3) * 3
    _units.append(tuple((_br + _r) * 9 + (_bc + _c) for _r in range(3) for _c in range(3)))
UNITS = tuple(_units)

_peers = []
for _i in range(81):
    _seen, _lst = set(), []
    for _u in UNITS:
        if _i in _u:
            for _q in _u:
                if _q != _i and _q not in _seen:
                    _seen.add(_q)
                    _lst.append(_q)
    _peers.append(tuple(_lst))
PEERS = tuple(_peers)

UNITS_OF_CELL = tuple(tuple(k for k, u in enumerate(UNITS) if i in u) for i in range(81))


# ---------------------------------------------------------------- 随机数
def mulberry32(seed):
    state = seed & 0xFFFFFFFF

    def rnd():
        nonlocal state
        state = (state + 0x6D2B79F5) & 0xFFFFFFFF
        t = state
        t = ((t ^ (t >> 15)) * (1 | t)) & 0xFFFFFFFF
        t = (t + (((t ^ (t >> 7)) * (61 | t)) & 0xFFFFFFFF)) & 0xFFFFFFFF
        t = (t ^ (t >> 14)) & 0xFFFFFFFF
        return t / 4294967296.0

    return rnd


def hash_seed(s):
    h = 2166136261
    for ch in str(s):
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def shuffled(seq, rnd):
    a = list(seq)
    for i in range(len(a) - 1, 0, -1):
        j = int(rnd() * (i + 1))
        a[i], a[j] = a[j], a[i]
    return a


# ---------------------------------------------------------------- 生成完整解
def generate_solution(rnd):
    rows = [0] * 9
    cols = [0] * 9
    boxes = [0] * 9
    b = [0] * 81

    def rec(i):
        if i == 81:
            return True
        r, c, x = ROW_OF[i], COL_OF[i], BOX_OF[i]
        used = rows[r] | cols[c] | boxes[x]
        cand = [v for v in range(1, 10) if not used & (1 << v)]
        for v in shuffled(cand, rnd):
            m = 1 << v
            b[i] = v
            rows[r] |= m
            cols[c] |= m
            boxes[x] |= m
            if rec(i + 1):
                return True
            b[i] = 0
            rows[r] &= ~m
            cols[c] &= ~m
            boxes[x] &= ~m
        return False

    rec(0)
    return b


# ---------------------------------------------------------------- 解的个数
def count_solutions(board, limit=2):
    b = list(board)
    rows = [0] * 9
    cols = [0] * 9
    boxes = [0] * 9
    for i in range(81):
        v = b[i]
        if not v:
            continue
        m = 1 << v
        r, c, x = ROW_OF[i], COL_OF[i], BOX_OF[i]
        if (rows[r] | cols[c] | boxes[x]) & m:
            return 0
        rows[r] |= m
        cols[c] |= m
        boxes[x] |= m

    count = 0
    bitcount = BITCOUNT
    log2 = LOG2

    def rec():
        nonlocal count
        best_i, best_mask, best_n = -1, 0, 10
        for i in range(81):
            if b[i]:
                continue
            mask = ALL & ~(rows[ROW_OF[i]] | cols[COL_OF[i]] | boxes[BOX_OF[i]])
            n = bitcount[mask]
            if n == 0:
                return
            if n < best_n:
                best_n = n
                best_i = i
                best_mask = mask
                if n == 1:
                    break
        if best_i < 0:
            count += 1
            return
        r, c, x = ROW_OF[best_i], COL_OF[best_i], BOX_OF[best_i]
        m2 = best_mask
        while m2:
            bit = m2 & -m2
            m2 ^= bit
            v = log2[bit]
            b[best_i] = v
            rows[r] |= bit
            cols[c] |= bit
            boxes[x] |= bit
            rec()
            b[best_i] = 0
            rows[r] &= ~bit
            cols[c] &= ~bit
            boxes[x] &= ~bit
            if count >= limit:
                return

    rec()
    return count


# ---------------------------------------------------------------- 难度评级
def rate(board):
    """用技巧阶梯解题，返回 (最高技巧等级, 是否可解)"""
    b = list(board)
    elim = [0] * 81
    cand = [0] * 81
    level = [0]
    bitcount = BITCOUNT
    log2 = LOG2
    peers = PEERS
    units = UNITS

    def refresh():
        for i in range(81):
            if b[i]:
                cand[i] = 0
                continue
            used = 0
            for p in peers[i]:
                v = b[p]
                if v:
                    used |= 1 << v
            c = ALL & ~used & ~elim[i]
            if c == 0:
                return False
            cand[i] = c
        return True

    def is_full():
        for i in range(81):
            if not b[i]:
                return False
        return True

    def naked_single():
        for i in range(81):
            if b[i]:
                continue
            if bitcount[cand[i]] == 1:
                b[i] = log2[cand[i]]
                return True
        return False

    def hidden_single():
        for cells in units:
            for v in range(1, 10):
                bit = 1 << v
                cnt = 0
                pos = -1
                placed = False
                for i in cells:
                    if b[i] == v:
                        placed = True
                        break
                    if not b[i] and cand[i] & bit:
                        cnt += 1
                        pos = i
                if not placed and cnt == 1:
                    b[pos] = v
                    return True
        return False

    def drop_from(cells, mask, keep):
        changed = False
        for i in cells:
            if b[i] or i in keep:
                continue
            if cand[i] & mask:
                elim[i] |= cand[i] & mask
                cand[i] &= ~mask
                changed = True
        return changed

    def naked_subset():
        changed = False
        for cells in units:
            lst = []
            for i in cells:
                if b[i]:
                    continue
                n = bitcount[cand[i]]
                if 2 <= n <= 3:
                    lst.append(i)
            ln = len(lst)
            for a in range(ln):
                for c2 in range(a + 1, ln):
                    m2 = cand[lst[a]] | cand[lst[c2]]
                    if bitcount[m2] == 2 and drop_from(cells, m2, (lst[a], lst[c2])):
                        changed = True
                    for d in range(c2 + 1, ln):
                        m3 = m2 | cand[lst[d]]
                        if bitcount[m3] == 3 and drop_from(cells, m3, (lst[a], lst[c2], lst[d])):
                            changed = True
        return changed

    def hidden_pair():
        changed = False
        for cells in units:
            pos = []
            for v in range(1, 10):
                bit = 1 << v
                arr = []
                placed = False
                for i in cells:
                    if b[i] == v:
                        placed = True
                        break
                    if not b[i] and cand[i] & bit:
                        arr.append(i)
                pos.append(None if placed else arr)
            for v1 in range(1, 10):
                p1 = pos[v1 - 1]
                if not p1 or len(p1) != 2:
                    continue
                for v2 in range(v1 + 1, 10):
                    p2 = pos[v2 - 1]
                    if not p2 or len(p2) != 2:
                        continue
                    if p1[0] != p2[0] or p1[1] != p2[1]:
                        continue
                    keep = (1 << v1) | (1 << v2)
                    for cell in (p1[0], p1[1]):
                        if cand[cell] != keep:
                            elim[cell] |= cand[cell] & ~keep
                            cand[cell] = keep
                            changed = True
        return changed

    def pointing():
        changed = False
        for bx in range(9):
            cells = units[18 + bx]
            for v in range(1, 10):
                bit = 1 << v
                pos = []
                placed = False
                for i in cells:
                    if b[i] == v:
                        placed = True
                        break
                    if not b[i] and cand[i] & bit:
                        pos.append(i)
                if placed or len(pos) < 2:
                    continue
                same_row = all(ROW_OF[p] == ROW_OF[pos[0]] for p in pos)
                same_col = all(COL_OF[p] == COL_OF[pos[0]] for p in pos)
                if same_row:
                    for cc in range(9):
                        i2 = ROW_OF[pos[0]] * 9 + cc
                        if b[i2] or BOX_OF[i2] == bx:
                            continue
                        if cand[i2] & bit:
                            elim[i2] |= bit
                            cand[i2] &= ~bit
                            changed = True
                if same_col:
                    for rr in range(9):
                        i3 = rr * 9 + COL_OF[pos[0]]
                        if b[i3] or BOX_OF[i3] == bx:
                            continue
                        if cand[i3] & bit:
                            elim[i3] |= bit
                            cand[i3] &= ~bit
                            changed = True
        for u in range(18):
            cells = units[u]
            for v in range(1, 10):
                bit = 1 << v
                pos = []
                placed = False
                for i in cells:
                    if b[i] == v:
                        placed = True
                        break
                    if not b[i] and cand[i] & bit:
                        pos.append(i)
                if placed or len(pos) < 2:
                    continue
                box = BOX_OF[pos[0]]
                if not all(BOX_OF[p] == box for p in pos):
                    continue
                for i4 in units[18 + box]:
                    if b[i4]:
                        continue
                    same_line = (ROW_OF[i4] == u) if u < 9 else (COL_OF[i4] == u - 9)
                    if same_line:
                        continue
                    if cand[i4] & bit:
                        elim[i4] |= bit
                        cand[i4] &= ~bit
                        changed = True
        return changed

    def xwing():
        changed = False
        for v in range(1, 10):
            bit = 1 << v
            rows_pos = []
            for r in range(9):
                p, dead = [], False
                for c in range(9):
                    i = r * 9 + c
                    if b[i] == v:
                        dead = True
                        break
                    if not b[i] and cand[i] & bit:
                        p.append(c)
                rows_pos.append(None if dead else p)
            for r1 in range(9):
                if not rows_pos[r1] or len(rows_pos[r1]) != 2:
                    continue
                for r2 in range(r1 + 1, 9):
                    if not rows_pos[r2] or len(rows_pos[r2]) != 2:
                        continue
                    if rows_pos[r1] != rows_pos[r2]:
                        continue
                    ca, cb = rows_pos[r1]
                    for r3 in range(9):
                        if r3 in (r1, r2):
                            continue
                        ia, ib = r3 * 9 + ca, r3 * 9 + cb
                        if not b[ia] and cand[ia] & bit:
                            elim[ia] |= bit
                            cand[ia] &= ~bit
                            changed = True
                        if not b[ib] and cand[ib] & bit:
                            elim[ib] |= bit
                            cand[ib] &= ~bit
                            changed = True
            cols_pos = []
            for c in range(9):
                p, dead = [], False
                for r in range(9):
                    i = r * 9 + c
                    if b[i] == v:
                        dead = True
                        break
                    if not b[i] and cand[i] & bit:
                        p.append(r)
                cols_pos.append(None if dead else p)
            for c1 in range(9):
                if not cols_pos[c1] or len(cols_pos[c1]) != 2:
                    continue
                for c2 in range(c1 + 1, 9):
                    if not cols_pos[c2] or len(cols_pos[c2]) != 2:
                        continue
                    if cols_pos[c1] != cols_pos[c2]:
                        continue
                    ra, rb = cols_pos[c1]
                    for c3 in range(9):
                        if c3 in (c1, c2):
                            continue
                        ja, jb = ra * 9 + c3, rb * 9 + c3
                        if not b[ja] and cand[ja] & bit:
                            elim[ja] |= bit
                            cand[ja] &= ~bit
                            changed = True
                        if not b[jb] and cand[jb] & bit:
                            elim[jb] |= bit
                            cand[jb] &= ~bit
                            changed = True
        return changed

    def xy_wing():
        changed = False
        bi = [t for t in range(81) if not b[t] and bitcount[cand[t]] == 2]
        for P in bi:
            mp = cand[P]
            pp = peers[P]
            for ci in range(len(pp)):
                W1 = pp[ci]
                if b[W1] or bitcount[cand[W1]] != 2:
                    continue
                inter = cand[W1] & mp
                if bitcount[inter] != 1:
                    continue
                z1 = cand[W1] & ~mp
                if not z1:
                    continue
                need_y = mp & ~inter
                for di in range(ci + 1, len(pp)):
                    W2 = pp[di]
                    if b[W2] or bitcount[cand[W2]] != 2:
                        continue
                    if not cand[W2] & need_y:
                        continue
                    if cand[W2] & ~need_y != z1:
                        continue
                    pw1, pw2 = peers[W1], peers[W2]
                    for T in pw1:
                        if b[T] or T == P or T == W2:
                            continue
                        if T not in pw2:
                            continue
                        if cand[T] & z1:
                            elim[T] |= z1
                            cand[T] &= ~z1
                            changed = True
        return changed

    for _ in range(500):
        if not refresh():
            return 8, False
        if is_full():
            return (level[0] or 1), True
        if naked_single():
            if level[0] < 1:
                level[0] = 1
            continue
        if hidden_single():
            if level[0] < 2:
                level[0] = 2
            continue
        if naked_subset():
            if level[0] < 3:
                level[0] = 3
            continue
        if hidden_pair():
            if level[0] < 4:
                level[0] = 4
            continue
        if pointing():
            if level[0] < 5:
                level[0] = 5
            continue
        if xwing():
            if level[0] < 6:
                level[0] = 6
            continue
        if xy_wing():
            if level[0] < 7:
                level[0] = 7
            continue
        return 8, False
    return 8, False


# ---------------------------------------------------------------- 难度模型
BONUS = {1: 0, 2: 8, 3: 16, 4: 22, 5: 28, 6: 36, 7: 44, 8: 52}

TIERS = [
    {"name": "送分", "color": "#22c55e"},
    {"name": "正常", "color": "#38bdf8"},
    {"name": "进阶", "color": "#818cf8"},
    {"name": "困难", "color": "#f59e0b"},
    {"name": "大师", "color": "#f472b6"},
    {"name": "地狱", "color": "#ef4444"},
]

RATING_TEXT = {
    1: "显性唯一", 2: "隐性唯一", 3: "数对/三链", 4: "隐性数对",
    5: "区块删减", 6: "X-Wing", 7: "XY-Wing", 8: "需要试填",
}

TARGET_ANCHORS = [
    (1, 29), (2, 51), (6, 55), (15, 58), (25, 64), (35, 70),
    (45, 74), (52, 78), (58, 88), (65, 93), (72, 96),
    (80, 101), (90, 105), (100, 109),
]


def difficulty_score(givens, rating):
    return (81 - givens) + BONUS.get(rating, 0)


def tier_of(score):
    if score < 46:
        return 0
    if score < 58:
        return 1
    if score < 71:
        return 2
    if score < 86:
        return 3
    if score < 101:
        return 4
    return 5


def target_of(level):
    if level <= TARGET_ANCHORS[0][0]:
        return TARGET_ANCHORS[0][1]
    for i in range(1, len(TARGET_ANCHORS)):
        lo, hi = TARGET_ANCHORS[i - 1], TARGET_ANCHORS[i]
        if level <= hi[0]:
            t = (level - lo[0]) / (hi[0] - lo[0])
            return lo[1] + (hi[1] - lo[1]) * t
    return TARGET_ANCHORS[-1][1]


def difficulty_spec(level):
    lv = max(1, min(100, int(level)))
    if lv == 1:
        return dict(level=lv, target=29, givens_min=50, givens_max=57,
                    rating_min=1, rating_max=1, floor_givens=26)
    if lv == 2:
        return dict(level=lv, target=51, givens_min=35, givens_max=41,
                    rating_min=2, rating_max=2, floor_givens=26)
    t = (lv - 3) / 97.0
    givens_min = int(round(36 - 12 * t))
    if lv <= 12:
        rating_max, rating_min = 3, 1
    elif lv <= 26:
        rating_max, rating_min = 4, 2
    elif lv <= 42:
        rating_max, rating_min = 5, 2
    elif lv <= 60:
        rating_max, rating_min = 6, 3
    elif lv <= 80:
        rating_max, rating_min = 7, 4
    else:
        rating_max, rating_min = 8, 5
    return dict(level=lv, target=target_of(lv), givens_min=givens_min,
                givens_max=givens_min + 6, rating_min=rating_min,
                rating_max=rating_max, floor_givens=max(givens_min - 8, 24))


def count_givens(board):
    return sum(1 for v in board if v)


def penalty_of(v, spec):
    p = 0.0
    if v["givens"] > spec["givens_max"]:
        p += (v["givens"] - spec["givens_max"]) * 1.5
    if v["givens"] < spec["givens_min"] - 2:
        p += (spec["givens_min"] - 2 - v["givens"]) * 1.5
    if v["rating"] > spec["rating_max"]:
        p += (v["rating"] - spec["rating_max"]) * 3
    if v["rating"] < spec["rating_min"]:
        p += (spec["rating_min"] - v["rating"]) * 2
    return p


def search_one(spec, seed_str, want):
    """一个完整解：挖到底 → 逐格回填，留下最贴近目标难度分的版本"""
    rnd = mulberry32(hash_seed(seed_str))
    solution = generate_solution(rnd)
    puzzle = list(solution)
    order = shuffled(range(81), rnd)

    removed = []
    givens = 81
    for p in order:
        if givens <= spec["floor_givens"]:
            break
        val = puzzle[p]
        if not val:
            continue
        puzzle[p] = 0
        if count_solutions(puzzle, 2) == 1:
            removed.append(p)
            givens -= 1
        else:
            puzzle[p] = val

    best = None

    def consider(g):
        nonlocal best
        snap = list(puzzle)
        lvl, solved = rate(snap)
        score = difficulty_score(g, lvl)
        v = dict(puzzle=snap, givens=g, rating=lvl, score=score, solved=solved)
        total = abs(score - want) + penalty_of(v, spec)
        if best is None or total < best["total"]:
            best = dict(total=total, v=v)
        return score

    cap = spec["givens_max"] + 4
    consider(givens)
    for m in range(len(removed) - 1, -1, -1):
        if givens >= cap:
            break
        puzzle[removed[m]] = solution[removed[m]]
        givens += 1
        if consider(givens) < want - 14:
            break
    return best, solution


def generate(level, attempts=24, target_override=None):
    """生成一关"""
    import random as _random
    spec = difficulty_spec(level)
    want = spec["target"] if target_override is None else target_override
    hard = attempts * 3
    best = None
    a = 0
    while a < hard:
        if a >= attempts and best is not None and best["deviation"] <= 4:
            break
        seed = "%d#%d#%s" % (level, a, _random.random())
        a += 1
        pick, solution = search_one(spec, seed, want)
        v = pick["v"]
        res = dict(level=level, puzzle=v["puzzle"], solution=solution,
                   givens=v["givens"], rating=v["rating"], solved=v["solved"],
                   difficulty=v["score"], deviation=pick["total"],
                   target=want, seed=seed)
        if best is None or res["deviation"] < best["deviation"]:
            best = res
        if best["deviation"] <= 1.5:
            break
    best["tier"] = tier_of(best["difficulty"])
    best["tier_name"] = TIERS[best["tier"]]["name"]
    return best


# ---------------------------------------------------------------- 工具
def to_string(board):
    return "".join(str(v) if v else "." for v in board)


def from_string(s):
    return [int(ch) if ch.isdigit() and ch != "0" else 0 for ch in s]


def find_conflicts(board):
    bad = [0] * 81
    for cells in UNITS:
        seen = {}
        for i in cells:
            v = board[i]
            if not v:
                continue
            if v in seen:
                bad[i] = 1
                bad[seen[v]] = 1
            else:
                seen[v] = i
    return bad


def is_solved(board, solution):
    for i in range(81):
        if board[i] != solution[i]:
            return False
    return True


def candidates_of(board, index):
    used = 0
    for p in PEERS[index]:
        v = board[p]
        if v:
            used |= 1 << v
    return ALL & ~used


if __name__ == "__main__":
    import time
    t0 = time.time()
    for lv in (1, 2, 5, 30, 60, 100):
        r = generate(lv)
        print("第%3d关 %s 提示%2d 技巧=%s 难度分=%.0f(目标%.1f) %.2fs" % (
            lv, r["tier_name"], r["givens"], RATING_TEXT[r["rating"]],
            r["difficulty"], r["target"], time.time() - t0))
        t0 = time.time()
