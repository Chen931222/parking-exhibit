"""〈挪車的代價〉HUD 疊層 — 逐格產生透明 PNG，之後用 ffmpeg 疊回 3D 畫面。

畫面上同時呈現三個資料結構，車在它們之間移動：
  ParkingStack(5)  一般區（巷道）——index 0 是巷底，也就是堆疊底
  temp_stack       挪出來暫放的車（就是 main.py 裡那個 list）
  WaitingQueue(5)  等待區

色票與版式守 DESIGN.md：夜色＋單一標線黃，方角、1px 線，不做漸層／發光／圓角。

用法：
  python V1_hud.py [--events events.json] [--out renders\\hud] [--res 1280 720]
"""
import argparse
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

# ── 色票（DESIGN.md）
ASPHALT = (0x14, 0x14, 0x16)
CONCRETE = (0x26, 0x26, 0x2A)
LINE = (0xE9, 0xE6, 0xDF)
MUTED = (0x9B, 0x97, 0x8E)
PAINT = (0xF2, 0xB8, 0x24)          # 唯一強調色，只給讀數／目標／關鍵詞

FONTS = r"C:\Windows\Fonts"


def load(name, size, index=0, variation=None):
    f = ImageFont.truetype(os.path.join(FONTS, name), size, index=index)
    if variation:
        try:
            f.set_variation_by_name(variation)
        except Exception:
            pass
    return f


ap = argparse.ArgumentParser()
ap.add_argument("--events", default=r"G:\Projects\parking-lot\events.json")
ap.add_argument("--out", default=r"G:\Projects\parking-lot\renders\hud")
ap.add_argument("--res", nargs=2, type=int, default=[1280, 720])
ap.add_argument("--only", type=int, nargs="*", default=None, help="只畫這幾格（除錯用）")
A = ap.parse_args()

with open(A.events, encoding="utf-8") as fh:
    EV = json.load(fh)

W, H = A.res
S = W / 1280.0                       # 版面等比縮放
NFRAMES = EV['frames']
SHOTS = EV['shots']
ALLEY = EV['alley_plates']           # index 0 = 巷底 = 堆疊底
QUEUE = EV['queue_plates']
TARGET = EV['target']
MOVES = EV['moves']
FLAT = EV['flat_plate']

# Bahnschrift＝DIN 系工業告示體，對應 DESIGN.md 的 Archivo 路線（本機沒有 Archivo）
F_TITLE = load("bahnschrift.ttf", int(46 * S), variation="Bold")
F_HEAD = load("bahnschrift.ttf", int(17 * S), variation="SemiBold")
F_TC = load("msjhbd.ttc", int(17 * S))
F_TC_SM = load("msjh.ttc", int(13 * S))
F_TC_TITLE = load("msjhbd.ttc", int(34 * S))
F_MONO = load("consola.ttf", int(15 * S))
F_MONO_B = load("consolab.ttf", int(15 * S))
F_MONO_SM = load("consola.ttf", int(11 * S))
F_COUNT = load("consolab.ttf", int(46 * S))


def px(v):
    return int(round(v * S))


def ls_text(d, xy, s, font, fill, ls=1.6):
    """字距版 text（PIL 沒有 letter-spacing；工業告示體全大寫需要撐開）"""
    x, y = xy
    for ch in s:
        d.text((x, y), ch, font=font, fill=fill)
        x += d.textlength(ch, font=font) + ls * S
    return x


def rect(d, box, outline, width=1, fill=None):
    d.rectangle(box, outline=outline, width=max(1, px(width)), fill=fill)


def dashed_rect(d, box, colour, dash=5, gap=4, width=1):
    x0, y0, x1, y1 = box
    w = max(1, px(width))
    dash, gap = px(dash), px(gap)
    for (ax, ay, bx, by) in ((x0, y0, x1, y0), (x0, y1, x1, y1),
                             (x0, y0, x0, y1), (x1, y0, x1, y1)):
        horiz = ay == by
        t, end = (ax, bx) if horiz else (ay, by)
        while t < end:
            u = min(t + dash, end)
            if horiz:
                d.line((t, ay, u, by), fill=colour, width=w)
            else:
                d.line((ax, t, bx, u), fill=colour, width=w)
            t = u + gap


# ════════════════════════════════════════════════════ 逐格狀態
# 事件是引擎吐出來的，這裡只做「什麼時候顯示」的時間對位，不重算任何數字。
POPS = [e for e in EV['events'] if e['op'] == 'pop']
PUSHES = [e for e in EV['events'] if e['op'] == 'push']
LEAVE = next(e for e in EV['events'] if e['op'] == 'leave')
DEQ = next(e for e in EV['events'] if e['op'] == 'dequeue')
FLATLEAVE = next(e for e in EV['events'] if e['op'] == 'flat_leave')

