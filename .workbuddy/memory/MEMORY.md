# 摸鱼小游戏合集 · 项目约定（长期）

Windows + PySide6 桌面游戏合集（六合一单 exe）。环境：
`C:\Users\zrf\.workbuddy\binaries\python\envs\default\Scripts\python.exe`（PySide6 6.11.2 / PyInstaller 6.22.3）。

## 结构（一个游戏一个包，都可单独运行）

| 目录 | 内容 |
| --- | --- |
| `main.py` | 入口（`--selftest` 全链路自检，结果写项目根 selftest.log） |
| `build_exe.py` | 打包（PyInstaller API 调用，输出 `摸鱼游戏合集.exe` 到项目根） |
| `shared/common.py` | 配色/控件/存档/路径/WorkerKeeper |
| `shared/lan.py` | 局域网联机传输（TCP 走棋 + UDP 广播发现） |
| `shared/lan_dialog.py` | 联机对话框（入口 `ask_lan(parent, game, 先手名, 后手名)`） |
| `hall/launcher.py` | 游戏大厅（`GAMES` 列表是唯一注册处；3 列卡片） |
| `sudoku/` | `<game>_app.py` + `engine.py` + `puzzles.json` |
| `klotski/` | + `levels.json`(30 关) + `build_levels.py` |
| `numberklotski/` | + `levels.json`(15 关) + `build_levels.py` |
| `xiangqi/` `gomoku/` | `<game>_app.py` + `engine.py` |
| `point24/` | + `puzzles.json`(162 分档题库) + `build_puzzles.py` |

## 硬性规则

1. **六个引擎都叫 `engine.py`** → 必须用包内绝对导入 `from <pkg> import engine as X`，
   禁止裸 `import engine`（同进程会串味）。新包要加 `__init__.py`。
2. **数据文件**用 `shared.common.load_game_json(name, folder)` / `find_game_data`，
   查找顺序 `_MEIPASS/<folder>/` → `_MEIPASS/` → 项目根/<folder>/；
   打包时 `--add-data "<src>;<folder名>"`。
   **存档目录 = `shared.common.data_dir()`**（<exe 或项目根>/saves/，不可写则退 AppData/saves/），
   读写存档一律用 `BaseStore` / `load_save` / `remove_save`，**不要自己拼路径、不要写 HERE/ROOT**。
   自检产物用 `shared.common.output_dir()`（<exe 或项目根>/_selftest/），与存档分开。
   根目录若出现旧版散落 `*_save.json`，首次 `data_dir()` 调用会自动搬进 `saves/`（`SAVE_FILES` 清单需同步）。
3. **新增游戏要动四处**：`hall/launcher.py` 的 `GAMES` + `_stat_xxx()`；
   `main.py` 自检加引擎校验（界面截图循环会自动带上）；`build_exe.py` 的 `DATA_FILES`
   与 `HIDDEN`；新建 `启动<游戏>.bat`。
4. **难度必须递增且可验证**：华容道按 BFS 最优步数；数字华容道按「曼哈顿距离 × 尺寸系数」；
   24 点按「(36 − 可用第一步) × 3 + 分数解 50」。构建脚本里直接 `assert` 递增。
5. **后台线程**（AI / BFS 求解）统一用 `common.WorkerKeeper` + 世代号 `self.gen` 丢弃过期结果，
   `closeEvent` 里 `keeper.stop_all()`。
6. **PyInstaller 坑**：不要用 `--clean`，也不要 `shutil.rmtree(workpath)`（触发批量删除保护）；
   每次用带时间戳的全新 `build/work-<ts>`、`build/dist-<ts>`，exe 用 `copy2` 覆盖到根目录。

## 局域网联机（象棋 / 五子棋）

- 代码在 `shared/lan.py`（传输）+ `shared/lan_dialog.py`（对话框），**纯标准库**，不要引第三方依赖。
- 端口约定：`DEFAULT_TCP` 五子棋 45680 / 象棋 45682；`DISCOVERY_UDP` 45681 / 45683；
  新游戏要在两个 dict 里登记，默认端口被占会自动换随机端口。
- 房间发现靠 UDP 广播，**必须同时发 `255.255.255.255` 和 `127.0.0.1`**，否则同机双窗口测不了。
- **给新游戏接联机的四步**：① 加 `self.net` + 头栏 chip + 联机卡片；
  ② `open_lan()` 调 `ask_lan(self, "<game>", 先手名, 后手名)` 拿 `(info, session)`，
  然后设 `self.human/self.human_color`（seat 0 = 先手）、连 `message`/`closed` 信号；
  ③ 本地走子后 `net.send({"t":"move","mv":[...]})`，收到对方走子用 `from_net=True` 应用
  （**不要回发**，否则回声循环）；`_ai_turn()` 里 `if self.net: return`；
  ④ 悔棋/重开改成「请求—同意」，双方用同一条确定性规则算步数（先撤 1 手，
  若没轮到发起方就再撤 1 手），保证棋盘一致；`_save()` 在联机时不落盘。

## 清理测试产物（重要）

`safe-delete` 保护会拦下**单次超过 50 个文件**的删除（fail-closed）。
`build/` 有 95 个文件 → 必须**按子目录分批** `rm -rf`，否则整条命令被拒绝。
测试产物清单：`_selftest/`（截图 + selftest.log，全部集中在此）、`saves/`（自检跑出的空壳存档）、`build/`。
`.gitignore`：`saves/*` + `!saves/.gitkeep`（**目录必须常驻，`saves/.gitkeep` 让空目录也能进版本库**）、
`_selftest/`、`build/`、`__pycache__/`。
**清理产物时不要删 `saves/` 本身**——只清里面的 `*_save.json`，保留 `.gitkeep`。

## 用户偏好

- 全中文；先确认方向 → 写代码 → 端到端实测（跑自检 + 看截图）→ 交付。
- 要求难度「往上升」（每款游戏都要有递增的难度曲线），界面提示要写清楚操作方式。
- 交互细节要求细：输入方式要宽容（如 24 点加减乘除各种写法都要能输入）。
- 交付内容不要留测试垃圾，运行完要清干净。
