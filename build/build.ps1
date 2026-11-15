# TuneLock 原生工具编译脚本（Windows / PowerShell）
#
#   pwsh -File build/build.ps1            # 两个都编（能编哪个编哪个）
#   pwsh -File build/build.ps1 -Target qq # 只编 QqmDec.exe
#   pwsh -File build/build.ps1 -Target kgm # 只编 kgm_dec.exe
#
# 前置：
#   - kgm_dec.exe：任意 mingw-w64 gcc（64 位）即可，scoop install mingw 就够
#   - QqmDec.exe ：必须 **32 位** gcc（QQMusicCommon.dll 是 32 位）
#                  推荐 msys2 的 mingw32 环境：C:\msys64\mingw32\bin\gcc.exe
param(
    [ValidateSet('all', 'qq', 'kgm')]
    [string]$Target = 'all',
    [string]$Gcc32 = '',   # 32 位 gcc（编 QQ 解密器用），留空自动找
    [string]$Gcc64 = ''    # 64 位 gcc（编 kgm 解密器用），留空用 PATH 里的 gcc
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

function Find-Gcc32 {
    param([string]$Explicit)
    if ($Explicit) { return $Explicit }
    $cands = @(
        'C:\msys64\mingw32\bin\gcc.exe',
        'C:\msys64\mingw32\bin\i686-w64-mingw32-gcc.exe',
        (Get-Command i686-w64-mingw32-gcc -ErrorAction SilentlyContinue).Source
    ) | Where-Object { $_ -and (Test-Path $_) }
    return $cands | Select-Object -First 1
}

function Find-Gcc64 {
    param([string]$Explicit)
    if ($Explicit) { return $Explicit }
    $g = Get-Command gcc -ErrorAction SilentlyContinue
    return $g.Source
}

function Build-Kgm {
    $gcc = Find-Gcc64 $Gcc64
    if (-not $gcc) { Write-Warning '没找到 64 位 gcc，跳过 kgm_dec.exe'; return $false }
    $src = Join-Path $root 'tools/native/kugou/kgm_dec.c'
    $dstDir = Join-Path $root 'tools/native/kugou/bin'
    New-Item -ItemType Directory -Force -Path $dstDir | Out-Null
    $dst = Join-Path $dstDir 'kgm_dec.exe'
    Write-Host "==> kgm_dec.exe  <-  $gcc"
    & $gcc -O2 -o $dst $src
    if ($LASTEXITCODE -ne 0) { throw 'kgm_dec.c 编译失败' }
    Write-Host "    产物: $dst ($([math]::Round((Get-Item $dst).Length/1KB)) KB)"
    return $true
}

function Build-Qq {
    $gcc = Find-Gcc32 $Gcc32
    if (-not $gcc) {
        Write-Warning @'
没找到 32 位 gcc，跳过 QqmDec.exe。
  QQMusicCommon.dll 是 32 位，必须 32 位编译器：
    scoop install msys2     然后  pacman -S mingw-w64-i686-gcc
  或用 scoop 里的 mingw32：
    scoop install mingw-winlibs-llvm-ucrt?   # 自己确认有 i686 目标
  然后重跑：pwsh -File build/build.ps1 -Target qq -Gcc32 C:\msys64\mingw32\bin\gcc.exe
'@
        return $false
    }
    $src = Join-Path $root 'tools/native/qqmusic/QqmDec.c'
    $dstDir = Join-Path $root 'tools/native/qqmusic/bin'
    New-Item -ItemType Directory -Force -Path $dstDir | Out-Null
    $dst = Join-Path $dstDir 'QqmDec.exe'
    Write-Host "==> QqmDec.exe  <-  $gcc"
    # -municode 让 wmain 生效（Unicode 文件名必须），-mwindows 不必要（要控制台输出）
    & $gcc -O2 -municode -o $dst $src -lkernel32 -luser32
    if ($LASTEXITCODE -ne 0) { throw 'QqmDec.c 编译失败（确认是 32 位 gcc）' }
    Write-Host "    产物: $dst ($([math]::Round((Get-Item $dst).Length/1KB)) KB)"
    return $true
}

$okKgm = $false
$okQq = $false
if ($Target -in @('all', 'kgm')) { $okKgm = Build-Kgm }
if ($Target -in @('all', 'qq')) { $okQq = Build-Qq }

Write-Host ''
Write-Host ("kgm_dec.exe : {0}" -f $(if ($okKgm) { 'OK' } else { '跳过/失败' }))
Write-Host ("QqmDec.exe  : {0}" -f $(if ($okQq) { 'OK' } else { '跳过/失败' }))
Write-Host ''
Write-Host '别忘了把 QQ 音乐目录里的这两个 DLL 复制到 tools/native/qqmusic/bin/：'
Write-Host '  QQMusicCommon.dll（exe 同目录优先，否则从安装目录取）'
Write-Host '  CommonFunction.dll（必须和 exe 同目录，QQMusicCommon.dll 会按 exe 所在目录找它）'

# 只有"指定了要编却没编成"才算失败；all 模式下编成一个就算可用
if ($Target -eq 'all') { if (-not ($okKgm -or $okQq)) { exit 1 } }
elseif ($Target -eq 'kgm' -and -not $okKgm) { exit 1 }
elseif ($Target -eq 'qq' -and -not $okQq) { exit 1 }
