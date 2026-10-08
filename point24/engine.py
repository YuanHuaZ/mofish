# -*- coding: utf-8 -*-
"""
24 点引擎（无 GUI，可独立测试）

玩法：给定 4 个 1~13 的整数，每个恰好用一次，用 + - × ÷ 和括号凑出 24。
- 全程用 Fraction 精确计算，中间结果允许负数与分数（1 3 4 6 → 6÷(1-3÷4)）
- 求解器能输出**所有本质不同的解法**（交换律/结合律归一化后去重）
- 难度模型：可用「第一步分支数」衡量——分支越少越难；必须用到分数解的最难
"""
import ast
import itertools
import random
from fractions import Fraction
from functools import lru_cache

TARGET = Fraction(24)
CARD_MIN, CARD_MAX = 1, 13

# ------------------------------------------------------------------ 表达式树
class Node(object):
    """表达式节点：叶子存数字，内部节点存运算（+ / * 会做结合律归一化）"""

    __slots__ = ("kind", "items", "left", "right", "value", "_s")

    def __init__(self, kind, value, items=None, left=None, right=None):
        self.kind = kind
        self.value = value
        self.items = items
        self.left = left
        self.right = right
        self._s = None

    def text(self):
        if self._s is None:
            self._s = _render(self, 0)
        return self._s

    def all_int(self):
        """整棵子树的中间结果是否都是整数"""
        if self.kind == "n":
            return self.value.denominator == 1
        if self.value.denominator != 1:
            return False
        if self.kind in ("+", "*"):
            return all(x.all_int() for x in self.items)
        return self.left.all_int() and self.right.all_int()


PREC = {"+": 1, "-": 1, "*": 2, "/": 2, "n": 3}


def _num(v):
    return str(v.numerator) if v.denominator == 1 else "%d/%d" % (v.numerator, v.denominator)


def _render(node, parent):
    if node.kind == "n":
        return _num(node.value)
    op = node.kind
    if op == "+":
        s = "+".join(_render(x, 0) for x in node.items)
    elif op == "*":
        parts = []
        for x in node.items:
            t = _render(x, 0)
            if PREC[x.kind] < PREC["*"]:
                t = "(%s)" % t
            parts.append(t)
        s = "×".join(parts)
    elif op == "-":
        s = _render(node.left, PREC["-"]) + "-" + _render(node.right, PREC["-"] + 1)
    else:
        s = _render(node.left, PREC["/"]) + "÷" + _render(node.right, PREC["/"] + 1)
    if PREC[op] < parent:
        s = "(%s)" % s
    return s


def _leaf(v):
    return Node("n", Fraction(v))


def _add(a, b):
    items = []
    for x in (a, b):
        items.extend(x.items if x.kind == "+" else [x])
    items.sort(key=lambda x: x.text())
    return Node("+", a.value + b.value, items=items)


def _mul(a, b):
    items = []
    for x in (a, b):
        items.extend(x.items if x.kind == "*" else [x])
    items.sort(key=lambda x: x.text())
    return Node("*", a.value * b.value, items=items)


def _sub(a, b):
    return Node("-", a.value - b.value, left=a, right=b)


def _div(a, b):
    if b.value == 0:
        return None
    return Node("/", a.value / b.value, left=a, right=b)


def defs(nums):
    """全部本质不同的解（归一化后的表达式字符串，去重后排序）"""
    out = set()
    start = [_leaf(v) for v in nums]

    def rec(ns):
        if len(ns) == 1:
            if ns[0].value == TARGET:
                out.add(ns[0].text())
            return
        m = len(ns)
        for i in range(m):
            for j in range(i + 1, m):
                rest = [ns[k] for k in range(m) if k != i and k != j]
                a, b = ns[i], ns[j]
                cands = [_add(a, b), _sub(a, b), _sub(b, a), _mul(a, b),
                         _div(a, b), _div(b, a)]
                for node in cands:
                    if node is not None:
                        rec(rest + [node])

    rec(start)
    return sorted(out)


