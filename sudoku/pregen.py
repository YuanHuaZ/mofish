# -*- coding: utf-8 -*-
"""并行预算 100 关题库 -> puzzles.json（构建期运行一次）"""
import json
import os
import sys
import time
from multiprocessing import Pool

import engine as E

POOL_PER_LEVEL = 3          # 每关预存几道题（含首刷那道）
MAX_TRIES = 14

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "puzzles.json")


def build_level(lv):
    t0 = time.time()
    out, seen = [], set()
    ref = None
    tries = 0
    while len(out) < POOL_PER_LEVEL and tries < MAX_TRIES:
        tries += 1
        g = E.generate(lv, 36, ref)
        key = E.to_string(g["puzzle"])
        if key in seen:
            continue
        if E.count_solutions(g["puzzle"], 3) != 1:      # 必须唯一解
            continue
        seen.add(key)
        if ref is None:
            ref = g["difficulty"]
        out.append(dict(
            p=key,
            s=E.to_string(g["solution"]),
            givens=g["givens"],
            rating=g["rating"],
            difficulty=round(g["difficulty"], 1),
        ))
    return lv, out, time.time() - t0


def main():
    t0 = time.time()
    levels = list(range(1, 101))
    result = {}
    workers = min(6, os.cpu_count() or 4)
    with Pool(workers) as pool:
        for lv, puzzles, dt in pool.imap_unordered(build_level, levels):
            if not puzzles:
                print("!! 第 %d 关生成失败" % lv, flush=True)
                continue
            first = puzzles[0]
            result[str(lv)] = dict(
                tier=E.tier_of(first["difficulty"]),
                tierName=E.TIERS[E.tier_of(first["difficulty"])]["name"],
                refDiff=first["difficulty"],
                givens=first["givens"],
                rating=first["rating"],
                target=round(E.difficulty_spec(lv)["target"], 1),
                puzzles=puzzles,
            )
            print("第 %3d 关 %-4s 提示%2d 技巧=%-8s 难度分%5.1f (目标%5.1f) %4.1fs"
                  % (lv, result[str(lv)]["tierName"], first["givens"],
                     E.RATING_TEXT[first["rating"]], first["difficulty"],
                     result[str(lv)]["target"], dt), flush=True)

    data = dict(version=1, generatedAt=time.strftime("%Y-%m-%d %H:%M:%S"),
                poolPerLevel=POOL_PER_LEVEL, levels=result)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print("\n完成 %d/100 关，共 %d 道题，用时 %.1fs -> %s (%.0f KB)"
          % (len(result), sum(len(v["puzzles"]) for v in result.values()),
             time.time() - t0, OUT, os.path.getsize(OUT) / 1024), flush=True)


if __name__ == "__main__":
    main()
