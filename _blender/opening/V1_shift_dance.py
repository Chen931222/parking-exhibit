"""〈挪車的代價〉— 停車場即資料結構．動畫版 V1

以 parking-exhibit.blend 的幾何為底，把 `_src/*.py` 的堆疊邏輯**實際跑一次**，
再把引擎吐出來的 pop / push / dequeue 序列烘成 Blender 動畫。

用法（headless，全程不碰使用者開著的那個 Blender）：
  G:\\blender.exe -b "G:\\Projects\\parking-exhibit\\_blender\\parking-exhibit.blend" ^
     -P V1_shift_dance.py -- --save --events
  ... -- --save --keyframes            # 只渲九張關鍵影格驗收
  ... -- --save --anim --samples 256   # 完整序列

設計約束（承 DESIGN.md）：
  * 挪車台數由引擎真算，不是寫死的常數。
  * Blender 只出幾何與機構；順序是引擎給的，這裡只負責把它變成看得見的位移。
  * 車是非完整約束系統：位移與朝向必須來自同一條路徑積分，不可各自插值。
"""
import bpy
import bmesh  # noqa: F401  (保留給後續版本；載入成本可忽略)
import json
import math
import os
import sys
from mathutils import Matrix, Vector

# ════════════════════════════════════════════════════════════ CLI
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(flag, n=1, default=None, cast=str):
    if flag not in argv:
        return default
    i = argv.index(flag)
    vals = [cast(v) for v in argv[i + 1:i + 1 + n]]
    return vals[0] if n == 1 else vals


OUT_DIR = arg("--outdir", 1, r"G:\Projects\parking-lot")
SAMPLES = arg("--samples", 1, 256, int)
RES = arg("--res", 2, [1280, 720], int)
DO_SAVE = "--save" in argv
DO_ANIM = "--anim" in argv
DO_KEYS = "--keyframes" in argv
DO_EVENTS = "--events" in argv
FRANGE = arg("--frames", 2, None, int)
ONEFRAME = arg("--testframe", 1, None, int)
ENGINE = arg("--engine", 1, "CYCLES")

FPS = 24
sc = bpy.context.scene


def log(*a):
    print("[DANCE]", *a)
    sys.stdout.flush()


# ════════════════════════════════════════════════════════════ 1. 資料結構引擎
# 直接抄 _src/parking_stack.py 與 _src/waiting_queue.py，行為必須一致。
# 這裡不做任何「為了動畫好看」的改寫——挪幾台是這段程式算出來的。

class ParkingStack:
    def __init__(self, capacity):
        self.capacity = capacity
        self.stack = []

    def is_full(self):
        return len(self.stack) >= self.capacity

    def is_empty(self):
        return len(self.stack) == 0

    def push(self, car):
        if self.is_full():
            return False
        self.stack.append(car)
        return True

    def pop(self):
        if self.is_empty():
            return None
        return self.stack.pop()

    def find_car_index(self, plate):
        for i, car in enumerate(self.stack):
            if car['plate'] == plate:
                return i
        return None


class WaitingQueue:
    def __init__(self, capacity=None):
        self.capacity = capacity
        self.queue = []

    def is_empty(self):
        return len(self.queue) == 0

    def is_full(self):
        return self.capacity is not None and len(self.queue) >= self.capacity

    def enqueue(self, car):
        if self.is_full():
            return False
        self.queue.append(car)
        return True

    def dequeue(self):
        if self.is_empty():
            return None
        return self.queue.pop(0)


# 車牌是合成資料（DESIGN.md 要求標明），格式照 _src/main.py 的 is_valid_plate
ALLEY_PLATES = ["RBK-2140", "APH-6072", "MQD-3318", "TSV-9265", "KLN-4471"]
QUEUE_PLATES = ["ZWC-5083", "NFJ-1926", "GTX-7734"]
FLAT_PLATE = "BXH-8859"
TARGET_PLATE = ALLEY_PLATES[0]          # 巷底那台＝堆疊最底部

normal = ParkingStack(5)
waiting = WaitingQueue(5)
OPS = []                                 # 引擎操作日誌 → 動畫與 HUD 的唯一真相來源

for p in ALLEY_PLATES:                   # 依序 push：索引 0 最先進場、卡在最裡面
    normal.push({'plate': p})
    OPS.append({'op': 'push', 'plate': p, 'depth': len(normal.stack) - 1})
for p in QUEUE_PLATES:
    waiting.enqueue({'plate': p})

# ── car_leave(TARGET)：完全照 _src/main.py 的流程
idx = normal.find_car_index(TARGET_PLATE)
assert idx is not None, "目標車不在一般區"
log(f"目標 {TARGET_PLATE} 在堆疊索引 {idx}（0=最底/巷底），堆疊高度 {len(normal.stack)}")

temp_stack = []
POP_SEQ, PUSH_SEQ = [], []
while True:
    top = normal.pop()
    if top['plate'] == TARGET_PLATE:
        target_car = top
        break
    temp_stack.append(top)
    POP_SEQ.append(top['plate'])
    OPS.append({'op': 'pop', 'plate': top['plate'], 'reason': 'blocking'})

MOVES = len(temp_stack)                  # ← 挪車台數：引擎算的
OPS.append({'op': 'leave', 'plate': target_car['plate'], 'moves': MOVES})

while temp_stack:
    c = temp_stack.pop()
    normal.push(c)
    PUSH_SEQ.append(c['plate'])
    OPS.append({'op': 'push', 'plate': c['plate'], 'depth': len(normal.stack) - 1})

DEQUEUED = None
if not waiting.is_empty():
    DEQUEUED = waiting.dequeue()
    normal.push(DEQUEUED)
    OPS.append({'op': 'dequeue', 'plate': DEQUEUED['plate']})
    OPS.append({'op': 'push', 'plate': DEQUEUED['plate'], 'depth': len(normal.stack) - 1})

log(f"引擎結論：挪車 {MOVES} 台 | pop 序 {POP_SEQ} | push 序 {PUSH_SEQ}")
log(f"最終堆疊（底→頂）：{[c['plate'] for c in normal.stack]}")
assert MOVES == 4, f"預期挪 4 台，引擎給 {MOVES}"

# ════════════════════════════════════════════════════════════ 2. 場景座標
ALLEY_X = -8.5
SLOT_Y = [12.6, 9.7, 6.8, 3.9, 1.0]      # index 0 = 巷底 = 堆疊底
SLOT_PITCH = 2.9
BODY_FOR_SLOT = ["Body.002", "Body.003", "Body.004", "Body.005", "Body.006"]
PLATE_TO_BODY = dict(zip(ALLEY_PLATES, BODY_FOR_SLOT))
FLAT_BODY = "Body.012"                   # 平面車位對照組（9.6, 3.2）
QUEUE_BODY = "Body.018"                  # 等待區排頭（-9.6, -11.7）

# ── 巷道是被兩條緣石島夾出來的（island_temp_alley x=-11.25、island_alley_dis x=-6.15），
#    兩條島都從 y=-0.35 延伸到 y=14.05。也就是說：**車只能開到巷口以南才可以橫移**。
#    這一條限制決定了整段編排——車在巷子裡不可能閃給別人過。
Y_MOUTH = -1.8                           # 可以開始變換車道的最北位置（含車身餘裕）
STAGE_Y = -8.2                           # 暫存並排列的 y
# 暫存位（並排，橫向間距 1.9；車寬 1.10 → 車間淨距 0.8）
# 依 pop 順序由西往東排開，路徑呈扇形發散、彼此不交叉
STAGE_X = [-12.2, -10.3, -8.4, -6.5]
# 目標車必須在暫存列的北邊就轉走，否則會直接撞上——所以暫存列壓在 y=-8.2，
# 而目標車的左轉弧收在 y=-5.2，兩者淨距 1.15。


