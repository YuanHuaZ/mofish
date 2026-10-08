# -*- coding: utf-8 -*-
"""
数字华容道引擎（无 GUI，可独立测试）

经典数字滑块：N×N 棋盘放 1..N²-1，留一个空格，把数字按顺序归位。
- 3×3 用 BFS 求最优提示；4×4 及以上用曼哈顿距离启发式提示
- 打乱通过在已解局面上走随机合法步实现，天然保证一定有解
"""
import random
from collections import deque


def solved_tiles(n):
    return list(range(1, n * n)) + [0]


def is_solvable(tiles, n):
    """按逆序数奇偶性判断是否可解（含空格行奇偶修正）"""
    seq = [v for v in tiles if v != 0]
    inv = 0
    for i in range(len(seq)):
        for j in range(i + 1, len(seq)):
            if seq[i] > seq[j]:
                inv += 1
    if n % 2 == 1:
        return inv % 2 == 0
    blank_row_from_bottom = n - (tiles.index(0) // n)
    return (inv + blank_row_from_bottom) % 2 == 1


def shuffle(n, steps, seed=None):
    """从已解局面走 steps 步随机合法移动得到乱序局面"""
    rng = random.Random(seed)
    p = NumberPuzzle(n)
    last = None
    done = 0
    guard = 0
    while done < steps and guard < steps * 20 + 200:
        guard += 1
        cands = [i for i in p.movable() if i != last]
        if not cands:
            break
        i = rng.choice(cands)
        b = p.blank()
        p.move_at(i)
        last = b
        done += 1
    if p.solved():                       # 极小概率刚好走回原状
        return shuffle(n, steps, rng.random())
    return p.tiles


def bfs_next(tiles, n):
    """3×3 最优解：返回下一步应移动的格子下标"""
    start = tuple(tiles)
    goal = tuple(solved_tiles(n))
    if start == goal:
        return None
    parent = {start: (None, None)}
    dq = deque([start])
    while dq:
        cur = dq.popleft()
        b = cur.index(0)
        r, c = divmod(b, n)
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            if not (0 <= nr < n and 0 <= nc < n):
                continue
            j = nr * n + nc
            lst = list(cur)
            lst[b], lst[j] = lst[j], lst[b]
            nxt = tuple(lst)
            if nxt in parent:
                continue
            parent[nxt] = (cur, j)
            if nxt == goal:
                node, mv = goal, None
                while parent[node][0] is not None:
                    prev, m = parent[node]
                    mv = m
                    node = prev
                return mv
            dq.append(nxt)
    return None


class NumberPuzzle(object):
    def __init__(self, n=3, tiles=None, scramble=None, seed=None):
        self.n = n
        if tiles:
            self.tiles = list(tiles)
        elif scramble:
            self.tiles = shuffle(n, scramble, seed)
        else:
            self.tiles = solved_tiles(n)
        self.moves = 0
        self.history = []              # [(移动的格子下标, 当时空格位置)]

    # -------- 查询
    def blank(self):
        return self.tiles.index(0)

    def solved(self):
        return self.tiles == solved_tiles(self.n)

    def movable(self):
        """可滑动进空格的格子下标"""
        b = self.blank()
        r, c = divmod(b, self.n)
        out = []
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < self.n and 0 <= nc < self.n:
                out.append(nr * self.n + nc)
        return out

    def in_place(self, i):
        v = self.tiles[i]
        return v != 0 and v - 1 == i

    def manhattan(self):
        d = 0
        for i, v in enumerate(self.tiles):
            if not v:
                continue
            tr, tc = divmod(v - 1, self.n)
            r, c = divmod(i, self.n)
            d += abs(r - tr) + abs(c - tc)
        return d

    def placed(self):
        return sum(1 for i in range(self.n * self.n) if self.in_place(i))

    # -------- 操作
    def move_at(self, i):
        """把下标 i 的方块滑进空格，返回 (来源, 目的地)"""
        if i not in self.movable():
            return None
        b = self.blank()
        self.history.append((i, b))
        self.tiles[b], self.tiles[i] = self.tiles[i], self.tiles[b]
        self.moves += 1
        return (i, b)

    def move_dir(self, dr, dc):
        """按方向键：把该方向上的方块推进空格（即空格朝反方向移动）"""
        b = self.blank()
        r, c = divmod(b, self.n)
        nr, nc = r + dr, c + dc
        if not (0 <= nr < self.n and 0 <= nc < self.n):
            return None
        return self.move_at(nr * self.n + nc)

    def slide_to(self, i):
        """点同一行/列上的方块：整排一起滑到空格处（经典手感）"""
        b = self.blank()
        br, bc = divmod(b, self.n)
        r, c = divmod(i, self.n)
        if i == b or (r != br and c != bc):
            return []
        moved = []
        if r == br:
            step = 1 if c > bc else -1
            for cc in range(bc + step, c + step, step):
                mv = self.move_at(r * self.n + cc)
                if mv:
                    moved.append(mv)
        else:
            step = 1 if r > br else -1
            for rr in range(br + step, r + step, step):
                mv = self.move_at(rr * self.n + c)
                if mv:
                    moved.append(mv)
        return moved

    def undo(self):
        if not self.history:
            return None
        i, b = self.history.pop()
        self.tiles[b], self.tiles[i] = self.tiles[i], self.tiles[b]
        self.moves = max(0, self.moves - 1)
        return (b, i)

    def reset(self):
        self.tiles = solved_tiles(self.n)
        self.moves = 0
        self.history = []

    # -------- 提示
    def hint(self):
        """返回建议移动的格子下标；3×3 为最优解，其余为曼哈顿贪心"""
        if self.solved():
            return None
        if self.n == 3:
            return bfs_next(self.tiles, 3)
        last = self.history[-1][0] if self.history else None
        best, best_d = None, 10 ** 9
        for i in self.movable():
            if i == last:
                continue
            b = self.blank()
            self.tiles[b], self.tiles[i] = self.tiles[i], self.tiles[b]
            d = self.manhattan()
            self.tiles[b], self.tiles[i] = self.tiles[i], self.tiles[b]
            if d < best_d:
                best_d, best = d, i
        if best is None:                      # 只剩回头路
            best = self.movable()[0] if self.movable() else None
        return best

    # -------- 序列化
    def dump(self):
        return {"n": self.n, "tiles": list(self.tiles), "moves": self.moves}


# ------------------------------------------------------------------ 难度模型
# 难度分 = 初始曼哈顿距离 × 尺寸系数（棋盘越大、偏差越大，越难）
SIZE_W = {3: 1.00, 4: 1.08, 5: 1.16, 6: 1.24}

# (上限, 档位名, 颜色)
TIERS = [(15, "入门", "#38bdf8"), (30, "简单", "#22c55e"), (55, "普通", "#f0b23c"),
         (90, "困难", "#f97316"), (130, "专家", "#e5484d"), (10 ** 9, "大师", "#a78bfa")]


def difficulty_score(n, dist):
    return int(round(dist * SIZE_W.get(n, 1.0)))


def tier_of(score):
    for lim, name, color in TIERS:
        if score < lim:
            return name, color
    return TIERS[-1][1], TIERS[-1][2]


# ------------------------------------------------------------------ 关卡
# (边长, 目标初始偏差)——按难度递增排列，构建期从候选中挑最接近的
LEVEL_PLAN = [
    (3, 10), (3, 14), (3, 19),
    (4, 24), (4, 30), (4, 37), (4, 44),
    (5, 56), (5, 66), (5, 76), (5, 90),
    (6, 100), (6, 116), (6, 136), (6, 158),
]
SAMPLE_DEPTH = {3: 80, 4: 220, 5: 460, 6: 800}
SAMPLE_N = 420


def build_levels(seed=20261008):
    """按难度递增生成关：每关在候选中挑初始偏差最接近目标的一局"""
    rng = random.Random(seed)
    levels = []
    prev = -1
    for i, (n, target) in enumerate(LEVEL_PLAN, 1):
        best = None
        for _ in range(SAMPLE_N):
            s = rng.randrange(1 << 30)
            tiles = shuffle(n, SAMPLE_DEPTH[n], s)
            d = NumberPuzzle(n, tiles).manhattan()
            score = difficulty_score(n, d)
            if score <= prev:               # 必须比上一关更难
                continue
            gap = abs(d - target)
            if best is None or gap < best[0]:
                best = (gap, d, tiles, s)
        if best is None:
            tiles = shuffle(n, SAMPLE_DEPTH[n])
            d = NumberPuzzle(n, tiles).manhattan()
            best = (0, d, tiles, 0)
        _gap, d, tiles, s = best
        score = difficulty_score(n, d)
        prev = score
        name = "%d×%d" % (n, n)
        levels.append({"level": i, "n": n, "scramble": SAMPLE_DEPTH[n], "seed": s,
                       "dist": d, "score": score, "tier": tier_of(score)[0],
                       "tiles": tiles, "name": name})
    return levels


if __name__ == "__main__":
    import time
    t0 = time.time()
    last = -1
    for lv in build_levels():
        p = NumberPuzzle(lv["n"], lv["tiles"])
        assert is_solvable(lv["tiles"], lv["n"]), "第%d关不可解" % lv["level"]
        assert lv["score"] > last, "难度未递增：第%d关" % lv["level"]
        last = lv["score"]
        print("第%2d关 %s 难度分%3d（%s） 初始偏差%3d 已归位%2d/%2d"
              % (lv["level"], lv["name"], lv["score"], lv["tier"], lv["dist"],
                 p.placed(), lv["n"] ** 2 - 1))
    print("生成耗时 %.1fs" % (time.time() - t0))
    # 3×3 最优提示速度
    p = NumberPuzzle(3, shuffle(3, 40, 7))
    t0 = time.time()
    print("3×3 最优提示:", p.hint(), "耗时 %.2fs" % (time.time() - t0))
    p = NumberPuzzle(4, shuffle(4, 120, 9))
    print("4×4 贪心提示:", p.hint(), "曼哈顿", p.manhattan())
