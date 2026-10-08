# -*- coding: utf-8 -*-
"""
华容道引擎（无 GUI，可独立测试）

- 4x5 经典棋盘：「曹操」2x2 逃到下方出口（左下角坐标 (1,3)）即获胜
- 布局用 5 行 4 列文本描述，同一字母的格子构成一个矩形棋子
- BFS 最优解求解器（同形状棋子视为等价，65k 量级状态，秒级可解）
"""
from collections import deque

W, H = 4, 5
EXIT = (1, 3)              # 曹操左上角到达此处即逃脱
DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}

GENERAL_NAMES = ["张飞", "赵云", "马超", "黄忠"]

# ------------------------------------------------------------------ 布局
# 8 个经典布局，按最优步数递增排列（步数=每移动一格计 1 步）
LAYOUTS = [
    ("齐头并进", "ZCCY\nZCCY\nabcd\nMGGH\nM..H"),
    ("兵临城下", "ZYCC\nZYCC\nMGGH\nMabH\nc..d"),
    ("将拥曹营", "aCCb\nZCCY\nZGGY\nMcdH\nM..H"),
    ("峰回路转", "CCZY\nCCZY\nGGMH\nabMH\n.c.d"),
    ("兵分三路", "ZCCY\nZCCY\naGGb\nMcdH\nM..H"),
    ("层层设防", "ZCCY\nZCCY\naGGb\ncMHd\n.MH."),
    ("迫在眉睫", "ZCCY\nZCCY\nMGGH\nMabH\n.cd."),
    ("横刀立马", "ZCCY\nZCCY\nMGGH\nMabH\nc..d"),
]


def parse_layout(text):
    """解析文本布局 → 棋子列表 [{'id','x','y','w','h'}]"""
    rows = [r for r in text.strip().splitlines() if r.strip()]
    if len(rows) != H or any(len(r) != W for r in rows):
        raise ValueError("布局必须是 %dx%d：\n%s" % (H, W, text))
    cells = {}
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch != ".":
                cells.setdefault(ch, []).append((x, y))
    pieces = []
    for ch, pts in cells.items():
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        x0, y0 = min(xs), min(ys)
        w, h = max(xs) - x0 + 1, max(ys) - y0 + 1
        if w * h != len(pts):
            raise ValueError("棋子 %s 不是矩形" % ch)
        pieces.append({"id": ch, "x": x0, "y": y0, "w": w, "h": h})
    # 稳定排序：曹操 → 关羽 → 竖将 → 卒
    def key(p):
        return {4: 0, 2: 1, -2: 2, 1: 3}[p["w"] * p["h"]] + p["y"] * 0.01 + p["x"] * 0.001
    pieces.sort(key=key)
    return pieces


def name_pieces(pieces):
    """给棋子分配中文名"""
    gen = 0
    for p in pieces:
        a = p["w"] * p["h"]
        if p["w"] == 2 and p["h"] == 2:
            p["name"] = "曹操"
        elif p["w"] == 2 and p["h"] == 1:
            p["name"] = "关羽"
        elif p["w"] == 1 and p["h"] == 2:
            p["name"] = GENERAL_NAMES[gen % len(GENERAL_NAMES)]
            gen += 1
        else:
            p["name"] = "卒"
    return pieces


# ------------------------------------------------------------------ 求解器
def _canon(pieces):
    return tuple(sorted((w, h, x, y) for (w, h, x, y) in pieces))


def _expand(canon_state, occ):
    """从规范状态生成 (新状态, 走法) ；走法=(fx,fy,tx,ty,w,h)"""
    out = []
    for idx, (w, h, x, y) in enumerate(canon_state):
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if nx < 0 or ny < 0 or nx + w > W or ny + h > H:
                continue
            ok = True
            for j in range(w):
                for k in range(h):
                    cell = (nx + j, ny + k)
                    if cell in occ and not (x <= nx + j < x + w and y <= ny + k < y + h):
                        ok = False
                        break
                if not ok:
                    break
            if not ok:
                continue
            newp = list(canon_state)
            newp[idx] = (w, h, nx, ny)
            nxt = tuple(sorted(newp))
            out.append((nxt, (x, y, nx, ny, w, h)))
    return out


def _occupancy(canon_state):
    occ = set()
    for (w, h, x, y) in canon_state:
        for dy in range(h):
            for dx in range(w):
                occ.add((x + dx, y + dy))
    return occ


