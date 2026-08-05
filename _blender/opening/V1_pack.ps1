# 〈挪車的代價〉封裝與驗證
#
#   3D PNG 序列 + HUD 透明疊層 → MP4 / WebM → 規格檢查 → 完整解碼 → 接觸表
#
# 影格序列不直接讓 Blender 出 MP4：某幾格失敗時可以只補算那幾格，不必從頭來。
#
# 用法：
#   .\V1_pack.ps1                                   # 用 renders\seq（完整版）
#   .\V1_pack.ps1 -Seq preview -Name preview -Scale "1280:720" -Crf 22

param(
    [string]$Root  = "G:\Projects\parking-lot",
    [string]$Seq   = "seq",
    [string]$Hud   = "hud",
    [string]$Name  = "parking-lot-cost-of-moving",
    [string]$Scale = "",            # 空＝不縮放；預覽版用 "1280:720" 把低解析拉上來對齊 HUD
    [int]$Fps      = 24,
    [int]$Crf      = 18
)

$ErrorActionPreference = "Stop"
$R = $Root
$seqDir = Join-Path $R "renders\$Seq"
$hudDir = Join-Path $R "renders\$Hud"
$outDir = Join-Path $R "renders"
$mp4 = Join-Path $outDir "$Name.mp4"
$webm = Join-Path $outDir "$Name.webm"
$sheet = Join-Path $outDir "$Name-contact-sheet.jpg"

$nSeq = (Get-ChildItem $seqDir -Filter "frame_*.png").Count
$nHud = (Get-ChildItem $hudDir -Filter "hud_*.png").Count
Write-Host "[PACK] 3D 影格 $nSeq | HUD 影格 $nHud"
if ($nSeq -eq 0) { throw "找不到 3D 影格：$seqDir" }
if ($nSeq -ne $nHud) { Write-Host "[PACK] 警告：影格數不一致（$nSeq vs $nHud）" -ForegroundColor Yellow }

# 用串接組 filtergraph：雙引號字串裡的 `[ 會被 PowerShell 當成型別字面值起頭而解析失敗
$pre = if ($Scale) { '[0]scale=' + $Scale + '[v];[v][1]overlay=0:0' } else { '[0][1]overlay=0:0' }

Write-Host "[PACK] 合成並封裝 MP4 ..."
ffmpeg -y -loglevel error -framerate $Fps -i (Join-Path $seqDir "frame_%04d.png") `
       -framerate $Fps -i (Join-Path $hudDir "hud_%04d.png") `
       -filter_complex $pre `
       -c:v libx264 -preset slow -crf $Crf -pix_fmt yuv420p -movflags +faststart $mp4
if ($LASTEXITCODE -ne 0) { throw "MP4 封裝失敗" }

Write-Host "[PACK] 封裝 WebM ..."
ffmpeg -y -loglevel error -framerate $Fps -i (Join-Path $seqDir "frame_%04d.png") `
       -framerate $Fps -i (Join-Path $hudDir "hud_%04d.png") `
       -filter_complex $pre `
       -c:v libvpx-vp9 -b:v 0 -crf 30 -row-mt 1 -pix_fmt yuv420p $webm
if ($LASTEXITCODE -ne 0) { Write-Host "[PACK] WebM 失敗（不阻擋 MP4）" -ForegroundColor Yellow }

Write-Host "`n[PACK] ── 規格檢查 ─────────────────────────────"
ffprobe -v error -select_streams v:0 `
        -show_entries stream=codec_name,width,height,r_frame_rate,nb_frames `
        -show_entries format=duration -of default=noprint_wrappers=1 $mp4

Write-Host "`n[PACK] ── 完整解碼（無輸出＝沒有壞影格）──────────"
$decode = & ffmpeg -v error -i $mp4 -f null - 2>&1
if ($decode) { Write-Host $decode -ForegroundColor Red } else { Write-Host "  解碼乾淨 OK" -ForegroundColor Green }

Write-Host "`n[PACK] 產生接觸表 ..."
ffmpeg -y -loglevel error -i $mp4 -vf "fps=1,scale=320:-1,tile=5x6" -frames:v 1 $sheet

Get-Item $mp4, $webm, $sheet -ErrorAction SilentlyContinue |
    Select-Object @{n='檔案'; e={$_.Name}}, @{n='MB'; e={[math]::Round($_.Length/1MB, 2)}}, LastWriteTime |
    Format-Table -AutoSize
Write-Host "[PACK] 完成"