def build(op, a, b):
    """按玩家的选择顺序拼节点（不做交换律归一化，展示更直观）；除零返回 None"""
    if op == "+":
        return Node("+", a.value + b.value, items=[a, b])
    if op == "*":
        return Node("*", a.value * b.value, items=[a, b])
    if op == "-":
        return Node("-", a.value - b.value, left=a, right=b)
    if op == "/":
        if b.value == 0:
            return None
        return Node("/", a.value / b.value, left=a, right=b)
    raise ValueError("不支持的运算符：%r" % op)


OP_CHAR = {"+": "+", "-": "−", "*": "×", "/": "÷"}


def leaf(v):
    return _leaf(v)


def solutions(nums, limit=None):
    """带中间结果是否为整数的解法列表 [{expr, allInt}]"""
    out = {}
    start = [_leaf(v) for v in nums]

    def rec(ns):
        if len(ns) == 1:
            if ns[0].value == TARGET:
                t = ns[0].text()
                prev = out.get(t)
                flag = ns[0].all_int()
                out[t] = flag if prev is None else (prev or flag)
            return
        m = len(ns)
        for i in range(m):
            for j in range(i + 1, m):
                rest = [ns[k] for k in range(m) if k != i and k != j]
                a, b = ns[i], ns[j]
                for node in (_add(a, b), _sub(a, b), _sub(b, a), _mul(a, b),
                             _div(a, b), _div(b, a)):
                    if node is not None:
                        rec(rest + [node])

    rec(start)
    items = [{"expr": k, "allInt": v} for k, v in sorted(out.items())]
    return items[:limit] if limit else items


# ------------------------------------------------------------------ 可解性（记忆化）
@lru_cache(maxsize=None)
def _can(vals, target, int_only):
    vals = tuple(sorted(vals))
    if len(vals) == 1:
        return vals[0] == target
    n = len(vals)
    for i in range(n):
        for j in range(i + 1, n):
            rest = tuple(vals[k] for k in range(n) if k != i and k != j)
            a, b = vals[i], vals[j]
            cands = [a + b, a - b, b - a, a * b]
            if b != 0:
                cands.append(a / b)
            if a != 0:
                cands.append(b / a)
            for c in cands:
                if int_only and c.denominator != 1:
                    continue
                if _can(tuple(sorted(rest + (c,))), target, int_only):
                    return True
    return False


def can_make(nums, int_only=False):
    return _can(tuple(sorted(Fraction(v) for v in nums)), TARGET, int_only)


def first_branches(nums):
    """第一步有多少种走法仍然可解（越少越难），返回 (分支数, 总走法数)"""
    vals = tuple(sorted(Fraction(v) for v in nums))
    n = len(vals)
    ok = total = 0
    for i in range(n):
        for j in range(i + 1, n):
            rest = tuple(vals[k] for k in range(n) if k != i and k != j)
            a, b = vals[i], vals[j]
            cands = [a + b, a - b, b - a, a * b]
            if b != 0:
                cands.append(a / b)
            if a != 0:
                cands.append(b / a)
            for c in cands:
                total += 1
                if _can(tuple(sorted(rest + (c,))), TARGET, False):
                    ok += 1
    return ok, total


# ------------------------------------------------------------------ 难度
TIERS = [(35, "入门", "#38bdf8"), (65, "简单", "#22c55e"), (95, "普通", "#f0b23c"),
         (125, "困难", "#f97316"), (10 ** 9, "大师", "#a78bfa")]


def analyse(nums):
    """返回 {solvable, intOnly, nFirst, total}"""
    if not can_make(nums, False):
        return {"solvable": False, "intOnly": False, "nFirst": 0, "total": 36}
    ok, total = first_branches(nums)
    return {"solvable": True, "intOnly": can_make(nums, True),
            "nFirst": ok, "total": total}


def difficulty_score(info):
    """难度分：可用的第一步越少越难（满分约 105），必须用分数解的再加 50"""
    if not info["solvable"]:
        return 10 ** 6
    return (info["total"] - info["nFirst"]) * 3 + (50 if not info["intOnly"] else 0)


