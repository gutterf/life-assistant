# 双击「启动后端.bat」时实际跑的就是这个。
#
# 它做四件事：检查 .env → 打印手机该填的地址 → 检查端口有没有被占 → 起服务。
# 中文输出都在这里（.bat 必须保持纯 ASCII，cmd 用 OEM 代码页读 .bat 会乱码）。

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

# 本脚本在 <项目根>\scripts\ 下，后端在 <项目根>\backend\
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'
Set-Location $backend

function Line([string]$text = '', [string]$color = 'Gray') {
    Write-Host $text -ForegroundColor $color
}

Line ''
Line '  生活助手 · 后端' 'White'
Line '  ────────────────────────────────────────────'

# ---- 1. .env ----
if (-not (Test-Path '.env')) {
    Line '  ! 没找到 backend\.env' 'Yellow'
    Line '    先把 .env.example 复制成 .env，填上 DEEPSEEK_API_KEY 和 AMAP_KEY。' 'Yellow'
    Line ''
    Read-Host '  按回车退出'
    exit 1
}

$envText = Get-Content '.env' -Raw -Encoding UTF8
# 用 [ \t] 而不是 \s：\s 会匹配换行，于是 "AMAP_KEY=" 这种空值会跨行吃到下一行
# "AMAP_BASE_URL=..." 的首字母，误报成"已配置"。这个坑当场踩到过一次。
$hasDeepSeek = $envText -match '(?m)^[ \t]*DEEPSEEK_API_KEY[ \t]*=[ \t]*\S'
$hasAmap = $envText -match '(?m)^[ \t]*AMAP_KEY[ \t]*=[ \t]*\S'

$deepSeekMark = if ($hasDeepSeek) { '已配置' } else { '缺失' }
$amapMark = if ($hasAmap) { '已配置' } else { '缺失' }
$deepSeekColor = if ($hasDeepSeek) { 'Green' } else { 'Red' }
$amapColor = if ($hasAmap) { 'Green' } else { 'Yellow' }

Write-Host '  DeepSeek key   ' -NoNewline; Line $deepSeekMark $deepSeekColor
Write-Host '  高德 key       ' -NoNewline; Line $amapMark $amapColor
if (-not $hasAmap) {
    Line '                 （没有它，问路线和找店会降级成常识回答）' 'DarkGray'
}

# ---- 2. 手机该填的地址 ----
Line ''
Line '  手机 App 里「连接设置」要填的地址：' 'White'
$ips = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object {
        $_.IPAddress -notlike '127.*' -and
        $_.IPAddress -notlike '169.254.*' -and
        $_.PrefixOrigin -ne 'WellKnown' -and
        $_.InterfaceAlias -notmatch 'VPN|Tailscale|Radmin|Loopback'
    } | Sort-Object InterfaceAlias

if ($ips) {
    foreach ($ip in $ips) {
        Line ("    http://{0}:8000     （{1}）" -f $ip.IPAddress, $ip.InterfaceAlias) 'Cyan'
    }
} else {
    Line '    没找到局域网 IP，检查一下网线/Wi-Fi' 'Red'
}

# ---- 3. 端口 ----
$busy = Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue
if ($busy) {
    $owner = (Get-Process -Id $busy[0].OwningProcess -ErrorAction SilentlyContinue).ProcessName
    Line ''
    Line ("  ! 8000 端口已经被 {0} 占用了（PID {1}）" -f $owner, $busy[0].OwningProcess) 'Yellow'
    Line '    如果是上一次没关掉的后端，先关掉它再跑这个脚本。' 'DarkGray'
    Line ''
    Read-Host '  按回车退出'
    exit 1
}

# ---- 4. 起服务 ----
Line ''
Line '  正在启动…（这个窗口不要关，关了后端就停了）' 'DarkGray'
Line '  后端就绪后，手机浏览器开上面的地址加 /health 应该能看到 JSON。' 'DarkGray'
Line '  ────────────────────────────────────────────'
Line ''

& python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level info

Line ''
Line '  后端已停止。' 'Yellow'
Read-Host '  按回车关闭窗口'
