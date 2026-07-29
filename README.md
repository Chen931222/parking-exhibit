# 挪車的代價 — 停車場即資料結構

資料結構期末作業「停車場管理系統」的 3D 展示版。
取一台停在巷子深處的車，前面的車得先一台台挪開——
把堆疊（LIFO）的取出成本做成看得見的動畫與帳單，
旁邊放一排平面車位（隨機存取，O(1)）當對照。

線上版：https://parking-exhibit.vercel.app

## 內容

- `index.html` — 展示站本體（單檔，Three.js 是唯一外部函式庫）
- `_src/` — 課堂原始 Python：`parking_stack.py`、`waiting_queue.py`、`car_record_tree.py`、`main.py`
- `models/` — Kenney Car Kit 車模（CC0，License.txt 在資料夾內）

## 運作方式

網站引擎是 `_src/` 內 Python 邏輯的 JS 移植：堆疊×2（一般區＋身障區）、
等待佇列、BST 出入紀錄。動畫每一步旁的程式字條直接節錄課堂原始碼，
「挪車 k 台」的數字由引擎即時計算，不是寫死的。

展示層（3D 場景、動畫、網頁）在 AI 工具協作下完成；
資料結構的規則與行為以 `_src/` 的課堂原始碼為準。
