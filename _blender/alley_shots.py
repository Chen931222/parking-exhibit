"""夜間巷道渲染腳本 — 〈挪車的代價〉

三顆鏡頭（片子順序：建立 → 問題 → 代價）：
  3 對照 — 24mm 廣角推近，左巷道 LIFO vs 右平面車位 O(1)
  1 巷底 — 85mm 壓縮推進，最裡面那台亮著燈，前面卡了四台
  2 代價 — 35mm 低角，最前面那台實際挪出來（唯一有動作的一顆）

定裝（單張）:
  G:\\blender.exe -b _blender\\parking-exhibit.blend -P _blender\\alley_shots.py --factory-startup -- \
      --shot 2 --samples 400 --res 1600 900 --out out.png

動畫（全域連號，方便直接串成一支）:
  ... -- --shot 3 --anim --frames 1   96  --res 1280 720 --samples 256 --out D:\\seq\\sq_
  ... -- --shot 1 --anim --frames 97  192 --res 1280 720 --samples 256 --out D:\\seq\\sq_
  ... -- --shot 2 --anim --frames 193 288 --res 1280 720 --samples 256 --out D:\\seq\\sq_
"""
import bpy
import math
import sys
from mathutils import Matrix, Vector

# ---------------------------------------------------------------- args
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(flag, n=1, default=None, cast=str):
    if flag not in argv:
        return default
    i = argv.index(flag)
    vals = [cast(v) for v in argv[i + 1:i + 1 + n]]
    return vals[0] if n == 1 else vals


SHOT = arg("--shot", 1, 1, int)
SAMPLES = arg("--samples", 1, 400, int)
OUT = arg("--out", 1, r"G:\shot.png")
ANIM = "--anim" in argv
# 直式版（手機）：9:16。不是把橫式裁一刀就好——水平視角會被砍掉一半以上，
# 三顆鏡頭都要另外設機位與焦段，見各 shot 分支的 PORTRAIT 分歧。
PORTRAIT = "--portrait" in argv
RES = arg("--res", 2, [720, 1280] if PORTRAIT else [1600, 900], int)
LENS = arg("--lens", 1, None, float)
SKY = arg("--sky", 1, None, float)          # world background 強度覆寫
MOONE = arg("--moon", 1, None, float)       # 月光 SUN 瓦數覆寫
# 巷底那台的頭燈瓦數：它照的是 2.9m 外的前車車尾，不是 20m 外的路面，
# 用「照得遠」的瓦數會把車尾打爆成一團白霧
HL_DEEP = arg("--hl-energy", 1, 220.0, float)
FR = arg("--frames", 2, [1, 96], int)
F0, F1 = FR

sc = bpy.context.scene

# ---------------------------------------------------------------- engine
sc.render.engine = 'CYCLES'
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
sc.cycles.volume_step_rate = 2.0
sc.cycles.volume_max_steps = 512

sc.render.resolution_x, sc.render.resolution_y = RES
sc.render.resolution_percentage = 100
sc.render.filepath = OUT
sc.render.image_settings.file_format = 'PNG'
sc.view_settings.view_transform = 'AgX'
sc.view_settings.look = 'AgX - Medium High Contrast'
sc.view_settings.exposure = 0.35

if ANIM:
    sc.render.use_motion_blur = True
    sc.render.motion_blur_shutter = 0.5
    sc.render.fps = 24
    sc.frame_start, sc.frame_end = F0, F1


def stem(name):
    return name.split('.')[0]


def principled(m):
    return next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None) if m.node_tree else None


