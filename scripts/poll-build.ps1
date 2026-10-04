# 盯 GitHub Actions，编好了就把 ipa 下回桌面
#
# 用法：
#   set GH_TOK=<你的 GitHub token>
#   powershell -ExecutionPolicy Bypass -File scripts\poll-build.ps1
#
# 或者直接双击项目根目录的「推送并取ipa.bat」，它会带着 token 调这个脚本。
#
# 没设 token 时会自动回退到「git 已经缓存的 github 凭据」——也就是你 push 用的那个，
# 所以大多数情况下什么都不用配。

param(
    [string]$Token = $env:GH_TOK,
    [string]$Repo  = 'gutterf/life-assistant',
    [string]$Out   = "$env:USERPROFILE\Desktop\生活助手.ipa",
    [string]$ArtifactName = 'LifeAssistant-unsigned-ipa',
    [int]$MaxWaitMin = 30,
    [switch]$NoDownload
)

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
# PS 5.1 默认不加载 System.Net.Http，下面用到的 HttpClient 在这个程序集里。
try { Add-Type -AssemblyName System.Net.Http -ErrorAction Stop } catch { }

function Say([string]$m, [string]$Color = 'Gray') {
    Write-Host ("[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $m) -ForegroundColor $Color
}

# ---- token：优先参数，其次环境变量，最后问 git 要它已经在用的那个 ----
if (-not $Token) {
    try {
        $cred = "protocol=https`nhost=github.com`n`n" | git credential fill 2>$null
        $Token = (($cred | Select-String '^password=') -replace '^password=','').Trim()
    } catch { }
    if ($Token) { Say '使用 git 已缓存的 github 凭据' 'DarkGray' }
}
if (-not $Token) {
    Write-Host ''
    Write-Host '  没设 GH_TOK，也没能从 git 凭据里取到 token。先执行：' -ForegroundColor Yellow
    Write-Host '      set GH_TOK=ghp_你的token' -ForegroundColor Yellow
    Write-Host ''
    exit 1
}

$hdr = @{
    Authorization = "Bearer $Token"
    'User-Agent'  = 'dsh'
    Accept        = 'application/vnd.github+json'
}

function Gh([string]$path) {
    Invoke-RestMethod -Uri "https://api.github.com$path" -Headers $hdr -TimeoutSec 30
}

# ---- 找最近一次构建 ----
Say '查找构建记录…'
$run = $null
for ($i = 0; $i -lt 40; $i++) {
    try {
        $runs = Gh "/repos/$Repo/actions/runs?per_page=1"
        if ($runs.workflow_runs.Count -gt 0) { $run = $runs.workflow_runs[0]; break }
    } catch {
        Say ("查询失败：{0}" -f $_.Exception.Message) 'Red'
        exit 1
    }
    Start-Sleep -Seconds 5
}
if (-not $run) { Say '没找到构建记录。先去仓库的 Actions 页面手动跑一次。' 'Yellow'; exit 1 }

Say ("构建 #{0}  {1}" -f $run.run_number, (($run.head_commit.message -split "`n")[0]))
Say ("状态页 {0}" -f $run.html_url)

# ---- 等它跑完 ----
$deadline = (Get-Date).AddMinutes($MaxWaitMin)
$ok = $false
while ((Get-Date) -lt $deadline) {
    $cur = Gh "/repos/$Repo/actions/runs/$($run.id)"
    if ($cur.status -eq 'completed') {
        if ($cur.conclusion -ne 'success') {
            Say ("构建失败：{0}" -f $cur.conclusion) 'Red'
            Say ("日志在这里：{0}" -f $run.html_url) 'Red'
            # 把失败步骤的日志尾巴打出来，省得还要开浏览器
            try {
                $jobs = Gh "/repos/$Repo/actions/runs/$($run.id)/jobs"
                $bad = $jobs.jobs | Where-Object { $_.conclusion -ne 'success' } | Select-Object -First 1
                if ($bad) {
                    Say ("失败步骤：{0}" -f (($bad.steps | Where-Object { $_.conclusion -eq 'failure' } | Select-Object -First 1).name)) 'Red'
                }
            } catch { }
            exit 1
        }
        $ok = $true
        break
    }
    Say ("进行中… ({0})" -f $cur.status)
    Start-Sleep -Seconds 15
}
if (-not $ok) { Say ("等超时了，去 {0} 自己看" -f $run.html_url) 'Yellow'; exit 1 }
Say '构建成功' 'Green'
if ($NoDownload) { exit 0 }

# ---- 取 artifact ----
$arts = Gh "/repos/$Repo/actions/runs/$($run.id)/artifacts"
$target = $arts.artifacts | Where-Object { $_.name -eq $ArtifactName } | Select-Object -First 1
if (-not $target) {
    Say ("没找到名为 {0} 的 artifact，检查 workflow 里的 artifact 名字" -f $ArtifactName) 'Red'
    $arts.artifacts | ForEach-Object { Say ("  实际有：{0}" -f $_.name) }
    exit 1
}
Say ("下载 {0}  ({1:N1} MB)" -f $target.name, ($target.size_in_bytes / 1MB))

# ---- 下载 artifact ----
# GitHub 的 artifact 下载地址会 302 跳到 *.blob.core.windows.net。
# 这台机器上路由器的 DNS 解析不了那个域（查询直接超时），公共 DNS 可以。
# 而且 artifact 的签名地址只活很短时间，所以不能让 curl 先拿 Location 再单独下
# （手工两跳会 403）——正确做法是让 curl 带 token 一路跟随重定向：
# curl 跨域时会自动丢掉 Authorization，正好是这里需要的行为。
function Save-Artifact([string]$url, [string]$outPath) {
    $curl = "$env:SystemRoot\System32\curl.exe"
    $hdrFile = Join-Path $env:TEMP 'la-artifact-headers.txt'
    $auth = @('-H', "Authorization: Bearer $Token", '-H', 'User-Agent: dsh',
              '-H', 'Accept: application/vnd.github+json')

    # 第一跳只为探出 blob 的主机名（输出丢进 NUL，不取正文）
    $blobHost = $null
    & $curl -s -o NUL -D $hdrFile --max-time 60 @auth $url
    if (Test-Path $hdrFile) {
        $loc = Get-Content $hdrFile | Where-Object { $_ -match '^(?i)location:\s*(\S+)' } | Select-Object -First 1
        if ($loc -and $loc -match 'https?://([^/]+)/') { $blobHost = $Matches[1] }
    }

    $ips = @()
    if ($blobHost) {
        foreach ($dns in '223.5.5.5', '119.29.29.29', '180.76.76.76') {
            $ips = @(Resolve-DnsName $blobHost -Server $dns -Type A -ErrorAction SilentlyContinue |
                     Where-Object { $_.IPAddress } | Select-Object -ExpandProperty IPAddress)
            if ($ips.Count -gt 0) {
                Say ("{0} -> {1}（经 {2}）" -f $blobHost, ($ips -join ', '), $dns) 'DarkGray'
                break
            }
        }
    }

    $attempts = @()
    foreach ($ip in $ips) { $attempts += , @('--resolve', "${blobHost}:443:$ip") }
    $attempts += , @()   # 兜底：交给系统解析

    foreach ($extra in $attempts) {
        if (Test-Path $outPath) { Remove-Item $outPath -Force }
        & $curl -L --fail --silent --show-error --max-time 600 @auth @extra -o $outPath $url
        if ($LASTEXITCODE -eq 0 -and (Test-Path $outPath) -and (Get-Item $outPath).Length -gt 0) {
            return $true
        }
    }
    return $false
}

$tmpZip = Join-Path $env:TEMP 'lifeassistant-artifact.zip'
if (-not (Save-Artifact $target.archive_download_url $tmpZip)) {
    Say '下载 artifact 失败' 'Red'; exit 1
}
Say ("拿到 {0:N1} MB" -f ((Get-Item $tmpZip).Length / 1MB))

# ---- 解出 ipa ----
$tmpDir = Join-Path $env:TEMP 'lifeassistant-artifact'
if (Test-Path $tmpDir) { Remove-Item $tmpDir -Recurse -Force }
Expand-Archive -Path $tmpZip -DestinationPath $tmpDir -Force

$ipa = Get-ChildItem $tmpDir -Filter '*.ipa' -Recurse | Select-Object -First 1
if (-not $ipa) { Say '解出来的包里没有 ipa' 'Red'; exit 1 }

$outDir = Split-Path -Parent $Out
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }
Copy-Item $ipa.FullName $Out -Force

Remove-Item $tmpZip -Force -EA SilentlyContinue
Remove-Item $tmpDir -Recurse -Force -EA SilentlyContinue

# ---- 自检：确认它确实是未签名包 ----
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead($Out)
$signed = ($zip.Entries | Where-Object { $_.FullName -match 'embedded\.mobileprovision|_CodeSignature' }).Count
$zip.Dispose()

Say ('已保存 ' + $Out) 'Green'
Say ("大小 {0:N1} MB | 残留签名条目 {1} 个" -f ((Get-Item $Out).Length / 1MB), $signed)
Write-Host ''
Write-Host '  下一步：打开爱思助手，把它装到手机上。' -ForegroundColor White
Write-Host ''
