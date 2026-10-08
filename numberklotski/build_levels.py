# -*- coding: utf-8 -*-
"""
构建期脚本：生成数字华容道的关卡数据 levels.json

从 3×3 到 6×6 共 15 关，每关在大量候选中挑「初始偏差最接近目标」的一局，
并强制难度分严格递增（难度分 = 初始曼哈顿距离 × 尺寸系数）。
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from numberklotski import engine as NE  # noqa: E402


def main():
    t0 = time.time()
    levels = NE.build_levels()
    last = -1
    for lv in levels:
        assert NE.is_solvable(lv["tiles"], lv["n"]), "第%d关不可解" % lv["level"]
        assert lv["score"] > last, "第%d关难度未递增" % lv["level"]
        last = lv["score"]
    path = os.path.join(HERE, "levels.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"levels": levels}, f, ensure_ascii=False, separators=(",", ":"))
    print("数字华容道 %d 关，难度分 %d → %d，写入 %s（%d 字节，用时 %.1fs）"
          % (len(levels), levels[0]["score"], levels[-1]["score"], path,
             os.path.getsize(path), time.time() - t0))
    for lv in levels:
        print("  第%2d关 %s 难度分%3d（%s） 初始偏差 %3d"
              % (lv["level"], lv["name"], lv["score"], lv["tier"], lv["dist"]))


if __name__ == "__main__":
    main()