SRC = {                              # 逐段節錄 _src/main.py 的原始碼（一字不改）
    'idle':  ("lot.car_leave(\"%s\")" % TARGET, "在一般區裡找到它，然後開始把上面的車搬走"),
    'pop':   ("top = area.pop();  temp_stack.append(top)", "堆疊只能從頂端取——擋路的先出來"),
    'leave': ("self.record_tree.add_leave_record(plate, out_time)", "目標車離場，寫進 BST 出入紀錄"),
    'push':  ("while temp_stack:  area.push(temp_stack.pop())", "再一台台放回去；順序倒過來，整排往裡推一格"),
    'deq':   ("next_car = self.waiting_queue.dequeue()", "空出一格，等待區排頭遞補（FIFO）"),
}


def state_at(f):
    slots = list(ALLEY)              # index 0 = 巷底
    temp, queue = [], list(QUEUE)
    moving = {}
    moves = 0
    phase = 'idle'

    for e in POPS:                   # pop()：一起步就離開堆疊，抵達暫存位才算落定
        if f >= e['f0']:
            if e['plate'] in slots:
                slots[slots.index(e['plate'])] = None
            temp.append(e['plate'])
            moves = max(moves, e['moves_after'])
            if f < e['f1']:
                moving[e['plate']] = 'out'
                phase = 'pop'
            elif phase == 'idle':
                phase = 'pop'

    if f >= LEAVE['f0']:
        if TARGET in slots:
            slots[slots.index(TARGET)] = None
        if f <= LEAVE['f1']:
            moving[TARGET] = 'leave'
            phase = 'leave'

    for e in PUSHES:                 # push()：一起步就離開 temp_stack，抵達槽位才算落定
        if f >= e['f0']:
            if e['plate'] in temp:
                temp.remove(e['plate'])
            slots[e['to_slot']] = e['plate']
            if f < e['f1']:
                moving[e['plate']] = 'in'
            phase = 'push'

    if f >= DEQ['f0']:
        if DEQ['plate'] in queue:
            queue.remove(DEQ['plate'])
        if f <= DEQ['f1'] + 40:
            phase = 'deq'
        moving[DEQ['plate']] = 'queue'

    return slots, temp, queue, moving, moves, phase


def fade(f, a, b, ramp=10):
    """[a,b] 之間為 1，前後 ramp 格線性淡入淡出"""
    if f < a - ramp or f > b + ramp:
        return 0.0
    if f < a:
        return (f - (a - ramp)) / ramp
    if f > b:
        return ((b + ramp) - f) / ramp
    return 1.0


def al(c, a):
    return (c[0], c[1], c[2], int(max(0, min(1, a)) * 255))


# ════════════════════════════════════════════════════ 繪製
PANEL_W = px(252)
X_L = px(40)
X_R = W - px(40) - PANEL_W
Y_TOP = px(112)
ROW_H, ROW_G = px(32), px(6)


def chip(d, box, plate, a, *, target=False, ghost=False, idx=None, tag=None):
    """一台車＝一張方角票根。目標車給標線黃，在途中的畫虛線。"""
    col = PAINT if target else LINE
    if ghost:
        dashed_rect(d, box, al(col, 0.55 * a))
    else:
        rect(d, box, al(col, 0.85 * a))
    x0, y0, x1, y1 = box
    if target:                        # 目標：左緣加粗，一眼認出來
        d.rectangle((x0, y0, x0 + px(3), y1), fill=al(PAINT, 0.95 * a))
    tx = x0 + px(10)
    if idx is not None:
        d.text((tx, y0 + px(9)), f"[{idx}]", font=F_MONO_SM, fill=al(MUTED, 0.85 * a))
        tx += px(26)
    d.text((tx, y0 + px(6)), plate, font=F_MONO_B if target else F_MONO,
           fill=al(col, (0.55 if ghost else 1.0) * a))
    if tag:
        tw = d.textlength(tag, font=F_MONO_SM)
        d.text((x1 - px(10) - tw, y0 + px(9)), tag, font=F_MONO_SM,
               fill=al(MUTED, 0.9 * a))


def empty_slot(d, box, a, idx, label=""):
    dashed_rect(d, box, al(MUTED, 0.45 * a))
    d.text((box[0] + px(10), box[1] + px(9)), f"[{idx}]", font=F_MONO_SM,
           fill=al(MUTED, 0.55 * a))
    if label:
        d.text((box[0] + px(36), box[1] + px(8)), label, font=F_TC_SM,
               fill=al(MUTED, 0.75 * a))