# ---------------------------------------------------------------- 濕地面 + 積水遮罩
def wet_asphalt(mat):
    """noise -> ramp -> map range -> Roughness，做出乾濕不均的柏油"""
    nt = mat.node_tree
    bsdf = principled(mat)
    if not bsdf:
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
    mr.inputs['To Min'].default_value = 0.06   # 積水：近鏡面
    mr.inputs['To Max'].default_value = 0.38   # 乾柏油
    nt.links.new(tc.outputs['Generated'], noise.inputs['Vector'])
    nt.links.new(noise.outputs['Fac'], ramp.inputs['Fac'])
    nt.links.new(ramp.outputs['Color'], mr.inputs['Value'])
    nt.links.new(mr.outputs['Result'], bsdf.inputs['Roughness'])
    c = bsdf.inputs['Base Color'].default_value
    bsdf.inputs['Base Color'].default_value = (c[0] * 0.40, c[1] * 0.40, c[2] * 0.46, 1)


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
    elif s == 'W202_Paint':          # 車漆：清漆層，夜裡才有那條高光帶
        n.inputs['Roughness'].default_value = 0.18
        n.inputs['Metallic'].default_value = 0.55
        if 'Coat Weight' in n.inputs:
            n.inputs['Coat Weight'].default_value = 1.0
            n.inputs['Coat Roughness'].default_value = 0.03
    elif s == 'W202_LampF':          # 停著的車＝燈是暗的，只留玻璃反光
        n.inputs['Roughness'].default_value = 0.05