# ════════════════════════════════════════════════════════════ 3. 車輛運動學
# 車頭朝向：ψ=0 → 世界前方 (0,-1)（南、朝巷口）。轉 ψ 後前方 = (sin ψ, -cos ψ)。
# （由 alley_shots.py 以前後燈幾何實測定案；rotation_euler 的 π 是無效殘留值，
#   車件 rotation_mode 全是 QUATERNION，只能走矩陣。）

class Path:
    """由直線／圓弧分段組成的車輛軌跡。每段帶 dir：+1 前進、-1 倒車。

    位移與朝向來自同一條積分，所以車永遠沿著車頭方向走——
    把「平移」和「轉向」寫成兩條獨立插值，車就會斜著螃蟹走，一眼假。
    """

    def __init__(self, x0, y0, psi0=0.0):
        self.x0, self.y0, self.psi0 = x0, y0, psi0
        self.segs = []                    # (length, dpsi, dir)

    def straight(self, length, d=1):
        self.segs.append((abs(length), 0.0, d))
        return self

    def arc(self, radius, dpsi, d=1):
        self.segs.append((abs(radius * dpsi), dpsi, d))
        return self

    @property
    def length(self):
        return sum(s[0] for s in self.segs)

    def pose(self, s):
        """s = 已走的路徑長 → (x, y, psi, 帶號行進距離, 轉向角 delta, 是否倒車)"""
        x, y, psi = self.x0, self.y0, self.psi0
        signed = 0.0
        s = max(0.0, min(s, self.length))
        for (L, dpsi, d) in self.segs:
            u = min(s, L)
            if u > 0:
                if abs(dpsi) < 1e-9:
                    x += d * u * math.sin(psi)
                    y += d * u * -math.cos(psi)
                else:
                    k = dpsi / L
                    p1 = psi + k * u
                    isin = (math.cos(psi) - math.cos(p1)) / k
                    icos = (math.sin(p1) - math.sin(psi)) / k
                    x += d * isin
                    y += d * -icos
                    psi = p1
                signed += d * u
            s -= u
            if s <= 1e-9:
                # 目前這一段的轉向角（bicycle model）
                delta = 0.0
                if abs(dpsi) > 1e-9:
                    delta = math.atan(WHEELBASE * d * dpsi / L)
                return x, y, psi, signed, delta, (d < 0)
        return x, y, psi, signed, 0.0, (self.segs[-1][2] < 0 if self.segs else False)


def smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def s_curve(path, dx, dy, d=+1):
    """變換車道：兩段等半徑反向圓弧，淨轉角為 0（車頭朝向不變）。

    dx > 0 往東，dy > 0 是「沿目前車頭方向前進的距離」（ψ=0 時即往南；倒車時往北）。
    幾何：Δx = 2R(1-cos φ)，Δy = 2R sin φ → tan(φ/2) = |dx| / dy。
    倒車時同樣的 Δψ 會把車帶往相反的橫向，所以符號要翻。
    """
    if dy <= 1e-6:
        raise ValueError(f"s_curve 需要正的縱向行程，得到 {dy}")
    if abs(dx) < 1e-6:
        return path.straight(dy, d=d)
    phi = 2.0 * math.atan2(abs(dx), dy)
    R = abs(dx) / (2.0 * (1.0 - math.cos(phi)))
    if d > 0:
        s = 1.0 if dx > 0 else -1.0
    else:
        s = 1.0 if dx < 0 else -1.0
    path.arc(R, s * phi, d=d)
    path.arc(R, -s * phi, d=d)
    return path


# ── 抓車件
def car_parts(name):
    body = bpy.data.objects[name]
    p = body.matrix_world.translation
    parts = [body]
    for o in bpy.data.objects:
        if o.type == 'MESH' and o.name.startswith('Wheel_'):
            q = o.matrix_world.translation
            if (q.x - p.x) ** 2 + (q.y - p.y) ** 2 <= 1.55 ** 2:
                parts.append(o)
    return parts


def geo_center(o):
    """物件的網格幾何中心（世界座標）。輪件的原點在車心，不能拿原點當樞紐。"""
    c = sum((Vector(v) for v in o.bound_box), Vector()) / 8.0
    return o.matrix_basis @ c


def wheel_radius(o):
    ys = [v.co.y for v in o.data.vertices]
    zs = [v.co.z for v in o.data.vertices]
    return max((max(ys) - min(ys)) * abs(o.scale.y),
               (max(zs) - min(zs)) * abs(o.scale.z)) / 2.0


# 軸距：由前後輪幾何中心實測，不寫死
_ref = car_parts(BODY_FOR_SLOT[0])
_fl = next(o for o in _ref if o.name.startswith('Wheel_FL'))
_rl = next(o for o in _ref if o.name.startswith('Wheel_RL'))
WHEELBASE = (geo_center(_fl) - geo_center(_rl)).length
WHEEL_R = wheel_radius(_fl)
log(f"實測 軸距={WHEELBASE:.3f} 輪半徑={WHEEL_R:.3f}（場景單位；1m ≈ 0.58 單位）")


def move_matrix(px, py, dx, dy, dpsi):
    """繞 (px,py) 轉 dpsi 再平移 (dx,dy)"""
    P = Matrix.Translation(Vector((px, py, 0.0)))
    return (Matrix.Translation(Vector((dx, dy, 0.0))) @ P
            @ Matrix.Rotation(dpsi, 4, 'Z') @ P.inverted())