def _is_goal(canon_state):
    for (w, h, x, y) in canon_state:
        if w == 2 and h == 2 and (x, y) == EXIT:
            return True
    return False


def solve(layout_text, cap=900000):
    """返回最优走法序列 [{fx,fy,tx,ty,w,h}]，无解/超限返回 None"""
    pieces = parse_layout(layout_text)
    start = _canon([(p["w"], p["h"], p["x"], p["y"]) for p in pieces])
    return _bfs(start, cap)


def _bfs(start, cap):
    if _is_goal(start):
        return []
    info = {start: (None, None, _occupancy(start))}
    dq = deque([start])
    while dq:
        cur = dq.popleft()
        occ = info[cur][2]
        for nxt, mv in _expand(cur, occ):
            if nxt in info:
                continue
            info[nxt] = (cur, mv, _occupancy(nxt))
            if _is_goal(nxt):
                path = []
                node = nxt
                while info[node][0] is not None:
                    path.append(info[node][1])
                    node = info[node][0]
                path.reverse()
                return [dict(zip(("fx", "fy", "tx", "ty", "w", "h"), m)) for m in path]
            dq.append(nxt)
        if len(info) > cap:
            return None
    return None


# ------------------------------------------------------------------ 游戏状态
class Klotski(object):
    def __init__(self, layout_text=None):
        self.reset(layout_text or LAYOUTS[0][1])

    def reset(self, layout_text):
        self.layout = layout_text
        self.pieces = name_pieces(parse_layout(layout_text))
        self.moves = 0
        self.history = []
        self.solution = None

    # -------- 查询
    def occupancy(self):
        occ = {}
        for i, p in enumerate(self.pieces):
            for dy in range(p["h"]):
                for dx in range(p["w"]):
                    occ[(p["x"] + dx, p["y"] + dy)] = i
        return occ

    def piece_at(self, x, y):
        for i, p in enumerate(self.pieces):
            if p["x"] <= x < p["x"] + p["w"] and p["y"] <= y < p["y"] + p["h"]:
                return i
        return -1

    def can_move(self, i, dx, dy):
        p = self.pieces[i]
        occ = self.occupancy()
        nx, ny = p["x"] + dx, p["y"] + dy
        if nx < 0 or ny < 0 or nx + p["w"] > W or ny + p["h"] > H:
            return False
        for j in range(p["w"]):
            for k in range(p["h"]):
                cell = (nx + j, ny + k)
                if cell in occ and occ[cell] != i:
                    return False
        return True

    def move(self, i, dx, dy, record=True):
        if not self.can_move(i, dx, dy):
            return False
        p = self.pieces[i]
        if record:
            self.history.append((i, p["x"], p["y"]))
            self.moves += 1
        p["x"] += dx
        p["y"] += dy
        return True

    def undo(self):
        if not self.history:
            return False
        i, x, y = self.history.pop()
        self.pieces[i]["x"], self.pieces[i]["y"] = x, y
        self.moves = max(0, self.moves - 1)
        return True

    def solved(self):
        for p in self.pieces:
            if p["w"] == 2 and p["h"] == 2 and (p["x"], p["y"]) == EXIT:
                return True
        return False

    # -------- 求解
    def canon(self):
        return _canon([(p["w"], p["h"], p["x"], p["y"]) for p in self.pieces])

    def solve_from_here(self, cap=900000):
        """从当前局面求最优走法序列（可能耗时，建议放线程里）"""
        start = self.canon()
        if _is_goal(start):
            return []
        return _bfs(start, cap)

    def apply_move_dict(self, mv):
        """按求解器给出的走法（含棋子位置）在真实棋盘上执行一步"""
        for i, p in enumerate(self.pieces):
            if p["x"] == mv["fx"] and p["y"] == mv["fy"] and \
               p["w"] == mv["w"] and p["h"] == mv["h"]:
                dx, dy = mv["tx"] - mv["fx"], mv["ty"] - mv["fy"]
                return self.move(i, dx, dy)
        return False


if __name__ == "__main__":
    import time
    for name, text in LAYOUTS:
        t0 = time.time()
        sol = solve(text)
        dt = time.time() - t0
        print("%-6s 最优步数=%-4s 耗时=%.2fs" % (name, len(sol) if sol else "无解", dt))