def tier_of(score):
    for lim, name, color in TIERS:
        if score < lim:
            return name, color
    return TIERS[-1][1], TIERS[-1][2]


def describe(nums):
    info = analyse(nums)
    score = difficulty_score(info)
    return {"nums": list(nums), "score": score, "tier": tier_of(score)[0],
            "nFirst": info["nFirst"], "total": info["total"],
            "intOnly": info["intOnly"], "solvable": info["solvable"]}


# ------------------------------------------------------------------ 关卡 / 随机题
def all_solvable(max_n=CARD_MAX):
    """枚举 4 张牌的全部可解组合（1~max_n，可重复），按难度升序"""
    out = []
    for combo in itertools.combinations_with_replacement(range(1, max_n + 1), 4):
        info = analyse(combo)
        if info["solvable"]:
            out.append((difficulty_score(info), combo, info))
    out.sort(key=lambda t: (t[0], t[1]))
    return out


def build_levels(count=24, max_n=CARD_MAX):
    """按难度严格递增挑 count 关，并存下解法（用于提示与「其他解法」）"""
    pool = all_solvable(max_n)
    uniq, last = [], None
    for score, combo, info in pool:
        if score != last:
            uniq.append((score, combo, info))
            last = score
    if len(uniq) > count:
        step = (len(uniq) - 1) / float(count - 1)
        uniq = [uniq[int(round(i * step))] for i in range(count)]
    levels = []
    for i, (score, combo, info) in enumerate(uniq, 1):
        sols = solutions(combo)
        levels.append({
            "level": i, "nums": list(combo), "score": score,
            "tier": tier_of(score)[0], "nFirst": info["nFirst"],
            "intOnly": info["intOnly"], "nSolutions": len(sols),
            "solutions": [s["expr"] for s in sols[:6]],
        })
    return levels


def random_puzzle(tier=None, rng=None, avoid=()):
    """随机出一道可解的题（运行时兜底用）；tier 指定档位名时只在该档位内取"""
    rng = rng or random.Random()
    avoid = set(tuple(sorted(a)) for a in avoid)
    for _ in range(6000):
        nums = tuple(sorted(rng.randint(CARD_MIN, CARD_MAX) for _ in range(4)))
        if nums in avoid:
            continue
        info = analyse(nums)
        if not info["solvable"]:
            continue
        if tier and tier_of(difficulty_score(info))[0] != tier:
            continue
        return nums
    return (3, 3, 8, 8)


# ------------------------------------------------------------------ 无限关题库
TIER_ORDER = [name for _lim, name, _c in TIERS]


def bank_from_json(data):
    """把 puzzles.json 的内容转成 {档位: [(n1,n2,n3,n4), ...]}"""
    out = {}
    for tier, arr in (data.get("bank") or {}).items():
        lst = [tuple(sorted(int(v) for v in combo)) for combo in arr if len(combo) == 4]
        if lst:
            out[tier] = lst
    return out


def pick(bank, tier, rng=None, avoid=()):
    """从题库里随机取一题；题库不可用时退回运行时随机生成"""
    rng = rng or random.Random()
    avoid = set(tuple(sorted(a)) for a in avoid)
    pool = bank.get(tier) if bank else None
    if pool:
        cands = [c for c in pool if c not in avoid] or list(pool)
        if len(cands) > 1:
            return rng.choice(cands)
        return cands[0]
    return random_puzzle(tier, rng, avoid)