class Actor:
    """一台會動的車。

    **一台車只能有一個 Actor**：同一批物件若被兩個 Actor 各自寫 keyframe，
    後寫的會蓋掉先寫的，而且兩段之間沒有 key 的區間會被線性內插成鬼飄。
    多次移動請用 add_phase() 串起來——帶號里程也才會累積，
    否則車第二次起步時輪子會先倒轉回零。
    """

    def __init__(self, body_name, label=""):
        self.parts = car_parts(body_name)
        self.body = bpy.data.objects[body_name]
        self.base = {o: o.matrix_basis.copy() for o in self.parts}
        self.wheel_pivot = {o: geo_center(o) for o in self.parts if o.name.startswith('Wheel_')}
        self.wheel_r = {o: wheel_radius(o) for o in self.parts if o.name.startswith('Wheel_')}
        self.label = label
        c = self.body.matrix_world.translation
        self.px, self.py = c.x, c.y          # 靜止基準姿態（base matrix 所在位置）
        self.phases = []                     # (path, f0, f1, signed_offset)
        self.lights = []
        self.hl = self.rv = self.emis = []

    def add_phase(self, path, f0, f1):
        off = 0.0
        if self.phases:
            prev = self.phases[-1]
            off = prev[3] + prev[0].pose(prev[0].length)[3]
            px, py, ppsi = prev[0].pose(prev[0].length)[:3]
            # 下一段必須從上一段的終點接上，否則會瞬移
            assert abs(px - path.x0) < 1e-6 and abs(py - path.y0) < 1e-6 \
                and abs(ppsi - path.psi0) < 1e-6, \
                f"{self.label}: phase 接不上 ({px:.3f},{py:.3f},{ppsi:.3f}) -> " \
                f"({path.x0:.3f},{path.y0:.3f},{path.psi0:.3f})"
            assert f0 >= prev[2], f"{self.label}: phase 時間窗重疊"
        self.phases.append((path, f0, f1, off))
        return self

    @property
    def f0(self):
        return self.phases[0][1]

    @property
    def f1(self):
        return self.phases[-1][2]

    def moving_at(self, f):
        return any(p[1] <= f <= p[2] for p in self.phases)

    def pose_at(self, f):
        """回傳世界絕對姿態。段與段之間保持上一段的終點姿態（車是停著的）。"""
        p0, a0, _, off0 = self.phases[0]
        if f < a0:                        # 注意是 <，不是 <=：f == f0 要落進相位內，
                                          # 否則第一格會回報 reversing=False，倒車段被誤判成反向行駛
            x, y, psi, sg, _, _ = p0.pose(0.0)
            return x, y, psi, off0 + sg, 0.0, False
        done = None
        for ph in self.phases:
            path, a, b, off = ph
            if a <= f <= b:
                s = path.length * smoothstep((f - a) / max(b - a, 1))
                x, y, psi, sg, d, r = path.pose(s)
                return x, y, psi, off + sg, d, r
            if f > b:
                done = ph
        path, _, _, off = done                # 落在兩段之間或片尾 → 停在上一段終點
        x, y, psi, sg, _, _ = path.pose(path.length)
        return x, y, psi, off + sg, 0.0, False

    def bake(self, f):
        x, y, psi, signed, delta, reversing = self.pose_at(f)
        # dx/dy 一律相對「靜止基準位置」算絕對值，不可用某一段路徑的起點——
        # 第二段路徑的起點不等於 base matrix 的位置，會多平移一整段。
        M = move_matrix(self.px, self.py, x - self.px, y - self.py, psi)
        for o in self.parts:
            base = self.base[o]
            if o.name.startswith('Wheel_'):
                piv = self.wheel_pivot[o]
                W = base
                if o.name.startswith(('Wheel_FL', 'Wheel_FR')) and abs(delta) > 1e-6:
                    W = (Matrix.Translation(piv) @ Matrix.Rotation(delta, 4, 'Z')
                         @ Matrix.Translation(-piv) @ W)
                axis = (W.to_3x3() @ Vector((1.0, 0.0, 0.0))).normalized()
                ang = signed / self.wheel_r[o]          # 滾動量用帶號行進距離，不是弦長
                W = (Matrix.Translation(piv) @ Matrix.Rotation(ang, 4, axis)
                     @ Matrix.Translation(-piv) @ W)
                o.matrix_basis = M @ W
            else:
                o.matrix_basis = M @ base
            key_transform(o, f)
        for lo, lbase in self.lights:
            lo.matrix_basis = M @ lbase
            key_transform(lo, f)
        return reversing


def key_transform(o, frame):
    o.keyframe_insert('location', frame=frame)
    if o.rotation_mode == 'QUATERNION':
        o.keyframe_insert('rotation_quaternion', frame=frame)
    elif o.rotation_mode == 'AXIS_ANGLE':
        o.keyframe_insert('rotation_axis_angle', frame=frame)
    else:
        o.keyframe_insert('rotation_euler', frame=frame)


# ════════════════════════════════════════════════════════════ 4. 燈
def stem(name):
    return name.split('.')[0]


def principled(m):
    if not m.node_tree:
        return None
    return next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)


def light_up_lamps(obj, mat_stem, color, strength, tag):
    """只讓這一台的燈殼發光：材質槽改 OBJECT link 再換自己的複本，
    才不會波及共用同一顆材質的其他車。回傳 (emission node, material)。"""
    out = []
    for slot in obj.material_slots:
        if slot.material and stem(slot.material.name) == mat_stem:
            m = slot.material.copy()
            m.name = f"{tag}_{mat_stem}"
            t = m.node_tree
            o = next((n for n in t.nodes if n.type == 'OUTPUT_MATERIAL'), None)
            e = t.nodes.new('ShaderNodeEmission')
            e.inputs['Color'].default_value = (*color, 1)
            e.inputs['Strength'].default_value = strength
            if o:
                t.links.new(e.outputs['Emission'], o.inputs['Surface'])
            slot.link = 'OBJECT'
            slot.material = m
            out.append(e)
    return out


def add_headlights(actor, energy=1500.0, tag="hl"):
    """在車頭裝兩顆 spot。世界前向量 = (sin ψ, -cos ψ)，ψ=0 → (0,-1)。
    早期版本把燈裝到車尾並反向照，鏡頭直視就爆掉。
    visible_camera=False：光源本體不能被拍到，形狀交給燈殼自發光。"""
    made = []
    for sgn, t in ((-1, 'L'), (1, 'R')):
        ld = bpy.data.lights.new(f"{tag}_{t}", 'SPOT')
        ld.energy = energy
        ld.color = (1.0, 0.94, 0.84)
        ld.spot_size = math.radians(58)
        ld.spot_blend = 0.6
        ld.shadow_soft_size = 0.05
        ob = bpy.data.objects.new(f"{tag}_{t}", ld)
        # ψ=0：前方 -Y、右手 +X
        ob.location = (actor.px + sgn * 0.34, actor.py - 1.24, 0.55)
        ob.rotation_euler = (math.radians(93), 0, math.pi + sgn * math.radians(7))
        ob.visible_camera = False
        sc.collection.objects.link(ob)
        made.append(ob)
    actor.lights += [(o, o.matrix_basis.copy()) for o in made]
    return made


def add_reverse_lights(actor, tag="rv"):
    made = []
    for sgn in (-1, 1):
        ld = bpy.data.lights.new(f"{tag}_{sgn}", 'SPOT')
        ld.energy = 0.0
        ld.color = (0.92, 0.95, 1.0)
        ld.spot_size = math.radians(100)
        ld.spot_blend = 0.9
        ld.shadow_soft_size = 0.06
        ob = bpy.data.objects.new(f"{tag}_{sgn}", ld)
        ob.location = (actor.px + sgn * 0.30, actor.py + 1.24, 0.52)
        ob.rotation_euler = (math.radians(87), 0, math.radians(sgn * 6))
        ob.visible_camera = False
        sc.collection.objects.link(ob)
        made.append(ob)
    actor.lights += [(o, o.matrix_basis.copy()) for o in made]
    return made


def key_energy(light_obj, frame, value):
    light_obj.data.energy = value
    light_obj.data.keyframe_insert('energy', frame=frame)


def key_emission(node, frame, value):
    node.inputs['Strength'].default_value = value
    node.inputs['Strength'].keyframe_insert('default_value', frame=frame)


def action_fcurves(action):
    """Blender 4.4+ 改成 slotted action：action.fcurves 已經不存在，
    要走 layers → strips → channelbag。保留舊路徑以防降版執行。"""
    if hasattr(action, 'fcurves'):
        return list(action.fcurves)
    out = []
    for layer in getattr(action, 'layers', []):
        for strip in getattr(layer, 'strips', []):
            for cb in getattr(strip, 'channelbags', []):
                out.extend(cb.fcurves)
    return out