def draw_frame(f):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    slots, temp, queue, moving, moves, phase = state_at(f)

    # ── 開場標題（只在第一顆鏡頭）
    # 放在畫面中段兩塊面板之間：壓在左欄上會跟 MOVES 讀數疊在一起。
    ta = fade(f, 8, SHOTS['A'][1] + 6, ramp=14)
    if ta > 0:
        x, y = px(420), px(238)
        d.text((x, y), "挪車的代價", font=F_TC_TITLE, fill=al(LINE, ta))
        ls_text(d, (x + px(3), y + px(52)), "THE COST OF MOVING", F_HEAD,
                al(PAINT, 0.95 * ta), ls=3.0)
        d.line((x, y + px(80), x + px(300), y + px(80)), fill=al(MUTED, 0.5 * ta),
               width=max(1, px(1)))
        d.text((x, y + px(90)), "停車場即資料結構 · 資料結構期末專題",
               font=F_TC_SM, fill=al(MUTED, ta))

    pa = fade(f, SHOTS['B'][0] - 4, NFRAMES, ramp=16)     # 面板從第二顆鏡頭淡入
    if pa > 0:
        # 極淡的柏油底：壓在暗處幾乎看不見，只在鏡頭掃過濕地面反光時救回可讀性。
        # 刻意壓到 0.35——夜色是場景的光，不是深色模式模板。
        d.rectangle((X_L - px(14), Y_TOP - px(16),
                     X_L + PANEL_W + px(14), Y_TOP + px(496)), fill=al(ASPHALT, 0.35 * pa))
        d.rectangle((X_R - px(14), Y_TOP - px(16),
                     X_R + PANEL_W + px(14), Y_TOP + px(158)), fill=al(ASPHALT, 0.35 * pa))

        # ── 一般區 ParkingStack
        y = Y_TOP
        ls_text(d, (X_L, y), "NORMAL AREA", F_HEAD, al(LINE, pa), ls=2.6)
        d.text((X_L, y + px(22)), "一般區 · ParkingStack(capacity=5)",
               font=F_TC_SM, fill=al(MUTED, pa))
        d.line((X_L, y + px(44), X_L + PANEL_W, y + px(44)),
               fill=al(MUTED, 0.55 * pa), width=max(1, px(1)))
        y += px(54)
        for i in range(5):
            box = (X_L, y, X_L + PANEL_W, y + ROW_H)
            p = slots[i]
            tag = "巷底" if i == 0 else ("巷口" if i == 4 else None)
            if p:
                chip(d, box, p, pa, target=(p == TARGET),
                     ghost=(moving.get(p) == 'in'), idx=i, tag=tag)
            else:
                empty_slot(d, box, pa, i, tag or "")
            y += ROW_H + ROW_G

        # ── temp_stack：main.py 裡真的存在的那個 list
        y += px(12)
        ls_text(d, (X_L, y), "TEMP_STACK", F_HEAD, al(LINE, pa), ls=2.6)
        d.text((X_L, y + px(22)), "挪出來暫放的車", font=F_TC_SM, fill=al(MUTED, pa))
        d.line((X_L, y + px(44), X_L + PANEL_W, y + px(44)),
               fill=al(MUTED, 0.55 * pa), width=max(1, px(1)))
        y += px(54)
        cw = (PANEL_W - px(9)) // 4
        for k in range(4):
            box = (X_L + k * (cw + px(3)), y, X_L + k * (cw + px(3)) + cw, y + px(26))
            if k < len(temp):
                p = temp[k]
                gh = moving.get(p) in ('out',)
                if gh:
                    dashed_rect(d, box, al(LINE, 0.5 * pa))
                else:
                    rect(d, box, al(LINE, 0.8 * pa))
                d.text((box[0] + px(5), box[1] + px(5)), p.split('-')[0],
                       font=F_MONO_SM, fill=al(LINE, (0.5 if gh else 1.0) * pa))
            else:
                dashed_rect(d, box, al(MUTED, 0.3 * pa))

        # ── 挪車計數：帳單讀數，唯一的大數字
        y += px(46)
        ls_text(d, (X_L, y), "MOVES", F_HEAD, al(MUTED, pa), ls=2.6)
        d.text((X_L, y + px(20)), str(moves), font=F_COUNT, fill=al(PAINT, pa))
        nw = d.textlength(str(moves), font=F_COUNT)
        d.text((X_L + nw + px(9), y + px(46)), "台", font=F_TC, fill=al(PAINT, 0.9 * pa))
        d.text((X_L, y + px(80)), "為了取出巷底那 1 台", font=F_TC_SM, fill=al(MUTED, pa))

        # ── 等待區 WaitingQueue
        y = Y_TOP
        ls_text(d, (X_R, y), "WAITING QUEUE", F_HEAD, al(LINE, pa), ls=2.6)
        d.text((X_R, y + px(22)), "等待區 · WaitingQueue(capacity=5)",
               font=F_TC_SM, fill=al(MUTED, pa))
        d.line((X_R, y + px(44), X_R + PANEL_W, y + px(44)),
               fill=al(MUTED, 0.55 * pa), width=max(1, px(1)))
        y += px(54)
        for k in range(len(QUEUE)):
            box = (X_R, y, X_R + PANEL_W, y + px(26))
            if k < len(queue) or QUEUE[k] in queue:
                pass
            p = QUEUE[k]
            if p in queue:
                rect(d, box, al(LINE, 0.8 * pa))
                d.text((box[0] + px(10), box[1] + px(4)), p, font=F_MONO,
                       fill=al(LINE, pa))
                if p == queue[0]:
                    d.text((box[2] - px(46), box[1] + px(6)), "HEAD",
                           font=F_MONO_SM, fill=al(PAINT, 0.9 * pa))
            else:
                dashed_rect(d, box, al(MUTED, 0.35 * pa))
                d.text((box[0] + px(10), box[1] + px(4)), p, font=F_MONO,
                       fill=al(MUTED, 0.45 * pa))
                d.text((box[2] - px(66), box[1] + px(6)), "DEQUEUED",
                       font=F_MONO_SM, fill=al(MUTED, 0.7 * pa))
            y += px(26) + px(4)

    # ── 平面車位對照：只在那顆對照鏡頭裡出現。
    # 綁鏡頭而不是綁車的移動窗——C 機位看不到平面車位，
    # 在那裡打這張卡等於字幕在講畫面沒演的事。
    fa = fade(f, SHOTS['E'][0], SHOTS['E'][1], ramp=10)
    if fa > 0:
        bw, bh = px(268), px(74)
        x0, y0 = W - px(40) - bw, H - px(150) - bh
        d.rectangle((x0, y0, x0 + bw, y0 + bh), fill=al(ASPHALT, 0.72 * fa))
        rect(d, (x0, y0, x0 + bw, y0 + bh), al(MUTED, 0.6 * fa))
        ls_text(d, (x0 + px(12), y0 + px(10)), "FLAT BAY", F_HEAD, al(LINE, fa), ls=2.6)
        d.text((x0 + px(12), y0 + px(32)), "平面車位 · 隨機存取",
               font=F_TC_SM, fill=al(MUTED, fa))
        d.text((x0 + px(12), y0 + px(50)), "O(1)", font=F_MONO_B, fill=al(PAINT, fa))
        d.text((x0 + px(64), y0 + px(50)), "· 挪車 0 台，直接開走",
               font=F_TC_SM, fill=al(MUTED, fa))

    # ── 程式字條：直接節錄 _src/main.py，畫面在演哪一行就顯示哪一行
    ca = fade(f, SHOTS['B'][0] + 10, NFRAMES, ramp=16)
    if ca > 0:
        code, cap = SRC[phase]
        y0 = H - px(96)
        d.line((px(40), y0, W - px(40), y0), fill=al(MUTED, 0.45 * ca),
               width=max(1, px(1)))
        d.rectangle((px(40), y0, px(40) + px(4), y0 + px(46)), fill=al(PAINT, 0.9 * ca))
        d.text((px(56), y0 + px(6)), code, font=F_MONO, fill=al(LINE, ca))
        d.text((px(56), y0 + px(28)), cap, font=F_TC_SM, fill=al(MUTED, ca))
        lab = "_src/main.py · car_leave()"
        lw = d.textlength(lab, font=F_MONO_SM)
        d.text((W - px(40) - lw, y0 + px(8)), lab, font=F_MONO_SM,
               fill=al(MUTED, 0.8 * ca))
    return img


os.makedirs(A.out, exist_ok=True)
frames = A.only if A.only else range(1, NFRAMES + 1)
for i, f in enumerate(frames):
    draw_frame(f).save(os.path.join(A.out, f"hud_{f:04d}.png"))
    if i % 100 == 0:
        print(f"[HUD] {f}/{NFRAMES}")
        sys.stdout.flush()
print(f"[HUD] 完成 {len(list(frames)) if A.only else NFRAMES} 格 → {A.out}")