def next_tier(tier, streak, step=3):
    """无限关自动升级：每连过 step 题，难度档位 +1（封顶大师）"""
    idx = TIER_ORDER.index(tier) if tier in TIER_ORDER else 0
    idx = min(len(TIER_ORDER) - 1, idx + streak // step)
    return TIER_ORDER[idx]


# ------------------------------------------------------------------ 表达式输入校验
# 把各种写法统一成半角的 + - * / ( ) 0-9
_SUBST = {
    "×": "*", "✕": "*", "✖": "*", "⨯": "*", "·": "*", "⋅": "*", "＊": "*",
    "x": "*", "X": "*",
    "÷": "/", "／": "/", "∕": "/", "➗": "/",
    "−": "-", "–": "-", "—": "-", "－": "-", "‒": "-",
    "＋": "+",
    "（": "(", "）": ")", "【": "(", "】": ")", "［": "(", "］": ")",
    "　": " ", "\u00a0": " ",
    "０": "0", "１": "1", "２": "2", "３": "3", "４": "4",
    "５": "5", "６": "6", "７": "7", "８": "8", "９": "9",
    "＝": "=", "，": ",", "、": ",",
}


def normalize_expr(text):
    """把全角/花式符号统一成半角运算符，方便各种输入法"""
    return "".join(_SUBST.get(ch, ch) for ch in str(text)).strip()


def eval_expression(text, expect_nums):
    """解析玩家输入的表达式，返回 (值, 用到的数字列表)；不合法时抛 ValueError"""
    s = normalize_expr(text)
    s = s.rstrip("=").strip()
    if not s:
        raise ValueError("先写一个表达式，例如 8×3+3-3")
    try:
        tree = ast.parse(s, mode="eval")
    except SyntaxError:
        raise ValueError("表达式写法有误，例如 (8-2)×4 或 8*3+3-3")
    nums = []

    def walk(node):
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, int):
                raise ValueError("只能用题目给的整数与 + - × ÷ ")
            nums.append(node.value)
            return Fraction(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -walk(node.operand)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd):
            return walk(node.operand)
        if isinstance(node, ast.BinOp):
            a = walk(node.left)
            b = walk(node.right)
            if isinstance(node.op, ast.Add):
                return a + b
            if isinstance(node.op, ast.Sub):
                return a - b
            if isinstance(node.op, ast.Mult):
                return a * b
            if isinstance(node.op, ast.Div):
                if b == 0:
                    raise ValueError("不能除以 0")
                return a / b
        raise ValueError("只支持 + - × ÷ 与括号")

    value = walk(tree)
    if sorted(nums) != sorted(expect_nums):
        raise ValueError("必须把 %s 这四个数各用一次（你用了 %s）"
                         % ("、".join(map(str, sorted(expect_nums))),
                            "、".join(map(str, sorted(nums))) if nums else "空"))
    return value, nums


if __name__ == "__main__":
    import time
    t0 = time.time()
    print("=== 经典算例 ===")
    for nums in [(1, 3, 4, 6), (3, 3, 8, 8), (4, 4, 10, 10), (5, 5, 5, 1),
                 (8, 8, 3, 3), (1, 1, 1, 1)]:
        info = analyse(nums)
        sols = solutions(nums)
        print("%-12s 可解=%-5s 整数解=%-5s 分支%-3d 解法%3d  %s"
              % (nums, info["solvable"], info["intOnly"], info["nFirst"],
                 len(sols), sols[0]["expr"] if sols else "—"))
    print("=== 枚举 1~13 可解组合 ===")
    pool = all_solvable()
    print("可解组合 %d 个，用时 %.1fs" % (len(pool), time.time() - t0))
    print("最难前 5：", [(c, s) for s, c, _ in pool[-5:]])
    print("=== 表达式校验（各种输入写法都能识别）===")
    for t in ("8*3+3-3", "8×3+3-3", "8x3+3-3", "8X3+3-3", "8＊3＋3－3",
              "８×３＋３－３", " 8 · 3 + 3 - 3 ", "8*3+3-3=", "(8-3)*3+9-9"):
        try:
            v = eval_expression(t, [8, 3, 3, 3] if "9" not in t else [8, 3, 3, 9])[0]
            print("  %-16r → %s" % (t, v))
        except ValueError as exc:
            print("  %-16r → 拒绝：%s" % (t, exc))
    print("6÷(1-3÷4) =", eval_expression("6÷(1-3÷4)", [1, 3, 4, 6])[0])
    print("6/(1-3/4) =", eval_expression("6/(1-3/4)", [1, 3, 4, 6])[0])
    try:
        eval_expression("6*4", [1, 3, 4, 6])
    except ValueError as exc:
        print("数没用全被拒绝：", exc)