# ---------------------------------------------------------------- 鈉燈發光
for m in bpy.data.materials:
    if stem(m.name) == 'lot_lamplens' and m.node_tree:
        nt = m.node_tree
        out = next((n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'), None)
        em = nt.nodes.new('ShaderNodeEmission')
        em.inputs['Color'].default_value = (1.0, 0.68, 0.34, 1)
        em.inputs['Strength'].default_value = 45.0
        if out:
            nt.links.new(em.outputs['Emission'], out.inputs['Surface'])

# ---------------------------------------------------------------- 冷暖對比
moon = bpy.data.objects.get('moon')
if moon:
    # 3.2 而非原本的 2.1：深色車漆在夜裡只能靠反射成形，天空與月光是唯二
    # 打得到車頂／側面的「場景裡真實存在的光源」。三顆共用同一組值，
    # 免得剪在一起時出現打光跳動。
    moon.data.energy = MOONE if MOONE is not None else 3.2
    moon.data.color = (0.42, 0.56, 0.95)
    moon.data.angle = math.radians(3.0)

w = sc.world
nt = w.node_tree
bg = next((n for n in nt.nodes if n.type == 'BACKGROUND'), None)
if bg:
    bg.inputs['Color'].default_value = (0.010, 0.016, 0.036, 1)
    bg.inputs['Strength'].default_value = SKY if SKY is not None else 0.30
vs = nt.nodes.new('ShaderNodeVolumeScatter')
vs.inputs['Color'].default_value = (0.58, 0.64, 0.80, 1)
vs.inputs['Density'].default_value = 0.0013
vs.inputs['Anisotropy'].default_value = 0.62
wout = next((n for n in nt.nodes if n.type == 'OUTPUT_WORLD'), None)
if wout:
    nt.links.new(vs.outputs['Volume'], wout.inputs['Volume'])


# ---------------------------------------------------------------- 車輛工具
# 輪子自轉方向：由 check_wheel.py 用「輪頂位移應為車身兩倍」實測定為 +1
# （實測 +1 → 1.855、-1 → 0.660，以 1.0＝不轉為軸對稱）
SPIN_SIGN = arg("--spin-sign", 1, 1.0, float)

# Shot 2 機位（可從命令列覆寫，方便掃機位）
CAM0 = arg("--cam0", 3, [-1.60, -8.20, 0.95], float)
AIM0 = arg("--aim0", 3, [-8.20, -0.20, 0.88], float)
CAM1 = arg("--cam1", 3, [-2.30, -7.60, 0.90], float)
AIM1 = arg("--aim1", 3, [-8.60, -1.60, 0.86], float)


def car_parts(x, y, radius=1.55):
    """靠座標抓一台車的零件（Body + 四顆輪），不依賴命名編號對應"""
    out = []
    for o in bpy.data.objects:
        if o.type != 'MESH':
            continue
        if not (o.name.startswith('Body.') or o.name.startswith('Wheel_')):
            continue
        p = o.matrix_world.translation
        if (p.x - x) ** 2 + (p.y - y) ** 2 <= radius ** 2:
            out.append(o)
    return out


def move_matrix(piv, dx, dy, dz_rot):
    """繞 piv 轉 dz_rot 再平移 (dx,dy) 的世界矩陣"""
    P = Matrix.Translation(Vector((piv[0], piv[1], 0.0)))
    R = Matrix.Rotation(dz_rot, 4, 'Z')
    T = Matrix.Translation(Vector((dx, dy, 0.0)))
    return T @ P @ R @ P.inverted()


# 挪車路徑：圓弧，不是直線。
# 車是非完整約束系統——只能沿著車頭方向走。把「位移」和「轉向」寫成兩條
# 獨立插值（沿固定直線平移 + 原地轉），車就會斜著螃蟹走，一眼假。
# 車頭是局部 -Y、世界旋轉是單位四元數（由前後燈幾何實測；rotation_euler 的 π
# 是無效殘留值），所以世界前方 = (0,-1)。轉 th（逆時針為正）後前方 = (sinθ, -cosθ)，
# 沿曲率積分得：dx = Rs(1-cos th)， dy = -Rs·sin th， Rs = 弧長/轉角（帶正負號）。
# 用帶號半徑才能同時支援左轉（+，往 +X）與右轉（-，往 -X）。
ARC_LEN = 3.40                     # 行進弧長 (m)。比車身(2.6m)長，讀得出「讓開了」，
                                   # 但不會跑到畫面外緣讓構圖散掉
ARC_TURN = math.radians(-40)       # 右轉出巷、沿橫向通道往西，光束才會掃離機位


def arc_pose(s):
    """s∈[0,1] → (dx, dy, dtheta, 已走弧長)，車頭永遠是路徑切線"""
    th = ARC_TURN * s
    Rs = ARC_LEN / ARC_TURN
    return Rs * (1.0 - math.cos(th)), -Rs * math.sin(th), th, ARC_LEN * s


def apply_xf(o, M):
    """用 matrix_basis 疊加變換。

    這些車件的 rotation_mode 是 QUATERNION，直接寫 rotation_euler 完全無效
    ——車身不會轉、只有位置被繞著樞紐搬走，輪子就飛出輪拱。
    走矩陣才不必管物件用的是 euler 還是 quaternion。
    （全部無父物件、無約束，所以 matrix_basis 等於 matrix_world，
      而且不需要等 depsgraph 更新就能讀。）
    """
    o.matrix_basis = M @ o.matrix_basis


def wheel_radius(o):
    """從 mesh 邊界算實際輪半徑。停放車輛是 0.579 倍的縮小複本，
    輪徑 0.368 而不是主角車的 0.63，寫死常數會讓滾動量差一倍以上。"""
    ys = [v.co.y for v in o.data.vertices]
    zs = [v.co.z for v in o.data.vertices]
    return max((max(ys) - min(ys)) * abs(o.scale.y),
               (max(zs) - min(zs)) * abs(o.scale.z)) / 2.0


def spin_wheel(o, angle):
    """繞輪子自己的軸（本地 X＝最薄那軸＝輪軸）自轉。

    樞紐必須用輪子的幾何中心，不能用物件原點——這些輪件的原點在車心，
    繞原點轉會變成「繞車公轉」而不是自轉（就是 59f3d9c 在網頁版修過的那個坑）。
    """
    mb = o.matrix_basis
    axis = (mb.to_3x3() @ Vector((1.0, 0.0, 0.0))).normalized()
    local_c = sum((Vector(c) for c in o.bound_box), Vector()) / 8.0
    piv = mb @ local_c
    R = Matrix.Rotation(angle, 4, axis)
    o.matrix_basis = Matrix.Translation(piv) @ R @ Matrix.Translation(-piv) @ mb


def key_transform(o, frame):
    o.keyframe_insert('location', frame=frame)
    if o.rotation_mode == 'QUATERNION':
        o.keyframe_insert('rotation_quaternion', frame=frame)
    elif o.rotation_mode == 'AXIS_ANGLE':
        o.keyframe_insert('rotation_axis_angle', frame=frame)
    else:
        o.keyframe_insert('rotation_euler', frame=frame)


def light_up_lamps(obj):
    """只讓這一台的頭燈燈殼發光：材質槽改成 OBJECT link 再換自己的複本，
    才不會波及共用同一顆 W202_LampF 的其他車"""
    for slot in obj.material_slots:
        if slot.material and stem(slot.material.name) == 'W202_LampF':
            m = slot.material.copy()
            m.name = "HERO_LampF"
            t = m.node_tree
            o = next((n for n in t.nodes if n.type == 'OUTPUT_MATERIAL'), None)
            e = t.nodes.new('ShaderNodeEmission')
            e.inputs['Color'].default_value = (1.0, 0.95, 0.87, 1)
            e.inputs['Strength'].default_value = 9.0
            if o:
                t.links.new(e.outputs['Emission'], o.inputs['Surface'])
            slot.link = 'OBJECT'
            slot.material = m


def headlights(x, y, heading=math.pi, energy=1600.0, toe=0.0, name="hl"):
    """在 (x,y) 車頭裝兩顆 spot。

    車身本地前方是 +Y，所以世界前向量 = R(θ)·(0,1) = (-sinθ, cosθ)。
    早期版本寫成 (sinθ, -cosθ)，燈會裝到車尾並反向照 → 直射鏡頭爆掉。
    toe：兩盞燈各自向外撇開的角度，避免光軸正對鏡頭。
    """
    fx, fy = -math.sin(heading), math.cos(heading)
    objs = []
    for sgn, tag in ((-1, 'L'), (1, 'R')):
        ld = bpy.data.lights.new(f"{name}_{tag}", 'SPOT')
        ld.energy = energy
        ld.color = (1.0, 0.94, 0.84)
        ld.spot_size = math.radians(56)
        ld.spot_blend = 0.6
        ld.shadow_soft_size = 0.05
        ob = bpy.data.objects.new(f"{name}_{tag}", ld)
        ob.location = (x + fx * 1.28 - fy * sgn * 0.60,
                       y + fy * 1.28 + fx * sgn * 0.60,
                       0.62)
        ob.rotation_euler = (math.radians(92), 0, heading + sgn * toe)
        # 關掉相機可見性：否則鏡頭直視時會拍到光源本體那顆死白光球，
        # 整片糊成一塊。形狀交給燈殼自發光（light_up_lamps）去給。
        ob.visible_camera = False
        sc.collection.objects.link(ob)
        objs.append(ob)
    return objs


def hero_body(x, y):
    return next((o for o in car_parts(x, y) if o.name.startswith('Body.')), None)


def key_cam(cam, aim, f, cloc, aloc):
    cam.location = cloc
    cam.keyframe_insert('location', frame=f)
    aim.location = aloc
    aim.keyframe_insert('location', frame=f)


def pick(land, port):
    """依橫式／直式選一組值；CLI 的 --cam0 等覆寫優先"""
    return port if PORTRAIT else land


def set_cam(lens, land0, landa0, land1, landa1, port0, porta0, port1, porta1,
            focus, fstop, port_lens=None):
    cam.data.lens = LENS if LENS is not None else pick(lens, port_lens or lens)
    # 直式時 sensor 貼合垂直邊，水平視角只剩約一半，所以機位要重設而不是裁切
    cam.data.sensor_fit = 'VERTICAL' if PORTRAIT else 'AUTO'
    cam.data.dof.focus_distance = focus
    cam.data.dof.aperture_fstop = fstop
    c0 = arg("--cam0", 3, list(pick(land0, port0)), float)
    a0 = arg("--aim0", 3, list(pick(landa0, porta0)), float)
    c1 = arg("--cam1", 3, list(pick(land1, port1)), float)
    a1 = arg("--aim1", 3, list(pick(landa1, porta1)), float)
    if ANIM:
        key_cam(cam, aim, F0, c0, a0)
        key_cam(cam, aim, F1, c1, a1)
    else:
        cam.location = [(c0[i] + c1[i]) / 2 for i in range(3)]
        aim.location = [(a0[i] + a1[i]) / 2 for i in range(3)]


# ---------------------------------------------------------------- 鏡頭
cam = bpy.data.objects['cam']
aim = bpy.data.objects['aim']
cam.constraints.clear()
cam.data.dof.use_dof = True

if SHOT == 1:
    # 巷底：開燈的是「最裡面那台」(y=12.6)。前面四台擋住，只從輪廓邊緣暈出來。
    # toe 6° 把兩盞燈往外撇，先前正對鏡頭那塊過曝白斑就是這樣來的。
    deep = hero_body(-8.5, 12.6)
    if deep:
        light_up_lamps(deep)
    headlights(-8.5, 12.6, energy=HL_DEEP, toe=math.radians(8))
    # 稍微離軸 + 抬到 1.6m：車頂線錯開才數得出「前面卡了四台」，
    # 壓在正中線 (x=-8.5, z=0.94) 會疊成單一輪廓，主題就消失了。
    # 直式：車道往上收的縱深剛好吃滿長邊，焦段放寬避免只剩一台車的寬度。
    set_cam(85.0,
            (-7.72, -16.90, 1.74), (-8.5, 4.40, 1.06),
            (-7.72, -11.60, 1.50), (-8.5, 5.30, 0.96),
            (-7.55, -15.20, 1.66), (-8.5, 4.40, 0.96),
            (-7.55, -10.80, 1.46), (-8.5, 5.30, 0.86),
            focus=15.0, fstop=2.8, port_lens=52.0)

elif SHOT == 2:
    # 代價：最前面那台實際挪出來，這是唯一有動作的一顆
    parts = car_parts(-8.5, 1.0)
    body = next((o for o in parts if o.name.startswith('Body.')), None)
    if body:
        light_up_lamps(body)
    PIV = (-8.5, 1.0)
    # 頭燈先建在原位，再跟車一起套同一個矩陣
    hl = headlights(PIV[0], PIV[1], heading=math.pi, energy=2200.0)
    movers = parts + hl

    if ANIM:
        # 逐格烘焙，不能只下頭尾兩個 keyframe：
        # 車件的 rotation_mode 是 QUATERNION，而四元數只編碼「朝向」不編碼「圈數」。
        # 整段輪子要轉三圈多，slerp 只會走最短路徑 → 只轉不到一圈，看起來像在打滑。
        base = {o: o.matrix_basis.copy() for o in movers}
        span = max(F1 - F0, 1)
        for f in range(F0, F1 + 1):
            t = (f - F0) / span
            s = t * t * (3.0 - 2.0 * t)          # smoothstep：起步與收尾自然
            dx, dy, dth, arc_len = arc_pose(s)   # 滾動量要用弧長，不是弦長
            Mf = move_matrix(PIV, dx, dy, dth)
            for o in movers:
                o.matrix_basis = Mf @ base[o]
                if o.name.startswith('Wheel_'):
                    spin_wheel(o, SPIN_SIGN * arc_len / wheel_radius(o))
                key_transform(o, f)
    else:
        dx, dy, dth, _ = arc_pose(1.0)
        M = move_matrix(PIV, dx, dy, dth)
        for o in movers:
            apply_xf(o, M)

    # 攝影機幾乎不動：動作由車本身提供。
    # 先前鏡頭走了 3.7m、注視點又移了 2.7m，背景視差被放大成「路燈在跑」。
    # 橫式機位在東南側，車往西轉出巷，光束掃離鏡頭而不是轟進來。
    # 直式：橫向移動在 9:16 最吃虧，所以機位壓低靠近、車道往畫面上方收，
    # 車的位移就變成「朝鏡頭斜切過來」而不是左右平移。
    set_cam(35.0,
            (-1.60, -8.20, 0.95), (-8.20, -0.20, 0.88),
            (-2.30, -7.60, 0.90), (-8.60, -1.60, 0.86),
            (-4.30, -10.90, 1.32), (-8.90, 1.10, 0.96),
            (-4.65, -10.55, 1.26), (-9.25, 0.30, 0.92),
            focus=8.2, fstop=2.2, port_lens=24.0)

else:
    # 對照：左邊巷道 LIFO，右邊平面車位 O(1)，鈉燈頭進畫
    deep = hero_body(-8.5, 12.6)
    if deep:
        light_up_lamps(deep)
    headlights(-8.5, 12.6, energy=HL_DEEP, toe=math.radians(8))
    # 起幀壓低、拉近一點，免得最近那盞鈉燈卡在左上角爆掉。
    # 直式：改成貼近地面的縱深構圖，前景車位線往上收，遠方燈桿當垂直節奏。
    set_cam(24.0,
            (12.90, -15.70, 5.25), (-4.50, 4.60, 1.62),
            (10.20, -11.90, 4.35), (-4.50, 4.60, 1.50),
            (8.80, -13.60, 4.00), (-3.00, 2.60, 0.95),
            (6.90, -10.60, 3.40), (-3.00, 2.60, 0.88),
            focus=21.0, fstop=5.6, port_lens=26.0)

tt = cam.constraints.new('TRACK_TO')
tt.target = aim
tt.track_axis = 'TRACK_NEGATIVE_Z'
tt.up_axis = 'UP_Y'
sc.camera = cam

# ---------------------------------------------------------------- 合成器輝光
# 5.2 必須把 Render Layers 放進群組內；用 Group Input 會渲出全黑（A/B 實測 0.0003 vs 0.2834）
try:
    ng = bpy.data.node_groups.new('NightGlare', 'CompositorNodeTree')
    ng.interface.new_socket('Image', in_out='OUTPUT', socket_type='NodeSocketColor')
    rl = ng.nodes.new('CompositorNodeRLayers')
    rl.location = (-400, 0)
    rl.scene = sc
    gout = ng.nodes.new('NodeGroupOutput')
    gout.location = (600, 0)

    bloom = ng.nodes.new('CompositorNodeGlare')
    bloom.location = (0, 0)
    bloom.inputs['Type'].default_value = 'Bloom'        # 5.x 吃顯示字串，不是 enum id
    bloom.inputs['Quality'].default_value = 'High'
    # 克制：只有真正的光源該發光，不要每個輪圈鍍鉻都在爆星
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
    print("GLARE: on")
except Exception as e:
    print("GLARE SKIPPED:", type(e).__name__, e)

bpy.context.view_layer.update()

TESTFRAME = arg("--testframe", 1, None, int)
if TESTFRAME is not None:
    # 只渲動畫區間裡的某一格（拿來驗手感／量時間，不用跑整批）
    sc.frame_set(TESTFRAME)
    print(f"RENDER TESTFRAME {TESTFRAME} shot={SHOT} @ {RES[0]}x{RES[1]} / {SAMPLES}spp -> {OUT}")
    bpy.ops.render.render(write_still=True)
elif ANIM:
    print(f"RENDER ANIM shot={SHOT} frames {F0}-{F1} @ {RES[0]}x{RES[1]} / {SAMPLES}spp -> {OUT}")
    bpy.ops.render.render(animation=True)
else:
    print(f"RENDER STILL shot={SHOT} @ {RES[0]}x{RES[1]} / {SAMPLES}spp -> {OUT}")
    bpy.ops.render.render(write_still=True)
print("DONE")
