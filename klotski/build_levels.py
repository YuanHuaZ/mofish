# -*- coding: utf-8 -*-
"""
构建期脚本：生成不规则华容道的关卡数据 levels.json

1) 8 个经典布局（横刀立马、层层设防…）逐一 BFS 求解；
2) 程序化随机生成大量 4×5 布局，用多进程并行 BFS 验证可解；
3) 合并去重后按最优步数递增取 30 关，最优解一并写入题库，
   运行时可秒开显示「最少步数」、即时提示、一键自动演示。
"""
import json
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from klotski import engine as KE  # noqa: E402

TARGET_LEVELS = 30
MIN_STEPS, MAX_STEPS = 45, 130

LETTERS = {"C": "C", "G": "G", "V": "ZYIH", "S": "abcde"}
SHAPES = [("C", 2, 2), ("G", 2, 1)] + [("V", 1, 2)] * 4 + [("S", 1, 1)] * 4

# 生成关卡的名字池（取自典故 / 兵法的意象，仅作关卡标签）
NAME_POOL = [
    "四面楚歌", "围魏救赵", "十面埋伏", "暗度陈仓", "背水一战", "声东击西",
    "以逸待劳", "金蝉脱壳", "单刀赴会", "火烧连营", "草船借箭", "三顾茅庐",
    "势如破竹", "瓮中捉鳖", "绝处逢生", "步步为营", "险中求胜", "柳暗花明",
    "反客为主", "临危不惧", "化险为夷", "力挽狂澜", "绝地反击", "拨云见日",
    "峰峦叠嶂", "九曲回廊", "一线生机", "重围突围", "弃车保帅", "置之死地",
    "虎口脱险", "起死回生", "曲径通幽", "拨乱反正", "转危为安", "破釜沉舟",
    "瞒天过海", "借刀杀人", "顺手牵羊", "调虎离山", "欲擒故纵", "釜底抽薪",
]


def gen_layout(rng):
    """随机生成一个合法的 4x5 布局文本"""
    board = [["."] * KE.W for _ in range(KE.H)]
    counters = {}

    def fits(x, y, w, h):
        if x + w > KE.W or y + h > KE.H:
            return False
        return all(board[y + dy][x + dx] == "."
                   for dy in range(h) for dx in range(w))

    def paint(x, y, w, h, ch):
        for dy in range(h):
            for dx in range(w):
                board[y + dy][x + dx] = ch

    def place(i):
        if i == len(SHAPES):
            return True
        kind, w, h = SHAPES[i]
        spots = [(x, y) for y in range(KE.H - h + 1) for x in range(KE.W - w + 1)
                 if fits(x, y, w, h)]
        rng.shuffle(spots)
        for (x, y) in spots:
            counters[kind] = counters.get(kind, 0) + 1
            ch = LETTERS[kind][counters[kind] - 1]
            paint(x, y, w, h, ch)
            if place(i + 1):
                return True
            paint(x, y, w, h, ".")
            counters[kind] -= 1
        return False

    return "\n".join("".join(r) for r in board) if place(0) else None


def _solve_one(text):
    try:
        sol = KE.solve(text, cap=200000)
    except Exception:
        return text, None
    return text, (len(sol) if sol else None)


def collect_generated(target, seed=20261008, rounds=4):
    rng = random.Random(seed)
    seen, good = set(), []
    for _ in range(rounds):
        cands = []
        while len(cands) < target * 4:
            t = gen_layout(rng)
            if not t:
                continue
            try:
                key = KE._canon([(p["w"], p["h"], p["x"], p["y"])
                                 for p in KE.parse_layout(t)])
            except Exception:
                continue
            if key in seen:
                continue
            seen.add(key)
            cands.append(t)
        try:
            from concurrent.futures import ProcessPoolExecutor
            with ProcessPoolExecutor(max_workers=min(8, os.cpu_count() or 4)) as ex:
                res = list(ex.map(_solve_one, cands, chunksize=4))
        except Exception:
            res = [_solve_one(t) for t in cands]
        good += [(t, n) for (t, n) in res if n and MIN_STEPS <= n <= MAX_STEPS]
        print("  本轮候选 %d 个，可解且步数合适 %d 个（累计 %d）"
              % (len(cands), len(good), len(good)))
        if len(good) >= target:
            break
    return good


def main():
    t0 = time.time()
    out = {}
    print("求解 %d 个经典布局…" % len(KE.LAYOUTS))
    for name, text in KE.LAYOUTS:
        sol = KE.solve(text)
        if sol:
            out[text] = (name, sol)
            print("  %-6s 最少 %3d 步" % (name, len(sol)))

    print("随机生成不规则布局（多进程 BFS 验证可解）…")
    for text, n in collect_generated(TARGET_LEVELS - len(out)):
        out.setdefault(text, (None, None))
    print("  合计可用布局 %d 个" % len(out))

    items = []
    for text, (name, sol) in out.items():
        sol = sol or KE.solve(text)
        if sol:
            items.append((len(sol), text, name, sol))
    items.sort(key=lambda t: t[0])
    if len(items) > TARGET_LEVELS:
        step = (len(items) - 1) / float(TARGET_LEVELS - 1)
        items = [items[i] for i in sorted({int(round(k * step))
                                           for k in range(TARGET_LEVELS)})]

    pool = list(NAME_POOL)
    levels = []
    prev = 0
    for i, (steps, text, name, sol) in enumerate(items, 1):
        if not name:
            name = pool.pop(0) if pool else "布局 %02d" % i
        assert steps >= prev, "难度未递增"
        prev = steps
        levels.append({"level": i, "name": name, "layout": text,
                       "minSteps": steps, "solution": sol})
    path = os.path.join(HERE, "levels.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"levels": levels}, f, ensure_ascii=False, separators=(",", ":"))
    print("共 %d 关，写入 %s（%d 字节，用时 %.1fs）"
          % (len(levels), path, os.path.getsize(path), time.time() - t0))
    for lv in levels:
        print("  第%2d关 %-6s 最少 %3d 步" % (lv["level"], lv["name"], lv["minSteps"]))


if __name__ == "__main__":
    main()