def make_constant(datablocks):
    """頭燈／倒車燈／燈殼自發光要硬切，不能淡入淡出成鬼影。"""
    n = 0
    for db in datablocks:
        ad = getattr(db, 'animation_data', None)
        if ad and ad.action:
            for fc in action_fcurves(ad.action):
                for kp in fc.keyframe_points:
                    kp.interpolation = 'CONSTANT'
                n += 1
    return n


# ════════════════════════════════════════════════════════════ 5. 分鏡與時間軸
F_A0, F_A1 = 1, 48            # 建立
F_B0, F_B1 = 49, 108          # 問題
F_C0 = 109                    # 代價（挪車之舞）

V_FWD = 4.6 / FPS             # 場景單位／格。4.6 u/s ≒ 7.9 m/s，收尾平均約 24 km/h
V_REV = 3.6 / FPS             # 倒車慢一點
POP_STAG = 32
PUSH_STAG = 28


def dur(length, v):
    return max(8, int(round(length / v)))


def frame_at_len(f0, f1, path, target_len):
    """這條路徑走到 target_len 時是第幾格（反解 smoothstep，用二分法避開端點導數為 0）"""
    r = min(max(target_len / path.length, 0.0), 1.0)
    lo, hi = 0.0, 1.0
    for _ in range(50):
        mid = 0.5 * (lo + hi)
        if smoothstep(mid) < r:
            lo = mid
        else:
            hi = mid
    return int(round(f0 + 0.5 * (lo + hi) * (f1 - f0)))


# ── 路徑：pop 是「直線出巷 → 變換車道到暫存位」，push 是同一條路倒著走回去、多推一格
pop_paths, push_paths = {}, {}
for k, plate in enumerate(POP_SEQ):
    slot_i = BODY_FOR_SLOT.index(PLATE_TO_BODY[plate])
    sx = STAGE_X[k]
    p = Path(ALLEY_X, SLOT_Y[slot_i]).straight(SLOT_Y[slot_i] - Y_MOUTH, d=+1)
    s_curve(p, sx - ALLEY_X, Y_MOUTH - STAGE_Y, d=+1)
    pop_paths[plate] = p

for k, plate in enumerate(PUSH_SEQ):
    sx = STAGE_X[POP_SEQ.index(plate)]
    slot_y = SLOT_Y[k]                                  # 歸位後的新槽位（比原位深一格）
    p = Path(ALLEY_X + (sx - ALLEY_X), STAGE_Y)
    s_curve(p, ALLEY_X - sx, Y_MOUTH - STAGE_Y, d=-1)   # 倒車變換車道回巷道中線
    p.straight(slot_y - Y_MOUTH, d=-1)                  # 倒車直線進巷
    push_paths[plate] = p

# ── 時間軸
pop_start, pop_end = [], []
t = F_C0
for k, plate in enumerate(POP_SEQ):
    d = dur(pop_paths[plate].length, V_FWD)
    pop_start.append(t)
    pop_end.append(t + d)
    t += POP_STAG

# 目標車：等最後一台（APH）車尾退出巷口才動
lp = pop_paths[POP_SEQ[-1]]
A_F0 = frame_at_len(pop_start[-1], pop_end[-1], lp, lp.segs[0][0] + 1.6) + 6

target_body = PLATE_TO_BODY[TARGET_PLATE]
A_STRAIGHT = SLOT_Y[0] - Y_MOUTH
A_ARC = 3.4 * math.pi / 2
p_t = (Path(ALLEY_X, SLOT_Y[0])
       .straight(A_STRAIGHT, d=+1)
       .arc(3.4, math.pi / 2, d=+1)                      # 左轉往東，避開西側的暫存列
       .straight(12.0, d=+1))                            # 一路開向出口，不要停在通道正中間
A_F1 = A_F0 + dur(p_t.length, V_FWD)

# 歸位車不必等目標車完全停妥，只要它駛離巷口與迴轉區就可以開始倒車
push_start, push_end = [], []
t = frame_at_len(A_F0, A_F1, p_t, A_STRAIGHT + A_ARC + 4.0) + 6
for k, plate in enumerate(PUSH_SEQ):
    d = dur(push_paths[plate].length, V_REV)
    push_start.append(t)
    push_end.append(t + d)
    t += PUSH_STAG

F_END = max(push_end) + 46
F_D0 = F_END - 70             # 結算鏡頭

log(f"時間軸：建立 {F_A0}-{F_A1} | 問題 {F_B0}-{F_B1} | 代價 {F_C0}-{max(push_end)} | 收尾 {F_D0}-{F_END}")
for k, plate in enumerate(POP_SEQ):
    log(f"  pop  {plate} f{pop_start[k]}-{pop_end[k]}  len={pop_paths[plate].length:6.2f}")
log(f"  出場 {TARGET_PLATE} f{A_F0}-{A_F1}  len={p_t.length:6.2f}")
for k, plate in enumerate(PUSH_SEQ):
    log(f"  push {plate} f{push_start[k]}-{push_end[k]}  len={push_paths[plate].length:6.2f}"
        f"  → 槽位 y={SLOT_Y[k]}")
log(f"總長 {F_END} 格 = {F_END / FPS:.2f} 秒")

sc.frame_start, sc.frame_end = 1, F_END
sc.render.fps = FPS

# ── 建立 Actor：一台車一個，多次移動用 add_phase 串接
ACTORS = []
EVENTS = []
ACTOR_BY_PLATE = {}

for k, plate in enumerate(POP_SEQ):
    a = Actor(PLATE_TO_BODY[plate], label=plate)
    a.add_phase(pop_paths[plate], pop_start[k], pop_end[k])
    ACTORS.append(a)
    ACTOR_BY_PLATE[plate] = a
    EVENTS.append({'op': 'pop', 'plate': plate, 'f0': pop_start[k], 'f1': pop_end[k],
                   'from_slot': BODY_FOR_SLOT.index(PLATE_TO_BODY[plate]),
                   'moves_after': k + 1})

for k, plate in enumerate(PUSH_SEQ):
    ACTOR_BY_PLATE[plate].add_phase(push_paths[plate], push_start[k], push_end[k])
    EVENTS.append({'op': 'push', 'plate': plate, 'f0': push_start[k], 'f1': push_end[k],
                   'to_slot': k, 'moves_after': MOVES})

A_ACTOR = Actor(target_body, label=TARGET_PLATE)
A_ACTOR.add_phase(p_t, A_F0, A_F1)
ACTORS.append(A_ACTOR)
EVENTS.append({'op': 'leave', 'plate': TARGET_PLATE, 'f0': A_F0, 'f1': A_F1, 'moves': MOVES})

# 對照組：平面車位那台直接開走，全程 0 挪車
p_f = (Path(9.6, 3.2)
       .straight(5.2, d=+1)
       .arc(3.4, math.pi / 2, d=+1)
       .straight(5.0, d=+1))
FLAT_F0 = pop_start[1]
FLAT_F1 = FLAT_F0 + dur(p_f.length, V_FWD)
FLAT_ACTOR = Actor(FLAT_BODY, label=FLAT_PLATE)
FLAT_ACTOR.add_phase(p_f, FLAT_F0, FLAT_F1)
ACTORS.append(FLAT_ACTOR)
EVENTS.append({'op': 'flat_leave', 'plate': FLAT_PLATE, 'f0': FLAT_F0, 'f1': FLAT_F1, 'moves': 0})

