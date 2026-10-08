# -*- coding: utf-8 -*-
"""
构建期脚本：生成 24 点的无限关题库 puzzles.json

枚举 1~13 的全部四张牌组合（可重复，共 1820 种，其中 1362 种可解），
按难度档位分桶存起来。运行时按档位随机抽题即可实现「无限关」，
还能避免连续出同一题；档位由连击数自动提升（每连过 3 题升一档）。
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from point24 import engine as E  # noqa: E402


def main():
    t0 = time.time()
    pool = E.all_solvable()
    bank = {}
    for score, combo, info in pool:
        tier = E.tier_of(score)[0]
        bank.setdefault(tier, []).append(list(combo))
    data = {"tiers": E.TIER_ORDER, "count": len(pool), "bank": bank}
    path = os.path.join(HERE, "puzzles.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print("可解组合 %d 个 → %s（%d 字节，用时 %.1fs）"
          % (len(pool), path, os.path.getsize(path), time.time() - t0))
    for tier in E.TIER_ORDER:
        lst = bank.get(tier, [])
        sample = lst[0] if lst else None
        print("  %-4s %5d 题   例：%s" % (tier, len(lst),
                                        " ".join(map(str, sample)) if sample else "—"))
    assert all(bank.get(t) for t in E.TIER_ORDER), "存在空档位"


if __name__ == "__main__":
    main()