# 排隊車遞補：倒車出等待格並轉向場內（片尾只演到它動起來，不演完停妥）
p_q = (Path(-9.6, -11.7)
       .straight(3.2, d=-1)
       .arc(4.0, -math.radians(55), d=-1))
Q_F1 = F_END - 4
Q_F0 = Q_F1 - dur(p_q.length, V_REV)
Q_ACTOR = Actor(QUEUE_BODY, label=DEQUEUED['plate'])
Q_ACTOR.add_phase(p_q, Q_F0, Q_F1)
ACTORS.append(Q_ACTOR)
EVENTS.append({'op': 'dequeue', 'plate': DEQUEUED['plate'], 'f0': Q_F0, 'f1': Q_F1})

# ── 燈：移動中的車開頭燈＋燈殼發光；倒車時亮倒車燈
LIGHT_DBS = []
for a in ACTORS:
    tag = a.label.replace(':', '_')
    hl = add_headlights(a, energy=1500.0 if a is not A_ACTOR else 1900.0, tag=f"HL_{tag}")
    rv = add_reverse_lights(a, tag=f"RV_{tag}")
    emis = light_up_lamps(a.body, 'W202_LampF', (1.0, 0.95, 0.87), 0.0, f"E_{tag}")
    a.hl, a.rv, a.emis = hl, rv, emis
    LIGHT_DBS += [o.data for o in hl + rv]
    # 自發光的動畫掛在材質的 node_tree 上，不在燈的 datablock —— 一起收進來才切得掉
    LIGHT_DBS += [e.id_data for e in emis]

log(f"Actor {len(ACTORS)} 台，新增燈光 {len(LIGHT_DBS)} 顆")

# ════════════════════════════════════════════════════════════ 6. 逐格烘焙
# 車件 rotation_mode 是 QUATERNION，而四元數只編碼「朝向」不編碼「圈數」；
# 只下頭尾兩個 keyframe 的話，slerp 會走最短路徑，輪子看起來像在打滑。
# 擋路的四台在「問題」那顆鏡頭裡必須維持暗的：只要它們先亮，觀眾的眼睛就會被
# 巷口那台吸走，而那台不是主角。它們在自己起步的那一格才點燈，正好當成切點的節奏。
ON, OFF = 0, 20                         # 開燈提前 / 熄燈延後（格）
# 目標車必須在「問題」那一顆鏡頭就亮著，否則觀眾不知道我們要取哪一台——
# 但它前面 2.9 單位就是另一台車的車尾，用開闊路面的瓦數會把那片車尾打成一團白霧，
# 所以在巷子裡先用低瓦，等它真的開始動、前方淨空了才升上去。
TARGET_IDLE_F = 34
TARGET_IDLE_E = 520.0
TARGET_IDLE_EMIS = 28.0                 # 燈殼自發光才是「認人」的訊號，要從車陣縫隙透出來

for a in ACTORS:
    is_target = (a.label == TARGET_PLATE)
    warm_on = TARGET_IDLE_F if is_target else max(1, a.f0 - ON)
    warm_off = min(F_END, a.f1 + OFF)
    full = 1900.0 if is_target else 1500.0
    for o in a.hl:
        key_energy(o, 1, 0.0)
        key_energy(o, max(1, warm_on - 1), 0.0)
        if is_target:
            key_energy(o, warm_on, TARGET_IDLE_E)
            key_energy(o, max(1, a.f0 - ON), full)
        else:
            key_energy(o, warm_on, full)
        key_energy(o, warm_off, 0.0)
    for e in a.emis:
        key_emission(e, 1, 0.0)
        key_emission(e, max(1, warm_on - 1), 0.0)
        key_emission(e, warm_on, TARGET_IDLE_EMIS if is_target else 9.0)
        if is_target:
            key_emission(e, max(1, a.f0 - 1), 9.0)
        key_emission(e, warm_off, 0.0)

    # 倒車燈：只在有倒車段的那個 phase 亮
    for o in a.rv:
        key_energy(o, 1, 0.0)
    for (path, pa, pb, _) in a.phases:
        if not any(s[2] < 0 for s in path.segs):
            continue
        for o in a.rv:
            key_energy(o, max(1, pa - 4), 0.0)
            key_energy(o, pa, 140.0)
            key_energy(o, pb, 140.0)
            key_energy(o, min(F_END, pb + 8), 0.0)

log("燈光曲線改常數插值：", make_constant(set(LIGHT_DBS)), "條 F-Curve")

log("烘焙動畫…")
for a in ACTORS:
    # 只烘自己的時間窗（含前後各留一格靜止），其餘影格靠常數外插保持不動
    lo, hi = max(1, a.f0 - 1), min(F_END, a.f1 + 1)
    for f in range(lo, hi + 1):
        a.bake(f)
    a.bake(1)                            # 起始靜止姿態
    a.bake(F_END)                        # 結束靜止姿態
log("烘焙完成")

# ════════════════════════════════════════════════════════════ 7. 夜景分級
# 沿用 alley_shots.py 已驗證過的一組值，三顆鏡頭共用，免得剪在一起打光跳動。
def wet_asphalt(mat):
    nt = mat.node_tree
    b = principled(mat)
    if not b:
        return
    tc = nt.nodes.new('ShaderNodeTexCoord')
    noise = nt.nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = 7.0
    noise.inputs['Detail'].default_value = 5.0
    noise.inputs['Roughness'].default_value = 0.6
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.38
    ramp.color_ramp.elements[1].position = 0.62
    mr = nt.nodes.new('ShaderNodeMapRange')
    mr.inputs['To Min'].default_value = 0.06      # 積水：近鏡面
    mr.inputs['To Max'].default_value = 0.38      # 乾柏油
    nt.links.new(tc.outputs['Generated'], noise.inputs['Vector'])
    nt.links.new(noise.outputs['Fac'], ramp.inputs['Fac'])
    nt.links.new(ramp.outputs['Color'], mr.inputs['Value'])
    nt.links.new(mr.outputs['Result'], b.inputs['Roughness'])
    c = b.inputs['Base Color'].default_value
    b.inputs['Base Color'].default_value = (c[0] * 0.40, c[1] * 0.40, c[2] * 0.46, 1)


for m in bpy.data.materials:
    s, n = stem(m.name), principled(m)
    if not n:
        continue
    if s in ('lot_asphalt', 'lot_asphalt_tex'):
        wet_asphalt(m)
    elif s == 'lot_apron':
        n.inputs['Roughness'].default_value = 0.22
        c = n.inputs['Base Color'].default_value
        n.inputs['Base Color'].default_value = (c[0] * 0.22, c[1] * 0.22, c[2] * 0.28, 1)
    elif s in ('lot_wall', 'lot_coping', 'lot_kerb', 'lot_kerb_tip', 'lot_booth'):
        c = n.inputs['Base Color'].default_value
        n.inputs['Base Color'].default_value = (c[0] * 0.30, c[1] * 0.30, c[2] * 0.35, 1)
        n.inputs['Roughness'].default_value = 0.78
    elif s in ('lot_paint_w', 'lot_stripe_w', 'lot_paint_y', 'lot_stripe_r'):
        n.inputs['Roughness'].default_value = 0.40
    elif s == 'W202_Paint':                       # 車漆：清漆層，夜裡才有那條高光帶
        n.inputs['Roughness'].default_value = 0.18
        n.inputs['Metallic'].default_value = 0.55
        if 'Coat Weight' in n.inputs:
            n.inputs['Coat Weight'].default_value = 1.0
            n.inputs['Coat Roughness'].default_value = 0.03
    elif s == 'W202_LampF':                       # 停著的車＝燈是暗的，只留玻璃反光
        n.inputs['Roughness'].default_value = 0.05

for m in bpy.data.materials:
    if stem(m.name) == 'lot_lamplens' and m.node_tree:
        nt = m.node_tree
        out = next((n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'), None)
        em = nt.nodes.new('ShaderNodeEmission')
        em.inputs['Color'].default_value = (1.0, 0.68, 0.34, 1)
        em.inputs['Strength'].default_value = 45.0
        if out:
            nt.links.new(em.outputs['Emission'], out.inputs['Surface'])

moon = bpy.data.objects.get('moon')
if moon:
    moon.data.energy = 3.2
    moon.data.color = (0.42, 0.56, 0.95)
    moon.data.angle = math.radians(3.0)

w = sc.world
nt = w.node_tree
bg = next((n for n in nt.nodes if n.type == 'BACKGROUND'), None)
if bg:
    bg.inputs['Color'].default_value = (0.010, 0.016, 0.036, 1)
    bg.inputs['Strength'].default_value = 0.30
vs = nt.nodes.new('ShaderNodeVolumeScatter')
vs.inputs['Color'].default_value = (0.58, 0.64, 0.80, 1)
vs.inputs['Density'].default_value = 0.0008   # 廣角遠景會把霧疊厚，太濃整片糊成灰
vs.inputs['Anisotropy'].default_value = 0.62
wout = next((n for n in nt.nodes if n.type == 'OUTPUT_WORLD'), None)
if wout:
    nt.links.new(vs.outputs['Volume'], wout.inputs['Volume'])

# ════════════════════════════════════════════════════════════ 8. 四顆鏡頭
def make_cam(name, lens, focus, fstop, keys):
    """keys = [(frame, cam_loc, aim_loc), ...]"""
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    cd.dof.use_dof = True
    cd.dof.focus_distance = focus
    cd.dof.aperture_fstop = fstop
    co = bpy.data.objects.new(name, cd)
    sc.collection.objects.link(co)
    ai = bpy.data.objects.new(f"{name}_aim", None)
    ai.empty_display_size = 0.4
    sc.collection.objects.link(ai)
    tt = co.constraints.new('TRACK_TO')
    tt.target = ai
    tt.track_axis = 'TRACK_NEGATIVE_Z'
    tt.up_axis = 'UP_Y'
    for (f, cl, al) in keys:
        co.location = cl
        co.keyframe_insert('location', frame=f)
        ai.location = al
        ai.keyframe_insert('location', frame=f)
    return co


# A 建立：高空下降推向巷道。先給整座場的脈絡（右邊那排平面車位＝O(1) 的對照組），
# 收在巷口附近，正好接上第二顆的機位——不要拍成一張沒有主體的空景。
CAM_A = make_cam("SHOT_A", 26.0, 24.0, 6.3, [
    (F_A0, (6.0, -30.0, 18.0), (-6.5, 4.0, 1.0)),
    (F_A1 + 6, (-2.0, -21.0, 7.6), (-8.5, 4.0, 1.0)),
])
# B 問題：85mm 壓縮巷道縱深。亮著的是最裡面那台，前面卡了四台，車頂線錯開才數得出來
CAM_B = make_cam("SHOT_B", 85.0, 15.0, 2.8, [
    (F_B0, (-7.72, -16.90, 1.74), (-8.5, 4.40, 1.06)),
    (F_B1 + 6, (-7.72, -12.40, 1.52), (-8.5, 5.30, 0.96)),
])
# C 代價：主戲。機位放在巷口西南，巷道往畫面深處收，暫存列橫在前景——
# 一顆鏡頭要同時讀到「巷子在變空」和「代價堆在旁邊」。
# 機位放在巷口的東南側，不是西南側：西南側 5 單位外就是 sodium4 的燈桿
# （Blender -14, -14.6），從那裡拍會有一根柱子把畫面從中間劈開。
CAM_C = make_cam("SHOT_C", 30.0, 14.0, 3.6, [
    (F_C0,          (-2.0, -15.5, 3.6), (-8.8,  4.0, 1.0)),   # 開始挪，巷道還是滿的
    (pop_end[-1],   (-1.5, -19.0, 5.2), (-9.5,  0.0, 1.0)),   # 四台都出來，退開露出暫存列
    (A_F1,          (-1.5, -20.0, 5.4), (-8.8, -1.0, 1.0)),   # 目標車往東駛出畫面
    (push_end[-1],  (-2.0, -17.0, 4.4), (-8.6,  4.5, 1.0)),   # 推回巷道，鏡頭跟著回到巷子
])
# E 對照（插入 C 中間的一顆切換鏡頭）：平面車位那台直接開走，全程 0 挪車。
# 這一顆是必要的，不是點綴——HUD 上那張「O(1) / 挪車 0 台」的卡片如果沒有畫面對應，
# 就變成字幕在講一件觀眾看不到的事。C 機位的軸向離平面車位 51°，30mm 根本吃不到。
# 機位避開 pole_6（Blender 19, -14.6）：貼太近會有一根柱子糊在鏡頭前。
F_E0 = FLAT_F0 + 9
F_E1 = F_E0 + 60
CAM_E = make_cam("SHOT_E", 30.0, 17.0, 4.0, [
    (F_E0, (14.0, -14.5, 4.0), (12.5, -1.5, 1.0)),
    (F_E1, (12.6, -15.8, 4.4), (12.0, -2.5, 1.0)),
])
# D 結算：巷道補滿但整排往裡推了一格，巷口那格空著；等待區的車正在倒出來遞補
CAM_D = make_cam("SHOT_D", 40.0, 15.0, 4.0, [
    (F_D0,  (-3.5, -13.0, 3.4), (-8.5, 5.0, 1.0)),
    (F_END, (-5.0, -16.5, 4.6), (-8.5, 6.0, 1.0)),
])

for mk in list(sc.timeline_markers):
    sc.timeline_markers.remove(mk)
for (nm, f, camobj) in (("A", F_A0, CAM_A), ("B", F_B0, CAM_B),
                        ("C", F_C0, CAM_C), ("E", F_E0, CAM_E),
                        ("C2", F_E1 + 1, CAM_C), ("D", F_D0, CAM_D)):
    m = sc.timeline_markers.new(f"shot{nm}", frame=f)
    m.camera = camobj
sc.camera = CAM_A
log(f"分鏡：A 1-{F_A1} | B {F_B0}-{F_B1} | C {F_C0}-{F_E0 - 1} | "
    f"E(對照) {F_E0}-{F_E1} | C {F_E1 + 1}-{F_D0 - 1} | D {F_D0}-{F_END}")

# ════════════════════════════════════════════════════════════ 9. 算圖設定
sc.render.engine = ENGINE
if ENGINE == 'CYCLES':
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'OPTIX'
    prefs.refresh_devices()
    for d in prefs.devices:
        d.use = (d.type == 'OPTIX')
    sc.cycles.device = 'GPU'
    sc.cycles.samples = SAMPLES
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.008
    sc.cycles.use_denoising = True
    sc.cycles.denoiser = 'OPTIX'
    sc.cycles.max_bounces = 10
    sc.cycles.volume_bounces = 2
    sc.cycles.caustics_reflective = False
    sc.cycles.caustics_refractive = False

sc.render.resolution_x, sc.render.resolution_y = RES
sc.render.resolution_percentage = 100
sc.render.image_settings.file_format = 'PNG'
sc.render.use_motion_blur = True
sc.render.motion_blur_shutter = 0.5
sc.view_settings.view_transform = 'AgX'
sc.view_settings.look = 'AgX - Medium High Contrast'
# 廣角鏡裡沒被鈉燈照到的柏油佔掉大半畫面，用 alley_shots.py 那顆特寫的 0.35
# 會整片沉進黑裡。這裡調高，但保留夜色——不是把夜景拉成陰天。
sc.view_settings.exposure = arg("--exposure", 1, 0.62, float)

# 夜景輝光：克制，只有真正的光源該發光
try:
    ng = bpy.data.node_groups.new('NightGlare', 'CompositorNodeTree')
    ng.interface.new_socket('Image', in_out='OUTPUT', socket_type='NodeSocketColor')
    rl = ng.nodes.new('CompositorNodeRLayers')
    rl.location = (-400, 0)
    rl.scene = sc
    gout = ng.nodes.new('NodeGroupOutput')
    gout.location = (600, 0)
    bloom = ng.nodes.new('CompositorNodeGlare')
    bloom.inputs['Type'].default_value = 'Bloom'      # 5.x 吃顯示字串，不是 enum id
    bloom.inputs['Quality'].default_value = 'High'
    bloom.inputs['Threshold'].default_value = 2.2
    bloom.inputs['Size'].default_value = 0.5
    bloom.inputs['Strength'].default_value = 0.25
    streak = ng.nodes.new('CompositorNodeGlare')
    streak.location = (300, 0)
    streak.inputs['Type'].default_value = 'Streaks'
    streak.inputs['Quality'].default_value = 'High'
    streak.inputs['Threshold'].default_value = 4.0
    streak.inputs['Streaks'].default_value = 4
    streak.inputs['Strength'].default_value = 0.05
    streak.inputs['Fade'].default_value = 0.92
    ng.links.new(rl.outputs['Image'], bloom.inputs['Image'])
    ng.links.new(bloom.outputs['Image'], streak.inputs['Image'])
    ng.links.new(streak.outputs['Image'], gout.inputs[0])
    sc.use_nodes = True
    sc.compositing_node_group = ng
    log("GLARE on")
except Exception as e:
    log("GLARE skipped:", type(e).__name__, e)

bpy.context.view_layer.update()

# ════════════════════════════════════════════════════════════ 10. 數值驗證
CHECK_FRAMES = [1, F_A1, F_B1, F_C0 + 20, pop_end[0], F_E0 + 30, pop_end[3],
                A_F0 + 40, A_F1, push_start[0] + 60, push_end[-1], F_END]
GROUND_Z = 0.12
ALLEY_XMIN, ALLEY_XMAX = -10.68, -6.54   # 兩側緣石島內緣


HALF_L, HALF_W = 1.305, 0.55             # 車 2.61 × 1.10


def obb(x, y, psi, hl=HALF_L, hw=HALF_W):
    """車的 2D footprint：回傳 (中心, 長軸單位向量, 短軸單位向量, hl, hw)"""
    fwd = (math.sin(psi), -math.cos(psi))
    rgt = (-fwd[1], fwd[0])
    return ((x, y), fwd, rgt, hl, hw)


def obb_overlap(A, B):
    """SAT：四條分離軸都重疊才算相撞。回傳最小重疊量（<=0 代表分離）。"""
    (ca, fa, ra, hla, hwa) = A
    (cb, fb, rb, hlb, hwb) = B
    d = (cb[0] - ca[0], cb[1] - ca[1])
    best = 1e9
    for ax in (fa, ra, fb, rb):
        proj = abs(d[0] * ax[0] + d[1] * ax[1])
        ea = hla * abs(fa[0] * ax[0] + fa[1] * ax[1]) + hwa * abs(ra[0] * ax[0] + ra[1] * ax[1])
        eb = hlb * abs(fb[0] * ax[0] + fb[1] * ax[1]) + hwb * abs(rb[0] * ax[0] + rb[1] * ax[1])
        gap = proj - (ea + eb)
        if gap > 0:
            return 0.0                    # 找到分離軸 → 沒撞
        best = min(best, -gap)
    return best


def static_obstacles():
    """場內會擋車的實體（扁平的標線／人孔／排水柵不算）。回傳世界 XY 矩形。"""
    hard_pref = ('island_', 'isl_', 'wall_', 'booth_', 'pole_', 'poleft_', 'bollard_',
                 'bollcap_', 'cone_', 'gate_', 'psign_', 'pylon_', 'pil_', 'lens_',
                 'head_', 'arm_')
    soft_pref = ('kerb_', 'ws_', 'stripe_', 'tip_')     # 低矮：壓到只算警告
    out = []
    for o in bpy.data.objects:
        if o.type != 'MESH':
            continue
        n = o.name
        hard = n.startswith(hard_pref)
        soft = n.startswith(soft_pref)
        if not (hard or soft):
            continue
        pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
        zmax = max(p.z for p in pts)
        if zmax < 0.16:                   # 幾乎貼地，車開過去也沒事
            continue
        xs = [p.x for p in pts]
        ys = [p.y for p in pts]
        out.append((n, min(xs), min(ys), max(xs), max(ys), hard))
    return out


def rect_obb_overlap(rect, A):
    x0, y0, x1, y1 = rect
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    B = ((cx, cy), (1.0, 0.0), (0.0, 1.0), (x1 - x0) / 2, (y1 - y0) / 2)
    return obb_overlap(A, B)


def verify():
    log("── 數值驗證 " + "─" * 52)
    ok = True

    # ① 解析式掃描：每 2 格檢查一次車車相撞、車撞固定物、車頭 vs 位移
    obstacles = static_obstacles()
    log(f"  固定障礙物 {len(obstacles)} 件納入檢查")
    hits, statics, dirbad = [], [], []
    for f in range(1, F_END + 1, 2):
        poses = []
        for a in ACTORS:
            x, y, psi, _, _, rev = a.pose_at(f)
            poses.append((a.label, obb(x, y, psi), a.moving_at(f)))
            if a.moving_at(f):
                x0, y0, p0, _, _, _ = a.pose_at(f - 1)
                x1, y1, p1, _, _, _ = a.pose_at(f + 1)
                dx, dy = x1 - x0, y1 - y0
                if math.hypot(dx, dy) > 1e-4:
                    fwd = Vector((math.sin(psi), -math.cos(psi)))
                    mv = Vector((dx, dy)).normalized()
                    dot = fwd.dot(mv) * (-1 if rev else 1)
                    if dot < 0.985:
                        dirbad.append((f, a.label, round(dot, 4), rev))
        for i in range(len(poses)):
            for j in range(i + 1, len(poses)):
                if not (poses[i][2] or poses[j][2]):
                    continue              # 兩台都停著＝原本就這樣停的，不算
                ov = obb_overlap(poses[i][1], poses[j][1])
                if ov > 0.02:
                    hits.append((f, poses[i][0], poses[j][0], round(ov, 3)))
        for (lbl, A, moving) in poses:
            if not moving:
                continue
            for (n, x0, y0, x1, y1, hard) in obstacles:
                ov = rect_obb_overlap((x0, y0, x1, y1), A)
                if ov > (0.02 if hard else 0.12):
                    statics.append((f, lbl, n, round(ov, 3), 'HARD' if hard else 'soft'))

    def brief(rows, n=6):
        seen, out = set(), []
        for r in rows:
            k = tuple(r[1:3])
            if k in seen:
                continue
            seen.add(k)
            out.append(r)
            if len(out) >= n:
                break
        return out

    if hits:
        ok = False
        log(f"  ✗ 車輛互撞 {len(hits)} 筆（去重後示例）：{brief(hits)}")
    else:
        log("  ✓ 全程無車輛互撞")
    if statics:
        ok = False
        log(f"  ✗ 撞到固定物 {len(statics)} 筆（去重後示例）：{brief(statics)}")
    else:
        log("  ✓ 全程無車輛撞到緣石島／牆／燈桿／車阻")
    if dirbad:
        ok = False
        log(f"  ✗ 車頭方向與位移不一致 {len(dirbad)} 筆：{brief(dirbad)}")
    else:
        log("  ✓ 車頭方向全程等於行進切線（含倒車），dot ≥ 0.985")

    # ② 巷道橫向邊界：只有真的在巷子裡的車才受兩側緣石島約束
    #    （平面車位那台 x=9.6 不在巷道，拿去比會得到 -16.69 這種假警報）
    alley_actors = [a for a in ACTORS if a.label in ALLEY_PLATES]
    worst_x, worst_x_at = -1e9, None
    for f in range(1, F_END + 1, 2):
        for a in alley_actors:
            x, y, psi, _, _, _ = a.pose_at(f)
            if not (-1.0 < y < 14.0):
                continue
            half = HALF_L * abs(math.sin(psi)) + HALF_W * abs(math.cos(psi))
            v = max((ALLEY_XMIN + half) - x, x - (ALLEY_XMAX - half))
            if v > worst_x:
                worst_x, worst_x_at = v, (f, a.label, round(x, 3))
    log(f"  巷道側向：最差侵入 {worst_x:+.3f}（負值＝還有餘裕）@ {worst_x_at}"
        f" {'✓' if worst_x <= 0 else '✗ 壓到緣石島'}")
    ok = ok and worst_x <= 0

    # ③ 場景實測：四輪貼地。
    #    不能拿輪子 mesh 的 bound_box 角點當最低點——輪胎是圓的，
    #    自轉時角點會掃到半對角線 0.26（> 半徑 0.184），量出來永遠像是陷進地面。
    worst_gap, worst_gap_at = 0.0, None
    for f in CHECK_FRAMES:
        sc.frame_set(f)
        bpy.context.view_layer.update()
        for a in ACTORS:
            for o in a.parts:
                if not o.name.startswith('Wheel_'):
                    continue
                cw = sum((o.matrix_world @ Vector(v) for v in o.bound_box), Vector()) / 8.0
                gap = (cw.z - a.wheel_r[o]) - GROUND_Z
                if abs(gap) > abs(worst_gap):
                    worst_gap, worst_gap_at = gap, (f, a.label, o.name)
    log(f"  四輪貼地誤差最大 {worst_gap:+.5f}（門檻 ±0.01）@ {worst_gap_at}"
        f" {'✓' if abs(worst_gap) <= 0.01 else '✗'}")
    ok = ok and abs(worst_gap) <= 0.01

    # ④ 終局狀態：必須等於引擎算出來的堆疊
    sc.frame_set(F_END)
    bpy.context.view_layer.update()
    log("  終局槽位（引擎說堆疊底→頂應為 " + " ".join(PUSH_SEQ) + "）：")
    for k, plate in enumerate(PUSH_SEQ):
        c = bpy.data.objects[PLATE_TO_BODY[plate]].matrix_world.translation
        err = c.y - SLOT_Y[k]
        ok = ok and abs(err) <= 0.02
        log(f"    {plate}  y={c.y:7.3f}  應為 {SLOT_Y[k]:6.2f}  誤差 {err:+.4f} "
            f"{'✓' if abs(err) <= 0.02 else '✗'}   x={c.x:7.3f}")
    c = bpy.data.objects[target_body].matrix_world.translation
    log(f"    {TARGET_PLATE}（已離場）落點 ({c.x:.2f}, {c.y:.2f})")
    log(f"  巷口 y={SLOT_Y[4]} 應空著（等待區的 {DEQUEUED['plate']} 已被 dequeue，尚未停妥）")
    log(f"  ── 總結：{'全部通過 ✓' if ok else '有未通過項目 ✗'} " + "─" * 30)
    return ok


VERIFY_OK = verify()

# ════════════════════════════════════════════════════════════ 11. 輸出
os.makedirs(OUT_DIR, exist_ok=True)
if DO_EVENTS:
    payload = {
        'fps': FPS, 'frames': F_END, 'res': RES,
        'target': TARGET_PLATE, 'moves': MOVES,
        'alley_plates': ALLEY_PLATES, 'queue_plates': QUEUE_PLATES,
        'flat_plate': FLAT_PLATE, 'dequeued': DEQUEUED['plate'],
        'pop_seq': POP_SEQ, 'push_seq': PUSH_SEQ,
        'final_stack': [c['plate'] for c in normal.stack],
        'shots': {'A': [F_A0, F_A1], 'B': [F_B0, F_B1],
                  'C': [F_C0, push_end[-1]], 'E': [F_E0, F_E1],
                  'D': [F_D0, F_END]},
        'events': EVENTS, 'ops': OPS,
    }
    ep = os.path.join(OUT_DIR, "events.json")
    with open(ep, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    log("events →", ep)

if DO_SAVE:
    bp = os.path.join(OUT_DIR, "parking_lot_dance.blend")
    bpy.ops.wm.save_as_mainfile(filepath=bp)
    log("blend →", bp)

if ONEFRAME is not None:
    sc.frame_set(ONEFRAME)
    sc.render.filepath = os.path.join(OUT_DIR, "renders", f"test_{ONEFRAME:04d}.png")
    bpy.ops.render.render(write_still=True)
    log("test frame →", sc.render.filepath)
elif DO_KEYS:
    d = os.path.join(OUT_DIR, "renders", "keys")
    os.makedirs(d, exist_ok=True)
    for f in CHECK_FRAMES:
        sc.frame_set(f)
        sc.render.filepath = os.path.join(d, f"key_{f:04d}.png")
        log(f"key frame {f} …")
        bpy.ops.render.render(write_still=True)
    log("key frames →", d)
elif DO_ANIM:
    if FRANGE:
        sc.frame_start, sc.frame_end = FRANGE
    d = os.path.join(OUT_DIR, "renders", arg("--seq", 1, "seq"))
    os.makedirs(d, exist_ok=True)
    sc.render.filepath = os.path.join(d, "frame_")
    log(f"RENDER ANIM {sc.frame_start}-{sc.frame_end} @ {RES[0]}x{RES[1]} / {SAMPLES}spp")
    bpy.ops.render.render(animation=True)

log("DONE")
